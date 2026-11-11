from ..items import JobItem
from ..parsers import (
    build_indeed_url,
    find_indeed_next_page,
    parse_indeed_card,
    parse_indeed_descriptions,
)
from .base import BaseJobSpider


class IndeedSpider(BaseJobSpider):
    """Indeed results pages + the batch ``jobdescs`` endpoint.

    Listing cards carry no description, so unknown job ids on a page are collected
    and their descriptions fetched in **one** request per page instead of one per job.
    """

    name = "indeed"
    source = "indeed.com"

    def start_requests(self):
        for keyword, location in self.queries():
            url = build_indeed_url(self.settings.get("INDEED_LISTING_URL"), keyword, location)
            yield self.listing_request(url, keyword, location, page=1, known=0)

    def listing_request(self, url, keyword, location, page, known):
        return self.make_request(
            url,
            callback=self.parse_listings,
            dont_filter=True,
            meta={"keyword": keyword, "location": location, "page": page, "known": known},
        )

    def parse_listings(self, response):
        meta = response.meta
        known = meta["known"]
        pending = {}

        for card in response.css("div.tapItem"):
            job = parse_indeed_card(card, response.url)
            if not job["source_id"]:
                continue
            if self.is_known(job["source_id"]):
                known += 1
                continue
            job.update(keyword=meta["keyword"], search_location=meta["location"])
            pending[job["source_id"]] = job

        if pending:
            url = self.settings.get("INDEED_DESCRIPTION_URL").format(ids=",".join(pending))
            yield self.make_request(url, callback=self.parse_descriptions, meta={"jobs": pending})

        next_page = find_indeed_next_page(response)
        if next_page and known < self.max_known and meta["page"] < self.max_pages:
            yield self.listing_request(
                response.urljoin(next_page), meta["keyword"], meta["location"], meta["page"] + 1, known
            )

    def parse_descriptions(self, response):
        descriptions = parse_indeed_descriptions(response.text)
        for job_id, job in response.meta["jobs"].items():
            job["description"] = descriptions.get(job_id, "")
            yield JobItem(**job)
