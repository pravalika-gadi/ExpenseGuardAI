"""ExpenseGuard AI — Real Model Context Protocol (MCP) Server.

Exposes deterministic expense validation tools via the official Python MCP SDK.
Runs as a stdio server or in-process callable service.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

from mcp.server.mcpserver import MCPServer

import validators
from config import DEFAULT_CATEGORY_LIMITS, DEFAULT_RECEIPT_THRESHOLD

# Configure logging to stderr to prevent interfering with stdio transport
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("ExpenseGuardMCPServer")

server = MCPServer(
    name="expenseguard-mcp-server",
    version="1.0.0",
    instructions="Official MCP server providing deterministic validation tools for employee expense reports.",
)


@server.tool()
def read_expense_report(file_path: str) -> str:
    """Read an expense report file (CSV or Excel) from disk and parse records.

    Args:
        file_path: Absolute or relative path to CSV or Excel file.

    Returns:
        JSON string containing row_count, column_names, and parsed records.
    """
    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "status": "error",
                "message": f"File not found at path: {file_path}",
                "records": [],
            })

        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif ext == ".csv":
            df = pd.read_csv(file_path)
        else:
            return json.dumps({
                "status": "error",
                "message": f"Unsupported file extension '{ext}'. Must be .csv, .xlsx, or .xls",
                "records": [],
            })

        # Replace NaN with None so JSON serialization works cleanly
        records = df.where(pd.notnull(df), None).to_dict(orient="records")

        return json.dumps({
            "status": "success",
            "file_name": os.path.basename(file_path),
            "row_count": len(records),
            "columns": list(df.columns),
            "records": records,
        }, default=str)
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e),
            "records": [],
        })


@server.tool()
def check_missing_fields(records_json: str) -> str:
    """Validate mandatory fields across all expense records.

    Args:
        records_json: JSON string representing list of expense records.

    Returns:
        JSON string of flagged records with missing mandatory fields and evidence.
    """
    try:
        records = json.loads(records_json)
        flagged = validators.check_missing_fields(records)
        return json.dumps({
            "status": "success",
            "flagged_count": len(flagged),
            "flagged_items": flagged,
        })
    except Exception as e:
        logger.error(f"Error in check_missing_fields: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e), "flagged_items": []})


@server.tool()
def check_duplicate_expenses(records_json: str) -> str:
    """Identify exact and potential duplicate transactions across expense records.

    Args:
        records_json: JSON string representing list of expense records.

    Returns:
        JSON string of duplicate records with matching references and evidence.
    """
    try:
        records = json.loads(records_json)
        flagged = validators.check_duplicate_expenses(records)
        return json.dumps({
            "status": "success",
            "flagged_count": len(flagged),
            "flagged_items": flagged,
        })
    except Exception as e:
        logger.error(f"Error in check_duplicate_expenses: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e), "flagged_items": []})


@server.tool()
def validate_expense_amounts(records_json: str, limits_json: str = "{}") -> str:
    """Validate numeric amounts, positive values, non-future dates, and category caps.

    Args:
        records_json: JSON string representing list of expense records.
        limits_json: Optional JSON string of category limits overrides.

    Returns:
        JSON string of records violating amount policies or category caps.
    """
    try:
        records = json.loads(records_json)
        category_limits = dict(DEFAULT_CATEGORY_LIMITS)
        if limits_json and limits_json.strip() and limits_json.strip() != "{}":
            custom_limits = json.loads(limits_json)
            category_limits.update({k: float(v) for k, v in custom_limits.items()})

        flagged = validators.validate_expense_amounts(records, category_limits)
        return json.dumps({
            "status": "success",
            "flagged_count": len(flagged),
            "flagged_items": flagged,
        })
    except Exception as e:
        logger.error(f"Error in validate_expense_amounts: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e), "flagged_items": []})


@server.tool()
def check_receipt_status(records_json: str, threshold: float = DEFAULT_RECEIPT_THRESHOLD) -> str:
    """Flag expenses requiring receipts that are missing verification.

    Args:
        records_json: JSON string representing list of expense records.
        threshold: Minimum amount threshold requiring receipt verification.

    Returns:
        JSON string of flagged records missing required receipts.
    """
    try:
        records = json.loads(records_json)
        flagged = validators.check_receipt_status(records, receipt_threshold=float(threshold))
        return json.dumps({
            "status": "success",
            "flagged_count": len(flagged),
            "flagged_items": flagged,
        })
    except Exception as e:
        logger.error(f"Error in check_receipt_status: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e), "flagged_items": []})


@server.tool()
def generate_expense_summary(records_json: str, limits_json: str = "{}") -> str:
    """Calculate overall financial summary and compliance metrics.

    Args:
        records_json: JSON string representing list of expense records.
        limits_json: Optional JSON string of category limits.

    Returns:
        JSON string of summary statistics, compliance rates, and breakdowns.
    """
    try:
        records = json.loads(records_json)
        category_limits = dict(DEFAULT_CATEGORY_LIMITS)
        if limits_json and limits_json.strip() and limits_json.strip() != "{}":
            custom_limits = json.loads(limits_json)
            category_limits.update({k: float(v) for k, v in custom_limits.items()})

        summary = validators.generate_expense_summary(records, category_limits=category_limits)
        return json.dumps({
            "status": "success",
            "summary": summary,
        })
    except Exception as e:
        logger.error(f"Error in generate_expense_summary: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e), "summary": {}})


def run_stdio():
    """Run the MCP server over stdio for child process integration."""
    logger.info("Starting ExpenseGuard MCP server on stdio transport...")
    server.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
