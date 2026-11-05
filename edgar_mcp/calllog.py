"""Log every tool call: name, arguments, latency, row count, error.

Lines go to stderr (visible in `docker compose logs -f mcp`) and are appended
to logs/tool_calls.jsonl in the repo, so you can see what your agent did.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
import time
from pathlib import Path

LOG_FILE = Path(os.environ.get("TOOL_LOG", "/workspace/logs/tool_calls.jsonl"))

log = logging.getLogger("edgar_mcp.calls")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)  # never stdout: that's the stdio protocol channel
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False


def _row_count(result) -> int | None:
    if isinstance(result, dict):
        for key in ("row_count", "results", "rows"):
            v = result.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, list):
                return len(v)
    if isinstance(result, list):
        return len(result)
    return None


def _write(entry: dict) -> None:
    short = {k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v) for k, v in entry["args"].items()}
    status = f"ERROR {entry['error']}" if entry.get("error") else f"rows={entry['rows']}"
    log.info("tool=%s %.0fms %s args=%s", entry["tool"], entry["ms"], status, json.dumps(short))
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def logged(fn):
    """Decorator for async tool functions. Keeps the signature and docstring intact."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": fn.__name__, "args": kwargs}
        try:
            result = await fn(*args, **kwargs)
            entry["rows"] = _row_count(result)
            return result
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            _write(entry)

    return wrapper
