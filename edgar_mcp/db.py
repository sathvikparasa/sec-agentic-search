"""Database access for the MCP server.

The server connects as `mcp_reader`: a role with SELECT only, whose sessions
default to read-only transactions and a 5 s statement timeout (set on the role
in docker/db/initdb/00-roles.sql, and again here per connection).
"""

from __future__ import annotations

import datetime as dt
import decimal
import os

import psycopg
from mcp.server.mcpserver.exceptions import ToolError
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async

DSN = os.environ.get("DATABASE_URL", "postgresql://mcp_reader:mcp_reader@db:5432/edgar")
STATEMENT_TIMEOUT_MS = int(os.environ.get("STATEMENT_TIMEOUT_MS", "5000"))

_pool: AsyncConnectionPool | None = None


async def _configure(conn: AsyncConnection) -> None:
    await register_vector_async(conn)
    await conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
    await conn.execute("SET default_transaction_read_only = on")
    # Let filtered vector searches keep scanning the HNSW index until they
    # find enough rows that pass the WHERE clause (pgvector >= 0.8).
    await conn.execute("SET hnsw.iterative_scan = relaxed_order")
    await conn.execute("SET hnsw.ef_search = 100")
    await conn.commit()


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(DSN, min_size=1, max_size=5, configure=_configure, open=False)
        await _pool.open(wait=True, timeout=30)
    return _pool


def to_json(v):
    """Make a database value JSON-friendly."""
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if hasattr(v, "tolist"):  # numpy / pgvector
        return v.tolist()
    return v


async def fetch(sql: str, params=None, max_rows: int | None = None):
    """Run one query in a read-only transaction. Returns (columns, rows, more_rows_exist).

    Database errors (syntax, unknown column, timeout, write attempts) are raised as
    ToolError, so the calling agent sees Postgres's message and can fix its query.
    """
    try:
        return await _fetch(sql, params, max_rows)
    except psycopg.errors.QueryCanceled as e:
        raise ToolError(f"Query cancelled after {STATEMENT_TIMEOUT_MS // 1000}s statement timeout. "
                        f"Filter more (ticker, concept, fiscal_year) or aggregate. ({e})") from e
    except psycopg.Error as e:
        raise ToolError(f"Database error: {str(e).strip()}") from e


async def _fetch(sql: str, params, max_rows: int | None):
    p = await pool()
    async with p.connection() as conn:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            cur = await conn.execute(sql, params)
            if cur.description is None:
                return [], [], False
            cols = [d.name for d in cur.description]
            if max_rows is None:
                rows = await cur.fetchall()
                more = False
            else:
                rows = await cur.fetchmany(max_rows + 1)
                more = len(rows) > max_rows
                rows = rows[:max_rows]
            return cols, [[to_json(v) for v in r] for r in rows], more
