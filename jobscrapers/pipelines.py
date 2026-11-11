from datetime import datetime, timezone

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from .jobstore import JobStore


class CleanTextPipeline:
    """Strip whitespace on every string field and stamp the scrape time."""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        for key, value in list(adapter.items()):
            if isinstance(value, str):
                adapter[key] = value.strip()
        if not adapter.get("scraped_at"):
            adapter["scraped_at"] = datetime.now(timezone.utc).isoformat()
        return item


class SqliteJobPipeline:
    """Persist jobs to SQLite; drop (and count) duplicates."""

    def __init__(self, db_path: str, stats=None):
        self.db_path = db_path
        self.stats = stats
        self.store = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("DB_PATH", "data/jobs.db"), crawler.stats)

    def open_spider(self, spider):
        self.store = JobStore(self.db_path)

    def close_spider(self, spider):
        if self.store:
            self.store.close()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if not adapter.get("source_id"):
            raise DropItem("job has no source_id")
        if self.store.add(adapter.asdict()):
            if self.stats:
                self.stats.inc_value("jobs/new")
            return item
        if self.stats:
            self.stats.inc_value("jobs/duplicate")
        raise DropItem(f"duplicate job {adapter['source']}:{adapter['source_id']}")
