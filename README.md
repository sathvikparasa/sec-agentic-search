# Agentic Search over SEC Filings

Build an MCP server that lets your coding agent answer questions about public companies, with
sources, from SEC EDGAR data: XBRL financial facts for SQL, plus 10-K and S-1 text for search.

Everything runs locally in Docker. The data is already inside the images, so you never call the
SEC API. The one online piece is query embedding for search, through Voyage AI (MongoDB Atlas):
you'll be given a `VOYAGE_API_KEY`.

## Before the workshop (10 minutes, at home)

1. **Install Docker Desktop** (or Docker Engine + Compose v2 on Linux) and start it.
   - **Windows:** Docker Desktop with the **WSL 2** backend. **Clone the repo inside WSL**
     (e.g. `~/code` in your Ubuntu terminal), not under `C:\` or `/mnt/c`. On the Windows
     filesystem, bind mounts are slow and file-change events don't reach the container.
   - Apple Silicon and Intel Macs are both supported (multi-arch images).
2. **Clone:** `git clone https://github.com/sathvikparasa/sec-agentic-search && cd sec-agentic-search`
3. **Pull the images** (~1.2 GB; do this on good Wi-Fi): `docker compose pull`
4. **Set the key** you were given (every new terminal, before `docker compose up`):
   `export VOYAGE_API_KEY=...` (PowerShell users: run this inside WSL)
5. **Check:** `docker compose run --rm app check`

You should see:

```
[PASS] db          Postgres reachable as mcp_reader, pgvector 0.8.1
[PASS] read-only   writes are rejected
[PASS] data        40 companies, 142 filings, ... facts, ... chunks
[PASS] embeddings  voyage voyage-4-lite, 512 dims, key works
[PASS] mcp         http://mcp:8000/mcp up; tools: ping, query_financials, search_filings, get_section; ping ok

All checks passed. You're ready.
```

No Docker? Open the repo in **GitHub Codespaces** (Code → Codespaces → Create). The dev
container pulls the images and starts the stack for you (4-core machine recommended).

## Start it

```bash
docker compose up -d          # db, mcp (http://localhost:8000/mcp), app
docker compose logs -f mcp    # watch every tool call your agent makes
```

The first start restores the database (about 30 seconds); later starts are instant.
`docker compose down` stops everything; `docker compose down -v` is never needed.

## Connect your agent

The server speaks MCP over **streamable HTTP** at `http://localhost:8000/mcp`, and over
**stdio** via `docker compose exec`. Use HTTP if your client supports it.

**Claude Code** (run inside the repo):

```bash
claude mcp add --transport http edgar http://localhost:8000/mcp
claude mcp list        # edgar: ... - ✓ Connected
```

**Cursor**: already configured. This repo ships `.cursor/mcp.json`; enable `edgar` under Settings → MCP. It contains:

```json
{ "mcpServers": { "edgar": { "url": "http://localhost:8000/mcp" } } }
```

**Claude Desktop** (stdio): Settings → Developer → Edit Config, then restart Claude Desktop.
Replace the path with where you cloned the repo (on Windows, a WSL path works via `wsl`, see below):

```json
{
  "mcpServers": {
    "edgar": {
      "command": "docker",
      "args": ["compose", "--project-directory", "/absolute/path/to/sec-agentic-search",
               "exec", "-T", "mcp", "python", "-m", "edgar_mcp"]
    }
  }
}
```

Windows + WSL: use `"command": "wsl"` and put `docker` first in `args`, with the WSL path
(`/home/you/sec-agentic-search`).

**Any other client**: stdio command `docker compose exec -T mcp python -m edgar_mcp`, or HTTP URL above.

After you edit a tool, the server reloads by itself (about a second). In Claude Code, run
`/mcp` → reconnect if the tool list looks stale.

## What's here

| Piece | What it does |
|---|---|
| `db` | Postgres 16 + pgvector: `companies`, `filings`, `facts` (XBRL), `sections`, `chunks` (embeddings + full-text index) |
| `edgar_mcp/` | The MCP server. **You edit `edgar_mcp/server.py`.** DB pool, embedding helper and tool-call logging are done. |
| `CLAUDE.md` / `AGENTS.md` | Schema, tool contracts, EDGAR quirks, for your coding agent to read |
| `tests/` | Smoke tests for the finished tools (`docker compose run --rm app smoke`) |
| `evals/` | 30 questions with answers computed from the data (instructor-run) |
| `scripts/fetch/` | How the data was built from EDGAR (instructor-only; you never need it) |

Data: 40 US-listed tech companies; XBRL facts (annual, quarterly, balance-sheet); the 3 latest
10-Ks per company (Business, Risk Factors, MD&A); and for the 22 companies that IPO'd in 2015 or
later, the final IPO prospectus (Business, Risk Factors). See `data/report.md`.

## Stages

Each stage is one tool. Ask your coding agent to build it from the contract in `CLAUDE.md`, then
connect your agent to the server and try the test question. Watch `docker compose logs -f mcp`.

| Stage | Build | Test with | Time |
|---|---|---|---|
| 1 | `query_financials(sql)`: read-only SQL over the facts, 200-row cap, a docstring that teaches the schema | "How did Airbnb's net income change from 2019 to 2023?" | ~10 min |
| 2 | `search_filings(query, ticker?, form?, section?, top_k=8)`: keyword + vector, merged with reciprocal rank fusion; passages with sources | "What risks about its contractors did DoorDash disclose in its S-1?" | ~8 min |
| 3 | `get_section(ticker, form, section, fy?)` (optional) + fix revenue tags | "Which companies here grew revenue fastest last year, and what did they credit for it?" | ~7 min |

**Behind? `git checkout stage-N`** (e.g. `git checkout stage-2`). Stash or commit your work
first. Each branch builds on the previous one, and `stage-3` is the finished version. The server
reloads on checkout, and `CLAUDE.md` changes with the branch too.

## Troubleshooting

- `check` fails on `mcp`: `docker compose logs mcp` (a syntax error in `server.py` shows here).
- Port 8000 in use: `export MCP_PORT=8001` before `docker compose up -d`, and use
  `http://localhost:8001/mcp` in your client config.
- Stale tools in your client: reconnect the server (`/mcp` in Claude Code).
- Reset everything: `docker compose down && docker compose up -d` (data is restored from the image).

## Instructor notes

- Rebuild the dataset: `export SEC_USER_AGENT="Your Name you@example.edu"; scripts/fetch/run_all.sh`
  (≤ 8 req/s, cached in `data/raw/`; writes `docker/db/edgar.dump` and `data/report.md`).
- Publish: upload the dump to the `data-v1` release, push to `main`, and the `images` workflow
  builds multi-arch images to GHCR. Set `IMAGE_PREFIX` in `.env` to `ghcr.io/<owner>/<repo>`.
- Evals: `evals/setup_worktrees.sh`, then
  `docker compose exec app python -m evals.run --stage 2` and `--stage 3`.
