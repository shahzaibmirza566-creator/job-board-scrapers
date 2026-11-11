"""Scrapy settings.

Every secret and environment-specific value is read from environment variables
(optionally loaded from a local ``.env`` file). Nothing sensitive is hard-coded.
See ``.env.example`` for the full list.
"""
import os

try:  # optional convenience: load a local .env file if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BOT_NAME = "jobscrapers"
SPIDER_MODULES = ["jobscrapers.spiders"]
NEWSPIDER_MODULE = "jobscrapers.spiders"

# --- Politeness -------------------------------------------------------------
ROBOTSTXT_OBEY = _env_bool("ROBOTSTXT_OBEY", True)
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "6"))
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "0.5"))
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 30.0
RETRY_TIMES = 3
COOKIES_ENABLED = False
HTTPERROR_ALLOW_ALL = False

DEFAULT_REQUEST_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
}
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

# --- Optional rendering / proxy provider (ScrapingBee) ----------------------
# Leave empty to use plain Scrapy requests.
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY", "")
if SCRAPINGBEE_API_KEY:
    DOWNLOADER_MIDDLEWARES = {"scrapy_scrapingbee.ScrapingBeeMiddleware": 725}

# --- Storage ----------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "data/jobs.db")

ITEM_PIPELINES = {
    "jobscrapers.pipelines.CleanTextPipeline": 100,
    "jobscrapers.pipelines.SqliteJobPipeline": 300,
}

# --- Crawl limits -----------------------------------------------------------
# Stop paginating a query after this many already-seen jobs (incremental crawls).
MAX_KNOWN_JOBS_PER_QUERY = int(os.getenv("MAX_KNOWN_JOBS_PER_QUERY", "80"))
# Hard cap on listing pages per keyword/location pair.
MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))

# --- Source-specific configuration -------------------------------------------
# Monster's web client sends a public key with its search requests. Copy it from
# your browser's network tab (it is intentionally not committed here).
MONSTER_API_KEY = os.getenv("MONSTER_API_KEY", "")
MONSTER_START_URL = "https://www.monster.com/jobs/search"
MONSTER_API_URL = (
    "https://appsapi.monster.io/jobs-svx-service/v2/monster/search-jobs/samsearch/en-US"
)
ZIPRECRUITER_SEARCH_URL = (
    "https://www.ziprecruiter.com/candidate/search"
    "?days=1&radius=100&no_header_footer=1&location={location}&page={page}&search={keyword}"
)

# Default queries when none are passed with -a keywords=... -a locations=...
DEFAULT_KEYWORDS = ["python developer"]
DEFAULT_LOCATIONS = ["Texas"]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
