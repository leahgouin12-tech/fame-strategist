import json

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

EARLY = json.dumps([{"value": str(i), "username": f"person{i}"} for i in range(20)])
LATE = json.dumps([{"value": "0", "username": "person0"}, {"value": "1", "username": "person1"},
                   {"value": "99", "username": "arrived.now"}])


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""), tmp_path / "g.sqlite3")
    with TestClient(app) as test_client:
        test_client.app = app
        yield test_client


def post_export(client, text, taken, source="followers_1.json"):
    return client.post("/graph/read", data={"taken": taken, "source": source, "paste": text})


def test_the_graph_page_starts_by_saying_where_the_file_comes_from(client):
    page = client.get("/graph").text
    assert "Download your" in page and "password" in page.lower()
    assert "0 accounts left" not in page, "no churn may be invented from nothing"


def test_one_export_is_a_list_not_a_trend(client):
    page = post_export(client, EARLY, "2026-11-01").text
    assert "20 names" in page and "second export" in page.lower()
    assert len(client.app.state.db.get_graph()) == 1


def test_two_exports_name_the_churn_and_place_it_on_the_calendar(client):
    post_export(client, EARLY, "2026-11-01")
    page = post_export(client, LATE, "2026-11-12").text
    assert "18 accounts left" in page
    assert "arrived.now" in page and "person2" in page
    assert "Insight, no action" in page


def test_a_long_lost_list_is_counted_not_dumped(client):
    post_export(client, EARLY, "2026-11-01")
    page = post_export(client, LATE, "2026-11-12").text
    assert "6 more" in page, "twelve names on screen, the rest as a count"
    assert "person19" not in page


def test_a_real_upload_is_read_the_same_way_as_a_paste(client):
    landed = client.post("/graph/read",
                         data={"taken": "2026-11-01", "paste": ""},
                         files={"file": ("followers_1.json", EARLY, "application/json")},
                         follow_redirects=False)
    assert landed.status_code == 303
    stored = client.app.state.db.get_graph()
    assert stored[0]["names"][:3] == ["person0", "person1", "person2"]


def test_a_file_this_app_cannot_read_is_named_not_counted(client):
    page = post_export(client, "no handles, just prose about the week", "2026-11-01").text
    assert client.app.state.db.get_graph() == []
    assert "does not recognise" in page


def test_forgetting_takes_the_handles_off_the_disk(client):
    post_export(client, EARLY, "2026-11-01")
    client.post("/graph/forget")
    assert client.app.state.db.get_graph() == []
    assert "person0" not in client.get("/graph").text
