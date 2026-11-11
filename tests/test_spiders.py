"""Spider-level tests using fabricated responses (no network access)."""
import json

from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.utils.test import get_crawler

from jobscrapers.spiders.monster import MonsterSpider
from jobscrapers.spiders.ziprecruiter import ZipRecruiterSpider

SETTINGS = {
    "MONSTER_API_KEY": "test-key",
    "MONSTER_API_URL": "https://api.example.test/search",
    "MONSTER_START_URL": "https://www.example.test/jobs",
    "ZIPRECRUITER_SEARCH_URL": "https://zip.example.test/search?location={location}&page={page}&search={keyword}",
    "DEFAULT_KEYWORDS": ["python developer"],
    "DEFAULT_LOCATIONS": ["Texas"],
    "MAX_PAGES": 3,
    "MAX_KNOWN_JOBS_PER_QUERY": 2,
}


def make_spider(spider_cls, tmp_path, **kwargs):
    settings = dict(SETTINGS, DB_PATH=str(tmp_path / "jobs.db"))
    crawler = get_crawler(spider_cls, settings)
    return spider_cls.from_crawler(crawler, **kwargs)


def json_response(spider, body, **meta):
    request = Request("https://api.example.test/search", meta=meta)
    return TextResponse(request.url, body=json.dumps(body), encoding="utf-8", request=request)


def monster_job(job_id):
    return {"jobId": job_id, "jobPosting": {"title": f"Job {job_id}", "url": f"https://x.test/{job_id}"}}


MONSTER_META = {"keyword": "python", "location": "Texas", "offset": 0, "page": 1, "known": 0, "fingerprint": "fp"}


def test_queries_come_from_spider_arguments(tmp_path):
    spider = make_spider(MonsterSpider, tmp_path, keywords="a, b", locations="X")
    assert list(spider.queries()) == [("a", "X"), ("b", "X")]


def test_queries_fall_back_to_settings_defaults(tmp_path):
    spider = make_spider(MonsterSpider, tmp_path)
    assert list(spider.queries()) == [("python developer", "Texas")]


def test_monster_yields_new_jobs_and_paginates(tmp_path):
    spider = make_spider(MonsterSpider, tmp_path)
    body = {"jobResults": [monster_job(1), monster_job(2)], "estimatedTotalSize": 100}
    output = list(spider.parse_listings(json_response(spider, body, **MONSTER_META)))

    items = [o for o in output if not isinstance(o, Request)]
    requests = [o for o in output if isinstance(o, Request)]
    assert [i["source_id"] for i in items] == ["1", "2"]
    assert all(i["keyword"] == "python" and i["search_location"] == "Texas" for i in items)
    assert len(requests) == 1  # next page
    assert json.loads(requests[0].body)["offset"] == 9


def test_monster_skips_known_jobs_and_stops_at_cap(tmp_path):
    spider = make_spider(MonsterSpider, tmp_path)
    spider.store.add({"source": "monster.com", "source_id": "1"})
    spider.store.add({"source": "monster.com", "source_id": "2"})

    body = {"jobResults": [monster_job(1), monster_job(2), monster_job(3)], "estimatedTotalSize": 100}
    output = list(spider.parse_listings(json_response(spider, body, **MONSTER_META)))

    items = [o for o in output if not isinstance(o, Request)]
    requests = [o for o in output if isinstance(o, Request)]
    assert [i["source_id"] for i in items] == ["3"]  # 1 and 2 already stored
    assert requests == []  # 2 known jobs hit MAX_KNOWN_JOBS_PER_QUERY -> stop paginating


def test_monster_stops_on_last_page(tmp_path):
    spider = make_spider(MonsterSpider, tmp_path)
    body = {"jobResults": [monster_job(1)], "estimatedTotalSize": 5}
    output = list(spider.parse_listings(json_response(spider, body, **MONSTER_META)))
    assert not any(isinstance(o, Request) for o in output)


CARD = """
<article class="job_result" data-listing-version-key="{id}">
  <a class="job_link" href="https://zip.example.test/jobs/{id}"><span class="just_job_title">Job {id}</span></a>
</article>
"""


def zip_response(card_ids):
    request = Request("https://zip.example.test/search", meta={"keyword": "python", "location": "Texas", "page": 1, "known": 0})
    html = "<html><body>" + "".join(CARD.format(id=i) for i in card_ids) + "</body></html>"
    return HtmlResponse(request.url, body=html, encoding="utf-8", request=request)


def test_ziprecruiter_requests_details_only_for_unknown_jobs(tmp_path):
    spider = make_spider(ZipRecruiterSpider, tmp_path)
    spider.store.add({"source": "ziprecruiter.com", "source_id": "a1"})

    requests = list(spider.parse_listings(zip_response(["a1", "a2", "a3"])))
    assert [r.url for r in requests] == [
        "https://zip.example.test/jobs/a2",
        "https://zip.example.test/jobs/a3",
    ]  # known job skipped; fewer than 8 cards -> no next page


def test_ziprecruiter_paginates_on_full_page(tmp_path):
    spider = make_spider(ZipRecruiterSpider, tmp_path)
    requests = list(spider.parse_listings(zip_response([f"j{i}" for i in range(10)])))
    next_pages = [r for r in requests if "search?" in r.url]
    assert len(next_pages) == 1
    assert "page=2" in next_pages[0].url


def test_ziprecruiter_detail_builds_item(tmp_path):
    spider = make_spider(ZipRecruiterSpider, tmp_path)
    job = {"source": "ziprecruiter.com", "source_id": "a2", "title": "Job a2", "url": "https://zip.example.test/jobs/a2"}
    request = Request(job["url"], meta={"job": job})
    html = '<div class="jobDescriptionSection"><p>Full  description</p></div>'
    response = HtmlResponse(job["url"], body=html, encoding="utf-8", request=request)
    (item,) = list(spider.parse_detail(response))
    assert item["description"] == "Full description"
    assert item["source_id"] == "a2"
