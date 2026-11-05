"""Stage 2: companyfacts -> normalized, deduplicated us-gaap facts.

Quirks handled:
- The same fact (concept, unit, period) appears in every later filing that repeats
  it as a comparative. We keep ONE row per (cik, concept, unit, start, end): the
  most recently filed value (so restatements win).
- `fy`/`fp` in companyfacts describe the FILING, not the period. After dedupe a
  FY2020 value usually carries fy=2022. We keep fy/fp raw and derive
  `fiscal_year` from the fact's own end date and the company's fiscal year end.
- `period_type`: instant (no start date: balance-sheet items), annual
  (~1 year), quarterly (~3 months). Other durations (6/9-month YTD, odd
  transition periods) are dropped and counted in the report.
- `frame` (calendar alignment like CY2023, CY2023Q4I) is assigned by the SEC to
  just one of the duplicate records, so we keep it from whichever duplicate has it.
- Only facts from periodic financial reports count (10-K, 10-Q, 10-KT and amendments).
  Proxy statements (DEF 14A / PRE 14A) carry "pay versus performance" XBRL tables that
  re-report net income, sometimes rounded or on another basis, and are filed AFTER the
  10-K, so without this filter "latest filed wins" would pick the proxy's number
  (Coinbase FY2023 net income would read exactly $100,000,000 instead of $94,871,000).
- Revenue tags are NOT normalized here (see the `revenue` view in schema.sql).
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from scripts.fetch.edgar_client import EdgarClient
from scripts.fetch.fetch import FACTS

BUILD = Path("data/build")
FINANCIAL_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A"}


def fye_date(year: int, mmdd: str) -> dt.date:
    m, d = int(mmdd[:2]), int(mmdd[2:])
    if m == 2 and d == 29:
        d = 28
    return dt.date(year, m, d)


def fiscal_year_of(end: dt.date, mmdd: str) -> int:
    """Fiscal year (named by the calendar year it ends in) that `end` falls in.

    52/53-week years end within a few days of the nominal date, so an end date
    within 7 days of any fiscal year end belongs to that year (handles e.g. a
    year that nominally ends Dec 31 but actually ended Jan 2).
    """
    for y in (end.year - 1, end.year, end.year + 1):
        if abs((end - fye_date(y, mmdd)).days) <= 7:
            return y
    return end.year if end <= fye_date(end.year, mmdd) else end.year + 1


def period_type(start: str | None, end: str) -> str | None:
    if not start:
        return "instant"
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    if 350 <= days <= 380:
        return "annual"
    if 80 <= days <= 100:
        return "quarterly"
    return None


def build_company(cf: dict, cik: int, ticker: str, mmdd: str, stats: Counter) -> list[dict]:
    best: dict[tuple, dict] = {}
    frames: dict[tuple, str] = {}
    for concept, body in cf.get("facts", {}).get("us-gaap", {}).items():
        for unit, entries in body.get("units", {}).items():
            for e in entries:
                stats["raw"] += 1
                if e.get("form") not in FINANCIAL_FORMS:
                    stats["dropped_non_financial_form"] += 1
                    continue
                start, end = e.get("start"), e["end"]
                ptype = period_type(start, end)
                if ptype is None:
                    stats["dropped_other_duration"] += 1
                    continue
                key = (concept, unit, start, end)
                if e.get("frame"):
                    frames[key] = e["frame"]
                cur = best.get(key)
                # latest filed wins; tie-break on accession for determinism
                if cur is None or (e["filed"], e["accn"]) > (cur["filed"], cur["accn"]):
                    if cur is not None:
                        stats["duplicates_removed"] += 1
                    best[key] = {**e, "_ptype": ptype}
                else:
                    stats["duplicates_removed"] += 1
    rows = []
    for (concept, unit, start, end), e in best.items():
        rows.append({
            "cik": cik, "ticker": ticker, "concept": concept, "unit": unit,
            "value": e["val"], "fy": e.get("fy"), "fp": e.get("fp"), "form": e.get("form"),
            "filed": e["filed"], "start_date": start, "end_date": end,
            "frame": frames.get((concept, unit, start, end)), "accession": e["accn"],
            "fiscal_year": fiscal_year_of(dt.date.fromisoformat(end), mmdd),
            "period_type": e["_ptype"],
        })
    return rows


def main() -> None:
    client = EdgarClient()
    companies = json.loads((BUILD / "companies.json").read_text())
    stats: Counter = Counter()
    out = []
    for c in companies:
        cf = client.get_json(FACTS.format(cik=c["cik"]))
        rows = build_company(cf, c["cik"], c["ticker"], c["fiscal_year_end"], stats)
        print(f"{c['ticker']:5} {len(rows):7d} facts")
        out += rows
    stats["kept"] = len(out)
    with open(BUILD / "facts.jsonl", "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    (BUILD / "facts_stats.json").write_text(json.dumps(stats, indent=2))
    print(dict(stats))


if __name__ == "__main__":
    main()
