"""Pytest Suite for AI Agent Orchestration and Tool Planning."""

import pytest
import pandas as pd

from agent import ExpenseAuditAgent
from config import ExpenseGuardConfig


class TestAgent:
    """Verifies agent tool planning, execution coordination, and fallback."""

    def test_agent_tool_planning(self):
        agent = ExpenseAuditAgent()

        # Full audit
        full_tools = agent.plan_tools("full")
        assert len(full_tools) == 5
        assert "check_duplicate_expenses" in full_tools
        assert "generate_expense_summary" in full_tools

        # Duplicate scan
        dup_tools = agent.plan_tools("duplicate")
        assert "check_duplicate_expenses" in dup_tools
        assert "check_missing_fields" not in dup_tools

        # Receipt scan
        receipt_tools = agent.plan_tools("receipt")
        assert "check_receipt_status" in receipt_tools
        assert "check_duplicate_expenses" not in receipt_tools

    def test_agent_run_audit_fast_mode(self):
        """Test agent execution with deterministic explanations (fast mode)."""
        agent = ExpenseAuditAgent()
        records = [
            {
                "transaction_id": "T1",
                "employee_id": "EMP-01",
                "date": "2026-10-10",
                "category": "Meals",
                "description": "Lunch meeting",
                "amount": 2200.0,  # Exceeds 1500
                "receipt_attached": True,
            },
            {
                "transaction_id": "T2",
                "employee_id": "EMP-02",
                "date": "2026-10-10",
                "category": "Travel",
                "description": "Taxi",
                "amount": 400.0,
                "receipt_attached": True,
            },
        ]

        result = agent.run_audit(records, audit_mode="full", explain_with_llm=False)
        assert result["status"] == "success"
        assert result["summary"]["total_records"] == 2
        assert result["summary"]["flagged_count"] == 1
        assert result["summary"]["passing_count"] == 1

        flagged = result["flagged_items"][0]
        assert flagged["transaction_id"] == "T1"
        assert "Category Limit Exceeded" in flagged["rule_triggered"]
        assert "reimbursement" in flagged["plain_explanation"].lower() or "exceeds" in flagged["plain_explanation"].lower()
        assert len(result["logs"]) >= 5
