import json
from urllib.parse import quote_plus

from ..items import JobItem
from ..parsers import (
    glassdoor_has_next,
    glassdoor_page_url,
    parse_glassdoor_cards,
    parse_glassdoor_job,
    parse_glassdoor_location_id,
)
from .base import BaseJobSpider


class GlassdoorSpider(BaseJobSpider):
    """Glassdoor: resolve each location to an id once, then page through listings.

    location autocomplete (once per location) -> listing pages per keyword ->
    detail pages for jobs that are not stored yet.
    """

    name = "glassdoor"
    source = "glassdoor.com"

    def start_requests(self):
        for location in self.locations:
            url = self.settings.get("GLASSDOOR_LOCATION_URL").format(location=quote_plus(location))
            yield self.make_request(
                url, callback=self.parse_location, params={"render_js": False}, meta={"location": location}
            )

    def parse_location(self, response):
        location = response.meta["location"]
        try:
            payload = json.loads(response.text or "[]")
        except ValueError:
            payload = []
        location_id = parse_glassdoor_location_id(payload)
        if not location_id:
            self.logger.warning("no Glassdoor location id found for %r", location)
            return
        for keyword in self.keywords:
            url = self.settings.get("GLASSDOOR_LISTING_URL").format(
                keyword=quote_plus(keyword), location_id=location_id
            )
            yield self.listing_request(glassdoor_page_url(url, 1), keyword, location, page=1, known=0)

    def listing_request(self, url, keyword, location, page, known):
        return self.make_request(
            url,
            callback=self.parse_listing,
            params={"render_js": False},
            dont_filter=True,
            meta={"keyword": keyword, "location": location, "page": page, "known": known},
        )

    def parse_listing(self, response):
        meta = response.meta
        known = meta["known"]

        for job_id, href in parse_glassdoor_cards(response):
            if self.is_known(job_id):
                known += 1
                continue
            yield self.make_request(
                response.urljoin(href),
                callback=self.parse_detail,
                params={"render_js": False},
                meta={"job_id": job_id, "keyword": meta["keyword"], "location": meta["location"]},
            )

        if glassdoor_has_next(response) and known < self.max_known and meta["page"] < self.max_pages:
            yield self.listing_request(
                glassdoor_page_url(response.url, meta["page"] + 1),
                meta["keyword"], meta["location"], meta["page"] + 1, known,
            )

    def parse_detail(self, response):
        job = parse_glassdoor_job(response, response.url, response.meta["job_id"])
        if job:
            job.update(keyword=response.meta["keyword"], search_location=response.meta["location"])
            yield JobItem(**job)
