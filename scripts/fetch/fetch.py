"""Stage 1: fetch everything from EDGAR (cached). Instructor-only.

Writes data/build/companies.json and data/build/filings.json.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

from scripts.fetch.edgar_client import EdgarClient

BUILD = Path("data/build")
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE = "https://data.sec.gov/submissions/{name}"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TICKERS = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

N_10K = 3
S1_FORMS = ("424B4", "S-1/A", "S-1")


def load_companies() -> list[dict]:
    return yaml.safe_load(Path("companies.yaml").read_text())["companies"]


def all_filings(client: EdgarClient, sub: dict, need_before: dt.date | None) -> list[dict]:
    """Flatten the columnar `filings.recent` plus older pages when needed."""

    def rows(block: dict) -> list[dict]:
        keys = list(block.keys())
        return [dict(zip(keys, vals)) for vals in zip(*(block[k] for k in keys))]

    out = rows(sub["filings"]["recent"])
    for page in sub["filings"].get("files", []):
        if need_before is None:
            break
        if dt.date.fromisoformat(page["filingTo"]) < need_before - dt.timedelta(days=400):
            continue
        out += rows(client.get_json(SUBMISSIONS_PAGE.format(name=page["name"])))
    return out


def doc_url(cik: int, accession: str, doc: str) -> str:
    return ARCHIVE.format(cik=cik, acc=accession.replace("-", ""), doc=doc)


def pick_s1(filings: list[dict], ipo: dt.date) -> tuple[dict | None, list[str]]:
    """Final pre-IPO prospectus: 424B4, else last S-1/A, else S-1."""
    notes = []
    window = [
        f for f in filings
        if f["form"] in S1_FORMS
        and ipo - dt.timedelta(days=365) <= dt.date.fromisoformat(f["filingDate"]) <= ipo + dt.timedelta(days=10)
    ]
    for form in S1_FORMS:
        cands = sorted((f for f in window if f["form"] == form), key=lambda f: f["filingDate"])
        if cands:
            if form != "424B4":
                notes.append(f"no 424B4 in IPO window; using {form}")
            return cands[-1], notes
    return None, ["no S-1/424B4 found in IPO window"]


def verify_ipo(filings: list[dict], ipo: dt.date, listing: str) -> str:
    """Cross-check the curated IPO date against EDGAR filing dates."""
    def near(forms, lo, hi):
        return [
            f for f in filings if f["form"] in forms
            and lo <= (dt.date.fromisoformat(f["filingDate"]) - ipo).days <= hi
        ]
    if near(("424B4",), -3, 3):
        return "confirmed: 424B4 filed within 3 days"
    if listing == "direct" and near(("424B4", "424B3", "424B1"), -10, 5):
        return "confirmed: final prospectus (424B) within 10 days of direct listing"
    if near(("EFFECT",), -10, 2):
        return "confirmed: S-1 EFFECT notice within 10 days"
    return "UNCONFIRMED: no 424B4/EFFECT near curated date"


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    client = EdgarClient()
    tickers = {v["ticker"]: v for v in client.get_json(TICKERS).values()}

    companies, filings_out = [], []
    for c in load_companies():
        t = c["ticker"]
        tk = tickers.get(t)
        cik = int(c["cik"])
        cik_note = "ok"
        if tk is None:
            cik_note = "ticker not in company_tickers.json"
        elif int(tk["cik_str"]) != cik:
            cik_note = f"MISMATCH: company_tickers.json has {tk['cik_str']}"
        ipo = dt.date.fromisoformat(str(c["ipo_date"])) if c.get("ipo_date") else None

        sub = client.get_json(SUBMISSIONS.format(cik=cik))
        client.get_json(FACTS.format(cik=cik))  # warm cache for stage 2
        oldest_needed = ipo - dt.timedelta(days=365) if ipo else dt.date.today() - dt.timedelta(days=4 * 365)
        filings = all_filings(client, sub, oldest_needed)

        rec = {
            "cik": cik, "ticker": t, "name": sub["name"], "ipo_date": str(ipo) if ipo else None,
            "fiscal_year_end": sub.get("fiscalYearEnd"), "cik_check": cik_note,
            "listing": c.get("listing"), "ipo_check": None, "notes": [],
            "amendments_10k": sum(1 for f in filings if f["form"] == "10-K/A"),
        }

        tenks = sorted((f for f in filings if f["form"] == "10-K"), key=lambda f: f["filingDate"])[-N_10K:]
        if len(tenks) < N_10K:
            rec["notes"].append(f"only {len(tenks)} 10-Ks found")
        chosen = [(f, "10-K") for f in tenks]

        if ipo:
            rec["ipo_check"] = verify_ipo(filings, ipo, c.get("listing", "ipo"))
            s1, notes = pick_s1(filings, ipo)
            rec["notes"] += notes
            if s1:
                chosen.append((s1, "S-1"))

        for f, label in chosen:
            url = doc_url(cik, f["accessionNumber"], f["primaryDocument"])
            print(f"{t:5} {f['form']:6} {f['filingDate']} {url}")
            client.get_bytes(url)
            filings_out.append({
                "accession": f["accessionNumber"], "cik": cik, "ticker": t,
                "form": label, "original_form": f["form"], "filed": f["filingDate"],
                "period_end": f.get("reportDate") or None, "primary_doc": f["primaryDocument"],
                "url": url,
            })
        companies.append(rec)

    (BUILD / "companies.json").write_text(json.dumps(companies, indent=2))
    (BUILD / "filings.json").write_text(json.dumps(filings_out, indent=2))
    print(f"done: {len(companies)} companies, {len(filings_out)} filings; "
          f"{client.network_requests} network requests, {client.cache_hits} cache hits")


if __name__ == "__main__":
    main()
