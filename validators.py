"""Deterministic Expense Validation Engine for ExpenseGuard AI.

Provides rule-based validation for expense records without relying on LLMs
for arithmetic or definitive validation logic.
"""

from typing import List, Dict, Any, Tuple, Optional
import math
from datetime import datetime, date
import re
import pandas as pd

from config import (
    DEFAULT_CATEGORY_LIMITS,
    DEFAULT_RECEIPT_THRESHOLD,
    MANDATORY_FIELDS,
    COLUMN_ALIASES,
    ExpenseGuardConfig,
)


def normalize_record_keys(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize dictionary keys to standard schema using column aliases."""
    normalized: Dict[str, Any] = {}
    lower_to_orig = {str(k).strip().lower(): k for k in record.keys()}

    for standard_col, aliases in COLUMN_ALIASES.items():
        matched_val = None
        for alias in aliases:
            if alias.lower() in lower_to_orig:
                orig_key = lower_to_orig[alias.lower()]
                matched_val = record[orig_key]
                break
        normalized[standard_col] = matched_val

    # Also keep any extra keys if present
    for k, v in record.items():
        cleaned_k = str(k).strip().lower()
        if not any(cleaned_k in [a.lower() for a in aliases] for aliases in COLUMN_ALIASES.values()):
            normalized[str(k).strip()] = v

    return normalized


def parse_boolean_receipt(val: Any) -> bool:
    """Parse various representations of receipt status into boolean."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return False
    if isinstance(val, bool):
        return val
    str_val = str(val).strip().lower()
    return str_val in ["true", "yes", "y", "1", "attached", "available", "present"]


def parse_amount(val: Any) -> Optional[float]:
    """Parse string or numeric amount into a float, stripping currency symbols."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and math.isnan(val):
            return None
        return float(val)
    str_val = str(val).strip()
    # Strip currency signs (₹, $, €, £), commas, and spaces
    cleaned = re.sub(r"[^\d.-]", "", str_val)
    if not cleaned or cleaned == "-" or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(val: Any) -> Optional[date]:
    """Parse date from various string and timestamp formats."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    if isinstance(val, date):
        return val
    str_val = str(val).strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str_val, fmt).date()
        except ValueError:
            continue
    return None


def check_missing_fields(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify expense records missing mandatory fields.

    Rule: Every record must contain non-empty transaction_id, employee_id, date,
    category, description, and valid amount.
    """
    flagged: List[Dict[str, Any]] = []

    for index, raw_record in enumerate(records):
        rec = normalize_record_keys(raw_record)
        missing: List[str] = []

        txn_id = rec.get("transaction_id")
        if not txn_id or str(txn_id).strip() == "" or (isinstance(txn_id, float) and math.isnan(txn_id)):
            missing.append("transaction_id")
            display_id = f"ROW-{index + 1}"
        else:
            display_id = str(txn_id).strip()

        emp_id = rec.get("employee_id")
        if not emp_id or str(emp_id).strip() == "" or (isinstance(emp_id, float) and math.isnan(emp_id)):
            missing.append("employee_id")

        dt = rec.get("date")
        if dt is None or str(dt).strip() == "" or (isinstance(dt, float) and math.isnan(dt)):
            missing.append("date")

        category = rec.get("category")
        if not category or str(category).strip() == "" or (isinstance(category, float) and math.isnan(category)):
            missing.append("category")

        description = rec.get("description")
        if not description or str(description).strip() == "" or (isinstance(description, float) and math.isnan(description)):
            missing.append("description")

        amt = parse_amount(rec.get("amount"))
        if amt is None:
            missing.append("amount")

        if missing:
            flagged.append({
                "transaction_id": display_id,
                "employee_id": str(emp_id).strip() if emp_id and not (isinstance(emp_id, float) and math.isnan(emp_id)) else "UNKNOWN",
                "date": str(dt) if dt else "UNKNOWN",
                "category": str(category) if category else "Unspecified",
                "amount": amt if amt is not None else 0.0,
                "status": "Invalid Data",
                "rule_triggered": "Missing Mandatory Fields",
                "evidence": f"The following mandatory fields are missing or empty: {', '.join(missing)}.",
                "plain_explanation": (
                    f"Transaction {display_id} cannot be processed for reimbursement because "
                    f"required information ({', '.join(missing)}) was omitted from the submission."
                ),
                "recommended_action": "Contact the submitting employee to provide the missing fields before proceeding.",
            })

    return flagged


def check_duplicate_expenses(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify exact and potential duplicate transactions.

    Exact duplicate: Same employee, same amount, same date, and identical description.
    Potential duplicate: Same employee, same amount, and same date (different description)
    OR same employee, same amount, with transaction dates within 2 calendar days.
    """
    flagged: List[Dict[str, Any]] = []
    parsed_records = []

    for index, raw_rec in enumerate(records):
        rec = normalize_record_keys(raw_rec)
        txn_id = str(rec.get("transaction_id") or f"ROW-{index + 1}").strip()
        emp_id = str(rec.get("employee_id") or "UNKNOWN").strip().upper()
        amt = parse_amount(rec.get("amount"))
        dt = parse_date(rec.get("date"))
        cat = str(rec.get("category") or "Unspecified").strip()
        desc = str(rec.get("description") or "").strip().lower()

        parsed_records.append({
            "index": index,
            "txn_id": txn_id,
            "emp_id": emp_id,
            "amount": amt,
            "date": dt,
            "raw_date": str(rec.get("date")),
            "category": cat,
            "description": desc,
            "raw_record": rec,
        })

    seen_flagged_indices = set()

    for i in range(len(parsed_records)):
        item_a = parsed_records[i]
        if item_a["amount"] is None or item_a["emp_id"] == "UNKNOWN":
            continue

        for j in range(i + 1, len(parsed_records)):
            if j in seen_flagged_indices:
                continue

            item_b = parsed_records[j]
            if item_b["amount"] is None or item_b["emp_id"] == "UNKNOWN":
                continue

            # Must be the same employee and exact same amount
            if item_a["emp_id"] == item_b["emp_id"] and abs(item_a["amount"] - item_b["amount"]) < 0.001:
                is_exact = False
                is_possible = False
                reason_details = ""

                # Check date match
                if item_a["date"] and item_b["date"]:
                    date_diff = abs((item_a["date"] - item_b["date"]).days)
                    if date_diff == 0:
                        if item_a["description"] == item_b["description"]:
                            is_exact = True
                            reason_details = (
                                f"Matches transaction {item_a['txn_id']} exactly: same employee ({item_a['emp_id']}), "
                                f"same amount (₹{item_a['amount']:,.2f}), same date ({item_a['date']}), and identical description."
                            )
                        else:
                            is_possible = True
                            reason_details = (
                                f"Matches transaction {item_a['txn_id']}: same employee ({item_a['emp_id']}), "
                                f"same amount (₹{item_a['amount']:,.2f}), and same date ({item_a['date']}) with description '{item_b['description']}'."
                            )
                    elif date_diff <= 2:
                        is_possible = True
                        reason_details = (
                            f"Possible near duplicate of {item_a['txn_id']}: same employee ({item_a['emp_id']}), "
                            f"same amount (₹{item_a['amount']:,.2f}), with dates only {date_diff} day(s) apart ({item_a['date']} vs {item_b['date']})."
                        )
                elif item_a["raw_date"] == item_b["raw_date"]:
                    is_possible = True
                    reason_details = (
                        f"Matches transaction {item_a['txn_id']}: same employee ({item_a['emp_id']}), "
                        f"same amount (₹{item_a['amount']:,.2f}), and matching date string '{item_a['raw_date']}'."
                    )

                if is_exact or is_possible:
                    seen_flagged_indices.add(j)
                    rule_label = "Exact Duplicate Transaction" if is_exact else "Possible Duplicate Transaction"
                    flagged.append({
                        "transaction_id": item_b["txn_id"],
                        "employee_id": item_b["emp_id"],
                        "date": item_b["raw_date"],
                        "category": item_b["category"],
                        "amount": item_b["amount"],
                        "status": "Needs Review",
                        "rule_triggered": rule_label,
                        "evidence": reason_details,
                        "plain_explanation": (
                            f"Transaction {item_b['txn_id']} appears to duplicate {item_a['txn_id']} submitted by employee "
                            f"{item_b['emp_id']} for ₹{item_b['amount']:,.2f}. This may indicate an accidental double submission."
                        ),
                        "recommended_action": (
                            f"Verify whether {item_b['txn_id']} and {item_a['txn_id']} represent separate distinct purchases "
                            f"or an accidental duplicate submission."
                        ),
                    })

    return flagged


def validate_expense_amounts(
    records: List[Dict[str, Any]],
    category_limits: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Validate numerical amounts, valid signs, sensible dates, and category policy limits.

    Rules:
    1. Amount must be positive (> 0).
    2. Date must not be in the future (beyond current date).
    3. Amount must not exceed the defined policy limit for its category.
    """
    if category_limits is None:
        category_limits = DEFAULT_CATEGORY_LIMITS

    flagged: List[Dict[str, Any]] = []
    current_date = date.today()

    for index, raw_rec in enumerate(records):
        rec = normalize_record_keys(raw_rec)
        txn_id = str(rec.get("transaction_id") or f"ROW-{index + 1}").strip()
        emp_id = str(rec.get("employee_id") or "UNKNOWN").strip()
        cat = str(rec.get("category") or "Unspecified").strip()
        amt = parse_amount(rec.get("amount"))
        dt = parse_date(rec.get("date"))
        raw_dt = str(rec.get("date") or "")

        # 1. Invalid or Non-positive Amount
        if amt is None:
            # Already handled in missing fields if absent, but flag if malformed
            flagged.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": raw_dt,
                "category": cat,
                "amount": 0.0,
                "status": "Invalid Data",
                "rule_triggered": "Invalid Amount Format",
                "evidence": f"The value '{rec.get('amount')}' could not be parsed as a numeric monetary amount.",
                "plain_explanation": f"Transaction {txn_id} contains an unparseable monetary amount '{rec.get('amount')}'.",
                "recommended_action": "Request corrected numerical expense figures from the employee.",
            })
            continue

        if amt <= 0.0:
            flagged.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": raw_dt,
                "category": cat,
                "amount": amt,
                "status": "Invalid Data",
                "rule_triggered": "Non-Positive Expense Amount",
                "evidence": f"Expense amount of ₹{amt:,.2f} is zero or negative.",
                "plain_explanation": (
                    f"Transaction {txn_id} lists an expense amount of ₹{amt:,.2f}. Regular reimbursement claims "
                    "must be positive monetary values. If this is a credit or refund, it requires separate processing."
                ),
                "recommended_action": "Check if this entry is an unapplied refund or typographical error.",
            })

        # 2. Future Date Check
        if dt and dt > current_date:
            flagged.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": raw_dt,
                "category": cat,
                "amount": amt,
                "status": "Invalid Data",
                "rule_triggered": "Future-Dated Expense",
                "evidence": f"Transaction date {dt} is in the future (current system date is {current_date}).",
                "plain_explanation": (
                    f"Transaction {txn_id} is dated {dt}, which has not occurred yet. Future dates are invalid "
                    "for incurred business expenses."
                ),
                "recommended_action": "Request the correct transaction date from the employee's receipt.",
            })

        # 3. Category Limit Exceeded
        limit = None
        for cat_key, max_val in category_limits.items():
            if cat_key.lower() == cat.lower():
                limit = max_val
                break

        if limit is not None and amt > limit:
            excess = amt - limit
            flagged.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": raw_dt,
                "category": cat,
                "amount": amt,
                "status": "Needs Review",
                "rule_triggered": "Category Limit Exceeded",
                "evidence": (
                    f"Amount ₹{amt:,.2f} exceeds the policy limit of ₹{limit:,.2f} for '{cat}' by ₹{excess:,.2f} "
                    f"({(excess / limit) * 100:.1f}% over limit)."
                ),
                "plain_explanation": (
                    f"Transaction {txn_id} of ₹{amt:,.2f} for '{cat}' exceeds the organizational policy cap "
                    f"of ₹{limit:,.2f}. Expenses above this threshold require departmental management approval."
                ),
                "recommended_action": "Obtain higher-level managerial sign-off or justification before approving reimbursement.",
            })

    return flagged


def check_receipt_status(
    records: List[Dict[str, Any]],
    receipt_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Flag expenses missing receipts when required by financial policy.

    Rule: Any expense equal to or exceeding the threshold (default ₹500) must have
    a verified attached receipt.
    """
    if receipt_threshold is None:
        receipt_threshold = DEFAULT_RECEIPT_THRESHOLD

    flagged: List[Dict[str, Any]] = []

    for index, raw_rec in enumerate(records):
        rec = normalize_record_keys(raw_rec)
        txn_id = str(rec.get("transaction_id") or f"ROW-{index + 1}").strip()
        emp_id = str(rec.get("employee_id") or "UNKNOWN").strip()
        cat = str(rec.get("category") or "Unspecified").strip()
        amt = parse_amount(rec.get("amount"))
        raw_dt = str(rec.get("date") or "")
        has_receipt = parse_boolean_receipt(rec.get("receipt_attached"))

        if amt is not None and amt >= receipt_threshold and not has_receipt:
            flagged.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": raw_dt,
                "category": cat,
                "amount": amt,
                "status": "Needs Review",
                "rule_triggered": "Missing Mandatory Receipt",
                "evidence": (
                    f"Amount is ₹{amt:,.2f} (exceeds receipt threshold of ₹{receipt_threshold:,.2f}) "
                    f"but receipt_attached is '{rec.get('receipt_attached')}'."
                ),
                "plain_explanation": (
                    f"Transaction {txn_id} requires proof of purchase because all expenses equal to or exceeding "
                    f"₹{receipt_threshold:,.2f} must have an attached receipt according to audit guidelines."
                ),
                "recommended_action": "Request the official merchant receipt or bill from the employee before approval.",
            })

    return flagged


def validate_expense_totals(
    records: List[Dict[str, Any]],
    claimed_total: Optional[float] = None,
) -> Dict[str, Any]:
    """Validate calculated sum of valid line items against the claimed report total."""
    calculated_sum = 0.0
    valid_count = 0
    invalid_count = 0

    for raw_rec in records:
        rec = normalize_record_keys(raw_rec)
        amt = parse_amount(rec.get("amount"))
        if amt is not None:
            calculated_sum += amt
            valid_count += 1
        else:
            invalid_count += 1

    calculated_sum = round(calculated_sum, 2)
    mismatch = False
    discrepancy = 0.0

    if claimed_total is not None and claimed_total > 0:
        claimed_total = round(claimed_total, 2)
        discrepancy = round(abs(calculated_sum - claimed_total), 2)
        if discrepancy > 0.01:
            mismatch = True

    return {
        "calculated_total": calculated_sum,
        "claimed_total": claimed_total if claimed_total is not None else calculated_sum,
        "line_items_count": len(records),
        "valid_amount_items": valid_count,
        "unparseable_items": invalid_count,
        "mismatch": mismatch,
        "discrepancy": discrepancy,
        "evidence": (
            f"Calculated sum of line items is ₹{calculated_sum:,.2f}, whereas claimed report total is "
            f"₹{claimed_total:,.2f} (discrepancy of ₹{discrepancy:,.2f})."
            if mismatch else "Report totals match calculated sum perfectly."
        ),
    }


def generate_expense_summary(
    records: List[Dict[str, Any]],
    category_limits: Optional[Dict[str, float]] = None,
    receipt_threshold: Optional[float] = None,
    claimed_total: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate high-level financial summary and compliance metrics."""
    if category_limits is None:
        category_limits = DEFAULT_CATEGORY_LIMITS
    if receipt_threshold is None:
        receipt_threshold = DEFAULT_RECEIPT_THRESHOLD

    # Run individual validation passes
    missing_flags = check_missing_fields(records)
    duplicate_flags = check_duplicate_expenses(records)
    amount_flags = validate_expense_amounts(records, category_limits)
    receipt_flags = check_receipt_status(records, receipt_threshold)
    totals_check = validate_expense_totals(records, claimed_total)

    total_records = len(records)
    total_amount = 0.0
    category_spending: Dict[str, float] = {}
    category_counts: Dict[str, int] = {}

    for raw_rec in records:
        rec = normalize_record_keys(raw_rec)
        amt = parse_amount(rec.get("amount")) or 0.0
        cat = str(rec.get("category") or "Unspecified").strip()
        total_amount += amt
        category_spending[cat] = category_spending.get(cat, 0.0) + amt
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Deduplicate flagged transaction IDs
    all_flagged_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for flag_group in [missing_flags, duplicate_flags, amount_flags, receipt_flags]:
        for item in flag_group:
            tid = item["transaction_id"]
            if tid not in all_flagged_by_id:
                all_flagged_by_id[tid] = []
            all_flagged_by_id[tid].append(item)

    flagged_transactions_count = len(all_flagged_by_id)
    passing_transactions_count = max(0, total_records - flagged_transactions_count)

    # Calculate flagged amount
    flagged_amount = 0.0
    for tid, items in all_flagged_by_id.items():
        flagged_amount += items[0]["amount"]

    compliance_rate = (
        (passing_transactions_count / total_records * 100.0)
        if total_records > 0 else 100.0
    )

    return {
        "total_records": total_records,
        "total_amount": round(total_amount, 2),
        "passing_count": passing_transactions_count,
        "flagged_count": flagged_transactions_count,
        "flagged_amount": round(flagged_amount, 2),
        "passing_amount": round(total_amount - flagged_amount, 2),
        "compliance_rate": round(compliance_rate, 1),
        "missing_fields_count": len(missing_flags),
        "duplicates_count": len(duplicate_flags),
        "policy_limit_exceeded_count": len([f for f in amount_flags if f["rule_triggered"] == "Category Limit Exceeded"]),
        "missing_receipts_count": len(receipt_flags),
        "invalid_amounts_count": len([f for f in amount_flags if f["rule_triggered"] != "Category Limit Exceeded"]),
        "totals_reconciliation": totals_check,
        "category_spending": {k: round(v, 2) for k, v in category_spending.items()},
        "category_counts": category_counts,
    }


def run_all_validations(
    records: List[Dict[str, Any]],
    config: Optional[ExpenseGuardConfig] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Execute complete deterministic validation pipeline.

    Returns:
    - List of unified transaction items with status, triggered rules, evidence, and recommendations.
    - Financial summary dictionary.
    """
    if config is None:
        config = ExpenseGuardConfig()

    category_limits = config.category_limits
    receipt_threshold = config.receipt_threshold

    missing_flags = check_missing_fields(records)
    duplicate_flags = check_duplicate_expenses(records)
    amount_flags = validate_expense_amounts(records, category_limits)
    receipt_flags = check_receipt_status(records, receipt_threshold)

    # Index all flags by transaction_id
    flags_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for flag_group in [missing_flags, duplicate_flags, amount_flags, receipt_flags]:
        for item in flag_group:
            tid = item["transaction_id"]
            if tid not in flags_by_id:
                flags_by_id[tid] = []
            flags_by_id[tid].append(item)

    unified_items: List[Dict[str, Any]] = []

    for index, raw_rec in enumerate(records):
        rec = normalize_record_keys(raw_rec)
        txn_id = str(rec.get("transaction_id") or f"ROW-{index + 1}").strip()
        emp_id = str(rec.get("employee_id") or "UNKNOWN").strip()
        dt = str(rec.get("date") or "")
        cat = str(rec.get("category") or "Unspecified").strip()
        desc = str(rec.get("description") or "").strip()
        amt = parse_amount(rec.get("amount")) or 0.0
        has_receipt = parse_boolean_receipt(rec.get("receipt_attached"))

        if txn_id in flags_by_id:
            items = flags_by_id[txn_id]
            rules = [it["rule_triggered"] for it in items]
            evidences = [it["evidence"] for it in items]
            actions = [it["recommended_action"] for it in items]
            explanations = [it["plain_explanation"] for it in items]
            combined_status = "Invalid Data" if any(it.get("status") == "Invalid Data" for it in items) else "Needs Review"
            unified_items.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": dt,
                "category": cat,
                "description": desc,
                "amount": amt,
                "receipt_attached": has_receipt,
                "status": combined_status,
                "rule_triggered": " | ".join(rules),
                "evidence": " ".join(evidences),
                "plain_explanation": " ".join(explanations),
                "recommended_action": " ".join(actions),
                "flags_detail": items,
            })
        else:
            unified_items.append({
                "transaction_id": txn_id,
                "employee_id": emp_id,
                "date": dt,
                "category": cat,
                "description": desc,
                "amount": amt,
                "receipt_attached": has_receipt,
                "status": "Passed",
                "rule_triggered": "None",
                "evidence": f"Transaction complies with all policy rules for {cat} (amount ₹{amt:,.2f}).",
                "plain_explanation": (
                    f"Transaction {txn_id} satisfies all financial guidelines. Receipt is confirmed and the amount "
                    f"is within the permissible cap for {cat}."
                ),
                "recommended_action": "Ready for human reviewer sign-off.",
                "flags_detail": [],
            })

    summary = generate_expense_summary(
        records,
        category_limits=category_limits,
        receipt_threshold=receipt_threshold,
        claimed_total=config.claimed_total if config.claimed_total > 0 else None,
    )

    return unified_items, summary
