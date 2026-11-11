"""Pure parsing helpers.

Everything here is side-effect free (no network, no Scrapy engine), so it can be
unit-tested with small fixtures. Spiders only orchestrate requests; the logic
that turns a payload into a normalised job lives in this module.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from scrapy import Selector

_WS = re.compile(r"\s+")


def clean_text(value: Optional[str]) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends."""
    if not value:
        return ""
    return _WS.sub(" ", value).strip()


def html_to_text(html: Optional[str]) -> str:
    """Flatten an HTML fragment to plain text, ignoring script/style nodes."""
    if not html:
        return ""
    selector = Selector(text=html)
    parts = selector.xpath(
        "//text()[not(ancestor::script) and not(ancestor::style)]"
    ).getall()
    return clean_text(" ".join(parts))


def format_salary(
    minimum: Any = None, maximum: Any = None, unit: Optional[str] = None, symbol: str = "$"
) -> str:
    """Render a salary range such as ``$50000 - $70000 YEAR``; empty if unknown."""
    if minimum in (None, "") and maximum in (None, ""):
        return ""
    low = f"{symbol}{minimum}" if minimum not in (None, "") else ""
    high = f"{symbol}{maximum}" if maximum not in (None, "") else ""
    amount = " - ".join(part for part in (low, high) if part)
    return f"{amount} {unit}".strip() if unit else amount


# --------------------------------------------------------------------------- #
# Monster
# --------------------------------------------------------------------------- #
def build_monster_payload(
    keyword: str,
    location: str,
    offset: int,
    fingerprint: str,
    page_size: int = 9,
    radius_miles: int = 20,
) -> dict:
    """Body of the JSON search request sent to Monster's search API."""
    return {
        "jobQuery": {
            "query": keyword,
            "locations": [
                {
                    "country": "us",
                    "address": location,
                    "radius": {"unit": "mi", "value": radius_miles},
                }
            ],
        },
        "jobAdsRequest": {
            "position": list(range(1, page_size + 1)),
            "placement": {
                "channel": "MOBILE",
                "location": "JobSearchPage",
                "property": "monster.com",
                "type": "JOB_SEARCH",
                "view": "CARD",
            },
        },
        "fingerprintId": fingerprint,
        "offset": offset,
        "pageSize": page_size,
        "histogramQueries": ["count(company_display_name)", "count(employment_type)"],
        "searchId": "",
    }


def extract_monster_fingerprint(next_data: dict) -> Optional[str]:
    """Pull the client auth key out of the page's ``__NEXT_DATA__`` JSON."""
    return (
        next_data.get("runtimeConfig", {}).get("api", {}).get("splitClientAuthKey")
    )


def parse_monster_job(result: dict) -> dict:
    """Normalise one entry of Monster's ``jobResults`` array."""
    posting = result.get("jobPosting") or {}

    salary = ""
    base_salary = posting.get("baseSalary")
    if base_salary:
        value = base_salary.get("value") or {}
        salary = format_salary(value.get("minValue"), value.get("maxValue"), value.get("unitText"))

    location = ""
    locations = posting.get("jobLocation") or []
    if locations:
        address = locations[0].get("address") or {}
        parts = [address.get("addressLocality", ""), address.get("addressRegion", "")]
        location = ", ".join(part for part in parts if part)

    return {
        "source": "monster.com",
        "source_id": str(result.get("jobId", "")),
        "title": clean_text(posting.get("title")),
        "company": clean_text((posting.get("hiringOrganization") or {}).get("name")),
        "location": location,
        "employment_type": ", ".join(posting.get("employmentType") or []),
        "salary": salary,
        "summary": "",
        "description": html_to_text(posting.get("description")),
        "url": posting.get("url", ""),
    }


# --------------------------------------------------------------------------- #
# ZipRecruiter
# --------------------------------------------------------------------------- #
def build_ziprecruiter_url(template: str, keyword: str, location: str, page: int) -> str:
    return template.format(keyword=quote_plus(keyword), location=quote_plus(location), page=page)


def parse_ziprecruiter_card(card: Selector) -> dict:
    """Normalise one ``.job_result`` card from a ZipRecruiter listing page."""
    snippet = " ".join(card.css(".job_snippet *::text").getall())
    return {
        "source": "ziprecruiter.com",
        "source_id": card.attrib.get("data-listing-version-key", ""),
        "title": clean_text(card.css(".just_job_title::text").get("")),
        "company": clean_text(card.css(".t_org_link::text").get("")),
        "location": clean_text(card.css(".t_location_link::text").get("")),
        "employment_type": clean_text(card.css(".perks_type>p>span::text").get("")),
        "salary": clean_text(card.css(".perks_compensation>p>span::text").get("")),
        "summary": clean_text(snippet),
        "description": "",
        "url": card.css(".job_link::attr(href)").get(""),
    }


def parse_ziprecruiter_description(page: Selector) -> str:
    """Extract the long description from a ZipRecruiter job page."""
    for xpath in (
        '//div[@class="jobDescriptionSection"]//text()',
        '//div[@class="job_description"]//text()',
    ):
        text = clean_text(" ".join(page.xpath(xpath).getall()))
        if text:
            return text
    return ""


# --------------------------------------------------------------------------- #
# Indeed
# --------------------------------------------------------------------------- #
INDEED_NEXT_PAGE_SELECTORS = (
    'a[aria-label="Next Page"]::attr(href)',
    'a[aria-label="Next"]::attr(href)',
    'a[data-testid="pagination-page-next"]::attr(href)',
)


def build_indeed_url(template: str, keyword: str, location: str) -> str:
    return template.format(keyword=quote_plus(keyword), location=quote_plus(location))


def parse_indeed_card(card: Selector, base_url: str = "https://www.indeed.com") -> dict:
    """Normalise one ``div.tapItem`` card from an Indeed results page."""
    return {
        "source": "indeed.com",
        "source_id": card.css(".jobTitle>a::attr(data-jk)").get(""),
        "title": clean_text(card.css(".jobTitle>a>span::attr(title)").get("")),
        "company": clean_text("".join(card.css(".companyName ::text").getall())),
        "location": clean_text("".join(card.css(".companyLocation ::text").getall())),
        # relative XPath (".//"): an absolute "//" would search the whole page
        "employment_type": clean_text(card.xpath('.//*[@aria-label="Job type"]/following::text()[1]').get("")),
        "salary": clean_text(card.xpath('.//*[@aria-label="Salary"]/following::text()[1]').get("")),
        "summary": clean_text(" ".join(card.css(".job-snippet ::text").getall())),
        "description": "",
        "url": urljoin(base_url, card.css(".jobTitle>a::attr(href)").get("")),
    }


def find_indeed_next_page(page: Selector) -> Optional[str]:
    """Indeed has changed its pagination markup repeatedly, so try each known selector."""
    for css in INDEED_NEXT_PAGE_SELECTORS:
        href = page.css(css).get()
        if href:
            return href
    return None


def parse_indeed_descriptions(raw_json: str) -> Dict[str, str]:
    """Parse the ``jobdescs`` batch endpoint: ``{job_key: description_html}``."""
    try:
        data = json.loads(raw_json or "{}")
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: html_to_text(html) for key, html in data.items() if isinstance(html, str)}


# --------------------------------------------------------------------------- #
# Glassdoor
# --------------------------------------------------------------------------- #
def parse_glassdoor_location_id(payload: Any) -> Optional[str]:
    """First state-level (``locationType == "S"``) id from the location autocomplete."""
    for entry in payload if isinstance(payload, list) else []:
        if isinstance(entry, dict) and entry.get("locationType") == "S" and entry.get("locationId"):
            return str(entry["locationId"])
    return None


def parse_glassdoor_cards(page: Selector) -> List[Tuple[str, str]]:
    """``[(job_id, relative_detail_url), ...]`` from a listing page."""
    cards = []
    for card in page.css(".react-job-listing"):
        job_id = card.attrib.get("data-id", "")
        href = card.css(".jobLink ::attr(href)").get("")
        if job_id and href:
            cards.append((job_id, href))
    return cards


def glassdoor_has_next(page: Selector) -> bool:
    return bool(page.css(".nextButton")) and not page.css(".nextButton[disabled]")


def glassdoor_page_url(url: str, page: int) -> str:
    """Rewrite ``.../jobs.htm`` (or ``jobs_IP3.htm``) to page ``page``, keeping the query."""
    parts = urlsplit(url)
    path = re.sub(r"(_IP\d+)?\.htm$", f"_IP{page}.htm", parts.path)
    query = dict(parse_qsl(parts.query))
    query.setdefault("fromAge", "1")
    query.setdefault("radius", "100")
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def parse_glassdoor_job_json(app_cache: dict) -> Optional[dict]:
    node = (app_cache.get("initialState") or {}).get("jlData") or {}
    header = node.get("header") or {}
    if not header.get("jobTitleText"):
        return None
    type_keys = header.get("jobTypeKeys") or []
    return {
        "title": header.get("jobTitleText"),
        "company": header.get("employerNameFromSearch"),
        "location": header.get("locationName"),
        "employment_type": type_keys[0].split(".")[-1] if type_keys else "",
        "description": html_to_text((node.get("job") or {}).get("description")),
    }


def parse_glassdoor_job_html(page: Selector) -> dict:
    """Fallback for pages that do not embed ``window.appCache``."""
    return {
        "title": page.css("div.css-17x2pwl::text").get(""),
        "company": page.css("div.css-16nw49e::text").get(""),
        "location": page.css("div.css-1v5elnn::text").get(""),
        "employment_type": "",
        "description": " ".join(page.css("div.desc *::text").getall()),
    }


def parse_glassdoor_job(page: Selector, url: str, job_id: str) -> Optional[dict]:
    """Normalise a Glassdoor job page; ``None`` when no title could be found."""
    fields = None
    raw = page.css("script").re_first(r"window.appCache=(.*);")
    if raw:
        try:
            cache = json.loads(raw)
            fields = parse_glassdoor_job_json(cache) if isinstance(cache, dict) else None
        except ValueError:
            fields = None
    fields = fields or parse_glassdoor_job_html(page)

    job = {key: clean_text(value) for key, value in fields.items()}
    if not job["title"]:
        return None
    job.update(
        source="glassdoor.com",
        source_id=job_id,
        salary=clean_text(page.css("div>span.small::text").get("")),
        summary="",
        url=url,
    )
    return job
