from scrapy import Selector

from jobscrapers.parsers import (
    build_monster_payload,
    build_ziprecruiter_url,
    clean_text,
    extract_monster_fingerprint,
    format_salary,
    html_to_text,
    parse_monster_job,
    parse_ziprecruiter_card,
    parse_ziprecruiter_description,
)


def test_clean_text_collapses_whitespace():
    assert clean_text("  a \n\t b   c ") == "a b c"
    assert clean_text(None) == ""


def test_html_to_text_ignores_script_and_style():
    html = "<div><p>Hello</p><script>var x=1;</script><style>p{}</style><b>world</b></div>"
    assert html_to_text(html) == "Hello world"


def test_format_salary():
    assert format_salary(50000, 70000, "YEAR") == "$50000 - $70000 YEAR"
    assert format_salary(None, 70000) == "$70000"
    assert format_salary(None, None, "YEAR") == ""


def test_monster_payload_shape():
    payload = build_monster_payload("python", "Texas", offset=18, fingerprint="abc", page_size=9)
    assert payload["jobQuery"]["query"] == "python"
    assert payload["jobQuery"]["locations"][0]["address"] == "Texas"
    assert payload["offset"] == 18
    assert payload["fingerprintId"] == "abc"
    assert payload["jobAdsRequest"]["position"] == list(range(1, 10))


def test_extract_monster_fingerprint():
    data = {"runtimeConfig": {"api": {"splitClientAuthKey": "key123"}}}
    assert extract_monster_fingerprint(data) == "key123"
    assert extract_monster_fingerprint({}) is None


MONSTER_RESULT = {
    "jobId": 4242,
    "jobPosting": {
        "title": "  Senior  Python Developer ",
        "url": "https://example.test/job/4242",
        "description": "<p>Build <b>data</b> pipelines.</p>",
        "employmentType": ["FULL_TIME", "CONTRACTOR"],
        "hiringOrganization": {"name": "Acme Corp"},
        "jobLocation": [{"address": {"addressLocality": "Austin", "addressRegion": "TX"}}],
        "baseSalary": {"value": {"minValue": 90000, "maxValue": 120000, "unitText": "YEAR"}},
    },
}


def test_parse_monster_job_full():
    job = parse_monster_job(MONSTER_RESULT)
    assert job["source"] == "monster.com"
    assert job["source_id"] == "4242"
    assert job["title"] == "Senior Python Developer"
    assert job["company"] == "Acme Corp"
    assert job["location"] == "Austin, TX"
    assert job["employment_type"] == "FULL_TIME, CONTRACTOR"
    assert job["salary"] == "$90000 - $120000 YEAR"
    assert job["description"] == "Build data pipelines."


def test_parse_monster_job_tolerates_missing_fields():
    job = parse_monster_job({"jobId": 1, "jobPosting": {}})
    assert job["source_id"] == "1"
    assert job["location"] == ""
    assert job["salary"] == ""
    assert job["company"] == ""


def test_build_ziprecruiter_url_quotes_arguments():
    template = "https://example.test/search?location={location}&page={page}&search={keyword}"
    url = build_ziprecruiter_url(template, "data engineer", "New York", 3)
    assert url == "https://example.test/search?location=New+York&page=3&search=data+engineer"


CARD_HTML = """
<article class="job_result" data-listing-version-key="abc-123">
  <a class="job_link" href="https://example.test/jobs/abc-123">
    <span class="just_job_title">Data Engineer</span>
  </a>
  <a class="t_org_link">  Globex </a>
  <a class="t_location_link"> Remote, US </a>
  <div class="perks_type"><p><span>Full-time</span></p></div>
  <div class="perks_compensation"><p><span>$100k - $130k</span></p></div>
  <div class="job_snippet"><p>Own the <b>ETL</b> platform.</p></div>
</article>
"""


def test_parse_ziprecruiter_card():
    card = Selector(text=CARD_HTML).css(".job_result")[0]
    job = parse_ziprecruiter_card(card)
    assert job["source"] == "ziprecruiter.com"
    assert job["source_id"] == "abc-123"
    assert job["title"] == "Data Engineer"
    assert job["company"] == "Globex"
    assert job["location"] == "Remote, US"
    assert job["employment_type"] == "Full-time"
    assert job["salary"] == "$100k - $130k"
    assert job["summary"] == "Own the ETL platform."
    assert job["url"] == "https://example.test/jobs/abc-123"


def test_parse_ziprecruiter_description_falls_back_to_second_layout():
    page = Selector(text='<div class="job_description"><p>Great  role</p></div>')
    assert parse_ziprecruiter_description(page) == "Great role"
    assert parse_ziprecruiter_description(Selector(text="<div></div>")) == ""
