"""Pure parsing helpers.

Everything here is side-effect free (no network, no Scrapy engine), so it can be
unit-tested with small fixtures. Spiders only orchestrate requests; the logic
that turns a payload into a normalised job lives in this module.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote_plus

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
