"""Eval harness (instructor-run). Measures the agent using each stage's tools.

    # inside the app container, with ANTHROPIC_API_KEY passed through:
    python -m evals.run --stage 2            # tools as on the stage-2 branch
    python -m evals.run --stage 3            # + get_section and the revenue fix
    python -m evals.run --stage 3 --judge    # add the optional LLM judge column

It loads the MCP server code from a git worktree of that stage branch
(.worktrees/stage-N; create with evals/setup_worktrees.sh on the host), so the
agent sees exactly the tool descriptions attendees see on that branch.

Grading (deterministic; see evals/grading.py):
  correct         numeric: within relative tolerance; ranking: top-N tickers in order;
                  text: required facts mentioned (keyword groups); hybrid: both parts.
  valid citation  cited fact ids / chunk ids exist and support the answer.
  judge (optional, --judge, clearly separate): an LLM grades free-text answers against gold notes.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

from evals.grading import grade, judge_text

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5-5"   # pinned; recorded in every results file
EFFORT = "medium"
MAX_TURNS = 16
MAX_TOOL_RESULT_CHARS = 40_000

ANSWER_FORMAT = """
When you have the answer, end your reply with a JSON object on its own, in a ```json block:
{"answer": <see below>, "fact_ids": [<facts.id values you relied on>], "chunk_ids": [<chunk ids you relied on>]}
- For a single number: the number in raw units (dollars, not millions), e.g. 4792000000. Percentages as percent, e.g. 23.5.
- For a ranking: a list of tickers, best first, e.g. ["NVDA", "PLTR", "CRWD"].
- For a text question: a short answer in sentences.
- For a question that needs both: {"answer": {"value": <number, ticker or list>, "explanation": "<sentences>"}, ...}
Cite only ids that actually appeared in tool results or excerpts you were given.
""".strip()

AGENT_SYSTEM = ("You are a financial research analyst. Answer questions about public companies using "
                "the tools, which cover SEC EDGAR data. Verify numbers with the data rather than "
                "estimating.\n\n" + ANSWER_FORMAT)


def load_questions() -> list[dict]:
    return yaml.safe_load((ROOT / "evals" / "questions.yaml").read_text())["questions"]


def git_commit(path: Path) -> str:
    """Commit of a checkout. Works without git installed (the app image has none):
    setup_worktrees.sh writes COMMIT into each worktree; for the main repo read .git."""
    if (path / "COMMIT").exists():
        return (path / "COMMIT").read_text().strip()
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        pass
    try:
        head = (path / ".git" / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        if (path / ".git" / ref).exists():
            return (path / ".git" / ref).read_text().strip()[:7]
        for line in (path / ".git" / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split()[0][:7]
    except OSError:
        pass
    return "unknown"


def extract_json(text: str):
    """Last ```json block (or last {...}) in the reply."""
    import re
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    cands = blocks or re.findall(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", text, re.S)
    for c in reversed(cands):
        try:
            return json.loads(c)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- agentic

def load_stage_server(stage: int):
    """Import edgar_mcp.server from .worktrees/stage-N in a fresh module namespace."""
    wt = ROOT / ".worktrees" / f"stage-{stage}"
    if not (wt / "edgar_mcp" / "server.py").exists():
        sys.exit(f"Missing {wt}. On the host run: evals/setup_worktrees.sh")
    for name in [m for m in sys.modules if m == "edgar_mcp" or m.startswith("edgar_mcp.")]:
        del sys.modules[name]
    sys.path.insert(0, str(wt))
    try:
        server = importlib.import_module("edgar_mcp.server")
    finally:
        sys.path.remove(str(wt))
    return server.mcp, git_commit(wt)


async def run_agentic(q: dict, mcp_server) -> dict:
    import anthropic
    from mcp import Client

    t0 = time.perf_counter()
    client = anthropic.AsyncAnthropic()
    calls, usage_total = [], {}
    async with Client(mcp_server) as mc:
        tools = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                 for t in (await mc.list_tools()).tools if t.name != "ping"]
        messages = [{"role": "user", "content": q["question"]}]
        resp = None
        for _ in range(MAX_TURNS):
            resp = await client.messages.create(
                model=MODEL, max_tokens=16000, system=AGENT_SYSTEM, tools=tools, messages=messages,
                output_config={"effort": EFFORT}, cache_control={"type": "ephemeral"},
            )
            for k, v in resp.usage.model_dump().items():
                if isinstance(v, int):
                    usage_total[k] = usage_total.get(k, 0) + v
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                break
            results = []
            for b in (b for b in resp.content if b.type == "tool_use"):
                ct0 = time.perf_counter()
                r = await mc.call_tool(b.name, b.input)
                text = "\n".join(getattr(c, "text", "") for c in r.content) or json.dumps(r.structured_content)
                calls.append({"tool": b.name, "args": b.input, "is_error": bool(r.is_error),
                              "ms": round((time.perf_counter() - ct0) * 1000), "result_chars": len(text),
                              "result": text[:MAX_TOOL_RESULT_CHARS]})
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": text[:MAX_TOOL_RESULT_CHARS], "is_error": bool(r.is_error)})
            messages.append({"role": "user", "content": results})
    reply = "".join(b.text for b in resp.content if b.type == "text") if resp else ""
    return {"reply": reply, "seconds": time.perf_counter() - t0, "tool_calls": calls,
            "stop_reason": resp.stop_reason if resp else None, "usage": usage_total}


# ---------------------------------------------------------------- main

async def main_async(args) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set (export it in your shell, then `docker compose up -d app`).")
    questions = load_questions()
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only.split(","))]
    label = f"agentic-stage{args.stage}"
    server, server_commit = load_stage_server(args.stage)

    sem = asyncio.Semaphore(args.concurrency)

    async def one(q):
        async with sem:
            for attempt in range(3):
                try:
                    run = await run_agentic(q, server)
                    break
                except Exception as e:  # noqa: BLE001 - record and retry transient failures
                    run = {"reply": "", "seconds": 0, "tool_calls": [], "error": repr(e)}
                    await asyncio.sleep(5 * (attempt + 1))
            parsed = extract_json(run["reply"])
            g = await asyncio.to_thread(grade, q, parsed, run)
            if args.judge and q["category"] in ("text", "hybrid"):
                g["judge_correct"] = await judge_text(q, run["reply"])
            print(f"  {q['id']:6} {q['category']:8} correct={g['correct']!s:5} "
                  f"citation={g['citation_valid']!s:5} {run['seconds']:5.1f}s  {g.get('detail', '')}", flush=True)
            return {"id": q["id"], "category": q["category"], "question": q["question"],
                    "parsed": parsed, **g, **run}

    print(f"== {label}: {len(questions)} questions, model {MODEL}, effort {EFFORT}")
    rows = await asyncio.gather(*(one(q) for q in questions))

    n = len(rows)
    summary = {
        "label": label, "model": MODEL, "effort": EFFORT, "n": n,
        "correct": sum(r["correct"] for r in rows),
        "citation_valid": sum(r["citation_valid"] for r in rows),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / max(n, 1), 1),
        "by_category": {},
    }
    for cat in ("numeric", "ranking", "text", "hybrid"):
        rs = [r for r in rows if r["category"] == cat]
        if rs:
            summary["by_category"][cat] = {"n": len(rs), "correct": sum(r["correct"] for r in rs),
                                           "citation_valid": sum(r["citation_valid"] for r in rs)}
    if args.judge:
        judged = [r for r in rows if "judge_correct" in r]
        summary["llm_judge_text_hybrid"] = {"n": len(judged), "correct": sum(bool(r["judge_correct"]) for r in judged)}

    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    meta = {"timestamp": stamp, "model": MODEL, "effort": EFFORT, "stage": args.stage,
            "repo_commit": git_commit(ROOT), "server_commit": server_commit, "max_turns": MAX_TURNS}
    (out_dir / f"{stamp}-{label}.json").write_text(json.dumps(
        {"meta": meta, "summary": summary,
         "results": [{k: v for k, v in r.items() if k not in ("tool_calls",)} |
                     {"tool_calls": [{k: v for k, v in c.items() if k != "result"} for c in r["tool_calls"]]}
                     for r in rows]}, indent=2, default=str))
    with (out_dir / f"{stamp}-{label}.raw.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")

    print()
    print(f"| Approach | Correct | Valid citation | Avg. seconds |")
    print(f"|---|---|---|---|")
    print(f"| {label} | {summary['correct']} / {n} | {summary['citation_valid']} / {n} | {summary['avg_seconds']} |")
    print(f"by category: {json.dumps(summary['by_category'])}")
    if args.judge:
        print(f"LLM judge (optional, text+hybrid only): {summary['llm_judge_text_hybrid']}")
    print(f"results: evals/results/{stamp}-{label}.json (model {MODEL})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", type=int, choices=[2, 3], required=True)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--judge", action="store_true", help="OPTIONAL: add an LLM-judge column for text/hybrid")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
