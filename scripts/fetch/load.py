"""Stage 5: load build artifacts into a scratch Postgres for pg_dump. Instructor-only."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from edgar_mcp.embed import fingerprint
from scripts.fetch.facts import fiscal_year_of

BUILD = Path("data/build")
DSN = os.environ.get("BUILD_DSN", "postgresql://postgres:postgres@localhost:5432/edgar")

POST_LOAD = """
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX chunks_filter ON chunks (ticker, form, section);
CREATE INDEX filings_ticker ON filings (ticker, form);

GRANT USAGE ON SCHEMA public TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_reader;
ANALYZE;
"""


def jsonl(name: str):
    with open(BUILD / name) as f:
        for line in f:
            yield json.loads(line)


def main() -> None:
    companies = json.loads((BUILD / "companies.json").read_text())
    filings = json.loads((BUILD / "filings.json").read_text())
    fye = {c["cik"]: c["fiscal_year_end"] for c in companies}
    extracted = {s["accession"] for s in jsonl("sections.jsonl")}
    vecs = np.load(BUILD / "embeddings.npy")

    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("DO $$BEGIN CREATE ROLE mcp_reader LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END$$;")
        conn.execute(Path("scripts/fetch/schema.sql").read_text())
        register_vector(conn)
        with conn.cursor() as cur:
            with cur.copy("COPY companies (cik, ticker, name, ipo_date, fiscal_year_end) FROM STDIN") as cp:
                for c in companies:
                    cp.write_row((c["cik"], c["ticker"], c["name"], c["ipo_date"], c["fiscal_year_end"]))
            with cur.copy("COPY filings (accession, cik, ticker, form, original_form, filed, period_end, "
                          "fiscal_year, primary_doc, url) FROM STDIN") as cp:
                for f in filings:
                    fy = (fiscal_year_of(dt.date.fromisoformat(f["period_end"]), fye[f["cik"]])
                          if f["form"] == "10-K" and f["period_end"] else None)
                    cp.write_row((f["accession"], f["cik"], f["ticker"], f["form"], f["original_form"],
                                  f["filed"], f["period_end"], fy, f["primary_doc"], f["url"]))
            with cur.copy("COPY facts (id, cik, ticker, concept, unit, value, period_type, fiscal_year, "
                          "start_date, end_date, frame, fy, fp, form, filed, accession) FROM STDIN") as cp:
                for i, r in enumerate(jsonl("facts.jsonl"), 1):
                    cp.write_row((i, r["cik"], r["ticker"], r["concept"], r["unit"], r["value"],
                                  r["period_type"], r["fiscal_year"], r["start_date"], r["end_date"],
                                  r["frame"], r["fy"], r["fp"], r["form"], r["filed"], r["accession"]))
            with cur.copy("COPY sections (accession, section, text) FROM STDIN") as cp:
                for r in jsonl("sections.jsonl"):
                    cp.write_row((r["accession"], r["section"], r["text"]))
            with cur.copy("COPY chunks (id, accession, cik, ticker, form, filed, section, chunk_index, "
                          "text, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
                cp.set_types(["bigint", "text", "bigint", "text", "text", "date", "text", "int4",
                              "text", "vector"])  # vector(512)
                for r, v in zip(jsonl("chunks.jsonl"), vecs):
                    cp.write_row((r["id"], r["accession"], r["cik"], r["ticker"], r["form"],
                                  dt.date.fromisoformat(r["filed"]), r["section"], r["chunk_index"],
                                  r["text"], v))
        meta = {
            "embedding": fingerprint(),
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "filings_with_sections": len(extracted),
        }
        for k, v in meta.items():
            conn.execute("INSERT INTO dataset_meta VALUES (%s, %s)", (k, json.dumps(v)))
        conn.execute(POST_LOAD)
        for t in ("companies", "filings", "facts", "sections", "chunks"):
            print(t, conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0])


if __name__ == "__main__":
    main()
