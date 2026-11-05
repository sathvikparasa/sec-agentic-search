"""Stage 3: strip HTML/iXBRL and extract key sections. Instructor-only.

10-K: business (Item 1), risk_factors (Item 1A), mda (Item 7)
S-1:  business (BUSINESS), risk_factors (RISK FACTORS)

Strategy: render the document to lines of text, find every line that looks
like the section's heading, and for each candidate take the text up to the
next heading that ends the section. The table of contents produces short
candidates, the real section the longest one, so we keep the longest.
Every attempt is logged to data/build/extraction_log.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import lxml.html
from lxml import etree

from scripts.fetch.edgar_client import EdgarClient

BUILD = Path("data/build")
MIN_CHARS = {"business": 3000, "risk_factors": 8000, "mda": 5000}
MAX_CHARS = 1_500_000

BLOCK = {
    "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "section", "article", "ul", "ol", "center", "pre", "blockquote",
}
CELL = {"td", "th"}


def _hidden(el) -> bool:
    style = (el.get("style") or "").replace(" ", "").lower()
    return "display:none" in style


# Page furniture repeated at every page break: page numbers, "Table of Contents" links.
PAGE_NOISE = re.compile(r"^(?:\d{1,3}|[ivx]{1,5}|page \d{1,3}|table of contents|index)$", re.I)


def html_to_lines(raw: bytes) -> list[str]:
    parser = lxml.html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    try:
        root = lxml.html.fromstring(raw, parser=parser)
    except (etree.ParserError, ValueError):
        return []
    # Drop inline-XBRL header (hidden facts), scripts, styles and hidden blocks.
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if tag in ("script", "style", "head", "title", "ix:header") or _hidden(el):
            el.drop_tree()

    parts: list[str] = []

    def walk(el):
        tag = el.tag.split("}")[-1].lower() if isinstance(el.tag, str) else ""
        if tag in BLOCK:
            parts.append("\n")
        if el.text and isinstance(el.tag, str):
            parts.append(el.text)
        for child in el:
            walk(child)
        if tag in CELL:
            parts.append(" | ")
        elif tag in BLOCK:
            parts.append("\n")
        if el.tail:
            parts.append(el.tail)

    walk(root)
    text = "".join(parts).replace("\xa0", " ").replace("​", "")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        line = re.sub(r"(\s*\|\s*)+$", "", line)          # trailing cell separators
        line = re.sub(r"^(\s*\|\s*)+", "", line)
        line = re.sub(r"(\s*\|\s*){2,}", " | ", line)
        if line and not PAGE_NOISE.match(line):
            lines.append(line)
    return lines


# Heading patterns are matched against the START of a line.
I = re.IGNORECASE
def item(n: str) -> re.Pattern:
    # "Item 1.", "ITEM 1 -", "Item 1: Business", "Item 1 | Business". Not 1A/10/1B.
    return re.compile(rf"^item\s*{n}(?![0-9a-z])\s*[\.\:\-–—|]?", I)


TENK = {
    "business": (item("1"), [item("1a"), item("2")]),
    "risk_factors": (item("1a"), [item("1b"), item("1c"), item("2")]),
    "mda": (item("7"), [item("7a"), item("8")]),
}

SMALL = {"and", "of", "the", "in", "for", "to", "on", "or", "a", "an"}


def exact(*titles: str) -> re.Pattern:
    """Whole-line heading match, case-SENSITIVE over the casings headings use
    (UPPER, Title Case, Sentence case), no trailing period: so body text like
    "...harm our business." can't start a section."""
    variants = set()
    for t in titles:
        words = t.lower().split()
        title = " ".join(w if w in SMALL and i else w[:1].upper() + w[1:] for i, w in enumerate(words))
        variants |= {t.upper(), title, " ".join(w[:1].upper() + w[1:] for w in words),
                     t[0].upper() + t[1:].lower()}
    alts = "|".join(re.escape(v).replace(r"\ ", r"\s+") for v in sorted(variants))
    return re.compile(rf"^(?:{alts})$")

S1_AFTER_RISK = exact(
    "special note regarding forward-looking statements", "special note regarding forward looking statements",
    "cautionary note regarding forward-looking statements", "forward-looking statements",
    "market, industry, and other data", "market, industry and other data", "market and industry data",
    "industry and market data", "use of proceeds", "letter from our founders", "dividend policy",
)
S1_AFTER_BUSINESS = exact(
    "management", "executive officers and directors", "executive officers, key employees and directors",
    "executive compensation", "certain relationships and related party transactions",
    "principal stockholders", "principal and selling stockholders", "description of capital stock",
)
S1 = {
    "risk_factors": (exact("risk factors"), [S1_AFTER_RISK]),
    "business": (exact("business"), [S1_AFTER_BUSINESS]),
}

# Companies whose 10-K doesn't use "Item N." headings. Intel uses its own
# layout (plus a cross-reference index) with titles repeated as page headers;
# the longest-candidate rule still finds the real sections.
MDA_INTC = exact("management's discussion and analysis", "management\u2019s discussion and analysis")
TENK_OVERRIDES = {
    # 2024-25 layout: "Fundamentals of Our Business" / MD&A / "Risk Factors and Other Key
    # Information" (risk factors, then Sales and Marketing, Properties, ...).
    # 2026 layout: "Our Business" / MD&A / "Risk Factors" / "Other Key Information".
    "INTC": {
        "business": (exact("our business", "fundamentals of our business"), [MDA_INTC]),
        "mda": (MDA_INTC, [exact("risk factors", "risk factors and other key information")]),
        "risk_factors": (exact("risk factors"), [exact(
            "other key information", "sales and marketing", "properties",
            "quantitative and qualitative disclosures about market risk")]),
    },
}


def extract_section(lines: list[str], start_pat, end_pats, min_chars: int):
    starts = [i for i, l in enumerate(lines) if start_pat.search(l)]
    if not starts:
        return None, "start heading not found"
    best = None
    for s in starts:
        e = next((j for j in range(s + 1, len(lines)) if any(p.search(lines[j]) for p in end_pats)), None)
        if e is None:
            continue
        body = "\n".join(lines[s:e])
        if best is None or len(body) > len(best):
            best = body
    if best is None:
        return None, f"{len(starts)} start(s) found but no end heading after any"
    if len(best) < min_chars:
        return None, f"longest candidate only {len(best)} chars (< {min_chars})"
    if len(best) > MAX_CHARS:
        return None, f"candidate implausibly long ({len(best)} chars)"
    return best, "ok"


def main() -> None:
    client = EdgarClient()
    filings = json.loads((BUILD / "filings.json").read_text())
    log, sections = [], []
    for f in filings:
        raw = client.get_bytes(f["url"])
        lines = html_to_lines(raw)
        spec = (TENK_OVERRIDES.get(f["ticker"], TENK) if f["form"] == "10-K" else S1)
        for name, (start, ends) in spec.items():
            text, status = extract_section(lines, start, ends, MIN_CHARS[name])
            log.append({
                "ticker": f["ticker"], "form": f["form"], "original_form": f["original_form"],
                "filed": f["filed"], "accession": f["accession"], "section": name,
                "ok": text is not None, "status": status, "chars": len(text or ""), "url": f["url"],
            })
            mark = "ok  " if text else "FAIL"
            print(f"{mark} {f['ticker']:5} {f['form']:4} {f['filed']} {name:13} {status}")
            if text:
                sections.append({"accession": f["accession"], "section": name, "text": text})
    (BUILD / "extraction_log.json").write_text(json.dumps(log, indent=2))
    with open(BUILD / "sections.jsonl", "w") as out:
        for s in sections:
            out.write(json.dumps(s) + "\n")
    ok = sum(r["ok"] for r in log)
    print(f"extracted {ok}/{len(log)} sections")


if __name__ == "__main__":
    main()
