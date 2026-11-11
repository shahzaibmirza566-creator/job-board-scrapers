# job-board-scrapers

[![CI](https://github.com/shahzaibmirza566-creator/job-board-scrapers/actions/workflows/ci.yml/badge.svg)](https://github.com/shahzaibmirza566-creator/job-board-scrapers/actions/workflows/ci.yml)

Incremental job-listing crawlers for **ZipRecruiter** and **Monster**, built with Scrapy.
A reference implementation of a production pattern I use for recurring scraping jobs:
crawl daily, **never re-fetch what you already have**, and store everything in one normalised schema.

## What it demonstrates

- **Incremental crawling.** A SQLite store with `UNIQUE(source, source_id)` is checked *before* a
  detail page is requested, so a daily run only fetches new jobs. Pagination stops after
  `MAX_KNOWN_JOBS_PER_QUERY` already-seen jobs.
- **Two extraction styles in one project.** ZipRecruiter is HTML (listing cards + detail pages);
  Monster is a JSON search API whose client key is read from the page's `__NEXT_DATA__`.
- **Clean separation.** Parsing is pure functions in `parsers.py` (unit-tested without a network);
  spiders only orchestrate requests; the pipeline only persists.
- **Config from the environment.** No secrets in code. Optional ScrapingBee routing is switched on by
  setting one variable.
- **Tests + CI.** 22 tests (parsers, storage, pipeline, and spider flows with fabricated responses).

## Architecture

```
keywords x locations
        |
        v
   Spider (monster / ziprecruiter)
        |  skips jobs already in SQLite (JobStore.exists)
        v
   JobItem  -->  CleanTextPipeline  -->  SqliteJobPipeline  -->  data/jobs.db
                                              |
                                              +-- duplicates dropped + counted in crawl stats
```

```
jobscrapers/
  parsers.py     pure functions: payload builders, job/card parsers, salary formatting
  jobstore.py    SQLite store (idempotent inserts, existence checks)
  pipelines.py   text cleaning + persistence, stats: jobs/new, jobs/duplicate
  spiders/       base.py (queries, request factory) , monster.py , ziprecruiter.py
  settings.py    all configuration, read from environment variables
tests/           parser, store, pipeline and spider tests
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the values you need

# ZipRecruiter
scrapy crawl ziprecruiter -a keywords="python developer,data engineer" -a locations="Texas,California"

# Monster (needs MONSTER_API_KEY in .env)
scrapy crawl monster -a keywords="data engineer" -a locations="Texas" -a max_pages=5
```

Results are written to `data/jobs.db` (table `jobs`). Re-running the same command only adds new jobs.

```bash
sqlite3 data/jobs.db "select source, count(*) from jobs group by source;"
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SCRAPINGBEE_API_KEY` | Route requests through ScrapingBee (optional) | empty (plain Scrapy) |
| `MONSTER_API_KEY` | Public key Monster's web client sends (copy from the browser network tab) | required for `monster` |
| `DB_PATH` | SQLite file | `data/jobs.db` |
| `ROBOTSTXT_OBEY` | Respect robots.txt | `true` |
| `CONCURRENT_REQUESTS`, `DOWNLOAD_DELAY` | Politeness | `6`, `0.5` |
| `MAX_PAGES` | Hard cap of listing pages per query | `20` |
| `MAX_KNOWN_JOBS_PER_QUERY` | Stop paginating after this many already-seen jobs | `80` |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Notes and limitations

- This is a **portfolio/reference implementation** derived from a 2022 project. Site markup and
  private APIs change often, so selectors and endpoints may need updating before it works against
  the live sites today. The parsing and storage logic is covered by tests using fixtures.
- Use it responsibly: respect each site's terms of service and robots.txt, rate-limit your crawls,
  and handle any personal data in line with the law that applies to you.
- Client-specific integrations from the original project (a private job API, cloud screenshot upload,
  a proxy list) were removed on purpose; storage here is a local SQLite file.

## License

MIT
