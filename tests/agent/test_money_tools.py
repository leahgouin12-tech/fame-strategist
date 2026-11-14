"""The two money tools, run the way the command centre runs them.

The registry proved the arithmetic elsewhere; what is proved here is the delivery - that a tool
with no numbers refuses instead of quoting zero, that the number it reports is the one stored
where the page will show it, that the floor she typed reaches the sentence, and that the label
check reads the post sitting in the composer rather than only the text a form happened to send.
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from src.agent import orchestrator
from src.app import create_app
from src.config import Config
from src.metrics.ingest import MetricRow

TODAY = datetime.date(2026, 11, 14)


def rows(platform, count, views=1000):
    return [MetricRow(platform, f"{platform}{i}", TODAY, views, views, 40.0, 9, 3, 2)
            for i in range(count)]


@pytest.fixture
def alone(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "money.sqlite3")
    client = TestClient(app)
    return client, client.app.state.kit


def test_quoting_with_nothing_imported_refuses_rather_than_quoting_zero(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "money.quote", {})
    assert out.kind == "skipped", out.summary
    assert "no numbers have been imported" in out.summary


def test_a_real_import_comes_back_with_its_own_median_and_published_bands(alone):
    client, kit = alone
    kit.save_rows(rows("tiktok", 5))
    out = orchestrator.execute(kit, "money.quote", {})
    assert out.kind == "advised", out.summary
    quote = out.detail["quotes"][0]
    assert quote["platform"] == "tiktok" and quote["posts"] == 5
    assert quote["median_views"] == 1000, "the median is hers, not a trend page's"
    assert quote["anchor"] == 15.27 and quote["low"] == 4.46 and quote["high"] == 25.71
    assert out.detail["where"] == "/money", "the summary has to point at the page that shows it"
    assert "tiktok" in out.summary


def test_the_floor_she_typed_shows_up_in_the_number_she_would_send(alone):
    client, kit = alone
    kit.save_rows(rows("tiktok", 5))
    kit.db.save_terms({"hourly": 50, "minutes": 90})
    out = orchestrator.execute(kit, "money.quote", {})
    quote = out.detail["quotes"][0]
    assert quote["floor"] == 75.0
    assert quote["under_floor"], "$15 against a $75 cost is the finding, not a footnote"
    assert "never under $75" in quote["line"]


def test_a_platform_with_too_few_posts_is_refused_by_name(alone):
    client, kit = alone
    kit.save_rows(rows("reels", 3))
    out = orchestrator.execute(kit, "money.quote", {})
    assert out.detail["quotes"] == []
    assert "reels: 3 posts imported, 5 needed" in out.detail["thin"][0]
    assert "Nothing here is priceable yet" in out.summary


def test_the_quote_is_remembered_where_the_page_can_read_it_back(alone):
    client, kit = alone
    kit.save_rows(rows("tiktok", 5))
    orchestrator.execute(kit, "money.quote", {})
    notes = kit.db.recall("quote")
    assert len(notes) == 1
    assert "tiktok" in notes[0]["body"] and notes[0]["source"] == "money/rate"


def test_the_label_tool_reads_the_staged_post_when_given_no_text(alone):
    client, kit = alone
    kit.db.save_staged({"caption": "they sent me the whole set, link in bio",
                        "surface": "reels", "platform": "instagram"}, TODAY.isoformat())
    out = orchestrator.execute(kit, "money.label", {})
    assert out.kind == "advised", out.summary
    assert out.detail["status"] == "missing"
    assert out.detail["checked"] == "staged post"
    assert out.detail["surface"] == "reels"
    assert out.detail["needs_video"], "a reel needs the label in the reel"
    assert not out.detail["safe_to_post"]


def test_text_she_gives_is_checked_as_it_is_written(alone):
    client, kit = alone
    good = orchestrator.execute(kit, "money.label",
                                {"text": "Sponsored by the gel that survived my shower"})
    assert good.detail["status"] == "clear"
    assert good.detail["safe_to_post"]
    buried = orchestrator.execute(kit, "money.label",
                                  {"text": "obsessed " * 30 + "advertisement"})
    assert buried.detail["status"] == "clear"
    assert not buried.detail["safe_to_post"], "a label past the fold is not a disclosure"


def test_with_no_caption_anywhere_it_says_so_instead_of_passing(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "money.label", {})
    assert out.kind == "skipped", out.summary
    assert "no caption to read" in out.summary
