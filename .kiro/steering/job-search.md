---
inclusion: always
---

# Job Search Bot — Project Conventions

## Project Overview

An automated job search pipeline that runs on a GitHub Actions hourly cron schedule. It fetches job postings from multiple sources, scores them for resume fit using Claude, generates tailored application materials for strong matches, and sends an email digest. It does **not** auto-submit applications.

## Architecture

The project is a small, flat Python scripts with no framework. Key files:

- `config.py` — all user-tunable settings and secrets (via environment variables)
- `db.py` — SQLite helpers for dedup tracking, metadata, and result persistence
- `discovery.py` — job fetching from Greenhouse, Lever, and JSearch (RapidAPI)
- `main.py` — orchestrator: fetch → score → generate materials → email digest
- `resume.txt` — plain-text resume used as context for Claude scoring/generation
- `hourly.yml` — GitHub Actions workflow (schedule + `jobs.db` commit back to repo)

## Data Model

SQLite database at `jobs.db` with two tables:

- `jobs`: `job_id` (PK), `title`, `company`, `url`, `score` (0–100), `status`, `reasoning`, `materials`, `seen_at`
- `meta`: key/value store — currently used to track `jsearch_last_run` timestamp

Job IDs are prefixed by source: `gh_` (Greenhouse), `lv_` (Lever), `js_` (JSearch).

## Job Sources

| Source | Cadence | Rate Limit | Notes |
|--------|---------|------------|-------|
| Greenhouse API | Every run | Unlimited/free | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Lever API | Every run | Unlimited/free | `api.lever.co/v0/postings/{slug}` |
| Apify multi-board | Every `APIFY_INTERVAL_HOURS` (default 6h) | Pay-per-result ($0.003/job) | Actor `openclawai/job-board-scraper` — LinkedIn, Indeed, Glassdoor simultaneously |
| JSearch (RapidAPI) | Every `JSEARCH_INTERVAL_HOURS` (default 6h) | 200 req/month free tier | Aggregates Google for Jobs → LinkedIn, Indeed, Glassdoor, etc. |

Apify rate-limiting is enforced via the `apify_last_run` meta key. JSearch rate-limiting is enforced via `jsearch_last_run`. Do not bypass either guard.

## Configuration (`config.py`)

All user-facing settings live here. Never hardcode secrets — always read from `os.environ.get(...)`.

Key settings:
- `APIFY_API_KEY` — Apify API token; gates the Apify source
- `APIFY_SEARCH_TERMS` — list of queries for the Apify multi-board scraper; each runs across all `APIFY_JOB_BOARDS`
- `APIFY_JOB_BOARDS` — boards to scrape (`linkedin`, `indeed`, `glassdoor`, `google`, `zip_recruiter`); default is LinkedIn + Indeed + Glassdoor
- `APIFY_MAX_RESULTS` — max results per board per search term (default 20); controls cost
- `APIFY_INTERVAL_HOURS` — cadence for Apify runs (default 6h); raise to cut costs
- `JSEARCH_QUERIES` — list of search strings; each entry = 1 API request per JSearch run. Keep short.
- `JSEARCH_INTERVAL_HOURS` — default 6 to stay inside the 200 req/month free tier
- `GREENHOUSE_COMPANIES` / `LEVER_COMPANIES` — list of ATS slugs to poll directly
- `KEYWORDS` — secondary filter applied to all results regardless of source (case-insensitive)
- `SCORE_THRESHOLD` — jobs scoring below this (0–100) are stored but not emailed or given tailored materials
- `GEMINI_API_KEY` — Gemini API key for scoring and material generation (free tier)
- `MODEL` — Gemini model (currently `gemini-2.0-flash`; 1,500 free req/day)

## Code Style

- Python 3.11, standard library + `requests` + `google-genai` SDK
- Use `contextlib.closing` with `sqlite3.connect` for all DB connections (see `db.py` pattern)
- Prefer `ON CONFLICT ... DO UPDATE` (upsert) for all DB writes to stay idempotent
- All external HTTP calls include a `timeout` parameter
- Errors from individual company fetches are caught and logged with `print(...)` — never let one source failure abort the full run
- No logging framework; `print()` is intentional for GitHub Actions log output

## Adding a New Job Source

1. Add a `fetch_<source>(...)` function in `discovery.py` returning a list of dicts with keys: `id`, `title`, `company`, `url`, `text`
2. Prefix `id` with a unique short source code (e.g., `wb_` for Workable)
3. Call it inside `fetch_new_postings()` with a try/except that prints on failure
4. Add any required config keys to `config.py` with `os.environ.get(...)` for secrets

## Secrets

All secrets are environment variables. In production they come from GitHub Actions secrets:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini API for job scoring and material generation (free tier) |
| `APIFY_API_KEY` | Apify multi-board job scraper |
| `ANTHROPIC_API_KEY` | No longer used — migrated to Gemini |
| `GMAIL_ADDRESS` | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail app password (not account password) |
| `RAPIDAPI_KEY` | JSearch via RapidAPI |

## GitHub Actions Workflow

- Runs on `cron: '0 * * * *'` (every hour, UTC) plus `workflow_dispatch` for manual triggers
- After `main.py` completes, commits `jobs.db` back to the repo with `[skip ci]` to persist dedup state between runs
- Requires `permissions: contents: write`

## Key Constraints

- Do not add auto-application submission logic to `main.py` — that belongs in a separate module
- Do not lower `APIFY_INTERVAL_HOURS` without considering cost; default 6h ≈ ~$65/month at default settings
- Do not lower `JSEARCH_INTERVAL_HOURS` below what the query count supports on the free tier (200 req/month)
- `jobs.db` is the source of truth for seen jobs; `apify_last_run` and `jsearch_last_run` meta keys guard rate limits — never bypass them
- Apify job IDs are prefixed `ap_<board>_<hash>` — hash is derived from the job URL to remain stable across runs
- Resume content (`resume.txt`) is passed as context to Claude — keep it plain text
