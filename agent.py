"""ExpenseGuard AI — AI Agent Orchestration Module.

Implements a goal-driven Tool-Using Agent that coordinates:
1. Review intent interpretation.
2. Dynamic MCP tool selection.
3. Real MCP tool invocation via MCP client.
4. Deterministic results synthesis.
5. Explainable AI explanation generation via local LLM (or fallback).
6. Human review recommendation dossier preparation.
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional

from config import ExpenseGuardConfig
from mcp_client import SyncMCPExpenseClient
from llm import OllamaClient
import validators

logger = logging.getLogger("ExpenseGuardAgent")


class ExpenseAuditAgent:
    """Coordinates tool selection, MCP execution, and explainable verification."""

    def __init__(self, config: Optional[ExpenseGuardConfig] = None):
        self.config = config or ExpenseGuardConfig()
        self.mcp_client = SyncMCPExpenseClient()
        self.llm_client = OllamaClient(
            base_url=self.config.ollama_base_url,
            model=self.config.ollama_model,
            timeout=self.config.ollama_timeout,
        )
        self.execution_logs: List[Dict[str, Any]] = []

    def _log_step(self, step_name: str, details: str, payload: Optional[Any] = None):
        """Record step in the agent's observable decision trail."""
        self.execution_logs.append({
            "timestamp": time.strftime("%H:%M:%S"),
            "step": step_name,
            "details": details,
            "payload": payload,
        })

    def plan_tools(self, audit_mode: str = "full") -> List[str]:
        """Determine which MCP tools to execute based on audit intent.

        Agent Characteristic: Dynamic Goal-Oriented Tool Selection.
        """
        audit_mode_lower = (audit_mode or "full").lower()

        if "duplicate" in audit_mode_lower:
            selected = ["check_duplicate_expenses", "generate_expense_summary"]
            reason = "Focused duplicate scan requested. Selecting duplicate detector and summary generator."
        elif "receipt" in audit_mode_lower:
            selected = ["check_receipt_status", "generate_expense_summary"]
            reason = "Receipt compliance scan requested. Selecting receipt validator and summary generator."
        elif "amount" in audit_mode_lower or "limit" in audit_mode_lower:
            selected = ["validate_expense_amounts", "generate_expense_summary"]
            reason = "Policy limits scan requested. Selecting amount validator and summary generator."
        else:
            selected = [
                "check_missing_fields",
                "check_duplicate_expenses",
                "validate_expense_amounts",
                "check_receipt_status",
                "generate_expense_summary",
            ]
            reason = "Comprehensive audit requested. Selecting full suite of validation tools."

        self._log_step(
            "Tool Planning",
            f"Audit Mode: '{audit_mode}'. {reason}",
            {"selected_tools": selected},
        )
        return selected

    def run_audit(
        self,
        records: List[Dict[str, Any]],
        audit_mode: str = "full",
        explain_with_llm: bool = True,
    ) -> Dict[str, Any]:
        """Execute end-to-end agent workflow.

        Steps:
        1. Discover available tools from MCP server.
        2. Plan necessary tools based on user audit mode.
        3. Invoke selected tools via MCP client.
        4. Synthesize tool results with deterministic rules.
        5. Generate AI explanations for flagged items.
        6. Produce final human review audit dossier.
        """
        start_time = time.time()
        self.execution_logs.clear()
        self._log_step("Agent Initialized", f"Beginning audit of {len(records)} expense transactions.")

        # Step 1: Discover Tools via MCP Client
        try:
            discovered_tools = self.mcp_client.discover_tools()
            self._log_step(
                "MCP Discovery",
                f"Discovered {len(discovered_tools)} MCP tools on server.",
                [t["name"] for t in discovered_tools],
            )
        except Exception as e:
            logger.error(f"MCP discovery failed: {e}")
            self._log_step("MCP Discovery Error", f"Failed to connect to MCP server: {e}")
            discovered_tools = []

        # Step 2: Plan Tools
        tools_to_run = self.plan_tools(audit_mode)

        # Step 3: Execute Selected Tools via MCP
        records_json = json.dumps(records, default=str)
        limits_json = json.dumps(self.config.category_limits)
        tool_results: Dict[str, Any] = {}

        for tool_name in tools_to_run:
            step_start = time.time()
            try:
                if tool_name == "check_missing_fields":
                    res_raw = self.mcp_client.call_tool(tool_name, {"records_json": records_json})
                elif tool_name == "check_duplicate_expenses":
                    res_raw = self.mcp_client.call_tool(tool_name, {"records_json": records_json})
                elif tool_name == "validate_expense_amounts":
                    res_raw = self.mcp_client.call_tool(tool_name, {
                        "records_json": records_json,
                        "limits_json": limits_json,
                    })
                elif tool_name == "check_receipt_status":
                    res_raw = self.mcp_client.call_tool(tool_name, {
                        "records_json": records_json,
                        "threshold": self.config.receipt_threshold,
                    })
                elif tool_name == "generate_expense_summary":
                    res_raw = self.mcp_client.call_tool(tool_name, {
                        "records_json": records_json,
                        "limits_json": limits_json,
                    })
                else:
                    res_raw = "{}"

                parsed = json.loads(res_raw) if res_raw else {}
                tool_results[tool_name] = parsed
                duration_ms = round((time.time() - step_start) * 1000, 1)

                flag_count = parsed.get("flagged_count", 0)
                self._log_step(
                    f"MCP Invocation: {tool_name}",
                    f"Completed in {duration_ms}ms with status '{parsed.get('status')}'. Flagged items: {flag_count}.",
                    parsed,
                )
            except Exception as e:
                logger.error(f"Error invoking {tool_name}: {e}")
                self._log_step(f"MCP Invocation Error: {tool_name}", str(e))
                tool_results[tool_name] = {"status": "error", "error": str(e), "flagged_items": []}

        # Step 4: Synthesize Results
        # Consolidate flags across executed tools
        flagged_items_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for t_name, t_data in tool_results.items():
            if "flagged_items" in t_data:
                for f_item in t_data["flagged_items"]:
                    tid = f_item["transaction_id"]
                    if tid not in flagged_items_by_id:
                        flagged_items_by_id[tid] = []
                    flagged_items_by_id[tid].append(f_item)

        # Build unified review items for all records
        unified_items: List[Dict[str, Any]] = []
        for index, raw_rec in enumerate(records):
            rec = validators.normalize_record_keys(raw_rec)
            txn_id = str(rec.get("transaction_id") or f"ROW-{index + 1}").strip()
            emp_id = str(rec.get("employee_id") or "UNKNOWN").strip()
            dt = str(rec.get("date") or "")
            cat = str(rec.get("category") or "Unspecified").strip()
            desc = str(rec.get("description") or "").strip()
            amt = validators.parse_amount(rec.get("amount")) or 0.0
            has_receipt = validators.parse_boolean_receipt(rec.get("receipt_attached"))

            if txn_id in flagged_items_by_id:
                items = flagged_items_by_id[txn_id]
                rules = [it["rule_triggered"] for it in items]
                evidences = [it["evidence"] for it in items]
                default_explanations = [it["plain_explanation"] for it in items]
                default_actions = [it["recommended_action"] for it in items]

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
                    "plain_explanation": " ".join(default_explanations),
                    "recommended_action": " ".join(default_actions),
                    "explanation_source": "deterministic_rules",
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
                    "explanation_source": "deterministic_rules",
                    "flags_detail": [],
                })

        # Step 5: Explainable AI Enhancement via LLM (or Fallback)
        flagged_only = [item for item in unified_items if item["status"] in ["Needs Review", "Invalid Data"]]
        if explain_with_llm:
            self._log_step(
                "XAI Synthesis",
                f"Generating grounded explanations for {len(flagged_only)} flagged transactions using LLM.",
            )

            for item in flagged_only:
                explanation_res = self.llm_client.explain_transaction(item)
                item["plain_explanation"] = explanation_res["explanation"]
                item["recommended_action"] = explanation_res["recommended_action"]
                item["explanation_source"] = explanation_res["source"]

        # Step 6: Generate Summary and Executive AI Synthesis
        summary = validators.generate_expense_summary(
            records,
            category_limits=self.config.category_limits,
            receipt_threshold=self.config.receipt_threshold,
            claimed_total=self.config.claimed_total if self.config.claimed_total > 0 else None,
        )

        ai_summary = self.llm_client.generate_audit_summary(summary, flagged_only)

        total_duration = round(time.time() - start_time, 2)
        self._log_step(
            "Audit Complete",
            f"Successfully processed {len(records)} records in {total_duration}s. {summary['flagged_count']} flagged for review.",
        )

        return {
            "status": "success",
            "duration_seconds": total_duration,
            "discovered_tools": [t["name"] for t in discovered_tools],
            "executed_tools": tools_to_run,
            "summary": summary,
            "ai_summary": ai_summary,
            "items": unified_items,
            "flagged_items": flagged_only,
            "valid_items": [it for it in unified_items if it["status"] in ["Passed", "Valid"]],
            "logs": self.execution_logs,
        }

