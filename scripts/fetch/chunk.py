"""Stage 4: cut sections into chunks. Instructor-only. (Embedding is stage 5, embed_chunks.py.)

- ~700 tokens per chunk (target; mean lands in 500-800) (WordPiece tokens, counted with the vendored chunk_tokenizer.json,
  the bge-small tokenizer), with ~100 tokens of overlap.
- Chunks never cross section boundaries (we chunk one section at a time).
- Each chunk also gets an `embed_text`: a short header ("Airbnb, Inc. (ABNB) S-1 risk
  factors") plus the chunk, so company/form identity is in the vector too. The stored
  `text` is the chunk alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tokenizers import Tokenizer

BUILD = Path("data/build")
TARGET, OVERLAP = 700, 100
SECTION_TITLE = {"business": "business", "risk_factors": "risk factors", "mda": "MD&A"}

_tok = Tokenizer.from_file(str(Path(__file__).with_name("chunk_tokenizer.json")))
_tok.no_truncation()


def ntok(s: str) -> int:
    return len(_tok.encode(s, add_special_tokens=False).ids)


def split_long(par: str) -> list[str]:
    """Split a paragraph longer than TARGET into sentence groups (then hard cuts)."""
    sents = re.split(r"(?<=[.;:!?])\s+", par)
    out, cur, cur_n = [], [], 0
    for s in sents:
        n = ntok(s)
        if n > TARGET:  # a single giant "sentence" (usually a table row run): cut by tokens
            enc = _tok.encode(s, add_special_tokens=False)
            for i in range(0, len(enc.offsets), TARGET):
                seg = enc.offsets[i:i + TARGET]
                out.append(s[seg[0][0]:seg[-1][1]])
            continue
        if cur_n + n > TARGET and cur:
            out.append(" ".join(cur))
            cur, cur_n = [], 0
        cur.append(s)
        cur_n += n
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_section(text: str) -> list[str]:
    pars = []
    for p in text.split("\n"):
        pars += split_long(p) if ntok(p) > TARGET else [p]
    sizes = [ntok(p) + 1 for p in pars]
    chunks, i = [], 0
    while i < len(pars):
        j, n = i, 0
        while j < len(pars) and (n + sizes[j] <= TARGET or j == i):
            n += sizes[j]
            j += 1
        chunks.append("\n".join(pars[i:j]))
        if j >= len(pars):
            break
        # step back to create ~OVERLAP tokens of overlap, but always advance
        k, back = j, 0
        while k - 1 > i and back + sizes[k - 1] <= OVERLAP:
            k -= 1
            back += sizes[k]
        i = k
    return chunks


def main() -> None:
    filings = {f["accession"]: f for f in json.loads((BUILD / "filings.json").read_text())}
    companies = {c["ticker"]: c for c in json.loads((BUILD / "companies.json").read_text())}
    rows = []
    with open(BUILD / "sections.jsonl") as fh:
        for line in fh:
            s = json.loads(line)
            f = filings[s["accession"]]
            header = f"{companies[f['ticker']]['name']} ({f['ticker']}) {f['form']} {SECTION_TITLE[s['section']]}"
            for idx, text in enumerate(chunk_section(s["text"])):
                rows.append({
                    "id": len(rows) + 1, "accession": f["accession"], "cik": f["cik"],
                    "ticker": f["ticker"], "form": f["form"], "filed": f["filed"],
                    "section": s["section"], "chunk_index": idx, "text": text,
                    "embed_text": header + "\n" + text,
                })
    toks = [ntok(r["text"]) for r in rows]
    with open(BUILD / "chunks.jsonl", "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    stats = {"chunks": len(rows), "mean_tokens": sum(toks) / max(len(toks), 1),
             "max_tokens": max(toks, default=0), "total_tokens": sum(toks)}
    (BUILD / "chunk_stats.json").write_text(json.dumps(stats, indent=2))
    print(stats)


if __name__ == "__main__":
    main()
