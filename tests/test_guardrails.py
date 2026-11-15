import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
FORBIDDEN = [
    "auto_follow", "autofollow", "unfollow", "send_dm", "buy_followers", "purchase_followers",
    "public_url", "instaloader", "snscrape", "selenium", "playwright",
    "sessionid", "cookiejar", "cookies.sqlite", "browsercookie", "appstate",
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


def test_the_server_reaches_a_phone_without_reaching_the_internet():
    """This rule used to read "loopback only", which is also "no phone, ever", and a phone
    cannot knock on a loopback. What must still never happen is that something from outside
    the laptop reads a page or a file without answering first - so the socket may open wider,
    but only with a door standing in front of it. run.py owns the socket; src/app.py is
    required to own the doorway."""
    launcher = (ROOT / "run.py").read_text(encoding="utf-8")
    assert 'HOST = "0.0.0.0"' in launcher and "host=HOST" in launcher
    assert "127.0.0.1" in launcher, "the laptop still opens the address it has always known"
    app_src = (SRC / "app.py").read_text(encoding="utf-8")
    assert "phone_door" in app_src and "net.is_foreign" in app_src, \
        "a wifi listener with no door in front of it is a leak, not a feature"
    assert "0.0.0.0" not in source_text(), "only run.py decides what to listen on"


def test_the_phone_cookie_is_hers_and_not_a_scraped_login():
    """The bare word "cookie" was on the forbidden list because a cookie in this codebase
    used to mean somebody had lifted a platform login. One exists now on purpose - the local
    door for her own phone - so the guardrail checks the shape of it instead of the spelling,
    and still refuses any code that reads stored logins."""
    both = (SRC / "net.py").read_text(encoding="utf-8") + (SRC / "app.py").read_text(encoding="utf-8")
    assert 'COOKIE = "fame_phone"' in both, "one cookie, named here, and no other"
    assert "httponly=True" in both and 'samesite="lax"' in both
    assert not re.search(r"cookiejar|HTTPCookieProcessor|browsercookie|\.cookies\[", both), \
        "reading somebody's saved logins is still exactly what this guardrail is for"


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


def test_a_string_written_by_a_script_carries_no_html_entities():
    """`textContent` does not decode entities, so a chip that set "copying&hellip;" printed the
    ampersand and the word on screen. An entity belongs in markup; a JavaScript string that
    reaches the DOM as text has to hold the character itself."""
    offenders = []
    for page in sorted((SRC / "templates").glob("*.html")):
        for line in page.read_text(encoding="utf-8").splitlines():
            writes_text = re.search(r"\.(textContent|innerText)\s*=", line)
            entity = re.search(r"&[a-zA-Z]+;|&#\d+;", line)
            if writes_text and entity:
                offenders.append(f"{page.name}: {entity.group(0)}")
    assert not offenders, "write the character, not the entity: " + ", ".join(offenders)
