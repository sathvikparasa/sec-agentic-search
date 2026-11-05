-- Schema for the workshop database. Loaded by scripts/fetch/load.py, then
-- dumped with pg_dump. The read-only role is created at restore time
-- (docker/db/initdb/00-roles.sql); the GRANTs below travel inside the dump.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE companies (
    cik             bigint PRIMARY KEY,
    ticker          text NOT NULL UNIQUE,
    name            text NOT NULL,
    ipo_date        date,              -- only set for 2015+ IPOs whose S-1 is in the dataset
    fiscal_year_end text NOT NULL      -- MMDD, e.g. '1231', '0126' (NVDA), '0930'
);

CREATE TABLE filings (
    accession     text PRIMARY KEY,
    cik           bigint NOT NULL REFERENCES companies(cik),
    ticker        text NOT NULL,
    form          text NOT NULL,        -- '10-K' or 'S-1' (S-1 = final pre-IPO prospectus)
    original_form text NOT NULL,        -- what was actually filed: 10-K, 424B4, S-1/A, S-1
    filed         date NOT NULL,
    period_end    date,                 -- fiscal period covered (10-K); null for S-1
    fiscal_year   int,                  -- fiscal year of period_end (10-K); null for S-1
    primary_doc   text NOT NULL,
    url           text NOT NULL         -- the document on sec.gov
);

-- One row per (company, concept, unit, period). Deduplicated: when a value was
-- reported in several filings, the most recently filed one is kept.
CREATE TABLE facts (
    id          bigint PRIMARY KEY,
    cik         bigint NOT NULL REFERENCES companies(cik),
    ticker      text NOT NULL,
    concept     text NOT NULL,          -- us-gaap tag, e.g. 'NetIncomeLoss'
    unit        text NOT NULL,          -- 'USD', 'shares', 'USD/shares', 'pure', ...
    value       numeric NOT NULL,
    period_type text NOT NULL CHECK (period_type IN ('annual', 'quarterly', 'instant')),
    fiscal_year int NOT NULL,           -- derived from end_date + company fiscal year end. USE THIS.
    start_date  date,                   -- null for instant (balance-sheet) facts
    end_date    date NOT NULL,
    frame       text,                   -- SEC calendar alignment: 'CY2023', 'CY2023Q4', 'CY2023Q4I'
    fy          int,                    -- RAW: fiscal year of the FILING that reported it, not of the period
    fp          text,                   -- RAW: fiscal period of that filing: FY, Q1, Q2, Q3
    form        text,                   -- form of the (latest) filing that reported it
    filed       date NOT NULL,
    accession   text NOT NULL           -- that filing's accession number
);
CREATE INDEX facts_lookup ON facts (concept, ticker, period_type, fiscal_year);
CREATE INDEX facts_ticker ON facts (ticker, concept);

CREATE TABLE chunks (
    id          bigint PRIMARY KEY,
    accession   text NOT NULL REFERENCES filings(accession),
    cik         bigint NOT NULL,
    ticker      text NOT NULL,
    form        text NOT NULL,
    filed       date NOT NULL,
    section     text NOT NULL CHECK (section IN ('business', 'risk_factors', 'mda')),
    chunk_index int NOT NULL,
    text        text NOT NULL,
    embedding   vector(512) NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

-- Full text of each extracted section (what chunks were cut from). Read with get_section.
CREATE TABLE sections (
    accession text NOT NULL REFERENCES filings(accession),
    section   text NOT NULL CHECK (section IN ('business', 'risk_factors', 'mda')),
    text      text NOT NULL,
    PRIMARY KEY (accession, section)
);

-- Provenance for `check` and evals: which embedding model built the vectors.
CREATE TABLE dataset_meta (
    key   text PRIMARY KEY,
    value jsonb NOT NULL
);

-- Revenue under one name. Companies tag total revenue with different us-gaap
-- concepts (and switched tags over time). For each company and period, take the
-- highest-priority tag present, so nothing is double counted.
-- (The tag list is finalized from the data; see scripts/fetch/report.py.)
CREATE VIEW revenue AS
SELECT DISTINCT ON (f.cik, f.period_type, f.start_date, f.end_date)
       f.cik, f.ticker, f.period_type, f.fiscal_year, f.start_date, f.end_date, f.frame,
       f.value, f.unit, f.concept AS source_concept, f.id AS fact_id, f.accession, f.filed
FROM facts f
JOIN (VALUES
    ('Revenues', 1),
    ('RevenueFromContractWithCustomerExcludingAssessedTax', 2),
    ('RevenueFromContractWithCustomerIncludingAssessedTax', 3),
    ('RevenuesNetOfInterestExpense', 4),
    ('SalesRevenueNet', 5),
    ('SalesRevenueServicesNet', 6)
) AS p(concept, priority) ON p.concept = f.concept
WHERE f.unit = 'USD' AND f.period_type IN ('annual', 'quarterly')
ORDER BY f.cik, f.period_type, f.start_date, f.end_date, p.priority;
