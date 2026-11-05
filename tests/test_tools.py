"""Smoke tests: every tool, called through the real MCP server over HTTP.

Tools that are still stubs on the current branch are skipped, so this runs on every branch
and passes in full on stage-3.

    docker compose run --rm app smoke        (or: docker compose exec app pytest -q tests)
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from mcp import Client

MCP_URL = os.environ.get("MCP_URL", "http://mcp:8000/mcp")


def call(name: str, args: dict | None = None):
    async def go():
        async with Client(MCP_URL) as c:
            return await c.call_tool(name, args or {})
    res = asyncio.run(go())
    if res.is_error and res.content and "isn't built yet" in getattr(res.content[0], "text", ""):
        pytest.skip(f"{name} is still a stub on this branch")
    payload = res.structured_content
    if payload is None and res.content:
        text = res.content[0].text
        try:
            payload = json.loads(text)
        except ValueError:
            payload = text
    return res.is_error, payload


def tools() -> set[str]:
    async def go():
        async with Client(MCP_URL) as c:
            return {t.name for t in (await c.list_tools()).tools}
    return asyncio.run(go())


def test_tools_listed():
    assert {"ping", "query_financials", "search_filings", "get_section"} <= tools()


def test_ping():
    err, out = call("ping")
    assert not err and out["status"] == "ok" and out["counts"]["companies"] == 40


# ---- query_financials ----

def test_query_financials_net_income():
    err, out = call("query_financials", {"sql": (
        "SELECT fiscal_year, value, id FROM facts WHERE ticker='ABNB' AND concept='NetIncomeLoss' "
        "AND period_type='annual' AND unit='USD' ORDER BY fiscal_year")})
    assert not err, out
    years = {r[0]: r[1] for r in out["rows"]}
    assert 2020 in years and years[2020] < 0          # Airbnb lost money in its IPO year
    assert max(years) >= 2024 and years[max(years)] > 0


def test_query_financials_row_cap():
    err, out = call("query_financials", {"sql": "SELECT id FROM facts"})
    assert not err
    assert out["row_count"] == 200 and out["truncated"] and "truncated" in out["note"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM facts",
    "SELECT 1; DROP TABLE facts",
    "CREATE TABLE x (y int)",
    "WITH d AS (DELETE FROM facts RETURNING *) SELECT count(*) FROM d",
])
def test_query_financials_is_read_only(sql):
    err, out = call("query_financials", {"sql": sql})
    assert err, f"write was not rejected: {sql}"


def test_query_financials_timeout():
    err, out = call("query_financials", {"sql": "SELECT pg_sleep(10)"})
    assert err and "timeout" in str(out).lower()


def test_revenue_view_covers_every_company():
    err, out = call("query_financials", {"sql": (
        "SELECT count(DISTINCT ticker) FROM revenue WHERE period_type='annual'")})
    assert not err and out["rows"][0][0] == 40


# ---- search_filings ----

def test_search_filings_filters_and_citations():
    err, out = call("search_filings", {"query": "independent contractor classification of Dashers",
                                       "ticker": "DASH", "form": "S-1"})
    assert not err, out
    res = out["results"]
    assert 1 <= len(res) <= 8
    for r in res:
        assert r["ticker"] == "DASH" and r["form"] == "S-1"
        assert r["url"].startswith("https://www.sec.gov/Archives/") and r["chunk_id"] and r["accession"]
    assert any("contractor" in r["text"].lower() for r in res)


def test_search_filings_section_alias_and_top_k():
    err, out = call("search_filings", {"query": "revenue growth drivers", "section": "MD&A", "top_k": 3})
    assert not err and len(out["results"]) == 3
    assert all(r["section"] == "mda" for r in out["results"])


def test_search_filings_bad_section():
    err, out = call("search_filings", {"query": "x", "section": "financial statements"})
    assert err


# ---- get_section ----

def test_get_section_paging():
    err, first = call("get_section", {"ticker": "ABNB", "form": "S-1", "section": "risk_factors"})
    assert not err, first
    assert first["total_chars"] > 20_000 and len(first["text"]) == 20_000
    assert first["next_offset"] == 20_000 and first["url"].startswith("https://www.sec.gov/")
    err, second = call("get_section", {"ticker": "ABNB", "form": "S-1", "section": "risk_factors",
                                       "offset": first["next_offset"]})
    assert not err and second["text"] != first["text"]


def test_get_section_fiscal_year():
    err, out = call("get_section", {"ticker": "NVDA", "form": "10-K", "section": "mda", "fy": 2025})
    assert not err, out
    assert out["fiscal_year"] == 2025 and out["form"] == "10-K"


def test_get_section_missing_lists_available():
    err, out = call("get_section", {"ticker": "AAPL", "form": "S-1", "section": "business"})
    assert err and "Available" in str(out)
