"""Parser and spider tests for the Indeed and Glassdoor sources (no network)."""
import json

from scrapy import Selector
from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.utils.test import get_crawler

from jobscrapers.parsers import (
    build_indeed_url,
    find_indeed_next_page,
    glassdoor_has_next,
    glassdoor_page_url,
    parse_glassdoor_cards,
    parse_glassdoor_job,
    parse_glassdoor_location_id,
    parse_indeed_card,
    parse_indeed_descriptions,
)
from jobscrapers.spiders.glassdoor import GlassdoorSpider
from jobscrapers.spiders.indeed import IndeedSpider

# ------------------------------- Indeed parsers -------------------------------
CARD = """
<div class="tapItem">
  <h2 class="jobTitle"><a data-jk="jk1" href="/rc/clk?jk=jk1"><span title=" Data Engineer ">Data Engineer</span></a></h2>
  <span class="companyName"><a>Initech</a></span>
  <div class="companyLocation"><span>Austin, TX</span></div>
  <div><svg aria-label="Job type"></svg><span>Full-time</span></div>
  <div class="job-snippet"><ul><li>Build  pipelines</li></ul></div>
</div>
"""


def test_parse_indeed_card():
    card = Selector(text=CARD).css("div.tapItem")[0]
    job = parse_indeed_card(card, "https://www.indeed.com/jobs?q=x")
    assert job["source"] == "indeed.com"
    assert job["source_id"] == "jk1"
    assert job["title"] == "Data Engineer"
    assert job["company"] == "Initech"
    assert job["location"] == "Austin, TX"
    assert job["summary"] == "Build pipelines"
    assert job["url"] == "https://www.indeed.com/rc/clk?jk=jk1"


def test_indeed_card_fields_do_not_leak_between_cards():
    # An absolute XPath would read the *first* card's job type for every card.
    html = CARD + CARD.replace("jk1", "jk2").replace("Full-time", "Contract")
    cards = Selector(text=html).css("div.tapItem")
    assert parse_indeed_card(cards[0])["employment_type"] == "Full-time"
    assert parse_indeed_card(cards[1])["employment_type"] == "Contract"


def test_indeed_url_and_next_page_fallbacks():
    template = "https://x.test/jobs?q={keyword}&l={location}"
    assert build_indeed_url(template, "data engineer", "New York") == "https://x.test/jobs?q=data+engineer&l=New+York"
    assert find_indeed_next_page(Selector(text='<a aria-label="Next Page" href="/p2"></a>')) == "/p2"
    assert find_indeed_next_page(Selector(text='<a data-testid="pagination-page-next" href="/p3"></a>')) == "/p3"
    assert find_indeed_next_page(Selector(text="<div></div>")) is None


def test_parse_indeed_descriptions_handles_bad_payloads():
    assert parse_indeed_descriptions('{"jk1": "<p>Hello <b>world</b></p>"}') == {"jk1": "Hello world"}
    assert parse_indeed_descriptions("not json") == {}
    assert parse_indeed_descriptions("[1, 2]") == {}


# ----------------------------- Glassdoor parsers ------------------------------
def test_glassdoor_location_id_picks_state_level():
    payload = [
        {"locationType": "C", "locationId": 1},
        {"locationType": "S", "locationId": 2278},
    ]
    assert parse_glassdoor_location_id(payload) == "2278"
    assert parse_glassdoor_location_id([]) is None
    assert parse_glassdoor_location_id({"not": "a list"}) is None


def test_glassdoor_cards_and_pagination_flags():
    html = (
        '<li class="react-job-listing" data-id="g1"><a class="jobLink" href="/job/1"></a></li>'
        '<li class="react-job-listing" data-id="g2"></li>'  # no link -> ignored
        '<button class="nextButton"></button>'
    )
    page = Selector(text=html)
    assert parse_glassdoor_cards(page) == [("g1", "/job/1")]
    assert glassdoor_has_next(page) is True
    assert glassdoor_has_next(Selector(text='<button class="nextButton" disabled></button>')) is False
    assert glassdoor_has_next(Selector(text="<div></div>")) is False


def test_glassdoor_page_url_rewrites_page_and_keeps_query():
    url = "https://www.glassdoor.com/Job/jobs.htm?sc.keyword=python&locT=S&locId=2278"
    first = glassdoor_page_url(url, 1)
    assert "/Job/jobs_IP1.htm?" in first and "sc.keyword=python" in first and "fromAge=1" in first
    third = glassdoor_page_url(first, 3)
    assert "/Job/jobs_IP3.htm?" in third
    assert third.count("fromAge") == 1  # not duplicated on the second rewrite


def test_glassdoor_job_from_embedded_json():
    cache = {"initialState": {"jlData": {
        "header": {
            "jobTitleText": "Backend Engineer",
            "employerNameFromSearch": "Hooli",
            "locationName": "Remote",
            "jobTypeKeys": ["jobtype.fulltime"],
        },
        "job": {"description": "<p>Write <b>Python</b></p>"},
    }}}
    html = f"<html><script>window.appCache={json.dumps(cache)};</script><div><span class='small'>$120k</span></div></html>"
    job = parse_glassdoor_job(Selector(text=html), "https://gd.test/job/1", "g1")
    assert job["title"] == "Backend Engineer"
    assert job["company"] == "Hooli"
    assert job["employment_type"] == "fulltime"
    assert job["description"] == "Write Python"
    assert job["source_id"] == "g1" and job["source"] == "glassdoor.com"


def test_glassdoor_job_html_fallback_and_empty():
    html = (
        '<div class="css-17x2pwl"> Data Analyst </div><div class="css-16nw49e">Umbrella</div>'
        '<div class="desc"><p>Analyse</p><p>data</p></div>'
    )
    job = parse_glassdoor_job(Selector(text=html), "u", "g2")
    assert (job["title"], job["company"], job["description"]) == ("Data Analyst", "Umbrella", "Analyse data")
    assert parse_glassdoor_job(Selector(text="<div></div>"), "u", "g3") is None


def test_glassdoor_job_survives_broken_json():
    html = "<script>window.appCache={broken;</script><div class='css-17x2pwl'>Fallback Title</div>"
    assert parse_glassdoor_job(Selector(text=html), "u", "g4")["title"] == "Fallback Title"


# --------------------------------- spiders ------------------------------------
SETTINGS = {
    "INDEED_LISTING_URL": "https://indeed.example.test/jobs?q={keyword}&l={location}",
    "INDEED_DESCRIPTION_URL": "https://indeed.example.test/jobdescs?jks={ids}",
    "GLASSDOOR_LOCATION_URL": "https://gd.example.test/locations?term={location}",
    "GLASSDOOR_LISTING_URL": "https://gd.example.test/Job/jobs.htm?sc.keyword={keyword}&locT=S&locId={location_id}",
    "DEFAULT_KEYWORDS": ["python"],
    "DEFAULT_LOCATIONS": ["Texas"],
    "MAX_PAGES": 3,
    "MAX_KNOWN_JOBS_PER_QUERY": 2,
}


def make_spider(spider_cls, tmp_path, **kwargs):
    crawler = get_crawler(spider_cls, dict(SETTINGS, DB_PATH=str(tmp_path / "jobs.db")))
    return spider_cls.from_crawler(crawler, **kwargs)


def indeed_page(cards_html, extra=""):
    request = Request(
        "https://indeed.example.test/jobs?q=python&l=Texas",
        meta={"keyword": "python", "location": "Texas", "page": 1, "known": 0},
    )
    body = f"<html>{cards_html}{extra}</html>"
    return HtmlResponse(request.url, body=body, encoding="utf-8", request=request)


def indeed_card(job_id):
    return CARD.replace("jk1", job_id)


def test_indeed_batches_unknown_ids_into_one_description_request(tmp_path):
    spider = make_spider(IndeedSpider, tmp_path)
    spider.store.add({"source": "indeed.com", "source_id": "old"})
    page = indeed_page(indeed_card("old") + indeed_card("new1") + indeed_card("new2"),
                       '<a aria-label="Next Page" href="/jobs?start=10"></a>')
    requests = list(spider.parse_listings(page))

    description_requests = [r for r in requests if "jobdescs" in r.url]
    assert len(description_requests) == 1
    assert description_requests[0].url.endswith("jks=new1,new2")  # "old" excluded
    assert sum("start=10" in r.url for r in requests) == 1  # next page requested


def test_indeed_stops_paginating_at_known_cap(tmp_path):
    spider = make_spider(IndeedSpider, tmp_path)
    for job_id in ("a", "b"):
        spider.store.add({"source": "indeed.com", "source_id": job_id})
    page = indeed_page(indeed_card("a") + indeed_card("b"),
                       '<a aria-label="Next Page" href="/jobs?start=10"></a>')
    assert list(spider.parse_listings(page)) == []  # nothing new, cap reached


def test_indeed_descriptions_become_items(tmp_path):
    spider = make_spider(IndeedSpider, tmp_path)
    jobs = {"jk1": {"source": "indeed.com", "source_id": "jk1", "title": "Data Engineer"}}
    request = Request("https://indeed.example.test/jobdescs?jks=jk1", meta={"jobs": jobs})
    response = TextResponse(request.url, body='{"jk1": "<p>Great role</p>"}', encoding="utf-8", request=request)
    (item,) = list(spider.parse_descriptions(response))
    assert item["description"] == "Great role" and item["source_id"] == "jk1"


def test_glassdoor_resolves_location_then_requests_each_keyword(tmp_path):
    spider = make_spider(GlassdoorSpider, tmp_path, keywords="python, go")
    request = Request("https://gd.example.test/locations?term=Texas", meta={"location": "Texas"})
    body = json.dumps([{"locationType": "S", "locationId": 2278}])
    response = TextResponse(request.url, body=body, encoding="utf-8", request=request)
    urls = [r.url for r in spider.parse_location(response)]
    assert len(urls) == 2
    assert all("locId=2278" in u and "jobs_IP1.htm" in u for u in urls)


def test_glassdoor_unknown_location_yields_nothing(tmp_path):
    spider = make_spider(GlassdoorSpider, tmp_path)
    request = Request("https://gd.example.test/locations?term=Nowhere", meta={"location": "Nowhere"})
    response = TextResponse(request.url, body="[]", encoding="utf-8", request=request)
    assert list(spider.parse_location(response)) == []


def test_glassdoor_listing_skips_known_jobs_and_paginates(tmp_path):
    spider = make_spider(GlassdoorSpider, tmp_path)
    spider.store.add({"source": "glassdoor.com", "source_id": "g-old"})
    request = Request(
        "https://gd.example.test/Job/jobs_IP1.htm?sc.keyword=python&locT=S&locId=2278&fromAge=1&radius=100",
        meta={"keyword": "python", "location": "Texas", "page": 1, "known": 0},
    )
    html = (
        '<li class="react-job-listing" data-id="g-old"><a class="jobLink" href="/job/old"></a></li>'
        '<li class="react-job-listing" data-id="g-new"><a class="jobLink" href="/job/new"></a></li>'
        '<button class="nextButton"></button>'
    )
    response = HtmlResponse(request.url, body=html, encoding="utf-8", request=request)
    requests = list(spider.parse_listing(response))
    assert [r.url for r in requests if "/job/" in r.url] == ["https://gd.example.test/job/new"]
    assert sum("jobs_IP2.htm" in r.url for r in requests) == 1


def test_glassdoor_detail_yields_item_with_search_context(tmp_path):
    spider = make_spider(GlassdoorSpider, tmp_path)
    request = Request("https://gd.example.test/job/new", meta={"job_id": "g-new", "keyword": "python", "location": "Texas"})
    html = '<div class="css-17x2pwl">Data Analyst</div>'
    response = HtmlResponse(request.url, body=html, encoding="utf-8", request=request)
    (item,) = list(spider.parse_detail(response))
    assert item["source_id"] == "g-new"
    assert item["keyword"] == "python" and item["search_location"] == "Texas"
