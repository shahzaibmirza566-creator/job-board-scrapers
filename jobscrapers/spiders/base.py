from __future__ import annotations

from typing import Iterable, List, Optional

import scrapy

from ..jobstore import JobStore

try:  # optional dependency: only needed when SCRAPINGBEE_API_KEY is set
    from scrapy_scrapingbee import ScrapingBeeRequest
except ImportError:  # pragma: no cover
    ScrapingBeeRequest = None


def _split(value: Optional[str], default: Iterable[str]) -> List[str]:
    if not value:
        return list(default)
    return [part.strip() for part in value.split(",") if part.strip()]


class BaseJobSpider(scrapy.Spider):
    """Shared behaviour for all job-board spiders.

    * Queries come from ``-a keywords="a,b" -a locations="X,Y"`` (or settings defaults).
    * ``make_request`` transparently uses ScrapingBee when an API key is configured.
    * ``is_known`` checks the SQLite store so already-scraped jobs are not re-fetched.
    * Pagination for a query stops after ``MAX_KNOWN_JOBS_PER_QUERY`` known jobs
      or ``MAX_PAGES`` pages, whichever comes first.
    """

    source = ""

    def __init__(self, keywords: str = None, locations: str = None, max_pages: str = None, **kwargs):
        super().__init__(**kwargs)
        self._keywords_arg = keywords
        self._locations_arg = locations
        self._max_pages_arg = max_pages
        self.store: Optional[JobStore] = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        settings = crawler.settings
        spider.keywords = _split(spider._keywords_arg, settings.getlist("DEFAULT_KEYWORDS"))
        spider.locations = _split(spider._locations_arg, settings.getlist("DEFAULT_LOCATIONS"))
        spider.max_pages = int(spider._max_pages_arg or settings.getint("MAX_PAGES", 20))
        spider.max_known = settings.getint("MAX_KNOWN_JOBS_PER_QUERY", 80)
        spider.use_scrapingbee = bool(settings.get("SCRAPINGBEE_API_KEY")) and ScrapingBeeRequest is not None
        spider.store = JobStore(settings.get("DB_PATH", "data/jobs.db"))
        return spider

    def closed(self, reason):
        if self.store:
            self.store.close()

    # -- helpers ----------------------------------------------------------- #
    def queries(self):
        """Every (keyword, location) pair to crawl."""
        for keyword in self.keywords:
            for location in self.locations:
                yield keyword, location

    def is_known(self, source_id: str) -> bool:
        return bool(source_id) and self.store.exists(self.source, source_id)

    def make_request(self, url: str, callback, **kwargs):
        """Build a request, routed through ScrapingBee when configured."""
        params = kwargs.pop("params", None)
        if self.use_scrapingbee:
            return ScrapingBeeRequest(url=url, callback=callback, params=params or {}, **kwargs)
        return scrapy.Request(url=url, callback=callback, **kwargs)
