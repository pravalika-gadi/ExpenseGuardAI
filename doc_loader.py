"""Universal Document, Invoice, and Screenshot Ingestion Engine for ExpenseGuard AI.

Provides high-accuracy extraction for:
- Image screenshots & photos (.png, .jpg, .jpeg, .webp, .bmp)
- PDF invoices, bills & statements (.pdf)
- Microsoft Word documents (.docx)
- Spreadsheets (.xlsx, .xls, .xlsm, .csv, .tsv)
- JSON expense feeds (.json)

Features:
- Column-preserving layout analysis (Tesseract PSM 4)
- Strict final-total-only extraction: reads the printed payable amount, never
  adding GST/tax or mistaking IDs/phone numbers for the total
- Postal PIN code and phone number shielding
- Clean bill/invoice number and merchant identification
- Intelligent category detection (Healthcare, Meals, Travel, Lodging, Office Supplies, etc.)
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import io

import pandas as pd
from PIL import Image

logger = logging.getLogger("ExpenseGuardDocLoader")

# Configure Tesseract
TESSERACT_COMMON_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
]

TESSERACT_AVAILABLE = False
try:
    import pytesseract
    for t_path in TESSERACT_COMMON_PATHS:
        if os.path.exists(t_path):
            pytesseract.pytesseract.tesseract_cmd = t_path
            TESSERACT_AVAILABLE = True
            break
    if not TESSERACT_AVAILABLE:
        try:
            pytesseract.get_tesseract_version()
            TESSERACT_AVAILABLE = True
        except Exception:
            TESSERACT_AVAILABLE = False
except ImportError:
    pytesseract = None
    TESSERACT_AVAILABLE = False

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None


CATEGORY_KEYWORDS = {
    "Healthcare": ["pharmacy", "wellness", "medicine", "paracetamol", "prescription", "chemist", "clinic", "diagnostics", "health", "hospital", "doctor", "tablet", "sanitizer"],
    "Meals": ["cafe", "coffee", "sandwich", "cappuccino", "food", "restaurant", "beverage", "meal", "lunch", "dinner", "burger", "pizza", "dining", "bakery", "kitchen", "bar", "swiggy", "zomato"],
    "Lodging": ["hotel", "motel", "resort", "inn", "lodging", "room", "stay at", "hotel stay", "night stay", "hostel", "marriott", "hyatt", "hilton", "oyo"],
    "Travel": ["travel", "bus", "ticket", "flight", "air", "airline", "indigo", "airindia", "train", "irctc", "metro", "fuel", "petrol", "diesel", "fuelmax", "fare", "uber", "ola", "cab", "taxi", "toll", "parking", "rapido"],
    "Office Supplies": ["book", "bookstore", "bookverse", "stationery", "paper", "pen", "notebook", "printer", "toner", "stapler", "office", "supplies", "desk"],
    "Software": ["aws", "azure", "google cloud", "github", "microsoft", "zoom", "slack", "software", "subscription", "license", "saas", "domain", "hosting", "jetbrains", "adobe", "openai", "atlassian"],
    "Shopping": ["clothing", "apparel", "fashion", "shirt", "electronics", "retail", "supermarket", "grocery", "mall", "store"],
}

HEADER_NOISE = [
    "tax invoice", "retail invoice", "cash memo", "invoice", "receipt", "bill",
    "prescription / retail invoice", "prescription", "ticket receipt", "ticket",
    "fuel receipt", "bill of supply", "original for recipient", "customer copy",
    "welcome", "e-receipt", "statement", "order summary", "gst invoice"
]

# Patterns that look like IDs / phone numbers / PIN codes — NOT amounts
_ID_LIKE_PATTERNS = [
    r"(?i)\b(?:emp|employee|user|staff|cust|customer|vendor)\s*(?:id|no|number|code)?\s*[:=]?\s*\d+",
    r"(?i)\b(?:invoice|inv|bill|ticket|receipt|order|booking|ref|reference|confirmation)\s*(?:id|no|number|code)?\s*[:=]?\s*[A-Za-z0-9/_-]+",
    r"\b\d{10}\b",  # 10-digit phone numbers
    r"\b[0-9]{6}\b",  # 6-digit PIN codes
    r"(?i)\bgstin\s*[:=]?\s*[A-Z0-9]+",
    r"(?i)\bpan\s*[:=]?\s*[A-Z0-9]+",
    r"(?i)\bdl\s*no\s*[:=]?\s*[A-Z0-9]+",
    r"(?i)\bfssai\s*[:=]?\s*[0-9]+",
    r"(?i)\b(?:ph|phone|tel|mobile|contact)\s*[:=]?\s*[\d\s+-]+",
]


def detect_category(text: str) -> str:
    """Classify expense category based on text content with exact word bounds."""
    text_lower = text.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in keywords):
            return cat
    return "Miscellaneous"


def extract_clean_merchant(lines: List[str]) -> str:
    """Extract store or merchant name from the top header lines."""
    for ln in lines[:6]:
        ln_l = ln.lower().strip()
        # Only skip pure header lines like 'Tax Invoice', 'Receipt', 'Bill'
        if any(ln_l == noise or ln_l.startswith(noise + ":") or ln_l.startswith(noise + " no") for noise in HEADER_NOISE):
            continue
        # Clean leading/trailing non-word symbols and trailing receipt noise
        cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", ln).strip()
        cleaned_vendor = re.sub(r"(?i)\s+(?:tax invoice|retail invoice|cash memo|invoice|receipt|bill)$", "", cleaned).strip()
        # Filter out address, phone, and postal code lines
        if (
            len(cleaned_vendor) >= 3
            and not cleaned_vendor.isdigit()
            and not any(a in cleaned_vendor.lower() for a in ["road", "street", "bengaluru", "bangalore", "delhi", "mumbai", "hyderabad", "gstin", "ka ", "nh ", "date:"])
        ):
            return cleaned_vendor[:50]
    return "Expense Receipt"


def extract_bill_number(lines: List[str], full_text: str) -> Optional[str]:
    """Extract standard bill/invoice identifier."""
    for ln in lines:
        bm = re.search(r"(?:bill\s*no|invoice\s*no|ticket\s*no|receipt\s*no|inv\s*no|order\s*id)\s*[:=\s]*[^\w]*([a-zA-Z0-9/_-]{4,25})", ln, re.I)
        if bm:
            val = bm.group(1).strip()
            if val.lower() not in ["number", "date", "copy", "invoice"]:
                return val
    # Standard format: XX/202X/XXXXX
    std_m = re.search(r"\b([A-Z]{2,4}/202[4-6]/[0-9]{4,6})\b", full_text)
    if std_m:
        return std_m.group(1)
    return None


def extract_receipt_date(lines: List[str]) -> str:
    """Extract transaction date from receipt text."""
    for ln in lines:
        dm = re.search(r"(?:date)\s*[:=\s]*\+?\s*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})", ln, re.I)
        if dm:
            return dm.group(1).replace("/", "-")
        dm2 = re.search(r"\b(202[4-6])[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12][0-9]|3[01])\b", ln)
        if dm2:
            return f"{dm2.group(1)}-{dm2.group(2)}-{dm2.group(3)}"
    return datetime.now().strftime("%Y-%m-%d")


def clean_amount_str(s: str) -> str:
    """Normalize comma decimals and OCR character misreads."""
    s = re.sub(r"([0-9]+),([0-9]{2})\b", r"\1.\2", s)
    s = s.replace(",", "")
    s = re.sub(r"\b[Ss]([0-9]{2}\.[0-9]{2})\b", r"5\1", s)
    # Strip currency acronyms (INR, Rs, USD, etc.) touching numbers (e.g. INR750.00 -> 750.00)
    s = re.sub(r"(?i)(?:inr|rs\.?|usd|eur|gbp)", " ", s)
    return s


def clean_glyph(val: float, subtotal: Optional[float] = None) -> float:
    """Resolve Rupee currency glyph misread as leading digit 2 or 8."""
    v_str = f"{val:.2f}"
    if v_str[0] in ["2", "8"]:
        try:
            stripped = float(v_str[1:])
            if subtotal is not None and subtotal > 0:
                if abs(stripped - subtotal) < abs(val - subtotal):
                    return stripped
            elif len(v_str) >= 6:
                if 20.0 <= stripped <= 50000.0 and val > 2000.0 and v_str[1] not in ["0", "9"]:
                    return stripped
        except ValueError:
            pass
    return val


def _is_id_or_noise_line(line: str) -> bool:
    """Return True if the line is an ID line, phone line, address, or other non-amount noise."""
    ln_l = line.lower().strip()
    # Addresses and location info
    if any(w in ln_l for w in ["gstin", "phone", "ph:", "tel:", "mobile", "road", "street",
                                "bengaluru", "bangalore", "delhi", "mumbai", "hyderabad",
                                "chennai", "kolkata", "pune", "fssai", "pan:", "dl no",
                                "pin:", "zip:", "email", "www.", "http"]):
        return True
    # Lines that are clearly IDs
    for pattern in _ID_LIKE_PATTERNS:
        if re.search(pattern, line):
            # Only exclude if no total-like keyword is also present
            if not any(k in ln_l for k in ["total", "payable", "amount paid", "grand total", "net"]):
                return True
    return False


def _is_year_value(val: float) -> bool:
    """Return True if the number looks like a calendar year, not an amount."""
    return val in [2024.0, 2025.0, 2026.0, 2027.0]


def extract_and_reconcile_amount(lines: List[str]) -> float:
    """Directly extract the printed Total amount from any bill.

    STRICT RULES:
    1. Extract ONLY the final printed total / grand total / net payable / amount paid.
    2. NEVER add GST/tax to the extracted total — read the printed amount as-is.
    3. NEVER mistake employee IDs, user IDs, invoice numbers, ticket numbers,
       phone numbers, subtotals, or tax amounts for the final total.
    4. If the total cannot be identified confidently, return 0.0 (caller shows "Total not detected").
    """
    # Detect subtotal if present to help disambiguate glyph artifacts
    subtotal_val = None
    for ln in lines:
        ln_clean = clean_amount_str(ln.strip())
        if "subtotal" in ln_clean.lower() or "sub total" in ln_clean.lower():
            nums = re.findall(r"\b[0-9]{1,6}(?:\.[0-9]{1,2})?\b", ln_clean)
            if nums:
                try:
                    s_candidate = float(nums[-1])
                    if 10.0 <= s_candidate <= 100000.0:
                        subtotal_val = s_candidate
                        break
                except ValueError:
                    pass

    total_candidates = []

    # Priority 1: "Grand Total" / "Net Payable" / "Amount Paid" / "Final Total" / "Order Total"
    priority_keywords = ["grand total", "net payable", "amount paid", "final total", "order total", "total payable", "amount due", "balance due", "total due"]
    for ln in lines:
        ln_clean = clean_amount_str(ln.strip())
        ln_l = ln_clean.lower()

        if _is_id_or_noise_line(ln):
            continue

        if any(k in ln_l for k in priority_keywords):
            stripped = re.sub(r"[%&*?₹$\(\)]+", " ", ln_clean)
            nums = re.findall(r"\b[0-9]{1,6}(?:\.[0-9]{1,2})?\b", stripped)
            for n in nums:
                try:
                    val = float(n)
                    if 1.0 <= val <= 300000.0 and not _is_year_value(val):
                        val = clean_glyph(val, subtotal=subtotal_val)
                        total_candidates.append(val)
                except ValueError:
                    pass

    if total_candidates:
        return round(total_candidates[-1], 2)

    # Priority 2: Plain "Total" line (but NOT "subtotal" or "tax total")
    for ln in lines:
        ln_clean = clean_amount_str(ln.strip())
        ln_l = ln_clean.lower()

        if _is_id_or_noise_line(ln):
            continue

        # Must contain "total" but NOT "sub" or "tax" prefix
        if "total" in ln_l and "sub" not in ln_l:
            # Exclude lines that are tax-amount lines (e.g. "CGST Total", "SGST Total", "Tax Total")
            if any(t in ln_l for t in ["cgst", "sgst", "igst", "tax total", "vat total", "gst total"]):
                continue

            stripped = re.sub(r"[%&*?₹$\(\)]+", " ", ln_clean)
            nums = re.findall(r"\b[0-9]{1,6}(?:\.[0-9]{1,2})?\b", stripped)
            for n in nums:
                try:
                    val = float(n)
                    if 1.0 <= val <= 300000.0 and not _is_year_value(val):
                        val = clean_glyph(val, subtotal=subtotal_val)
                        total_candidates.append(val)
                except ValueError:
                    pass

    if total_candidates:
        return round(total_candidates[-1], 2)

    # Priority 3: Travel ticket specific: look for 'Fare' or sum of fares
    fare_candidates = []
    for ln in lines:
        ln_clean = clean_amount_str(ln.strip())
        if "fare" in ln_clean.lower() or "convenience" in ln_clean.lower():
            nums = re.findall(r"\b[0-9]{1,5}(?:\.[0-9]{2})?\b", ln_clean)
            for n in nums:
                try:
                    val = float(n)
                    if 10.0 <= val <= 50000.0:
                        fare_candidates.append(val)
                except ValueError:
                    pass

    if fare_candidates:
        return round(sum(fare_candidates), 2)

    return 0.0


def parse_image_file(file_obj, filename: str) -> List[Dict[str, Any]]:
    """Parse receipt image or screenshot using multi-pass Tesseract layout analysis."""
    if not TESSERACT_AVAILABLE or pytesseract is None:
        raise RuntimeError("Tesseract OCR is not available for image processing.")

    image = Image.open(file_obj)
    # Upscale 2x for sharp character recognition on low-DPI receipt screenshots
    w, h = image.size
    if w < 1200 or h < 1200:
        image = image.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

    # Multi-pass OCR: PSM 4 (single column) and PSM 6 (block)
    ocr_text_psm4 = pytesseract.image_to_string(image, config="--psm 4")
    ocr_text_psm6 = pytesseract.image_to_string(image, config="--psm 6")

    combined_text = ocr_text_psm4 + "\n" + ocr_text_psm6
    if not combined_text.strip():
        return []

    lines_psm4 = [ln.strip() for ln in ocr_text_psm4.splitlines() if ln.strip()]
    lines_combined = lines_psm4 + ["---"] + [ln.strip() for ln in ocr_text_psm6.splitlines() if ln.strip()]

    merchant = extract_clean_merchant(lines_psm4)
    bill_no = extract_bill_number(lines_psm4, combined_text) or f"TXN-{abs(hash(merchant + filename)) % 90000 + 10000}"
    date_str = extract_receipt_date(lines_psm4)
    category = detect_category(combined_text)
    amount = extract_and_reconcile_amount(lines_combined)

    return [{
        "transaction_id": bill_no,
        "employee_id": "EMP-USER",
        "date": date_str,
        "category": category,
        "description": merchant,
        "amount": amount,
        "receipt_attached": True,
        "_source_file": filename,
        "_ocr_text": combined_text,
    }]


def is_tabular_report(lines: List[str]) -> bool:
    """Determine whether text represents a multi-row expense ledger or a single bill."""
    header_keywords = ["amount", "date", "category", "employee", "description", "id", "receipt"]
    for line in lines[:10]:
        line_lower = line.lower()
        matches = sum(1 for kw in header_keywords if kw in line_lower)
        if matches >= 3:
            return True
    return False


def parse_pdf_file(file_obj, filename: str) -> List[Dict[str, Any]]:
    """Parse PDF document. Accurately distinguishes between a single bill and a multi-row report."""
    if pypdf is None:
        raise RuntimeError("pypdf is not available for PDF processing.")

    reader = pypdf.PdfReader(file_obj)
    full_text = ""
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            full_text += txt + "\n"

    # Scanned PDF without text: run OCR on images
    if not full_text.strip() and TESSERACT_AVAILABLE and pytesseract is not None:
        ocr_text = ""
        for page in reader.pages:
            for img_obj in page.images:
                try:
                    pil_img = Image.open(io.BytesIO(img_obj.data))
                    ocr_text += pytesseract.image_to_string(pil_img, config="--psm 4") + "\n"
                except Exception:
                    continue
        full_text = ocr_text

    if not full_text.strip():
        return []

    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]

    # If the PDF is a multi-row tabular spreadsheet report:
    if is_tabular_report(lines):
        parsed_records: List[Dict[str, Any]] = []
        for line in lines:
            parts = [p.strip() for p in re.split(r",|\t| {2,}", line) if p.strip()]
            if len(parts) >= 4:
                amt_candidates = re.findall(r"[0-9]{1,4}\.[0-9]{2}\b", line)
                if amt_candidates:
                    parsed_records.append({
                        "transaction_id": parts[0] if not parts[0].replace(".", "").isdigit() else f"TXN-PDF-{len(parsed_records)+1:03d}",
                        "employee_id": parts[1] if len(parts) > 1 and "EMP" in parts[1].upper() else "EMP-USER",
                        "date": extract_receipt_date([line]),
                        "category": detect_category(line),
                        "description": parts[2] if len(parts) > 2 else "PDF Expense",
                        "amount": round(float(amt_candidates[0]), 2),
                        "receipt_attached": "receipt" in line.lower() or "yes" in line.lower() or "true" in line.lower(),
                        "_source_file": filename,
                    })
        if parsed_records:
            return parsed_records

    # Otherwise, it is a single bill/invoice/statement document:
    merchant = extract_clean_merchant(lines)
    bill_no = extract_bill_number(lines, full_text) or f"TXN-{abs(hash(merchant + filename)) % 90000 + 10000}"
    date_str = extract_receipt_date(lines)
    category = detect_category(full_text)
    amount = extract_and_reconcile_amount(lines)

    return [{
        "transaction_id": bill_no,
        "employee_id": "EMP-USER",
        "date": date_str,
        "category": category,
        "description": merchant,
        "amount": amount,
        "receipt_attached": True,
        "_source_file": filename,
        "_ocr_text": full_text,
    }]


def parse_docx_file(file_obj, filename: str) -> List[Dict[str, Any]]:
    """Parse Word document tables or extract single invoice details."""
    if docx is None:
        raise RuntimeError("python-docx is not available for Word document processing.")

    doc = docx.Document(file_obj)
    records: List[Dict[str, Any]] = []

    # Check tables
    for table in doc.tables:
        if len(table.rows) >= 2:
            headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
            for row in table.rows[1:]:
                row_vals = [cell.text.strip() for cell in row.cells]
                if any(row_vals):
                    row_dict = dict(zip(headers, row_vals))
                    row_dict["_source_file"] = filename
                    records.append(row_dict)

    if records:
        return records

    full_text = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
    if not full_text:
        return []

    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    merchant = extract_clean_merchant(lines)
    bill_no = extract_bill_number(lines, full_text) or f"TXN-{abs(hash(merchant + filename)) % 90000 + 10000}"
    date_str = extract_receipt_date(lines)
    category = detect_category(full_text)
    amount = extract_and_reconcile_amount(lines)

    return [{
        "transaction_id": bill_no,
        "employee_id": "EMP-USER",
        "date": date_str,
        "category": category,
        "description": merchant,
        "amount": amount,
        "receipt_attached": True,
        "_source_file": filename,
    }]


def parse_json_file(file_obj, filename: str) -> List[Dict[str, Any]]:
    """Parse JSON file containing list or dictionary of expense records."""
    if hasattr(file_obj, "read"):
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        data = json.loads(content)
    else:
        with open(file_obj, "r", encoding="utf-8") as f:
            data = json.load(f)

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ["expenses", "records", "transactions", "data", "items"]:
            if key in data and isinstance(data[key], list):
                records = data[key]
                break
        else:
            records = [data]
    else:
        records = []

    for r in records:
        if isinstance(r, dict):
            r["_source_file"] = filename
    return records


def parse_tabular_file(file_obj, filename: str) -> List[Dict[str, Any]]:
    """Parse Excel or CSV/TSV spreadsheets into list of record dictionaries."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".xlsx", ".xls", ".xlsm"]:
        df = pd.read_excel(file_obj)
    else:
        try:
            df = pd.read_csv(file_obj, sep=None, engine="python")
        except Exception:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            df = pd.read_csv(file_obj)

    df["_source_file"] = filename
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return records


def load_single_file(file_obj, filename: str) -> pd.DataFrame:
    """Universal loader that routes any document or image to its parser."""
    ext = os.path.splitext(filename)[1].lower()

    if ext in [".xlsx", ".xls", ".xlsm", ".csv", ".tsv"]:
        records = parse_tabular_file(file_obj, filename)
    elif ext == ".json":
        records = parse_json_file(file_obj, filename)
    elif ext == ".pdf":
        records = parse_pdf_file(file_obj, filename)
    elif ext in [".docx", ".doc"]:
        records = parse_docx_file(file_obj, filename)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
        records = parse_image_file(file_obj, filename)
    else:
        try:
            records = parse_tabular_file(file_obj, filename)
        except Exception:
            raise ValueError(f"Unsupported or unparseable document format '{ext}' for file {filename}")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return df


def load_documents_batch(file_items: List[Any]) -> pd.DataFrame:
    """Load and combine multiple files (screenshots, PDFs, spreadsheets) into a unified DataFrame."""
    combined_dfs = []

    for item in file_items:
        filename = getattr(item, "name", str(item))
        try:
            df = load_single_file(item, filename)
            if not df.empty:
                combined_dfs.append(df)
        except Exception as e:
            logger.warning(f"Could not parse file {filename}: {e}")

    if not combined_dfs:
        return pd.DataFrame()

    merged = pd.concat(combined_dfs, ignore_index=True)
    return merged


def extract_receipt_total_direct(file_obj, filename: str) -> Dict[str, Any]:
    """Direct receipt reader: upload a bill/receipt and immediately extract details.

    This function processes the file independently every time it is called.
    It never reuses previous OCR results or receipt amounts.

    Returns a dict with:
        total: float or None (the final printed payable amount, or None if not detected)
        merchant: str
        category: str
        date: str
        bill_no: str
        ocr_text: str (raw OCR text for debugging)
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
        if not TESSERACT_AVAILABLE or pytesseract is None:
            raise RuntimeError(
                "Tesseract OCR is not installed. Please install Tesseract-OCR to process receipt images. "
                "Download from: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        image = Image.open(file_obj)
        w, h = image.size
        if w < 1200 or h < 1200:
            image = image.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

        ocr_text_psm4 = pytesseract.image_to_string(image, config="--psm 4")
        ocr_text_psm6 = pytesseract.image_to_string(image, config="--psm 6")
        combined_text = ocr_text_psm4 + "\n" + ocr_text_psm6

        lines_psm4 = [ln.strip() for ln in ocr_text_psm4.splitlines() if ln.strip()]
        lines_combined = lines_psm4 + ["---"] + [ln.strip() for ln in ocr_text_psm6.splitlines() if ln.strip()]

    elif ext == ".pdf":
        if pypdf is None:
            raise RuntimeError("pypdf is not installed. Run: pip install pypdf")

        reader = pypdf.PdfReader(file_obj)
        full_text = ""
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                full_text += txt + "\n"

        if not full_text.strip() and TESSERACT_AVAILABLE and pytesseract is not None:
            for page in reader.pages:
                for img_obj in page.images:
                    try:
                        pil_img = Image.open(io.BytesIO(img_obj.data))
                        full_text += pytesseract.image_to_string(pil_img, config="--psm 4") + "\n"
                    except Exception:
                        continue

        combined_text = full_text
        lines_psm4 = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
        lines_combined = lines_psm4

    else:
        raise ValueError(f"Unsupported receipt format '{ext}'. Use PNG, JPG, or PDF.")

    if not combined_text.strip():
        return {
            "total": None,
            "merchant": "Unknown",
            "category": "Miscellaneous",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "bill_no": "",
            "ocr_text": "",
        }

    merchant = extract_clean_merchant(lines_psm4)
    bill_no = extract_bill_number(lines_psm4, combined_text) or ""
    date_str = extract_receipt_date(lines_psm4)
    category = detect_category(combined_text)
    amount = extract_and_reconcile_amount(lines_combined)

    # If amount is 0.0, we could not confidently identify the total
    total = amount if amount > 0.0 else None

    return {
        "total": total,
        "merchant": merchant,
        "category": category,
        "date": date_str,
        "bill_no": bill_no,
        "ocr_text": combined_text[:5000],
    }
