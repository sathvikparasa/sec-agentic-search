# EDGAR MCP workshop: context for coding agents

You are helping build an MCP server (`edgar_mcp/`) that lets an AI agent answer questions about
~40 US-listed tech companies from SEC EDGAR data, with citations. The server retrieves; it never
generates answers (there is no LLM inside it). The calling agent picks tools, reads results and
writes the answer.

## Where you are

**Branch `main` (start here):** `ping` works; `query_financials`, `search_filings` and `get_section` are stubs. Build stage 1 first.

## Rules

- **Tools are read-only.** Never write to the database, never add tools that modify data, never
  connect as anything but the `DATABASE_URL` role (`mcp_reader`: SELECT only, read-only
  transactions, 5 s statement timeout). Don't try to work around these limits.
- **Never call the SEC / EDGAR API.** All data is already in Postgres. The only network call
  is query embedding through `edgar_mcp.embed.embed_query` (Voyage, needs `VOYAGE_API_KEY`).
- **Don't edit** `edgar_mcp/embed.py` (it must match the model that built the stored vectors:
  `voyage-4-lite`, 512 dims, `input_type` document for passages and query for queries),
  `edgar_mcp/db.py` or `edgar_mcp/calllog.py` unless asked.
- Keep every tool decorated with `@mcp.tool()` then `@logged`, async, and returning JSON-friendly
  dicts. For errors the agent should read and fix (bad argument, SQL error), raise
  `ToolError("message")` (`from mcp.server.mcpserver.exceptions import ToolError`); any other
  exception reaches the agent only as "Error executing tool X". `db.fetch` already turns
  database errors into ToolError. Use `db.fetch(sql, params, max_rows=...)`; always pass user values as SQL parameters.
- The tool **docstring is the interface**: it's what the calling agent reads to decide when and
  how to use the tool. Write it for that reader: what the tool is for, what it is NOT for, the
  arguments, what comes back, and the data quirks below that would otherwise cause wrong answers.

## Running things

```bash
docker compose up -d                       # db + mcp (HTTP on localhost:8000/mcp) + app
docker compose logs -f mcp                 # server log, one line per tool call
docker compose run --rm app check          # health check
docker compose exec app python baseline.py "question"   # single-pass RAG, for comparison
```

The `mcp` service reloads automatically when you save a file in `edgar_mcp/` (polling, ~1 s).
Every tool call is also appended to `logs/tool_calls.jsonl` (tool, args, latency, row count, error).
Run SQL by hand: `docker compose exec db psql -U mcp_reader -d edgar` (password `mcp_reader`).

## Database schema (Postgres 16 + pgvector)

```
companies(cik, ticker, name, ipo_date, fiscal_year_end)
    ipo_date: only for the 22 companies that IPO'd 2015+ (their S-1 is in the data)
    fiscal_year_end: 'MMDD', e.g. '1231', '0131' (NVDA, CRM, SNOW...), '0630' (MSFT), '0926' (AAPL)

filings(accession, cik, ticker, form, original_form, filed, period_end, fiscal_year, primary_doc, url)
    form: '10-K' (3 latest per company) or 'S-1' (final IPO prospectus, 2015+ IPOs only)
    original_form: what was actually filed: '10-K' or '424B4' (all S-1 rows are 424B4 prospectuses)
    url: the document on sec.gov, for citations

facts(id, cik, ticker, concept, unit, value, period_type, fiscal_year, start_date, end_date,
      frame, fy, fp, form, filed, accession)
    one row per (company, us-gaap concept, unit, period); see quirks below

sections(accession, section, text)
    full extracted text: section in ('business', 'risk_factors', 'mda'); S-1s have no 'mda'

chunks(id, accession, cik, ticker, form, filed, section, chunk_index, text, embedding vector(512), tsv tsvector)
    ~600-token passages cut from sections (never across sections), ~100-token overlap
    embedding: Voyage voyage-4-lite, 512 dims (cosine). Indexes: HNSW on embedding, GIN on tsv.
    tsv = to_tsvector('english', text)
```

Embedding helper: `from edgar_mcp.embed import embed_query` returns a 512-dim list for a query
(Voyage API, `input_type="query"`, cached). It's blocking: call it with `await asyncio.to_thread(embed_query, q)`.
pgvector cosine distance is `embedding <=> %s::vector` (smaller = closer).

## EDGAR quirks (these cause confidently wrong answers)

1. **Duplicate facts.** A number is repeated in every later filing that shows it as a comparative.
   `facts` is already deduplicated: one row per period, keeping the most recently filed value
   (so restatements win). Don't re-aggregate duplicates yourself. Only 10-K/10-Q values are
   kept: proxy statements (DEF 14A) also tag net income in "pay versus performance" tables,
   sometimes rounded (Coinbase's 2023 proxy says $100,000,000; its 10-K says $94,871,000). Only 10-K/10-Q values are
   kept: proxy statements (DEF 14A) also tag net income in "pay versus performance" tables,
   sometimes rounded (Coinbase's 2023 proxy says $100,000,000; its 10-K says $94,871,000).
2. **`fy` is not the period's year.** `fy`/`fp` describe the *filing* that last reported the value:
   Airbnb's fiscal-2020 net income, repeated in its 2022 10-K, has `fy = 2022`. Use
   **`fiscal_year`** (derived from the period's own end date and the company's fiscal year end).
3. **Fiscal year ≠ calendar year.** NVDA's fiscal 2025 ended in January 2025; MSFT's fiscal year
   ends in June; AAPL's in September. To line companies up by calendar period, use `frame`
   (`CY2024`, `CY2024Q3`, `CY2024Q4I` for instants), which is set on only one row per period and can
   be NULL.
4. **Annual vs quarterly vs instant.** `period_type` is `annual`, `quarterly` (3 months) or `instant`
   (balance-sheet values at a date, `start_date` NULL). Always filter on it. Q4 is rarely reported on
   its own (Q4 = annual − Q1 − Q2 − Q3). 6- and 9-month year-to-date values were dropped.
5. **Revenue has several tags.** Companies report revenue under different concepts:
   `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax` (common since the 2018 revenue
   standard), `SalesRevenueNet` (older), and others; some switched tags over time. Querying one tag
   silently drops companies from a ranking, and the answer still sounds confident.
6. **Units.** `unit` is `USD` (raw dollars, not thousands or millions), `USD/shares`, `shares` or
   `pure`. Filing *text* usually says "in millions"; facts never do.
7. **Amendments.** 10-K/As exist for some companies. The text corpus uses original 10-Ks only;
   facts keep the latest filed value, which may come from an amendment.
8. **Extraction.** Sections were extracted from HTML; Intel uses a non-standard layout (handled).
   Some passages contain flattened tables (cells separated by ` | `).

## Tool contracts (what to build)

`ping` already works. The other three are stubs that raise `NotImplementedError`.

### Stage 1: `query_financials(sql: str) -> dict`
- Runs one read-only `SELECT`/`WITH` query against the tables above; rejects anything else.
- Returns `{columns, rows, row_count, truncated, note}`; at most **200 rows**, and when there are
  more, `truncated: true` plus a note telling the agent to aggregate or LIMIT.
- SQL errors (bad column, timeout) come back as tool errors the agent can read and fix.
- Its docstring must teach the agent the schema, units, `period_type`, `fiscal_year` vs `fy`,
  fiscal vs calendar years, a few example concepts, how to cite (`facts.id`, `accession`), and
  that this tool is for numbers, rankings and trends.

### Stage 2: `search_filings(query, ticker=None, form=None, section=None, top_k=8) -> dict`
- Hybrid search over `chunks`: a full-text query (on `tsv`) and a vector query (on `embedding`),
  each with the same filters, merged with **reciprocal rank fusion** (score = Σ 1/(60 + rank)).
- Filters: `ticker`, `form` ('10-K' | 'S-1'), `section` ('business' | 'risk_factors' | 'mda').
- Returns passages best first, each with `chunk_id, ticker, form, filed, section, accession, url, text`.
- The docstring says what's searchable (and what isn't: no 10-Qs, no financial statements) and
  says **not** to use it for numbers.

### Stage 3: `get_section(ticker, form, section, fy=None) -> dict`
- Returns the full text of one section of one filing from `sections`, capped per call (page
  through long sections), with filing metadata and URL for citation. `fy` picks which 10-K
  (default: latest).
- Plus: fix the revenue-tag problem (quirk 5) so cross-company revenue questions stop silently
  dropping companies.

## Test questions

- Stage 1: "How did Airbnb's net income change from 2019 to 2023?"
- Stage 2: "What risks about its contractors did DoorDash disclose in its S-1?"
- Stage 3: "Which companies here grew revenue fastest last year, and what did they credit for it?"
