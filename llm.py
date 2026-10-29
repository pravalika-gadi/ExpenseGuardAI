"""ExpenseGuard AI — Local LLM Integration Module via Ollama.

Provides local inference using open-source models (e.g. Llama 3.2 3B).
Adheres strictly to Explainable AI (XAI) principles:
- Grounded solely on deterministic tool evidence.
- Transparent, non-judgmental explanations.
- Actionable recommendations for human finance reviewers.
- Graceful offline fallback if Ollama or the model is unavailable.
"""

import sys
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple

from config import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OLLAMA_REQUEST_TIMEOUT_SECONDS,
)

logger = logging.getLogger("ExpenseGuardLLM")


class OllamaClient:
    """Client for local open-source LLM inference via Ollama."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: int = OLLAMA_REQUEST_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def check_health(self) -> Tuple[bool, str, List[str]]:
        """Check if Ollama service is reachable and list downloaded models.

        Returns:
            (is_available, status_message, list_of_models)
        """
        try:
            url = f"{self.base_url}/api/tags"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                if self.model in models or any(self.model in m for m in models):
                    return True, f"Ollama is online and '{self.model}' is ready.", models
                else:
                    return (
                        True,
                        f"Ollama is online, but model '{self.model}' was not found. Available: {', '.join(models) if models else 'None'}",
                        models,
                    )
            return False, f"Ollama returned HTTP status {resp.status_code}", []
        except requests.exceptions.ConnectionError:
            return False, f"Could not connect to Ollama at {self.base_url}. Service may be stopped.", []
        except Exception as e:
            return False, f"Ollama health check failed: {str(e)}", []

    def build_explanation_prompt(self, item: Dict[str, Any]) -> str:
        """Construct grounded, constrained prompt for XAI generation."""
        return (
            "You are an AI assistant helping a corporate finance audit team review expense submissions.\n"
            "Analyze the flagged transaction below using ONLY the provided facts and evidence.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Do NOT invent or assume facts not present in the evidence.\n"
            "2. Never accuse an employee of fraud, dishonesty, or misconduct. Label items as 'Needs Review'.\n"
            "3. Provide two distinct sections:\n"
            "   - 'Explanation': A clear, 1-2 sentence plain-language description of why this requires attention.\n"
            "   - 'Action': A single concrete, objective next step for the human reviewer.\n\n"
            "TRANSACTION DETAILS:\n"
            f"- Transaction ID: {item.get('transaction_id')}\n"
            f"- Employee ID: {item.get('employee_id')}\n"
            f"- Date: {item.get('date')}\n"
            f"- Category: {item.get('category')}\n"
            f"- Amount: ₹{item.get('amount')}\n"
            f"- Status: {item.get('status')}\n"
            f"- Triggered Rule: {item.get('rule_triggered')}\n"
            f"- Deterministic Evidence: {item.get('evidence')}\n\n"
            "Format your response as:\n"
            "Explanation: <clear explanation>\n"
            "Action: <recommended action>"
        )

    def explain_transaction(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an explainable AI justification for a single flagged item.

        Falls back gracefully to template-based deterministic explanations
        if Ollama is unavailable or inference fails.
        """
        # If already passed or no flags, return clean deterministic summary
        if item.get("status") in ["Valid", "Passed"]:
            return {
                "source": "deterministic",
                "explanation": item.get("plain_explanation", "Transaction complies with organizational policy."),
                "recommended_action": item.get("recommended_action", "Ready for human reviewer sign-off."),
            }

        prompt = self.build_explanation_prompt(item)

        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Low temperature for factual consistency
                    "num_predict": 150,   # Compact response
                },
            }
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                raw_text = resp.json().get("response", "").strip()
                explanation, action = self._parse_explanation_response(
                    raw_text,
                    fallback_explanation=item.get("plain_explanation", ""),
                    fallback_action=item.get("recommended_action", ""),
                )
                return {
                    "source": f"local_llm ({self.model})",
                    "explanation": explanation,
                    "recommended_action": action,
                    "raw_response": raw_text,
                }
            else:
                logger.warning(f"Ollama returned HTTP {resp.status_code}, falling back to deterministic explanation.")
        except Exception as e:
            logger.warning(f"Ollama inference unavailable ({e}), using deterministic fallback.")

        # Deterministic fallback
        return {
            "source": "deterministic_fallback",
            "explanation": item.get("plain_explanation", "Transaction flagged by audit rules."),
            "recommended_action": item.get("recommended_action", "Review transaction documentation."),
        }

    def generate_audit_summary(
        self, summary: Dict[str, Any], flagged_items: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate an executive-level audit synthesis of the entire expense report.

        Uses local LLM inference if Ollama is online, or generates a factual deterministic
        summary when offline.
        """
        total_rec = summary.get("total_records", 0)
        total_amt = summary.get("total_amount", 0.0)
        pass_cnt = summary.get("passing_count", 0)
        flag_cnt = summary.get("flagged_count", 0)
        flag_amt = summary.get("flagged_amount", 0.0)
        comp_rate = summary.get("compliance_rate", 100.0)
        dups = summary.get("duplicates_count", 0)
        missing_rcpt = summary.get("missing_receipts_count", 0)
        limit_over = summary.get("policy_limit_exceeded_count", 0)

        fallback_text = (
            f"ExpenseGuard AI audited {total_rec} transactions claimed for a total of ₹{total_amt:,.2f}. "
            f"{pass_cnt} items ({comp_rate}% compliance rate) satisfied all organizational expenditure policies. "
            f"{flag_cnt} items (totaling ₹{flag_amt:,.2f}) require human reviewer verification "
            f"due to policy limits ({limit_over}), missing receipts ({missing_rcpt}), or potential duplicates ({dups})."
        )

        prompt = (
            "You are an expert corporate finance auditor summarizing an expense verification report.\n"
            "Generate a professional, concise executive summary (2-3 sentences) based strictly on these verified metrics:\n"
            f"- Total Transactions: {total_rec}\n"
            f"- Total Claimed Amount: ₹{total_amt:,.2f}\n"
            f"- Passed Checks: {pass_cnt} ({comp_rate}% compliance rate)\n"
            f"- Flagged for Review: {flag_cnt} items (Totaling ₹{flag_amt:,.2f})\n"
            f"- Violations Breakdown: Duplicates={dups}, Missing Receipts={missing_rcpt}, Limit Caps Exceeded={limit_over}\n\n"
            "Rules:\n"
            "1. Ground entirely in the figures provided.\n"
            "2. Never accuse anyone of fraud or make final reimbursement decisions.\n"
            "3. State facts objectively for the human finance manager.\n"
            "Return only the concise executive summary text."
        )

        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 180,
                },
            }
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                raw_text = resp.json().get("response", "").strip()
                if raw_text and len(raw_text) > 20:
                    return {
                        "source": f"local_llm ({self.model})",
                        "summary_text": raw_text,
                    }
        except Exception:
            pass

        return {
            "source": "deterministic_synthesis",
            "summary_text": fallback_text,
        }

    def _parse_explanation_response(
        self,
        raw_text: str,
        fallback_explanation: str,
        fallback_action: str,
    ) -> Tuple[str, str]:
        """Extract explanation and action from LLM response text."""
        explanation = ""
        action = ""

        lines = raw_text.splitlines()
        for line in lines:
            cleaned = line.strip()
            if cleaned.lower().startswith("explanation:"):
                explanation = cleaned[len("explanation:"):].strip()
            elif cleaned.lower().startswith("action:"):
                action = cleaned[len("action:"):].strip()

        if not explanation:
            explanation = raw_text if raw_text else fallback_explanation
        if not action:
            action = fallback_action

        return explanation, action
