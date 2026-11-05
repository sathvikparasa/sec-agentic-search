"""EDGAR MCP server: tools that let an agent answer questions about public
companies from SEC filings, with citations.

There is no LLM in here. The server only retrieves; your agent decides which
tool to call, with what arguments, and writes the answer.
"""

from __future__ import annotations

import asyncio  # noqa: F401  (stage 2)
import re  # noqa: F401  (stage 1)

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from edgar_mcp import db
from edgar_mcp.calllog import logged
from edgar_mcp.embed import MODEL_NAME, embed_query  # noqa: F401  (embed_query: stage 2)

mcp = MCPServer(
    "edgar",
    instructions=(
        "Tools over SEC EDGAR data for ~40 US-listed tech companies: XBRL financial facts "
        "(query_financials) and the text of 10-K and S-1 filings. "
        "Cite fact ids / chunk ids and filing URLs in answers."
    ),
)

MAX_ROWS = 200  # stage 1: cap on rows returned by query_financials


class NotBuiltYet(ToolError, NotImplementedError):
    """Raised by the stubs. A ToolError, so the calling agent sees the message."""


@mcp.tool()
@logged
async def ping() -> dict:
    """Check that the server and database are up. Returns table row counts and the embedding model."""
    _, rows, _ = await db.fetch(
        "SELECT (SELECT count(*) FROM companies), (SELECT count(*) FROM filings), "
        "(SELECT count(*) FROM facts), (SELECT count(*) FROM chunks)"
    )
    companies, filings, facts, chunks = rows[0]
    return {
        "status": "ok",
        "counts": {"companies": companies, "filings": filings, "facts": facts, "chunks": chunks},
        "embedding_model": MODEL_NAME,
    }


@mcp.tool()
@logged
async def query_financials(sql: str) -> dict:
    """TODO (stage 1): run a read-only SQL query over the XBRL financial facts.

    This docstring is what the calling agent reads to decide when and how to use the tool, so
    replace it with one written for that reader. See CLAUDE.md -> "Stage 1" for the contract and
    the data quirks it should warn about.
    """
    raise NotBuiltYet("query_financials isn't built yet. See CLAUDE.md, Stage 1.")


@mcp.tool()
@logged
async def search_filings(
    query: str,
    ticker: str | None = None,
    form: str | None = None,
    section: str | None = None,
    top_k: int = 8,
) -> dict:
    """TODO (stage 2): hybrid keyword + vector search over 10-K and S-1 text.

    Replace this docstring with one written for the calling agent: what's searchable, the
    filters, what comes back, and when NOT to use it. See CLAUDE.md -> "Stage 2".
    Helpers you'll want: embed_query(query) and db.fetch(sql, params).
    """
    raise NotBuiltYet("search_filings isn't built yet. See CLAUDE.md, Stage 2.")


@mcp.tool()
@logged
async def get_section(
    ticker: str,
    form: str,
    section: str,
    fy: int | None = None,
) -> dict:
    """TODO (stage 3, optional): return the full text of one section of one filing, capped.

    See CLAUDE.md -> "Stage 3".
    """
    raise NotBuiltYet("get_section isn't built yet. See CLAUDE.md, Stage 3.")
