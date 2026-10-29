"""Pytest Suite for LLM Integration, XAI Prompting, and Fallback."""

import pytest
from llm import OllamaClient


class TestLLMIntegration:
    """Verifies Ollama client health checks, grounded prompt structure, and fallback."""

    def test_build_prompt_contains_evidence_and_constraints(self):
        client = OllamaClient()
        flagged_item = {
            "transaction_id": "EXP-999",
            "employee_id": "EMP-42",
            "date": "2026-10-15",
            "category": "Meals",
            "amount": 2500.0,
            "status": "Needs Review",
            "rule_triggered": "Category Limit Exceeded",
            "evidence": "Amount ₹2,500.00 exceeds limit of ₹1,500.00 by ₹1,000.00.",
        }

        prompt = client.build_explanation_prompt(flagged_item)
        assert "EXP-999" in prompt
        assert "EMP-42" in prompt
        assert "Never accuse an employee of fraud" in prompt
        assert "Category Limit Exceeded" in prompt
        assert "Amount ₹2,500.00 exceeds limit" in prompt

    def test_parse_explanation_response(self):
        client = OllamaClient()
        raw_llm = (
            "Explanation: The transaction exceeded the maximum allowed policy limit for meals.\n"
            "Action: Contact the employee to obtain department manager approval."
        )
        expl, act = client._parse_explanation_response(
            raw_llm,
            fallback_explanation="Default expl",
            fallback_action="Default act",
        )
        assert "exceeded the maximum allowed policy limit" in expl
        assert "Contact the employee" in act

    def test_offline_fallback_when_ollama_unreachable(self):
        # Point to unreachable port
        client = OllamaClient(base_url="http://localhost:99999", timeout=1)
        item = {
            "transaction_id": "T1",
            "status": "Needs Review",
            "plain_explanation": "Deterministic template explanation.",
            "recommended_action": "Deterministic template action.",
        }
        res = client.explain_transaction(item)
        assert res["source"] == "deterministic_fallback"
        assert res["explanation"] == "Deterministic template explanation."
        assert res["recommended_action"] == "Deterministic template action."
