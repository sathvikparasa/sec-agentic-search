"""`docker compose run --rm app check`: one PASS/FAIL line per service, plus data counts."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://mcp_reader:mcp_reader@db:5432/edgar")
MCP_URL = os.environ.get("MCP_URL", "http://mcp:8000/mcp")
EXPECTED = {"companies": 40, "filings": 142}

results: list[tuple[bool, str, str]] = []


def report(ok: bool, name: str, detail: str) -> None:
    results.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name:11} {detail}", flush=True)


def check_db() -> dict | None:
    try:
        with psycopg.connect(DSN, connect_timeout=5) as conn:
            ver = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
            counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                      for t in ("companies", "filings", "facts", "chunks")}
            meta = conn.execute("SELECT value FROM dataset_meta WHERE key = 'embedding'").fetchone()[0]
            try:
                conn.execute("CREATE TEMP TABLE should_fail (x int)")
                ro = False
            except psycopg.Error:
                ro = True
                conn.rollback()
        report(True, "db", f"Postgres reachable as mcp_reader, pgvector {ver[0] if ver else '?'}")
        report(ro, "read-only", "writes are rejected" if ro else "mcp_reader can write. It must be read-only!")
        ok = all(counts[k] == v for k, v in EXPECTED.items()) and counts["facts"] > 0 and counts["chunks"] > 0
        report(ok, "data", ", ".join(f"{v:,} {k}" for k, v in counts.items()))
        return meta
    except Exception as e:
        report(False, "db", f"cannot query {DSN.split('@')[-1]}: {e}")
        return None


def check_embeddings(meta: dict | None) -> None:
    from edgar_mcp.embed import NO_KEY, fingerprint, embed_query
    fp = fingerprint()
    if not os.environ.get("VOYAGE_API_KEY"):
        report(False, "embeddings", NO_KEY)
        return
    try:
        vec = embed_query("risk factors")
    except Exception as e:
        report(False, "embeddings", f"Voyage API call failed ({type(e).__name__}: {e}). "
                                    "Check the key and your network.")
        return
    same = meta is not None and all(meta.get(k) == fp[k] for k in ("provider", "model", "dim"))
    detail = f"{fp['provider']} {fp['model']}, {len(vec)} dims, key works"
    report(same and len(vec) == fp["dim"], "embeddings",
           detail if same else detail + f": DOES NOT MATCH the dataset ({meta})")


async def check_mcp() -> None:
    from mcp import Client
    try:
        async with asyncio.timeout(20):
            async with Client(MCP_URL) as client:
                tools = [t.name for t in (await client.list_tools()).tools]
                res = await client.call_tool("ping", {})
        payload = res.structured_content or json.loads(res.content[0].text)
        ok = not res.is_error and payload.get("status") == "ok"
        report(ok, "mcp", f"{MCP_URL} up; tools: {', '.join(tools)}; ping {'ok' if ok else 'FAILED'}")
    except Exception as e:
        msg = str(e) or type(e).__name__
        report(False, "mcp", f"{MCP_URL} not reachable ({msg}). Try: docker compose logs mcp")


def main() -> None:
    meta = check_db()
    check_embeddings(meta)
    asyncio.run(check_mcp())
    failed = [r for r in results if not r[0]]
    print()
    print("All checks passed. You're ready." if not failed else f"{len(failed)} check(s) failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
