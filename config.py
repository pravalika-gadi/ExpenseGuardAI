"""Configuration settings for ExpenseGuard AI.

Defines default category policy limits, mandatory columns, receipt requirements,
Ollama LLM settings, and configuration helper classes.
"""

import os
from typing import Dict, List, Any
from dataclasses import dataclass, field


# Default maximum allowed amounts per category in INR (₹)
DEFAULT_CATEGORY_LIMITS: Dict[str, float] = {
    "Meals": 1500.0,
    "Travel": 10000.0,
    "Lodging": 15000.0,
    "Software": 8000.0,
    "Office Supplies": 3000.0,
    "Entertainment": 2500.0,
    "Miscellaneous": 2000.0,
}

# Expenses equal to or exceeding this threshold strictly require a valid receipt
DEFAULT_RECEIPT_THRESHOLD: float = 500.0

# Mandatory fields required in every valid expense record
MANDATORY_FIELDS: List[str] = [
    "transaction_id",
    "employee_id",
    "date",
    "category",
    "description",
    "amount",
    "receipt_attached",
]

# Standard column aliases for flexible CSV/Excel header matching
COLUMN_ALIASES: Dict[str, List[str]] = {
    "transaction_id": ["transaction_id", "transaction id", "tx_id", "txn_id", "id", "expense_id"],
    "employee_id": ["employee_id", "employee id", "emp_id", "staff_id"],
    "date": ["date", "expense_date", "txn_date", "transaction_date"],
    "category": ["category", "expense_category", "type", "expense_type"],
    "description": ["description", "details", "purpose", "item_description", "notes"],
    "amount": ["amount", "expense_amount", "total", "cost", "value"],
    "receipt_attached": ["receipt_attached", "receipt attached", "receipt", "has_receipt", "receipt_status"],
}

# Ollama local LLM settings
DEFAULT_OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_REQUEST_TIMEOUT_SECONDS: int = int(os.environ.get("OLLAMA_TIMEOUT", "20"))


@dataclass
class ExpenseGuardConfig:
    """Dynamic configuration object for runtime settings."""
    category_limits: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CATEGORY_LIMITS))
    receipt_threshold: float = DEFAULT_RECEIPT_THRESHOLD
    mandatory_fields: List[str] = field(default_factory=lambda: list(MANDATORY_FIELDS))
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_timeout: int = OLLAMA_REQUEST_TIMEOUT_SECONDS
    claimed_total: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "category_limits": self.category_limits,
            "receipt_threshold": self.receipt_threshold,
            "mandatory_fields": self.mandatory_fields,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "ollama_timeout": self.ollama_timeout,
            "claimed_total": self.claimed_total,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpenseGuardConfig":
        """Construct configuration from dictionary."""
        return cls(
            category_limits=data.get("category_limits", dict(DEFAULT_CATEGORY_LIMITS)),
            receipt_threshold=float(data.get("receipt_threshold", DEFAULT_RECEIPT_THRESHOLD)),
            mandatory_fields=data.get("mandatory_fields", list(MANDATORY_FIELDS)),
            ollama_base_url=data.get("ollama_base_url", DEFAULT_OLLAMA_BASE_URL),
            ollama_model=data.get("ollama_model", DEFAULT_OLLAMA_MODEL),
            ollama_timeout=int(data.get("ollama_timeout", OLLAMA_REQUEST_TIMEOUT_SECONDS)),
            claimed_total=float(data.get("claimed_total", 0.0)),
        )
