# Data report

## Counts

| table | rows |
|---|---|
| companies | 40 |
| filings | 142 |
| facts | 305,471 |
| chunks | 12,401 |

Facts: 710,237 raw us-gaap records -> 305,471 after dedupe (269,062 duplicates removed, 129,888 non-annual/non-quarterly durations dropped, 5,816 records from non-10-K/10-Q forms (proxies, S-1s, 8-Ks) dropped).
Chunks: mean 600 tokens, max 699, 7,442,776 tokens in total (bge WordPiece count).

Annual facts span fiscal years 2006–2026.

## Filings per company

| ticker | name | FYE | 10-Ks (filed) | S-1 (original form) | IPO check | notes |
|---|---|---|---|---|---|---|
| AAPL | Apple Inc. | 0926 | 2024-11-01, 2025-10-31, 2026-11-03 | — | — |  |
| MSFT | MICROSOFT CORP | 0630 | 2024-07-30, 2025-07-30, 2026-07-29 | — | — |  |
| GOOGL | Alphabet Inc. | 1231 | 2024-01-31, 2025-02-05, 2026-02-05 | — | — | 2 10-K/A on file |
| AMZN | AMAZON COM INC | 1231 | 2024-02-02, 2025-02-07, 2026-02-06 | — | — |  |
| META | Meta Platforms, Inc. | 1231 | 2024-02-02, 2025-01-30, 2026-01-29 | — | — |  |
| NVDA | NVIDIA CORP | 0131 | 2024-02-21, 2025-02-26, 2026-02-25 | — | — |  |
| TSLA | Tesla, Inc. | 1231 | 2024-01-29, 2025-01-30, 2026-01-29 | — | — | 5 10-K/A on file |
| NFLX | NETFLIX INC | 1231 | 2024-01-26, 2025-01-27, 2026-01-23 | — | — | 2 10-K/A on file |
| CRM | Salesforce, Inc. | 0131 | 2024-03-06, 2025-03-05, 2026-03-02 | — | — |  |
| ADBE | ADOBE INC. | 1127 | 2024-01-17, 2025-01-13, 2026-01-15 | — | — |  |
| ORCL | ORACLE CORP | 0531 | 2024-06-20, 2025-06-18, 2026-06-22 | — | — |  |
| NOW | ServiceNow, Inc. | 1231 | 2024-01-25, 2025-01-30, 2026-01-29 | — | — | 1 10-K/A on file |
| INTU | INTUIT INC. | 0731 | 2024-09-04, 2025-09-03, 2026-09-09 | — | — |  |
| WDAY | Workday, Inc. | 0131 | 2024-03-08, 2025-03-11, 2026-03-06 | — | — |  |
| ADSK | Autodesk, Inc. | 0131 | 2024-06-10, 2025-03-06, 2026-03-03 | — | — |  |
| AMD | ADVANCED MICRO DEVICES INC | 1226 | 2024-01-31, 2025-02-05, 2026-02-04 | — | — | 1 10-K/A on file |
| INTC | INTEL CORP | 1226 | 2024-01-26, 2025-01-31, 2026-01-23 | — | — |  |
| QCOM | QUALCOMM INC/DE | 0927 | 2024-11-06, 2025-11-05, 2026-11-04 | — | — |  |
| UBER | Uber Technologies, Inc | 1231 | 2024-02-15, 2025-02-14, 2026-02-13 | 2019-05-13 (424B4) | confirmed: 424B4 filed within 3 days |  |
| LYFT | Lyft, Inc. | 1231 | 2024-02-20, 2025-02-14, 2026-02-11 | 2019-03-29 (424B4) | confirmed: 424B4 filed within 3 days | 1 10-K/A on file |
| PINS | PINTEREST, INC. | 1231 | 2024-02-08, 2025-02-06, 2026-02-12 | 2019-04-18 (424B4) | confirmed: 424B4 filed within 3 days |  |
| ZM | Zoom Communications, Inc. | 0131 | 2024-03-04, 2025-02-28, 2026-02-27 | 2019-04-18 (424B4) | confirmed: 424B4 filed within 3 days |  |
| CRWD | CrowdStrike Holdings, Inc. | 0131 | 2024-03-07, 2025-03-10, 2026-03-05 | 2019-06-13 (424B4) | confirmed: 424B4 filed within 3 days |  |
| DDOG | Datadog, Inc. | 1231 | 2024-02-23, 2025-02-20, 2026-02-18 | 2019-09-19 (424B4) | confirmed: 424B4 filed within 3 days |  |
| ABNB | Airbnb, Inc. | 1231 | 2024-02-16, 2025-02-13, 2026-02-12 | 2020-12-11 (424B4) | confirmed: 424B4 filed within 3 days |  |
| DASH | DoorDash, Inc. | 1231 | 2024-02-20, 2025-02-14, 2026-02-18 | 2020-12-09 (424B4) | confirmed: 424B4 filed within 3 days | 1 10-K/A on file |
| SNOW | Snowflake Inc. | 0131 | 2024-03-26, 2025-03-21, 2026-03-20 | 2020-09-16 (424B4) | confirmed: 424B4 filed within 3 days |  |
| PLTR | Palantir Technologies Inc. | 1231 | 2024-02-20, 2025-02-18, 2026-02-17 | 2020-09-30 (424B4) | confirmed: 424B4 filed within 3 days |  |
| U | Unity Software Inc. | 1231 | 2024-02-29, 2025-02-21, 2026-02-11 | 2020-09-18 (424B4) | confirmed: 424B4 filed within 3 days |  |
| RBLX | Roblox Corp | 1231 | 2024-02-21, 2025-02-18, 2026-02-11 | 2021-03-10 (424B4) | confirmed: 424B4 filed within 3 days |  |
| COIN | Coinbase Global, Inc. | 1231 | 2024-02-15, 2025-02-13, 2026-02-12 | 2021-04-14 (424B4) | confirmed: 424B4 filed within 3 days |  |
| HOOD | Robinhood Markets, Inc. | 1231 | 2024-02-27, 2025-02-18, 2026-02-18 | 2021-07-30 (424B4) | confirmed: 424B4 filed within 3 days | 1 10-K/A on file |
| RIVN | Rivian Automotive, Inc. / DE | 1231 | 2024-02-26, 2025-02-24, 2026-02-12 | 2021-11-12 (424B4) | confirmed: 424B4 filed within 3 days |  |
| DUOL | Duolingo, Inc. | 1231 | 2024-02-29, 2025-02-28, 2026-02-27 | 2021-07-28 (424B4) | confirmed: 424B4 filed within 3 days |  |
| BMBL | Bumble Inc. | 1231 | 2024-02-28, 2025-02-28, 2026-03-16 | 2021-02-12 (424B4) | confirmed: 424B4 filed within 3 days |  |
| SNAP | Snap Inc | 1231 | 2024-02-07, 2025-02-05, 2026-02-05 | 2017-03-03 (424B4) | confirmed: 424B4 filed within 3 days |  |
| XYZ | Block, Inc. | 1231 | 2024-02-22, 2025-02-24, 2026-02-26 | 2015-11-19 (424B4) | confirmed: 424B4 filed within 3 days |  |
| TWLO | TWILIO INC | 1231 | 2024-02-27, 2025-02-26, 2026-02-24 | 2016-06-23 (424B4) | confirmed: 424B4 filed within 3 days | 1 10-K/A on file |
| DOCU | DOCUSIGN, INC. | 0131 | 2024-03-21, 2025-03-18, 2026-03-18 | 2018-04-27 (424B4) | confirmed: 424B4 filed within 3 days |  |
| ETSY | ETSY INC | 1231 | 2024-02-22, 2025-02-19, 2026-02-19 | 2015-04-16 (424B4) | confirmed: 424B4 filed within 3 days |  |

## Section extraction: 404/404 succeeded

- 10-K business: 120 ok, 0 failed
- 10-K mda: 120 ok, 0 failed
- 10-K risk_factors: 120 ok, 0 failed
- S-1 business: 22 ok, 0 failed
- S-1 risk_factors: 22 ok, 0 failed

## Revenue tags in the data (annual, USD)

Which revenue-like us-gaap concepts each company used. Feeds the `revenue` view.

| concept | companies | fiscal years |
|---|---|---|
| RevenueFromContractWithCustomerExcludingAssessedTax | 33 | 2016–2026 |
| ContractWithCustomerLiabilityRevenueRecognized | 29 | 2017–2026 |
| CostOfRevenue | 24 | 2007–2026 |
| Revenues | 23 | 2007–2026 |
| IncreaseDecreaseInDeferredRevenue | 20 | 2007–2026 |
| BusinessAcquisitionsProFormaRevenue | 14 | 2010–2023 |
| SalesRevenueNet | 11 | 2007–2018 |
| SalesRevenueServicesNet | 8 | 2007–2018 |
| SalesRevenueGoodsNet | 8 | 2007–2017 |
| DeferredRevenueRevenueRecognized1 | 5 | 2016–2023 |
| EntityWideDisclosureOnGeographicAreasRevenueFromExternalCustomersAttributedToForeignCountries | 4 | 2008–2013 |
| EntityWideDisclosureOnGeographicAreasRevenueFromExternalCustomersAttributedToEntitysCountryOfDomicile | 4 | 2008–2013 |
| SubscriptionRevenue | 3 | 2008–2018 |
| LicenseAndServicesRevenue | 3 | 2010–2018 |
| LicensesRevenue | 3 | 2008–2017 |
| OperatingLeasesIncomeStatementSubleaseRevenue | 3 | 2008–2019 |
| RevenueFromContractWithCustomerIncludingAssessedTax | 3 | 2017–2026 |

Revenue view coverage, latest annual period per company:

| ticker | fiscal_year | source_concept | value |
|---|---|---|---|
| AAPL | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 478,834,000,000 |
| ABNB | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 12,241,000,000 |
| ADBE | 2025 | Revenues | 23,769,000,000 |
| ADSK | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 7,206,000,000 |
| AMD | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 34,639,000,000 |
| AMZN | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 716,924,000,000 |
| BMBL | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 965,658,000 |
| COIN | 2025 | Revenues | 7,181,325,000 |
| CRM | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 41,525,000,000 |
| CRWD | 2026 | RevenueFromContractWithCustomerIncludingAssessedTax | 4,812,005,000 |
| DASH | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 13,717,000,000 |
| DDOG | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 3,427,158,000 |
| DOCU | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 3,219,500,000 |
| DUOL | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 1,037,589,000 |
| ETSY | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 2,883,501,000 |
| GOOGL | 2025 | Revenues | 402,836,000,000 |
| HOOD | 2025 | Revenues | 4,473,000,000 |
| INTC | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 52,853,000,000 |
| INTU | 2026 | Revenues | 21,448,000,000 |
| LYFT | 2025 | Revenues | 6,316,261,000 |
| META | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 200,966,000,000 |
| MSFT | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 331,839,000,000 |
| NFLX | 2025 | Revenues | 45,183,036,000 |
| NOW | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 13,278,000,000 |
| NVDA | 2026 | Revenues | 215,938,000,000 |
| ORCL | 2026 | Revenues | 67,357,000,000 |
| PINS | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 4,221,767,000 |
| PLTR | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 4,475,446,000 |
| QCOM | 2026 | Revenues | 43,120,000,000 |
| RBLX | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 4,890,551,000 |
| RIVN | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 5,387,000,000 |
| SNAP | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 5,931,447,000 |
| SNOW | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 4,683,946,000 |
| TSLA | 2025 | Revenues | 94,827,000,000 |
| TWLO | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 5,067,220,000 |
| U | 2025 | RevenueFromContractWithCustomerExcludingAssessedTax | 1,849,648,000 |
| UBER | 2025 | Revenues | 52,017,000,000 |
| WDAY | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 9,552,000,000 |
| XYZ | 2025 | Revenues | 24,193,683,000 |
| ZM | 2026 | RevenueFromContractWithCustomerExcludingAssessedTax | 4,868,769,000 |
