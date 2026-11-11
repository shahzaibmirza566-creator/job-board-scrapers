import scrapy


class JobItem(scrapy.Item):
    """A normalised job posting, identical across all sources."""

    source = scrapy.Field()  # e.g. "monster.com"
    source_id = scrapy.Field()  # the site's own job id (used for de-duplication)
    title = scrapy.Field()
    company = scrapy.Field()
    location = scrapy.Field()
    employment_type = scrapy.Field()
    salary = scrapy.Field()
    summary = scrapy.Field()
    description = scrapy.Field()
    url = scrapy.Field()
    keyword = scrapy.Field()  # search keyword that surfaced the job
    search_location = scrapy.Field()  # search location that surfaced the job
    scraped_at = scrapy.Field()  # UTC ISO timestamp
