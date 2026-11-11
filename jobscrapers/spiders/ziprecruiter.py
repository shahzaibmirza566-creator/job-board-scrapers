from ..items import JobItem
from ..parsers import (
    build_ziprecruiter_url,
    parse_ziprecruiter_card,
    parse_ziprecruiter_description,
)
from .base import BaseJobSpider

# A full listing page has ~10 cards; fewer means we reached the last page.
FULL_PAGE_THRESHOLD = 8


class ZipRecruiterSpider(BaseJobSpider):
    """ZipRecruiter listing pages -> job detail pages.

    Cards already present in the SQLite store are skipped *before* the detail
    request is made, which is where most of the saved bandwidth comes from on
    incremental (daily) runs.
    """

    name = "ziprecruiter"
    source = "ziprecruiter.com"

    def start_requests(self):
        for keyword, location in self.queries():
            yield self.listing_request(keyword, location, page=1, known=0)

    def listing_request(self, keyword, location, page, known):
        url = build_ziprecruiter_url(
            self.settings.get("ZIPRECRUITER_SEARCH_URL"), keyword, location, page
        )
        return self.make_request(
            url,
            callback=self.parse_listings,
            dont_filter=True,
            meta={"keyword": keyword, "location": location, "page": page, "known": known},
        )

    def parse_listings(self, response):
        meta = response.meta
        cards = response.css(".job_result")
        known = meta["known"]

        for card in cards:
            job = parse_ziprecruiter_card(card)
            if not job["source_id"] or not job["url"]:
                continue
            if self.is_known(job["source_id"]):
                known += 1
                continue
            job.update(keyword=meta["keyword"], search_location=meta["location"])
            yield self.make_request(
                job["url"], callback=self.parse_detail, meta={"job": job}, dont_filter=True
            )

        if known < self.max_known and len(cards) >= FULL_PAGE_THRESHOLD and meta["page"] < self.max_pages:
            yield self.listing_request(meta["keyword"], meta["location"], meta["page"] + 1, known)

    def parse_detail(self, response):
        job = response.meta["job"]
        job["description"] = parse_ziprecruiter_description(response)
        yield JobItem(**job)
