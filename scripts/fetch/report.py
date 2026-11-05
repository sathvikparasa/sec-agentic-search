"""Stage 7: data report -> data/report.md (companies, filings, facts, chunks, failures)."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

BUILD = Path("data/build")
DSN = os.environ.get("BUILD_DSN", "postgresql://postgres:postgres@localhost:5432/edgar")
REVENUE_LIKE = "concept ILIKE '%revenue%' OR concept ILIKE 'SalesRevenue%'"


def main() -> None:
    companies = json.loads((BUILD / "companies.json").read_text())
    log = json.loads((BUILD / "extraction_log.json").read_text())
    stats = json.loads((BUILD / "facts_stats.json").read_text())
    chunk_stats = json.loads((BUILD / "chunk_stats.json").read_text())
    L = ["# Data report", ""]

    with psycopg.connect(DSN) as conn:
        q = lambda sql, *a: conn.execute(sql, a or None).fetchall()
        L += ["## Counts", "", "| table | rows |", "|---|---|"]
        for t in ("companies", "filings", "facts", "chunks"):
            L.append(f"| {t} | {q(f'SELECT count(*) FROM {t}')[0][0]:,} |")
        L += ["", f"Facts: {stats['raw']:,} raw us-gaap records -> {stats['kept']:,} after dedupe "
              f"({stats['duplicates_removed']:,} duplicates removed, "
              f"{stats['dropped_other_duration']:,} non-annual/non-quarterly durations dropped, "
              f"{stats.get('dropped_non_financial_form', 0):,} records from non-10-K/10-Q forms (proxies, S-1s, 8-Ks) dropped).",
              f"Chunks: mean {chunk_stats['mean_tokens']:.0f} tokens, max {chunk_stats['max_tokens']}, "
              f"{chunk_stats['total_tokens']:,} tokens in total (bge WordPiece count).", ""]
        fy = q("SELECT min(fiscal_year), max(fiscal_year) FROM facts WHERE period_type='annual'")[0]
        L += [f"Annual facts span fiscal years {fy[0]}–{fy[1]}.", ""]

        L += ["## Filings per company", "", "| ticker | name | FYE | 10-Ks (filed) | S-1 (original form) | IPO check | notes |",
              "|---|---|---|---|---|---|---|"]
        by = defaultdict(list)
        for row in q("SELECT ticker, form, original_form, filed FROM filings ORDER BY filed"):
            by[row[0]].append(row)
        for c in companies:
            tk = ", ".join(str(r[3]) for r in by[c["ticker"]] if r[1] == "10-K")
            s1 = ", ".join(f"{r[3]} ({r[2]})" for r in by[c["ticker"]] if r[1] == "S-1")
            notes = "; ".join(c["notes"] + ([f"CIK {c['cik_check']}"] if c["cik_check"] != "ok" else [])
                              + ([f"{c['amendments_10k']} 10-K/A on file"] if c["amendments_10k"] else []))
            L.append(f"| {c['ticker']} | {c['name']} | {c['fiscal_year_end']} | {tk} | {s1 or '—'} | "
                     f"{c['ipo_check'] or '—'} | {notes} |")

        fails = [r for r in log if not r["ok"]]
        L += ["", f"## Section extraction: {len(log) - len(fails)}/{len(log)} succeeded", ""]
        by_sec = Counter((r["form"], r["section"], r["ok"]) for r in log)
        for (form, sec) in sorted({(f, s) for f, s, _ in by_sec}):
            ok, bad = by_sec[(form, sec, True)], by_sec[(form, sec, False)]
            L.append(f"- {form} {sec}: {ok} ok, {bad} failed")
        if fails:
            L += ["", "| ticker | form | filed | section | reason | url |", "|---|---|---|---|---|---|"]
            for r in fails:
                L.append(f"| {r['ticker']} | {r['original_form']} | {r['filed']} | {r['section']} | "
                         f"{r['status']} | {r['url']} |")

        L += ["", "## Revenue tags in the data (annual, USD)", "",
              "Which revenue-like us-gaap concepts each company used. Feeds the `revenue` view.", "",
              "| concept | companies | fiscal years |", "|---|---|---|"]
        for concept, n, lo, hi in q(
            f"SELECT concept, count(DISTINCT ticker), min(fiscal_year), max(fiscal_year) FROM facts "
            f"WHERE ({REVENUE_LIKE}) AND period_type='annual' AND unit='USD' "
            f"GROUP BY concept HAVING count(DISTINCT ticker) >= 3 ORDER BY 2 DESC"):
            L.append(f"| {concept} | {n} | {lo}–{hi} |")
        L += ["", "Revenue view coverage, latest annual period per company:", "",
              "| ticker | fiscal_year | source_concept | value |", "|---|---|---|---|"]
        for t, fy_, src, v in q(
            "SELECT DISTINCT ON (ticker) ticker, fiscal_year, source_concept, value FROM revenue "
            "WHERE period_type='annual' ORDER BY ticker, end_date DESC"):
            L.append(f"| {t} | {fy_} | {src} | {v:,.0f} |")
        missing = q("SELECT ticker FROM companies WHERE ticker NOT IN (SELECT ticker FROM revenue)")
        if missing:
            L.append(f"\n**No revenue in view for:** {', '.join(m[0] for m in missing)}")

    Path("data/report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
