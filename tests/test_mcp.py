"""Pytest Suite verifying Genuine Model Context Protocol (MCP) Integration.

Validates that:
1. Real MCP server exposes required validation tools.
2. Real MCP client discovers all tools over stdio transport.
3. Real MCP client invokes tools and receives actual structured results.
4. Error handling behaves correctly on bad inputs or non-existent files.
"""

import json
import pytest

from mcp_client import SyncMCPExpenseClient
import mcp_server


class TestMCPIntegration:
    """Verifies official Python MCP SDK integration with real stdio client-server."""

    def test_mcp_server_module_tools_registered(self):
        """Verify tools are registered on the MCPServer instance."""
        # The MCPServer object tracks registered tools in its tool manager
        tool_names = list(mcp_server.server._tool_manager._tools.keys())
        expected = [
            "read_expense_report",
            "check_missing_fields",
            "check_duplicate_expenses",
            "validate_expense_amounts",
            "check_receipt_status",
            "generate_expense_summary",
        ]
        for exp in expected:
            assert exp in tool_names, f"Expected tool '{exp}' not found in registered server tools."

    def test_real_mcp_stdio_tool_discovery(self):
        """Verify the MCP client connects over stdio and discovers all server tools."""
        client = SyncMCPExpenseClient()
        tools = client.discover_tools()
        assert len(tools) >= 6

        discovered_names = [t["name"] for t in tools]
        expected_tools = [
            "read_expense_report",
            "check_missing_fields",
            "check_duplicate_expenses",
            "validate_expense_amounts",
            "check_receipt_status",
            "generate_expense_summary",
        ]
        for exp in expected_tools:
            assert exp in discovered_names

    def test_real_mcp_stdio_invoke_missing_fields(self):
        """Invoke check_missing_fields tool on real MCP server via stdio."""
        client = SyncMCPExpenseClient()
        records = [
            {"transaction_id": "T-VALID", "employee_id": "E1", "date": "2026-10-10", "category": "Meals", "description": "Lunch", "amount": 200, "receipt_attached": True},
            {"transaction_id": "T-INVALID", "employee_id": "", "date": "2026-10-10", "category": "Meals", "description": "", "amount": 200, "receipt_attached": True},
        ]
        raw_res = client.call_tool("check_missing_fields", {"records_json": json.dumps(records)})
        res = json.loads(raw_res)

        assert res.get("status") == "success"
        assert res.get("flagged_count") == 1
        assert res["flagged_items"][0]["transaction_id"] == "T-INVALID"

    def test_real_mcp_stdio_invoke_duplicate_expenses(self):
        """Invoke check_duplicate_expenses tool on real MCP server via stdio."""
        client = SyncMCPExpenseClient()
        records = [
            {"transaction_id": "D1", "employee_id": "EMP-01", "date": "2026-10-10", "amount": 750.0, "category": "Meals", "description": "Dinner"},
            {"transaction_id": "D2", "employee_id": "EMP-01", "date": "2026-10-10", "amount": 750.0, "category": "Meals", "description": "Dinner"},
        ]
        raw_res = client.call_tool("check_duplicate_expenses", {"records_json": json.dumps(records)})
        res = json.loads(raw_res)

        assert res.get("status") == "success"
        assert res.get("flagged_count") == 1
        assert res["flagged_items"][0]["transaction_id"] == "D2"

    def test_real_mcp_stdio_invoke_amounts_and_summary(self):
        """Invoke validate_expense_amounts and generate_expense_summary over stdio."""
        client = SyncMCPExpenseClient()
        records = [
            {"transaction_id": "A1", "employee_id": "E1", "date": "2026-10-10", "category": "Meals", "amount": 3000.0, "description": "Banquet"},
        ]
        limits = {"Meals": 1500.0}
        raw_res = client.call_tool("validate_expense_amounts", {
            "records_json": json.dumps(records),
            "limits_json": json.dumps(limits),
        })
        res = json.loads(raw_res)
        assert res.get("status") == "success"
        assert res.get("flagged_count") == 1
        assert "Category Limit Exceeded" in res["flagged_items"][0]["rule_triggered"]

        raw_summary = client.call_tool("generate_expense_summary", {
            "records_json": json.dumps(records),
            "limits_json": json.dumps(limits),
        })
        sum_res = json.loads(raw_summary)
        assert sum_res.get("status") == "success"
        assert sum_res["summary"]["total_amount"] == 3000.0

    def test_mcp_read_expense_report_file(self):
        """Test reading actual sample data file through MCP server."""
        client = SyncMCPExpenseClient()
        raw_res = client.call_tool("read_expense_report", {
            "file_path": "sample_data/sample_expenses_clean.csv",
        })
        res = json.loads(raw_res)
        assert res.get("status") == "success"
        assert res.get("row_count") == 10
        assert "transaction_id" in res.get("columns", [])

    def test_mcp_read_invalid_file(self):
        """Test read_expense_report handles non-existent file cleanly."""
        client = SyncMCPExpenseClient()
        raw_res = client.call_tool("read_expense_report", {
            "file_path": "non_existent_file_path_12345.csv",
        })
        res = json.loads(raw_res)
        assert res.get("status") == "error"
        assert "File not found" in res.get("message", "")
