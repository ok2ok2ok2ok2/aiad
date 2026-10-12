# AIAD MCP server

Try AIAD with Claude (or any MCP client). The server loads AIAD files, validates them, and
lets an AI assistant search products. Every answer comes with evidence levels, sponsorship
and the [AIAD Agent Rules](../AGENT_RULES.md).

## Install

```bash
pip install "mcp>=1.2" "jsonschema>=4.18"
```

Works with MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`).

## Run

```bash
python mcp/server.py                     # serves ./examples over stdio
python mcp/server.py --data path/to/dir  # your own *.ai-ads.json / *.ai-reviews.json files
```

Environment variables `AIAD_DATA_DIR` and `AIAD_VOCAB` work too.

### Claude Code

```bash
claude mcp add aiad -- python /absolute/path/to/aiad/mcp/server.py --now 2026-10-12T12:00:00Z
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aiad": {
      "command": "python",
      "args": ["/absolute/path/to/aiad/mcp/server.py"]
    }
  }
}
```

On Windows use a path like `C:\\path\\to\\aiad\\mcp\\server.py`.

## Tools

| Tool | What it does |
|---|---|
| `search_offers` | Filter by `query`, `category`, `region`, `max_price` + `currency`; pass the user's `needs` to flag `not_suitable_for` conflicts. Returns organic `results`, a separate `sponsored` list, and `presentation_rules`. |
| `get_offer` | One offer by publisher domain + offer id. |
| `list_categories` | Canonical spec keys/units and standard test protocols per category. |
| `get_agent_rules` | The three rules, rules A1–A8, and a drop-in system prompt. |
| `index_status` | Which files loaded and which the validator rejected, and why (`reload: true` re-reads the folder). |

## Try asking

- "I use Android and switch between my phone and laptop. Which noise-cancelling earbuds?"
- "I need a power bank I can take on a plane that charges a 140 W laptop."
- "My father uses a wheelchair. Weekday room near Cingjing under 3000 TWD?" (the paid listing is withheld because of a conflict)
- "Why is that offer labelled sponsored?"

## How the rules are enforced

- **Rejected files.** A file with any validator error is not served at all. This includes
  text aimed at the AI ("ignore previous instructions…"), not only the offending sentence (rule A6).
- **Paid placement is separated.** Paid offers are never in `results` and never affect its order (rule A2).
- **Conflicts.** If an offer's `not_suitable_for` matches the user's needs, the offer gets a
  `conflicts` entry and sinks to the bottom. A paid offer with a conflict is withheld and
  counted in `sponsored_withheld` (rule A4).
- **Expiry.** Expired offers and claims are dropped at query time.
- **Claim wording.** Each claim carries `say_as` text worded by its evidence level (rule A3).

## Limitations

- Conflict detection is a naive keyword overlap: English words of 3+ letters and Chinese
  character bigrams. It misses paraphrases ("wheelchair" vs "no lift") and can over-match
  common words. The agent must still read `not_suitable_for` itself.
- Search is substring matching, not semantic search.
- Data is loaded from local files. There is no crawler, account system or review collection yet.
  See [SPEC.md](../SPEC.md) for the planned platform.
