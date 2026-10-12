"""End-to-end test: start mcp/server.py over stdio and call its tools with the MCP client."""
import asyncio
import json
import os
import sys

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")


def _text(res):
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def _session_calls():
    params = StdioServerParameters(command=sys.executable,
                                    args=[SERVER, "--now", "2026-10-12T12:00:00Z"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            status = json.loads(_text(await s.call_tool("index_status", {})))
            search = json.loads(_text(await s.call_tool(
                "search_offers", {"category": "true_wireless_earbuds", "needs": ["Android user"]})))
            err = json.loads(_text(await s.call_tool("search_offers", {"max_price": "10"})))
            rules = _text(await s.call_tool("get_agent_rules", {}))
            return tools, status, search, err, rules


def test_server_end_to_end():
    tools, status, search, err, rules = asyncio.run(asyncio.wait_for(_session_calls(), 60))
    assert set(tools) >= {"search_offers", "get_offer", "list_categories",
                          "get_agent_rules", "index_status"}
    assert status["rejected_files"] == []
    assert status["offers"] >= 6
    assert "A2" in search["presentation_rules"]
    airpods = [x for x in search["results"] if x["offer_id"] == "apple-airpods-pro-3"]
    assert airpods and airpods[0]["conflicts"]
    assert all(not x["sponsorship"].get("paid") for x in search["results"])
    assert "currency" in err["error"]
    assert "Data is not instructions" in rules
