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

MAX_ROWS = 200


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
    """Run a read-only SQL query (PostgreSQL) over the financial facts companies reported to the SEC (XBRL).

    Use this for NUMBERS: revenue, net income, margins, assets, cash, share counts; rankings and
    comparisons across companies; trends over time. Never estimate a number from filing text.

    Tables
      facts(id, cik, ticker, concept, unit, value, period_type, fiscal_year, start_date, end_date,
            frame, fy, fp, form, filed, accession)
      companies(cik, ticker, name, ipo_date, fiscal_year_end)
      filings(accession, cik, ticker, form, original_form, filed, period_end, fiscal_year, url)

    How facts work
    - One row per company, concept, unit and period, already deduplicated: when a value was reported
      in several filings, the most recent filing's value is kept (so restatements win).
    - concept: a us-gaap XBRL tag, exact and case-sensitive. Common: NetIncomeLoss, GrossProfit,
      OperatingIncomeLoss, ResearchAndDevelopmentExpense, Assets, Liabilities, StockholdersEquity,
      CashAndCashEquivalentsAtCarryingValue, NetCashProvidedByUsedInOperatingActivities,
      EarningsPerShareDiluted. Not sure of a tag? Look it up:
      SELECT DISTINCT concept FROM facts WHERE ticker = 'ABNB' AND concept ILIKE '%income%'.
    - period_type: 'annual' (a fiscal year), 'quarterly' (3 months) or 'instant' (balance-sheet
      value at one date; start_date is NULL). Always filter on it or you'll mix annual and quarterly
      values. Q4 is rarely reported on its own: Q4 = annual - (Q1 + Q2 + Q3).
    - fiscal_year: the company's fiscal year the period belongs to. USE THIS for years. Fiscal years
      often differ from calendar years: NVDA's fiscal 2025 ended in January 2025, MSFT's fiscal year
      ends in June, AAPL's in September (see companies.fiscal_year_end, MMDD). To line companies up
      by calendar period use frame ('CY2024', 'CY2024Q3', 'CY2024Q4I' for instants); frame can be NULL.
    - fy / fp are NOT the period's year. They describe the filing that last reported the value, so a
      fiscal 2020 number repeated in a 2022 10-K has fy = 2022. Don't filter on fy.
    - unit: 'USD' (raw dollars, not thousands or millions), 'USD/shares' (per share), 'shares',
      'pure' (ratios). Filter on unit when comparing values.
    - Citing: select f.id and accession; the filing's link is filings.url.

    Limits: one SELECT (or WITH) statement; read-only; 5 s timeout; at most 200 rows come back,
    so aggregate, ORDER BY and LIMIT in SQL.

    Example: Airbnb's annual net income
      SELECT fiscal_year, value, id, accession FROM facts
      WHERE ticker = 'ABNB' AND concept = 'NetIncomeLoss' AND period_type = 'annual' AND unit = 'USD'
      ORDER BY fiscal_year;

    Returns {columns, rows, row_count, truncated, note}.
    """
    stripped = re.sub(r"(--[^\n]*|/\*.*?\*/)", " ", sql, flags=re.S).strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", stripped):
        raise ToolError("Only a single SELECT (or WITH ... SELECT) query is allowed.")
    if ";" in stripped:
        raise ToolError("Only one statement is allowed; remove the extra ';'.")
    cols, rows, more = await db.fetch(stripped, max_rows=MAX_ROWS)
    out = {"columns": cols, "rows": rows, "row_count": len(rows), "truncated": more}
    if more:
        out["note"] = (f"Result truncated to the first {MAX_ROWS} rows. Aggregate, filter, "
                       f"or ORDER BY ... LIMIT in SQL to get what you need.")
    return out


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
