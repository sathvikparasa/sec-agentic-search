"""Stage 5: embed chunks with Voyage (voyage-4-lite, 512 dims, input_type="document").

Needs VOYAGE_API_KEY (an Atlas model API key on a paid usage tier: the free trial is
limited to 3 requests/min). Resumable: every batch is cached on disk keyed by the
text hash + model, so a rerun only embeds what's missing.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from edgar_mcp.embed import EMBED_DIM, MODEL_NAME, embed_passages

BUILD = Path("data/build")
CACHE_DIR = BUILD / "emb_cache" / f"{MODEL_NAME}-{EMBED_DIM}"
BATCH = 128          # ~80k tokens per request; API limits are 1,000 texts / 1M tokens


def main() -> None:
    rows = [json.loads(line) for line in open(BUILD / "chunks.jsonl")]
    texts = [r["embed_text"] for r in rows]
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, np.ndarray] = {}
    for f in sorted(CACHE_DIR.glob("batch_*.npz")):
        z = np.load(f)
        cache.update(zip(z["keys"].tolist(), z["vecs"]))
    todo = list({k: t for k, t in zip(keys, texts) if k not in cache}.items())
    print(f"{MODEL_NAME} ({EMBED_DIM}d): {len(texts)} chunks, {len(texts) - len(todo)} cached, "
          f"{len(todo)} to embed", flush=True)

    t0, billed = time.time(), 0
    for i in range(0, len(todo), BATCH):
        part = todo[i:i + BATCH]
        vecs, tokens = embed_passages([t for _, t in part])
        billed += tokens
        arr = np.asarray(vecs, dtype=np.float32)
        assert arr.shape == (len(part), EMBED_DIM), arr.shape
        np.savez(CACHE_DIR / f"batch_{int(time.time() * 1000)}.npz",
                 keys=np.array([k for k, _ in part]), vecs=arr)
        cache.update(zip((k for k, _ in part), arr))
        done = min(i + BATCH, len(todo))
        if done % (BATCH * 20) == 0 or done == len(todo):
            print(f"  {done}/{len(todo)} embedded, {billed:,} tokens, {time.time() - t0:.0f}s", flush=True)

    vecs = np.stack([cache[k] for k in keys]).astype(np.float32)
    np.save(BUILD / "embeddings.npy", vecs)
    (BUILD / "embed_stats.json").write_text(json.dumps(
        {"model": MODEL_NAME, "dim": EMBED_DIM, "chunks": len(rows), "tokens_billed_this_run": billed}, indent=2))
    print(f"saved {vecs.shape} to data/build/embeddings.npy")


if __name__ == "__main__":
    main()
