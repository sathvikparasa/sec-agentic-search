"""Baseline: classic single-pass RAG. Compare it with your agent.

    docker compose exec app python baseline.py "What risks about its contractors did DoorDash disclose in its S-1?"

One embedding, one vector search (top 5), one LLM call. No SQL, no keyword
search, no second try. That's the point: watch where this breaks.

Provider (optional): set ANTHROPIC_API_KEY or OPENAI_API_KEY in your shell
before `docker compose up`. LLM_PROVIDER=anthropic|openai picks one if both
are set; LLM_MODEL overrides the model (required for OpenAI). With no key,
the script prints the retrieved chunks and a ready-to-paste prompt instead.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import psycopg
from pgvector.psycopg import register_vector

from edgar_mcp.embed import embed_query

DSN = os.environ.get("DATABASE_URL", "postgresql://mcp_reader:mcp_reader@db:5432/edgar")
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
TOP_K = 5

SYSTEM = (
    "You answer questions about public companies using ONLY the SEC filing excerpts provided. "
    "Cite the chunk ids you used like [chunk 123]. If the excerpts don't contain the answer, say so."
)


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    with psycopg.connect(DSN) as conn:
        register_vector(conn)
        conn.execute("SET hnsw.ef_search = 100")
        cur = conn.execute(
            """SELECT c.id, c.ticker, c.form, c.filed, c.section, f.url, c.text,
                      1 - (c.embedding <=> %s::vector) AS similarity
               FROM chunks c JOIN filings f USING (accession)
               ORDER BY c.embedding <=> %s::vector LIMIT %s""",
            (embed_query(question),) * 2 + (k,),
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_prompt(question: str, chunks: list[dict]) -> str:
    parts = [
        f"[chunk {c['id']}] {c['ticker']} {c['form']} filed {c['filed']} ({c['section']})\n{c['text']}"
        for c in chunks
    ]
    return "Excerpts from SEC filings:\n\n" + "\n\n---\n\n".join(parts) + f"\n\nQuestion: {question}"


def pick_provider() -> str | None:
    want = os.environ.get("LLM_PROVIDER", "").lower()
    if want in ("anthropic", "openai"):
        return want
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def ask_llm(provider: str, prompt: str) -> tuple[str, str]:
    if provider == "anthropic":
        import anthropic
        model = os.environ.get("LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL
        resp = anthropic.Anthropic().messages.create(
            model=model, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            return model, "(the model declined to answer)"
        return model, "".join(b.text for b in resp.content if b.type == "text")
    import openai
    model = os.environ.get("LLM_MODEL")
    if not model:
        sys.exit("Set LLM_MODEL to an OpenAI model id (e.g. from https://platform.openai.com/docs/models).")
    resp = openai.OpenAI().responses.create(model=model, instructions=SYSTEM, input=prompt)
    return model, resp.output_text


def answer(question: str, k: int = TOP_K) -> dict:
    """Used by evals/run.py --mode baseline."""
    t0 = time.perf_counter()
    chunks = retrieve(question, k)
    prompt = build_prompt(question, chunks)
    provider = pick_provider()
    model, text = ask_llm(provider, prompt) if provider else (None, None)
    return {"answer": text, "model": model, "chunks": chunks, "prompt": prompt,
            "seconds": time.perf_counter() - t0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=TOP_K)
    args = ap.parse_args()

    res = answer(args.question, args.k)
    print("=" * 78)
    print(f"Retrieved top {len(res['chunks'])} chunks by vector similarity:")
    for c in res["chunks"]:
        preview = " ".join(c["text"].split())[:160]
        print(f"  [chunk {c['id']}] {c['ticker']:5} {c['form']:4} {c['filed']} {c['section']:13} "
              f"sim={c['similarity']:.3f}\n      {preview}...")
    print("=" * 78)
    if res["answer"] is None:
        print("No LLM key set (ANTHROPIC_API_KEY / OPENAI_API_KEY), so here's the prompt.")
        print("Paste it into any chat model:\n")
        print(f"[System] {SYSTEM}\n")
        print(res["prompt"])
    else:
        print(f"Answer ({res['model']}, {res['seconds']:.1f}s):\n")
        print(res["answer"])


if __name__ == "__main__":
    main()
