"""ExpenseGuard AI — Real Model Context Protocol (MCP) Client.

Implements real MCP client integration using the official Python MCP SDK.
Discovers and invokes tools exposed by mcp_server.py over stdio transport.
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

logger = logging.getLogger("ExpenseGuardMCPClient")


class MCPExpenseClient:
    """Real MCP Client connecting to the local ExpenseGuard MCP Server via stdio."""

    def __init__(self, server_script_path: Optional[str] = None):
        if server_script_path is None:
            # Default to mcp_server.py in the same directory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            server_script_path = os.path.join(base_dir, "mcp_server.py")
        self.server_script_path = server_script_path
        self._discovered_tools: List[Dict[str, Any]] = []

    def _get_server_params(self) -> StdioServerParameters:
        """Construct server parameters for stdio process spawning."""
        # Ensure current directory is in PYTHONPATH so sibling modules are found
        env = dict(os.environ)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{base_dir}{os.pathsep}{current_pythonpath}" if current_pythonpath else base_dir
        # Ensure unbuffered stdio
        env["PYTHONUNBUFFERED"] = "1"

        return StdioServerParameters(
            command=sys.executable,
            args=[self.server_script_path],
            env=env,
        )

    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Connect to MCP server, discover available tools, and inspect schemas."""
        server_params = self._get_server_params()
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_response = await session.list_tools()

                self._discovered_tools = []
                for tool in tools_response.tools:
                    tool_info = {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    }
                    self._discovered_tools.append(tool_info)

                return self._discovered_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Invoke a tool on the MCP server and return text result."""
        server_params = self._get_server_params()
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                call_result = await session.call_tool(tool_name, arguments)

                # Extract text content from call_result
                text_parts = []
                if hasattr(call_result, "content"):
                    for content_item in call_result.content:
                        if hasattr(content_item, "text"):
                            text_parts.append(content_item.text)
                        elif isinstance(content_item, str):
                            text_parts.append(content_item)
                        else:
                            text_parts.append(str(content_item))
                return "".join(text_parts)

    async def run_full_pipeline(
        self,
        records: List[Dict[str, Any]],
        category_limits: Optional[Dict[str, float]] = None,
        receipt_threshold: float = 500.0,
    ) -> Dict[str, Any]:
        """Execute all validation tools within a single MCP session for efficiency."""
        server_params = self._get_server_params()
        records_json = json.dumps(records, default=str)
        limits_json = json.dumps(category_limits or {})

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # 1. Discover tools
                tools_response = await session.list_tools()
                discovered_names = [t.name for t in tools_response.tools]

                # 2. Check missing fields
                missing_res = await session.call_tool("check_missing_fields", {"records_json": records_json})
                missing_text = "".join([c.text for c in missing_res.content if hasattr(c, "text")])

                # 3. Check duplicates
                dup_res = await session.call_tool("check_duplicate_expenses", {"records_json": records_json})
                dup_text = "".join([c.text for c in dup_res.content if hasattr(c, "text")])

                # 4. Check amounts and category limits
                amount_res = await session.call_tool("validate_expense_amounts", {
                    "records_json": records_json,
                    "limits_json": limits_json,
                })
                amount_text = "".join([c.text for c in amount_res.content if hasattr(c, "text")])

                # 5. Check receipts
                receipt_res = await session.call_tool("check_receipt_status", {
                    "records_json": records_json,
                    "threshold": receipt_threshold,
                })
                receipt_text = "".join([c.text for c in receipt_res.content if hasattr(c, "text")])

                # 6. Generate summary
                summary_res = await session.call_tool("generate_expense_summary", {
                    "records_json": records_json,
                    "limits_json": limits_json,
                })
                summary_text = "".join([c.text for c in summary_res.content if hasattr(c, "text")])

                return {
                    "discovered_tools": discovered_names,
                    "missing_fields": json.loads(missing_text) if missing_text else {},
                    "duplicates": json.loads(dup_text) if dup_text else {},
                    "amounts": json.loads(amount_text) if amount_text else {},
                    "receipts": json.loads(receipt_text) if receipt_text else {},
                    "summary": json.loads(summary_text) if summary_text else {},
                }


class SyncMCPExpenseClient:
    """Synchronous interface for MCP client, ideal for Streamlit and simple scripts."""

    def __init__(self, server_script_path: Optional[str] = None):
        self.async_client = MCPExpenseClient(server_script_path)

    def _run_async(self, coro):
        """Run coroutine handling nested event loops if necessary."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # In an already running loop (such as some async servers), use nest_asyncio or thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(asyncio.run, coro).result()
            return result
        else:
            return loop.run_until_complete(coro)

    def discover_tools(self) -> List[Dict[str, Any]]:
        """Synchronously discover tools from MCP server."""
        return self._run_async(self.async_client.discover_tools())

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Synchronously invoke an MCP tool."""
        return self._run_async(self.async_client.call_tool(tool_name, arguments))

    def run_full_pipeline(
        self,
        records: List[Dict[str, Any]],
        category_limits: Optional[Dict[str, float]] = None,
        receipt_threshold: float = 500.0,
    ) -> Dict[str, Any]:
        """Synchronously execute full MCP validation pipeline."""
        return self._run_async(
            self.async_client.run_full_pipeline(
                records=records,
                category_limits=category_limits,
                receipt_threshold=receipt_threshold,
            )
        )
