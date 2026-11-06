"""Embedding helper shared by ingestion (scripts/fetch) and the MCP server.

Vectors come from Voyage AI's hosted `voyage-4-lite` model, through MongoDB Atlas's
Embedding API, at 512 dimensions. Passages were embedded with input_type="document";
queries use input_type="query". Both sides must use the same model, dimension and
library version, so everything lives here.

Needs VOYAGE_API_KEY in the environment (a model API key from MongoDB Atlas).
"""

from __future__ import annotations

import os
from functools import lru_cache
from importlib.metadata import version

from mcp.server.mcpserver.exceptions import ToolError

PROVIDER = "voyage"
MODEL_NAME = "voyage-4-lite"
EMBED_DIM = 512
VOYAGEAI_VERSION = "0.5.0"

NO_KEY = (
    "VOYAGE_API_KEY is not set. Search needs it to embed your query. Export it in your shell "
    "(export VOYAGE_API_KEY=...) and restart the stack: docker compose up -d"
)


@lru_cache(maxsize=1)
def _client():
    if not os.environ.get("VOYAGE_API_KEY"):
        raise ToolError(NO_KEY)  # a ToolError, so the agent (and the attendee) sees the message
    import voyageai

    # The client picks the endpoint from the key: Atlas model API keys go to ai.mongodb.com.
    return voyageai.Client(max_retries=4, timeout=30)


@lru_cache(maxsize=4096)
def _query_vec(text: str) -> tuple[float, ...]:
    client = _client()
    try:
        res = client.embed([text], model=MODEL_NAME, input_type="query", output_dimension=EMBED_DIM)
    except Exception as e:  # bad key, rate limit, network: tell the agent what happened
        raise ToolError(f"Embedding the query with Voyage failed ({type(e).__name__}: {e}). "
                        "Check VOYAGE_API_KEY and your network connection.") from e
    return tuple(res.embeddings[0])


def embed_query(text: str) -> list[float]:
    """Embed a search query (cached, so repeated searches don't call the API again)."""
    return list(_query_vec(text.strip()))


def embed_passages(texts: list[str]) -> tuple[list[list[float]], int]:
    """Embed passages for storage. Returns (vectors, tokens billed). Callers batch."""
    res = _client().embed(texts, model=MODEL_NAME, input_type="document", output_dimension=EMBED_DIM)
    return res.embeddings, res.total_tokens


def fingerprint() -> dict:
    """Identifies the embedding setup; stored in the dump and compared by `check`."""
    return {"provider": PROVIDER, "model": MODEL_NAME, "dim": EMBED_DIM,
            "input_type": {"passages": "document", "queries": "query"}, "voyageai": version("voyageai")}
