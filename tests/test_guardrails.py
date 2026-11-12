import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
FORBIDDEN = [
    "auto_follow", "autofollow", "unfollow", "send_dm", "buy_followers", "purchase_followers",
    "public_url", "instaloader", "snscrape", "selenium", "playwright", "cookie", "sessionid",
]


def source_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in SRC.rglob("*.py")
    )


def test_no_automation_of_follows_messages_or_scraped_logins():
    text = source_text().lower()
    hits = [verb for verb in FORBIDDEN if verb in text]
    assert not hits, f"the core must not contain these verbs at all: {hits}"


def test_nothing_is_uploaded_to_a_publicly_fetchable_address():
    urls = set(re.findall(r'https?://[^\s"\'<>]+', source_text()))
    allowed = {"https://generativelanguage.googleapis.com"}
    offenders = {u for u in urls if not any(u.startswith(a) for a in allowed)}
    assert not offenders, f"only the model endpoint may be hardcoded: {offenders}"


def test_the_server_never_binds_outside_localhost():
    assert "0.0.0.0" not in source_text()
    assert 'host="127.0.0.1"' in (ROOT / "run.py").read_text(encoding="utf-8")


def test_the_app_admits_it_cannot_promise_growth():
    from src.app import DISCLAIMER

    assert "cannot promise" in DISCLAIMER.lower()
    assert "growth" in DISCLAIMER.lower() or "followers" in DISCLAIMER.lower() or "reach" in DISCLAIMER.lower()


def test_no_placeholder_urls_survive_in_the_playbook():
    offenders = [p.name for p in (ROOT / "data" / "playbook").glob("*.md") if "example.com" in p.read_text(encoding="utf-8")]
    assert not offenders, f"unverified citations: {offenders}"


def test_every_playbook_file_is_named_after_its_id():
    from src.playbook.store import _parse

    bad = [p.name for p in (ROOT / "data" / "playbook").glob("*.md") if _parse(p).id != p.stem]
    assert not bad, bad


@pytest.mark.parametrize("verb", ["follow", "dm", "unfollow", "publish", "scrape", "upload_media"])
def test_no_endpoint_implements_an_account_action(verb):
    paths = {}
    from src.app import create_app

    app = create_app()
    for route in app.routes:
        path = getattr(route, "path", "")
        paths[path] = True
    assert not any(verb in p for p in paths), f"{verb} appears in {list(paths)}"


def test_secrets_stay_out_of_git():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "config.toml" in ignore
    assert ".venv" in ignore


def test_the_edit_ladder_is_not_reachable_from_phase_one():
    text = source_text().lower()
    for banned in ["imagegen", "inpaint", "esrgan", "rembg", "insightface", "mediapipe"]:
        assert banned not in text, f"{banned} belongs to Phase 2 and must not be wired yet"


def test_no_fixed_element_is_pinned_to_both_edges_of_the_viewport():
    """A fixed box with top AND bottom pinned stretches full-screen and paints over
    the app - which is exactly how every screen went blank while still returning 200."""
    css = (SRC / "static" / "app.css").read_text(encoding="utf-8")
    offenders = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if "position: fixed" not in body:
            continue
        edges = [re.search(rf"\b{edge}:\s*([^;]+)", body) for edge in ("top", "bottom")]
        if all(edges) and not any("auto" in m.group(1) for m in edges):
            offenders.append(sel.strip())
    assert not offenders, f"these cover the viewport: {offenders}"


def test_the_footer_is_a_strip_not_a_sheet():
    css = (SRC / "static" / "app.css").read_text(encoding="utf-8")
    foot = re.search(r"\.foot\s*\{([^}]*)\}", css).group(1)
    assert "top: auto" in foot
