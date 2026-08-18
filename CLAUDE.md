# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Pre-processed, standardized CSV election results for California elections (part of the [OpenElections](https://github.com/openelections) project). Source material (PDFs, XLS, DBF files from county/state election offices) lives in the sibling repository `~/code/openelections-sources-ca`, organized by year and election type. This repository holds the *output*: cleaned CSVs plus the Python parsing code used to produce them from those sources.

## Commands


Use Python and uv for dependencies and to run scripts.

Run the unit test suite (compares statewide CSVs against the sum of their per-county CSVs for a fixed set of year/date/election_type combinations defined in `tests/test_data.py`):
```
pytest --tb=short --color=yes
```

Run a single parametrized case (year/date/election_type), e.g. 2016 general:
```
pytest tests/test_data.py -k "2016 and 1108"
```

Data-quality tests (duplicate entries, file format, missing values, vote breakdown totals) are NOT in this repo — they're run in CI from the external `openelections/openelections-data-tests` repo against this repo's CSVs (see `.github/workflows/data_tests.yml`). There's no local equivalent command; check that workflow if you need to reproduce those checks.

## Repository layout

- **Year directories** (`2002/`, `2004/`, ..., `2020/`, etc.) hold the actual data output, one directory per election year. Inside a year directory:
  - A statewide consolidated CSV per election, e.g. `20201103__ca__general__precinct.csv` or `20140603__ca__primary.csv`.
  - A `counties/` subdirectory (in more recent years) with one CSV per county per election, e.g. `counties/20201103__ca__general__alameda__precinct.csv`. Older years sometimes place per-county precinct files directly in the year directory instead of a `counties/` subfolder — check both when working with a given year.
  - File naming follows the OpenElections convention: `{YYYYMMDD}__ca__{election_type}__[county__]{precinct|county}.csv`, where `election_type` is `primary`, `general`, `special__primary`, or `special__general`.
  - Standard CSV columns: `county, precinct, office, district, candidate, party, votes`, with optional vote-breakdown columns (`early_voting`, `election_day`, `provisional`, `absentee`, `federal`, `mail`) appended when the source distinguishes vote types.
  - `tests/test_data.py` encodes the invariant that these files must satisfy: for each covered election, grouping the county-level files by `(candidate, county, district, office)` and summing `votes` must equal the same grouping/sum on the statewide file, restricted to that county.

- **`src/`** contains the parsing code, which is not a single unified pipeline but a collection of scripts written over time for different source formats and years:
  - `src/parse_general_YYYY.py` / `src/parse_primary_YYYY.py` / `src/parse_special_*_YYYY.py` — per-year, per-election-type entry-point scripts.
  - `src/clarity_parser.py` — parses Clarity Elections XML/ZIP result feeds (used for some states/counties that publish results via the Clarity platform) using the `clarify` and `requests` libraries.
  - `src/swdb/` — a separate pipeline for pulling and normalizing data from the [Statewide Database (SWDB)](http://statewidedatabase.org/), which publishes DBF/CSV precinct-level files by county. `swdb.py` builds source URLs and downloads/normalizes files per county (`county_dict` maps county names to SWDB's numeric codes); `parse.py` drives this across `ELECTIONS` and `COUNTIES` (from `util.py`) and writes one CSV per county; `codes.py` and `writeins.py` hold office/party code mappings and write-in candidate handling; `candidates/*.json` hold per-election candidate lists used to resolve names.
  - `src/table/` and `src/utils/` — shared helper packages used by the PDF-based parsers (notably `parse_general_2018.py`): `table.Table`/`table.Row` model the OpenElections row schema and handle CSV emission (including dropping vote-breakdown columns that are mostly empty); `utils` has string-cleaning, office-name standardization, and PDF-rotation helpers built on `tabula-py` and `PyPDF2` for parsing multi-column, sometimes vertically-oriented, tables out of PDFs. See `src/README.md` and `src/requirements.md` for the detailed, interactive-input-driven workflow this PDF parser expects (county name, election date, table layout parameters, etc.) — it was built for a specific set of 2018 county PDFs (Modoc, Plumas, Sonoma) and generalizes only to similarly-formatted PDFs.
  - There is no single "run everything" command — each script targets a specific year/election/source format and is typically run and adapted by hand against the corresponding files in `~/code/openelections-sources-ca`.

- **`utils.py`** (repo root) — ad hoc helper functions (`generate_headers`, `generate_offices`, `generate_consolidated_file`) for building a statewide consolidated CSV out of per-county precinct CSVs for a given year, keyed on a fixed list of accepted office names. Distinct from `src/utils/`.

- **`execute.sh`** — a one-off shell script (using `wget`/`lynx`/`curl`) that was used to bulk-download historical PDF/XLS source files from the CA Secretary of State site; not part of the regular parsing workflow.

## Working with new data

When adding results for a new election, follow the existing file-naming and column conventions above so the file lands correctly relative to `tests/test_data.py` (if you add a new year/date/election_type combination there) and the external `openelections-data-tests` checks. Cross-reference the corresponding source files in `~/code/openelections-sources-ca/{year}/` to confirm format (PDF, XLS, DBF, Clarity feed) before choosing which existing parser to adapt.
