import json

from scrapy.exceptions import CloseSpider

from ..items import JobItem
from ..parsers import build_monster_payload, extract_monster_fingerprint, parse_monster_job
from .base import BaseJobSpider

PAGE_SIZE = 9


class MonsterSpider(BaseJobSpider):
    """Monster.com via its JSON search API.

    Flow: load the search page once to read the client auth key from
    ``__NEXT_DATA__`` -> POST one API request per keyword/location -> paginate by
    ``offset`` until the result set, the page cap or the known-job cap is reached.
    """

    name = "monster"
    source = "monster.com"

    def start_requests(self):
        if not self.settings.get("MONSTER_API_KEY"):
            raise CloseSpider("MONSTER_API_KEY is not set (see .env.example)")
        yield self.make_request(
            self.settings.get("MONSTER_START_URL"), callback=self.parse_start, dont_filter=True
        )

    def parse_start(self, response):
        raw = response.css("#__NEXT_DATA__::text").get()
        fingerprint = extract_monster_fingerprint(json.loads(raw)) if raw else None
        if not fingerprint:
            raise CloseSpider("could not find the client auth key on the Monster page")
        for keyword, location in self.queries():
            yield self.search_request(keyword, location, offset=0, page=1, known=0, fingerprint=fingerprint)

    def search_request(self, keyword, location, offset, page, known, fingerprint):
        payload = build_monster_payload(keyword, location, offset, fingerprint, PAGE_SIZE)
        url = f"{self.settings.get('MONSTER_API_URL')}?apikey={self.settings.get('MONSTER_API_KEY')}"
        return self.make_request(
            url,
            callback=self.parse_listings,
            method="POST",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json; charset=UTF-8", "Origin": "https://www.monster.com"},
            params={"render_js": False},
            dont_filter=True,
            meta={
                "keyword": keyword, "location": location, "offset": offset,
                "page": page, "known": known, "fingerprint": fingerprint,
            },
        )

    def parse_listings(self, response):
        meta = response.meta
        data = json.loads(response.text)
        known = meta["known"]

        for result in data.get("jobResults", []):
            job = parse_monster_job(result)
            if self.is_known(job["source_id"]):
                known += 1
                continue
            job.update(keyword=meta["keyword"], search_location=meta["location"])
            yield JobItem(**job)

        next_offset = meta["offset"] + PAGE_SIZE
        total = int(data.get("estimatedTotalSize") or 0)
        if known < self.max_known and total > next_offset and meta["page"] < self.max_pages:
            yield self.search_request(
                meta["keyword"], meta["location"], next_offset, meta["page"] + 1, known, meta["fingerprint"]
            )
