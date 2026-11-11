import pytest
from scrapy.exceptions import DropItem

from jobscrapers.items import JobItem
from jobscrapers.jobstore import JobStore
from jobscrapers.pipelines import CleanTextPipeline, SqliteJobPipeline


def make_job(source_id="1", **overrides):
    data = {"source": "example.com", "source_id": source_id, "title": "  Dev  ", "url": "https://x.test"}
    data.update(overrides)
    return data


def test_store_add_is_idempotent(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    assert store.add(make_job("1")) is True
    assert store.add(make_job("1")) is False  # same (source, source_id)
    assert store.add(make_job("2")) is True
    assert store.count() == 2
    assert store.exists("example.com", "1")
    assert not store.exists("example.com", "999")
    assert not store.exists("other.com", "1")  # id is scoped per source
    store.close()


def test_store_persists_between_connections(tmp_path):
    path = str(tmp_path / "jobs.db")
    first = JobStore(path)
    first.add(make_job("7"))
    first.close()
    second = JobStore(path)
    assert second.exists("example.com", "7")
    second.close()


class FakeStats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key, count=1):
        self.values[key] = self.values.get(key, 0) + count


def test_pipeline_drops_duplicates_and_counts(tmp_path):
    stats = FakeStats()
    pipeline = SqliteJobPipeline(str(tmp_path / "jobs.db"), stats)
    pipeline.open_spider(None)

    assert pipeline.process_item(JobItem(**make_job("1")), None)["source_id"] == "1"
    with pytest.raises(DropItem):
        pipeline.process_item(JobItem(**make_job("1")), None)
    with pytest.raises(DropItem):
        pipeline.process_item(JobItem(source="example.com", title="no id"), None)

    assert stats.values == {"jobs/new": 1, "jobs/duplicate": 1}
    pipeline.close_spider(None)


def test_clean_text_pipeline_strips_and_stamps_time():
    item = CleanTextPipeline().process_item(JobItem(**make_job("1")), None)
    assert item["title"] == "Dev"
    assert item["scraped_at"].endswith("+00:00")
