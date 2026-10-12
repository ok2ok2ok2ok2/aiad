#!/usr/bin/env python3
"""AIAD MCP server (stdio).

Lets an MCP client (Claude Desktop, Claude Code, ...) search AIAD product data
and receive it together with evidence levels, sponsorship and the agent rules.

Run:
    python mcp/server.py [--data DIR] [--vocab PATH] [--now ISO]

Environment variables AIAD_DATA_DIR / AIAD_VOCAB override the defaults
(<repo>/examples and <repo>/vocab/categories.json). AIAD_NOW / --now pins the
clock (ISO 8601) for demos and tests; default is the real current time.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import aiad_index  # noqa: E402

try:  # MCP Python SDK 2.x
    from mcp.server import MCPServer as _Server
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

VERSION = "0.1.0"

INSTRUCTIONS = (
    "AIAD product data with trust metadata. Always call get_agent_rules once before "
    "recommending products, and follow the presentation_rules returned with every search. "
    "Paid offers are only in 'sponsored'; never mix them into your own ranking."
)

_state: dict[str, Any] = {"data_dir": None, "vocab": None, "index": None, "now": None}


def _index():
    if _state["index"] is None:
        _state["index"] = aiad_index.load_index(_state["data_dir"], vocab_path=_state["vocab"],
                                                 now=_state["now"])
    return _state["index"]


server = _Server("aiad", instructions=INSTRUCTIONS)


@server.tool()
def search_offers(query: Optional[str] = None, category: Optional[str] = None,
                  region: Optional[str] = None, max_price: Optional[str] = None,
                  currency: Optional[str] = None,
                  needs: Optional[list[str]] = None) -> dict:
    """Search products. All filters are optional.

    query: words that must all appear (title, summary, specs, suitable_for).
    category: a category key from list_categories, e.g. "power_bank".
    region: ISO code such as "US", "CA", "TW-NAN".
    max_price + currency: price ceiling as a decimal string, e.g. "300" + "USD".
    needs: the user's needs and constraints in their own words, e.g.
           ["I use Android", "father uses a wheelchair"]; used to flag not_suitable_for conflicts.

    Returns organic 'results' and a separate 'sponsored' list (paid placements),
    plus 'presentation_rules' you must follow.
    """
    try:
        return aiad_index.search(_index(), query=query, category=category, region=region,
                                 max_price=max_price, currency=currency, needs=needs,
                                 now=_state["now"])
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool()
def get_offer(issuer_domain: str, offer_id: str) -> dict:
    """Get one offer by the publisher's domain and the offer id."""
    result = aiad_index.get_offer(_index(), issuer_domain, offer_id, now=_state["now"])
    if result is None:
        return {"error": "offer not found or no longer valid"}
    return {"offer": result, "presentation_rules": aiad_index.PRESENTATION_RULES}


@server.tool()
def list_categories() -> dict:
    """List product categories with their canonical spec keys/units and standard test protocols."""
    return aiad_index.list_categories(_state["vocab"])


@server.tool()
def get_agent_rules() -> str:
    """The AIAD Agent Rules: three core rules, rules A1-A8 and a drop-in system prompt."""
    return aiad_index.agent_rules(os.path.join(ROOT, "AGENT_RULES.md"))


@server.tool()
def index_status(reload: bool = False) -> dict:
    """Show which data files were loaded and which were rejected by the validator (and why).

    reload: re-read the data directory first.
    """
    if reload:
        _state["index"] = None
    st = aiad_index.status(_index())
    st["data_dir"] = _state["data_dir"]
    return st


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="AIAD MCP server (stdio)")
    ap.add_argument("--data", default=os.environ.get("AIAD_DATA_DIR", os.path.join(ROOT, "examples")))
    ap.add_argument("--vocab", default=os.environ.get("AIAD_VOCAB", os.path.join(ROOT, "vocab", "categories.json")))
    ap.add_argument("--now", default=os.environ.get("AIAD_NOW"),
                    help="pin the clock, ISO 8601 (e.g. 2026-10-12T12:00:00Z)")
    ap.add_argument("--version", action="version", version=f"aiad-mcp {VERSION}")
    args = ap.parse_args(argv)
    _state["data_dir"] = os.path.abspath(args.data)
    _state["vocab"] = os.path.abspath(args.vocab)
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        _state["now"] = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    server.run()  # stdio


if __name__ == "__main__":
    main()
