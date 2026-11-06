"""EDGAR MCP server: tools that let an agent answer questions about public
companies from SEC filings, with citations.

There is no LLM in here. The server only retrieves; your agent decides which
tool to call, with what arguments, and writes the answer.
"""

from __future__ import annotations

import asyncio
import re

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from edgar_mcp import db
from edgar_mcp.calllog import logged
from edgar_mcp.embed import MODEL_NAME, embed_query

mcp = MCPServer(
    "edgar",
    instructions=(
        "Tools over SEC EDGAR data for ~40 US-listed tech companies: XBRL financial facts "
        "(query_financials) and the text of 10-K and S-1 filings (search_filings, get_section). "
        "Cite fact ids / chunk ids and filing URLs in answers."
    ),
)

MAX_ROWS = 200


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
      revenue(cik, ticker, period_type, fiscal_year, start_date, end_date, frame, value, unit,
              source_concept, fact_id, accession, filed)

    How facts work
    - One row per company, concept, unit and period, already deduplicated: when a value was reported
      in several filings, the most recent filing's value is kept (so restatements win).
    - concept: a us-gaap XBRL tag, exact and case-sensitive. Common: NetIncomeLoss, GrossProfit,
      OperatingIncomeLoss, ResearchAndDevelopmentExpense, Assets, Liabilities, StockholdersEquity,
      CashAndCashEquivalentsAtCarryingValue, NetCashProvidedByUsedInOperatingActivities,
      EarningsPerShareDiluted. Not sure of a tag? Look it up:
      SELECT DISTINCT concept FROM facts WHERE ticker = 'ABNB' AND concept ILIKE '%income%'.
    - REVENUE: use the `revenue` view, not facts. Companies tag revenue with different concepts
      (Revenues, RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet, ...) and some
      switched tags over time. The view picks one per company and period. Querying a single revenue
      tag silently drops companies from rankings. source_concept shows which tag was used; cite
      fact_id.
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
    - Citing: select f.id (or revenue.fact_id) and accession; the filing's link is filings.url.

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


FORMS = {"10k": "10-K", "10-k": "10-K", "s1": "S-1", "s-1": "S-1", "424b4": "S-1"}
SECTIONS = {
    "business": "business", "item 1": "business",
    "risk_factors": "risk_factors", "risk factors": "risk_factors", "risks": "risk_factors",
    "item 1a": "risk_factors",
    "mda": "mda", "md&a": "mda", "item 7": "mda",
    "management's discussion and analysis": "mda",
}


def _norm(value: str | None, table: dict, what: str) -> str | None:
    if value is None or value == "":
        return None
    key = value.strip().lower().replace("_", " ") if what == "section" else value.strip().lower()
    key = key if key in table else key.replace(" ", "_")
    if key not in table:
        raise ToolError(f"Unknown {what} {value!r}. Use one of: {sorted(set(table.values()))}")
    return table[key]


SEARCH_SQL = """
WITH tsq AS (
    -- keyword side: OR the query's terms together (plain AND would demand every word)
    SELECT replace(plainto_tsquery('english', %(qtext)s)::text, '&', '|')::tsquery AS q
), vec AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank
    FROM chunks
    WHERE {where}
    ORDER BY embedding <=> %(qvec)s::vector
    LIMIT 50
), kw AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, tsq.q) DESC) AS rank
    FROM chunks, tsq
    WHERE tsv @@ tsq.q AND {where}
    ORDER BY ts_rank_cd(tsv, tsq.q) DESC
    LIMIT 50
), fused AS (
    SELECT id, sum(1.0 / (60 + rank)) AS score
    FROM (SELECT * FROM vec UNION ALL SELECT * FROM kw) AS both_lists
    GROUP BY id
    ORDER BY score DESC
    LIMIT %(top_k)s
)
SELECT c.id AS chunk_id, c.ticker, c.form, c.filed, c.section, c.accession, f.url,
       round(fused.score::numeric, 5) AS score, c.text
FROM fused
JOIN chunks c USING (id)
JOIN filings f ON f.accession = c.accession
ORDER BY fused.score DESC
"""


@mcp.tool()
@logged
async def search_filings(
    query: str,
    ticker: str | None = None,
    form: str | None = None,
    section: str | None = None,
    top_k: int = 8,
) -> dict:
    """Search the text of 10-K annual reports and S-1 IPO prospectuses. Hybrid search: keyword
    (full-text) and semantic (vector) results merged with reciprocal rank fusion.

    Use for WORDS, not numbers: risks, strategy, business model, competition, regulation, what
    management credits for results, what a company said at its IPO. Do NOT use it for numbers,
    rankings or trends. Passages are a handful of excerpts, not the data; use query_financials.

    What's searchable
    - 10-K: the 3 latest annual reports per company. Sections 'business' (Item 1),
      'risk_factors' (Item 1A), 'mda' (Item 7, management's discussion and analysis of results).
    - S-1: the final IPO prospectus, for companies that went public in 2015 or later (ABNB, DASH,
      SNOW, COIN, RBLX, UBER, ...). Sections 'business' and 'risk_factors'.
    - Not included: 10-Qs, 8-Ks, financial statement notes, S-1 MD&A.

    Args
      query: what you're looking for, in plain words. Specific beats broad:
             "independent contractor classification of Dashers" beats "risks".
      ticker: e.g. 'DASH'. Use it whenever the question is about one company.
      form: '10-K' or 'S-1'.
      section: 'business', 'risk_factors' or 'mda'.
      top_k: number of passages (default 8, max 20).

    Returns {results: [{chunk_id, ticker, form, filed, section, accession, url, score, text}]},
    best first. Each passage is ~400 words. Cite chunk_id and url. Several narrow searches beat
    one broad one; if results look off-topic, rephrase or add filters. To read around a passage,
    use get_section.
    """
    top_k = max(1, min(int(top_k), 20))
    where, params = ["true"], {}
    if ticker:
        where.append("ticker = %(ticker)s")
        params["ticker"] = ticker.strip().upper()
    if (f := _norm(form, FORMS, "form")):
        where.append("form = %(form)s")
        params["form"] = f
    if (s := _norm(section, SECTIONS, "section")):
        where.append("section = %(section)s")
        params["section"] = s
    params |= {"qvec": await asyncio.to_thread(embed_query, query), "qtext": query, "top_k": top_k}
    cols, rows, _ = await db.fetch(SEARCH_SQL.format(where=" AND ".join(where)), params)
    results = [dict(zip(cols, r)) for r in rows]
    out = {"results": results}
    if not results:
        out["note"] = "No passages matched. Check the ticker/form/section filters (S-1s exist only for 2015+ IPOs; S-1s have no 'mda')."
    return out


PAGE_CHARS = 20_000


@mcp.tool()
@logged
async def get_section(
    ticker: str,
    form: str,
    section: str,
    fy: int | None = None,
    offset: int = 0,
) -> dict:
    """Read the full text of one section of one filing, a page (up to 20,000 characters) at a time.

    Use it after search_filings when a passage isn't enough: to read the context around it, or to
    read a whole discussion (e.g. how MD&A explains a year's revenue growth). Sections are long
    (often 50k-300k characters), so locate with search_filings first and read only what you need.

    Args
      ticker: e.g. 'ABNB'.
      form: '10-K' or 'S-1'.
      section: 'business', 'risk_factors' or 'mda' ('mda' exists for 10-Ks only).
      fy: fiscal year of the 10-K (default: the latest one). Ignored for S-1.
      offset: character offset to start reading from; pass next_offset from the previous call.

    Returns {ticker, form, original_form, fiscal_year, filed, section, accession, url,
    total_chars, offset, next_offset, text}. next_offset is null when you've reached the end.
    Cite the accession and url.
    """
    f = _norm(form, FORMS, "form")
    s = _norm(section, SECTIONS, "section")
    params = {"ticker": ticker.strip().upper(), "form": f, "section": s}
    year_filter = ""
    if fy is not None and f == "10-K":
        year_filter = "AND fl.fiscal_year = %(fy)s"
        params["fy"] = int(fy)
    cols, rows, _ = await db.fetch(
        f"""SELECT fl.ticker, fl.form, fl.original_form, fl.fiscal_year, fl.filed, s.section,
                   fl.accession, fl.url, length(s.text) AS total_chars,
                   substr(s.text, %(start)s, {PAGE_CHARS}) AS text
            FROM sections s JOIN filings fl USING (accession)
            WHERE fl.ticker = %(ticker)s AND fl.form = %(form)s AND s.section = %(section)s {year_filter}
            ORDER BY fl.filed DESC LIMIT 1""",
        params | {"start": max(0, int(offset)) + 1},
    )
    if not rows:
        _, avail, _ = await db.fetch(
            "SELECT fl.form, fl.fiscal_year, s.section FROM sections s JOIN filings fl USING (accession) "
            "WHERE fl.ticker = %(ticker)s ORDER BY fl.filed DESC", params)
        if not avail:
            raise ToolError(f"No filings for ticker {params['ticker']!r}.")
        listing = ", ".join(f"{a[0]} fy={a[1]} {a[2]}" for a in avail)
        raise ToolError(f"No such section. Available for {params['ticker']}: {listing}")
    out = dict(zip(cols, rows[0]))
    end = max(0, int(offset)) + len(out["text"])
    out["offset"] = max(0, int(offset))
    out["next_offset"] = end if end < out["total_chars"] else None
    return out
