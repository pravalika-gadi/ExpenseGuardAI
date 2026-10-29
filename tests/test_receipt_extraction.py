"""Comprehensive test suite for receipt total extraction.

Tests cover:
- Different receipt formats (cafe, grocery, restaurant, pharmacy, travel, fuel, electronics, bookstore)
- Misleading IDs (employee IDs, user IDs, invoice numbers, ticket numbers, phone numbers)
- GST-inclusive totals (should read the printed final total, never add GST)
- Missing totals (should return 0.0 / "Total not detected")
- Consecutive uploads (each must be processed independently, no stale data)
"""

import pytest
from doc_loader import (
    extract_and_reconcile_amount,
    detect_category,
    extract_clean_merchant,
    extract_bill_number,
    extract_receipt_date,
    extract_receipt_total_direct,
    clean_amount_str,
    _is_id_or_noise_line,
)
import io
from PIL import Image, ImageDraw


class TestTotalExtraction:
    """Tests for extract_and_reconcile_amount — the core total-reading logic."""

    def test_simple_total_line(self):
        lines = [
            "Sunrise Cafe",
            "Date: 2026-10-15",
            "Cappuccino        250.00",
            "Sandwich          180.00",
            "Subtotal          430.00",
            "CGST 2.5%          10.75",
            "SGST 2.5%          10.75",
            "Total             451.50",
        ]
        assert extract_and_reconcile_amount(lines) == 451.50

    def test_grand_total_line(self):
        lines = [
            "SuperMart Grocery",
            "Item A            300.00",
            "Item B            200.00",
            "Subtotal          500.00",
            "GST                90.00",
            "Grand Total       590.00",
        ]
        assert extract_and_reconcile_amount(lines) == 590.00

    def test_net_payable_line(self):
        lines = [
            "Pharmacy Wellness",
            "Medicine           120.00",
            "Net Payable        120.00",
        ]
        assert extract_and_reconcile_amount(lines) == 120.00

    def test_amount_paid_line(self):
        lines = [
            "Restaurant Receipt",
            "Food              1200.00",
            "Tax                216.00",
            "Amount Paid       1416.00",
        ]
        assert extract_and_reconcile_amount(lines) == 1416.00


class TestMisleadingIDs:
    """Tests that IDs, phone numbers, and non-total numbers are NOT mistaken for the total."""

    def test_employee_id_not_extracted_as_total(self):
        lines = [
            "Expense Report",
            "Employee ID: 50432",
            "Date: 2026-10-10",
            "Category: Travel",
            "Description: Cab ride",
            "Amount: 350.00",
            "Total: 350.00",
        ]
        total = extract_and_reconcile_amount(lines)
        # Should be 350.00, not 50432
        assert total == 350.00

    def test_invoice_number_not_extracted(self):
        lines = [
            "Invoice No: 78234",
            "Date: 2026-10-12",
            "Item: Office chair",
            "Price: 4500.00",
            "CGST: 405.00",
            "SGST: 405.00",
            "Total: 5310.00",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 5310.00

    def test_phone_number_not_extracted(self):
        lines = [
            "FuelMax Station",
            "Phone: 9876543210",
            "Petrol 5L",
            "Total: 525.00",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 525.00

    def test_ticket_number_not_extracted(self):
        lines = [
            "IndiaRail Ticket",
            "Ticket No: 84752319",
            "PNR: 4523871906",
            "Class: 2A",
            "Fare: 1850.00",
            "Convenience Fee: 35.00",
            "Total: 1885.00",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 1885.00


class TestGSTInclusiveTotals:
    """Tests that GST-inclusive totals are read as-is, never recalculated."""

    def test_gst_inclusive_total_not_recalculated(self):
        """The total 472.00 already includes GST. We should NOT add GST again."""
        lines = [
            "Coffee House",
            "Latte             200.00",
            "Muffin            200.00",
            "Subtotal          400.00",
            "CGST 9%            36.00",
            "SGST 9%            36.00",
            "Total             472.00",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 472.00
        # Must NOT be 400 + 36 + 36 + any additional calculation

    def test_total_with_multiple_tax_lines(self):
        """Multiple tax lines should not inflate the extracted total."""
        lines = [
            "Electronics Store",
            "Laptop Charger    2500.00",
            "Subtotal          2500.00",
            "CGST 9%            225.00",
            "SGST 9%            225.00",
            "Round Off           0.00",
            "Grand Total       2950.00",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 2950.00

    def test_cgst_sgst_lines_not_extracted_as_total(self):
        """Tax amount lines should never be extracted as the total."""
        lines = [
            "Store ABC",
            "Widget            1000.00",
            "CGST Total          90.00",
            "SGST Total          90.00",
            "Total             1180.00",
        ]
        total = extract_and_reconcile_amount(lines)
        # Should be 1180.00, not 90.00
        assert total == 1180.00


class TestMissingTotals:
    """Tests for receipts where no total can be confidently identified."""

    def test_no_total_line_returns_zero(self):
        lines = [
            "Random Document",
            "This is just some text",
            "No amounts here",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 0.0

    def test_only_noise_lines_returns_zero(self):
        lines = [
            "GSTIN: 29AABCU1234F1Z5",
            "Phone: 080-12345678",
            "Road No. 4, Bangalore",
        ]
        total = extract_and_reconcile_amount(lines)
        assert total == 0.0


class TestConsecutiveUploads:
    """Tests that each upload is processed independently — no stale data."""

    def test_two_different_receipts_give_different_totals(self):
        """Simulates two consecutive uploads; each must yield its own total."""
        receipt_1_lines = [
            "Cafe Alpha",
            "Coffee            150.00",
            "Total             150.00",
        ]
        receipt_2_lines = [
            "Restaurant Beta",
            "Dinner           2200.00",
            "Total            2200.00",
        ]

        total_1 = extract_and_reconcile_amount(receipt_1_lines)
        total_2 = extract_and_reconcile_amount(receipt_2_lines)

        assert total_1 == 150.00
        assert total_2 == 2200.00
        assert total_1 != total_2

    def test_independent_processing_no_state_leakage(self):
        """Call extract_and_reconcile_amount three times; results must be independent."""
        lines_a = ["Total: 100.00"]
        lines_b = ["Grand Total: 999.00"]
        lines_c = ["Amount Paid: 50.00"]

        assert extract_and_reconcile_amount(lines_a) == 100.00
        assert extract_and_reconcile_amount(lines_b) == 999.00
        assert extract_and_reconcile_amount(lines_c) == 50.00


class TestDirectReceiptReader:
    """Tests for the extract_receipt_total_direct function used by the Receipt tab."""

    def test_unsupported_format_raises(self):
        stream = io.BytesIO(b"hello")
        with pytest.raises(ValueError, match="Unsupported receipt format"):
            extract_receipt_total_direct(stream, "file.txt")

    def test_returns_dict_with_expected_keys(self):
        """When Tesseract is available, result should have correct keys."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
        except Exception:
            pytest.skip("Tesseract not available")

        img = Image.new("RGB", (400, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Store", fill="black")
        draw.text((20, 60), "Total: 100.00", fill="black")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        result = extract_receipt_total_direct(buf, "test.png")
        assert "total" in result
        assert "merchant" in result
        assert "category" in result
        assert "date" in result
        assert "bill_no" in result
        assert "ocr_text" in result


class TestHelperFunctions:
    """Tests for helper functions in doc_loader."""

    def test_detect_category(self):
        assert detect_category("uber cab ride to airport") == "Travel"
        assert detect_category("pharmacy prescription medicine") == "Healthcare"
        assert detect_category("cappuccino and sandwich") == "Meals"
        assert detect_category("random text without keywords") == "Miscellaneous"

    def test_clean_amount_str(self):
        assert "750.00" in clean_amount_str("INR750.00")
        assert "750.00" in clean_amount_str("Rs.750.00")
        assert "1500.00" in clean_amount_str("1,500.00")

    def test_is_id_or_noise_line(self):
        assert _is_id_or_noise_line("Employee ID: 50432") is True
        assert _is_id_or_noise_line("Phone: 9876543210") is True
        assert _is_id_or_noise_line("GSTIN: 29AABCU1234F1Z5") is True
        assert _is_id_or_noise_line("Total: 500.00") is False

    def test_extract_merchant(self):
        lines = ["SuperMart Store", "Tax Invoice", "Date: 2026-10-15"]
        assert extract_clean_merchant(lines) == "SuperMart Store"

    def test_extract_date(self):
        lines = ["Date: 2026-10-15", "Other text"]
        assert extract_receipt_date(lines) == "2026-10-15"

    def test_year_values_not_treated_as_amounts(self):
        """Years like 2024, 2025, 2026 should not be treated as amounts."""
        lines = [
            "Invoice Date: 2026-10-15",
            "Total: 350.00",
        ]
        assert extract_and_reconcile_amount(lines) == 350.00

