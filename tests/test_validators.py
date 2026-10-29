"""Automated Pytest Suite for Deterministic Validation Engine."""

import pytest
from datetime import date, timedelta

from validators import (
    check_missing_fields,
    check_duplicate_expenses,
    validate_expense_amounts,
    check_receipt_status,
    validate_expense_totals,
    generate_expense_summary,
    run_all_validations,
    parse_amount,
    parse_date,
    parse_boolean_receipt,
    normalize_record_keys,
)
from config import DEFAULT_CATEGORY_LIMITS, DEFAULT_RECEIPT_THRESHOLD, ExpenseGuardConfig


class TestValidators:
    """Tests for pure Python deterministic validation logic."""

    def test_missing_mandatory_fields(self):
        records = [
            # Missing employee_id and description
            {
                "transaction_id": "T1",
                "employee_id": "",
                "date": "2026-10-15",
                "category": "Travel",
                "description": None,
                "amount": 500.0,
                "receipt_attached": True,
            },
            # Missing amount
            {
                "transaction_id": "T2",
                "employee_id": "EMP-01",
                "date": "2026-10-15",
                "category": "Meals",
                "description": "Lunch",
                "amount": "",
                "receipt_attached": True,
            },
            # Complete record
            {
                "transaction_id": "T3",
                "employee_id": "EMP-02",
                "date": "2026-10-15",
                "category": "Software",
                "description": "Git license",
                "amount": 1200.0,
                "receipt_attached": True,
            },
        ]

        flagged = check_missing_fields(records)
        assert len(flagged) == 2
        flagged_ids = [f["transaction_id"] for f in flagged]
        assert "T1" in flagged_ids
        assert "T2" in flagged_ids
        assert "T3" not in flagged_ids

    def test_exact_duplicate_detection(self):
        records = [
            {
                "transaction_id": "EXP-101",
                "employee_id": "EMP-01",
                "amount": 800.0,
                "date": "2026-10-10",
                "category": "Software",
                "description": "License subscription",
                "receipt_attached": True,
            },
            {
                "transaction_id": "EXP-102",
                "employee_id": "EMP-01",
                "amount": 800.0,
                "date": "2026-10-10",
                "category": "Software",
                "description": "License subscription",
                "receipt_attached": True,
            },
        ]
        flagged = check_duplicate_expenses(records)
        assert len(flagged) == 1
        assert flagged[0]["transaction_id"] == "EXP-102"
        assert flagged[0]["rule_triggered"] == "Exact Duplicate Transaction"
        assert "EXP-101" in flagged[0]["evidence"]

    def test_near_duplicate_detection(self):
        records = [
            {
                "transaction_id": "EXP-201",
                "employee_id": "EMP-05",
                "amount": 5500.0,
                "date": "2026-10-12",
                "category": "Travel",
                "description": "Flight booking",
                "receipt_attached": True,
            },
            {
                "transaction_id": "EXP-202",
                "employee_id": "EMP-05",
                "amount": 5500.0,
                "date": "2026-10-13",  # 1 day later
                "category": "Travel",
                "description": "Flight change",
                "receipt_attached": True,
            },
        ]
        flagged = check_duplicate_expenses(records)
        assert len(flagged) == 1
        assert flagged[0]["transaction_id"] == "EXP-202"
        assert flagged[0]["rule_triggered"] == "Possible Duplicate Transaction"
        assert "1 day(s) apart" in flagged[0]["evidence"]

    def test_negative_and_zero_amounts(self):
        records = [
            {
                "transaction_id": "T-NEG",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Travel",
                "amount": -250.0,
                "receipt_attached": True,
            },
            {
                "transaction_id": "T-ZERO",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Travel",
                "amount": 0.0,
                "receipt_attached": True,
            },
            {
                "transaction_id": "T-POS",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Travel",
                "amount": 400.0,
                "receipt_attached": True,
            },
        ]
        flagged = validate_expense_amounts(records)
        flagged_ids = [f["transaction_id"] for f in flagged]
        assert "T-NEG" in flagged_ids
        assert "T-ZERO" in flagged_ids
        assert "T-POS" not in flagged_ids

    def test_future_dates(self):
        future_date = (date.today() + timedelta(days=60)).strftime("%Y-%m-%d")
        past_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")

        records = [
            {
                "transaction_id": "T-FUT",
                "employee_id": "EMP-01",
                "date": future_date,
                "category": "Meals",
                "amount": 500.0,
                "receipt_attached": True,
            },
            {
                "transaction_id": "T-PAST",
                "employee_id": "EMP-01",
                "date": past_date,
                "category": "Meals",
                "amount": 500.0,
                "receipt_attached": True,
            },
        ]
        flagged = validate_expense_amounts(records)
        flagged_ids = [f["transaction_id"] for f in flagged]
        assert "T-FUT" in flagged_ids
        assert "T-PAST" not in flagged_ids

    def test_category_limit_exceeded(self):
        limits = {"Meals": 1500.0, "Travel": 10000.0}
        records = [
            {
                "transaction_id": "T-MEAL-OVER",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "amount": 2200.0,
                "receipt_attached": True,
            },
            {
                "transaction_id": "T-MEAL-OK",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "amount": 1200.0,
                "receipt_attached": True,
            },
        ]
        flagged = validate_expense_amounts(records, category_limits=limits)
        assert len(flagged) == 1
        assert flagged[0]["transaction_id"] == "T-MEAL-OVER"
        assert flagged[0]["rule_triggered"] == "Category Limit Exceeded"
        assert "₹2,200.00 exceeds the policy limit of ₹1,500.00" in flagged[0]["evidence"]

    def test_missing_receipt_threshold(self):
        threshold = 500.0
        records = [
            # High amount, no receipt -> flag
            {
                "transaction_id": "T-NO-RECEIPT-HIGH",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "amount": 750.0,
                "receipt_attached": "No",
            },
            # Low amount, no receipt -> allowed
            {
                "transaction_id": "T-NO-RECEIPT-LOW",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "amount": 300.0,
                "receipt_attached": False,
            },
            # High amount, with receipt -> allowed
            {
                "transaction_id": "T-HAS-RECEIPT",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "amount": 1200.0,
                "receipt_attached": True,
            },
        ]
        flagged = check_receipt_status(records, receipt_threshold=threshold)
        assert len(flagged) == 1
        assert flagged[0]["transaction_id"] == "T-NO-RECEIPT-HIGH"
        assert flagged[0]["rule_triggered"] == "Missing Mandatory Receipt"

    def test_totals_reconciliation(self):
        records = [
            {"amount": 100.0},
            {"amount": 250.50},
            {"amount": 149.50},
        ]
        # Sum is 500.0
        match_result = validate_expense_totals(records, claimed_total=500.0)
        assert match_result["mismatch"] is False
        assert match_result["calculated_total"] == 500.0

        mismatch_result = validate_expense_totals(records, claimed_total=600.0)
        assert mismatch_result["mismatch"] is True
        assert mismatch_result["discrepancy"] == 100.0

    def test_parsing_helpers(self):
        # Currency stripping
        assert parse_amount("₹1,500.00") == 1500.0
        assert parse_amount("$2,450.75") == 2450.75
        assert parse_amount(" -450 ") == -450.0
        assert parse_amount("invalid") is None

        # Booleans
        assert parse_boolean_receipt("yes") is True
        assert parse_boolean_receipt("True") is True
        assert parse_boolean_receipt("1") is True
        assert parse_boolean_receipt("no") is False
        assert parse_boolean_receipt(None) is False

        # Dates
        assert parse_date("2026-10-15") == date(2026, 10, 15)
        assert parse_date("15-10-2026") == date(2026, 10, 15)
        assert parse_date("10/15/2026") == date(2026, 10, 15)

    def test_run_all_validations_clean(self):
        records = [
            {
                "transaction_id": "OK-1",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "description": "Team lunch",
                "amount": 600.0,
                "receipt_attached": True,
            }
        ]
        items, summary = run_all_validations(records)
        assert len(items) == 1
        assert items[0]["status"] in ["Passed", "Valid"]
        assert summary["flagged_count"] == 0
        assert summary["compliance_rate"] == 100.0
