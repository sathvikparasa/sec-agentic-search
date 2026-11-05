"""Deterministic grading for evals/run.py. The LLM judge at the bottom is OPTIONAL."""

from __future__ import annotations

import os
import re

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://mcp_reader:mcp_reader@db:5432/edgar")


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("$", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _close(a, b, tol):
    a, b = _num(a), _num(b)
    if a is None or b is None:
        return False
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tol


def _value_part(parsed):
    if not isinstance(parsed, dict):
        return None
    ans = parsed.get("answer")
    if isinstance(ans, dict) and "value" in ans:
        return ans["value"]
    return ans


def _tickers(x) -> list[str]:
    if isinstance(x, str):
        x = re.split(r"[,\s]+", x)
    if not isinstance(x, list):
        return []
    out = []
    for t in x:
        if isinstance(t, dict):
            t = t.get("ticker") or next(iter(t.values()), "")
        out.append(str(t).strip().upper())
    return out


def _mentions(text: str, groups: list[list[str]]) -> bool:
    low = (text or "").lower()
    return all(any(alt.lower() in low for alt in group) for group in groups)


def _ids(parsed, key) -> list[int]:
    if not isinstance(parsed, dict):
        return []
    out = []
    for v in parsed.get(key) or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return out


def _fetch(sql, ids):
    if not ids:
        return []
    with psycopg.connect(DSN) as conn:
        return conn.execute(sql, (ids,)).fetchall()


def _value_strings(v: float) -> list[str]:
    """How a dollar value appears in filing text: in millions or thousands, with commas."""
    out = []
    for div in (1e6, 1e3):
        n = abs(v) / div
        if n >= 1:
            out.append(f"{n:,.0f}")
            if div == 1e6 and n < 100_000:
                out.append(f"{n:,.1f}")
    return out


def _numeric_citation(gold, parsed, run) -> bool:
    support = gold.get("support", [])
    fact_ids = _ids(parsed, "fact_ids")
    rows = _fetch("SELECT id, ticker, value FROM facts WHERE id = ANY(%s)", fact_ids)
    if any(r[0] in {s["fact_id"] for s in support} for r in rows):
        return True
    for r in rows:  # same number under a different (equivalent) fact row
        if any(r[1] == s["ticker"] and _close(r[2], s["value"], 1e-6) for s in support):
            return True
    # chunk citations (baseline): the cited passage must contain a supporting number
    chunks = _fetch("SELECT ticker, text FROM chunks WHERE id = ANY(%s)", _ids(parsed, "chunk_ids"))
    for tk, text in chunks:
        for s in support:
            if tk == s["ticker"] and any(v in text for v in _value_strings(float(s["value"]))):
                return True
    return False


def _text_citation(gold, parsed) -> bool:
    cited = _ids(parsed, "chunk_ids")
    if set(cited) & set(gold.get("gold_chunk_ids", [])):
        return True
    # gold chunk lists are drafts: also accept a cited chunk from the right filing that
    # itself contains every required fact
    rows = _fetch("SELECT ticker, form, text FROM chunks WHERE id = ANY(%s)", cited)
    for tk, form, text in rows:
        if tk == gold.get("ticker") and (not gold.get("form") or form == gold["form"]) \
                and _mentions(text, gold.get("must_mention", [])):
            return True
    return False


def grade(q: dict, parsed, run: dict) -> dict:
    gold, cat = q["gold"], q["category"]
    reply = run.get("reply", "")
    value = _value_part(parsed)
    detail = ""
    if parsed is None:
        return {"correct": False, "citation_valid": False, "detail": "no JSON answer"}

    if cat == "numeric":
        correct = _close(value, gold["value"], gold.get("rel_tol", 0.02))
        cit = _numeric_citation(gold, parsed, run)
        detail = f"got {value} want {gold['value']}"
    elif cat == "ranking":
        n = gold.get("top_n", len(gold["tickers"]))
        got = _tickers(value)[:n]
        correct = got == gold["tickers"][:n]
        cit = _numeric_citation(gold, parsed, run)
        detail = f"got {got} want {gold['tickers'][:n]}"
    elif cat == "text":
        correct = _mentions(reply, gold["must_mention"])
        cit = _text_citation(gold, parsed)
    else:  # hybrid
        if "tickers" in gold:
            n = gold.get("top_n", len(gold["tickers"]))
            v = _tickers(value if isinstance(value, list) else [value] if isinstance(value, str) else value)
            num_ok = v[:n] == gold["tickers"][:n]
        else:
            num_ok = _close(value, gold["value"], gold.get("rel_tol", 0.02))
        text_ok = _mentions(reply, gold["must_mention"])
        correct = num_ok and text_ok
        cit = _numeric_citation(gold, parsed, run) and _text_citation(gold, parsed)
        detail = f"number={'ok' if num_ok else 'wrong'} text={'ok' if text_ok else 'missing'}"
    return {"correct": bool(correct), "citation_valid": bool(cit), "detail": detail}


# ------------------------------------------------------------------ OPTIONAL
JUDGE_MODEL = "claude-sonnet-5-5"


async def judge_text(q: dict, reply: str) -> bool | None:
    """OPTIONAL LLM judge for free-text answers. Reported in its own column, never mixed
    into the deterministic `correct` score."""
    import anthropic
    gold = q["gold"]
    prompt = (f"Question: {q['question']}\n\nReference notes (what a correct answer must convey):\n"
              f"{gold.get('notes', '')}\nRequired points: {gold.get('must_mention')}\n\n"
              f"Candidate answer:\n{reply}\n\nIs the candidate answer correct and consistent with the "
              f"reference? Reply with exactly one word: CORRECT or INCORRECT.")
    resp = await anthropic.AsyncAnthropic().messages.create(
        model=JUDGE_MODEL, max_tokens=2000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if b.type == "text").strip().upper()
    return text.startswith("CORRECT") if text else None
