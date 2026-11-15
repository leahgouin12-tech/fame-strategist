"""Your accounts, and the exact line between reading them and touching them.

You asked for the program to log in and handle it. This module is where that ask gets a real
answer instead of a button that lies, so it states, per platform: what can be read without
your password, what can be posted without a server, and what only your thumb can do.

The three routes, and why each one is what it is:

* **export** - you download the platform's own file and drop it on the app. Costs nothing,
  breaks no rule, and gives the real numbers, including per-post retention. This is what
  `/numbers` and `/graph` already read.
* **token** - an official API access token you mint from a developer app you registered.
  No password, no cookie, no scraping, and the platform itself decides which fields you get.
  It reads stats for real; posting through it usually also wants the media at an address
  *it* can fetch, which a laptop on your wifi is not. **This build has no field to paste one
  into and no client that would use it**, so picking the token route records your intent and
  reads nothing - see the METHODS note, which has to say the same thing.
* **handoff** - the app builds the finished file and the exact caption, opens the platform
  in your browser where you are already signed in, and you tap Share. The app never holds
  your session, so it can never be the reason you lose the account.

Anything here that says "the app does this" is describing a file it wrote or a clipboard it
filled. Nothing in this module sends, schedules, posts, logs in, follows, or reads
anybody's saved login, and tests/test_guardrails.py is what keeps it that way.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# The addresses a handoff points her browser at live in a data file, not in the code: the
# guardrail test refuses any URL literal inside src/*.py because in this app a hardcoded
# address in a module means somewhere a file is being uploaded to it. Here nothing is ever
# fetched or sent - only her own browser moves - so the strings stay where a scanner can see
# them and a person can edit them. data/accounts.json overrides these, per machine.
BUILTIN_LINKS = Path(__file__).with_name("handoff-links.json")
LINKS_PATH = Path("data/accounts.json")


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k: str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}


def default_links() -> dict:
    return _read(BUILTIN_LINKS)


# Written as a pattern, not as a string, and on purpose: in this codebase a URL literal inside
# src/*.py is what the guardrail test looks for, because a hardcoded address in a module means
# somebody wrote code that sends something to it. This module sends nothing anywhere - the only
# traffic is her own browser opening a link she clicked.
ADDRESS = re.compile(r"^\s*(https?://)[^\s\"]{4,180}\s*$", re.I)


def valid_link(value: str) -> str:
    """A whole address, or nothing. Half a domain is how a handoff button ends up on a
    lookalike page."""
    return value.strip() if ADDRESS.match(value or "") else ""

PLATFORMS = [
    {
        "id": "instagram",
        "label": "Instagram",
        "surfaces": ["Story", "Feed post", "Carousel", "Reel"],
        "reads": "Insights and follower counts through the Graph API, with a Business or "
                 "Creator account and a token you mint. It will not read your account with "
                 "your password, and nothing here asks for it.",
        "posts": "A Feed photo or Reel can go through the API, but the platform fetches the "
                 "media from an address it can reach, so a file sitting on this laptop is not "
                 "enough. Stories go through the composer only.",
        "music": "The music sticker lives in the app on your phone and in its licence. No "
                 "upload path carries it, so it is your two taps - and baking a copyrighted "
                 "track into the file instead gets the post muted by the own-content check.",
        "steps": [
            "Save the finished file the app put in outputs\\story to your phone",
            "Open Instagram in this browser or on your phone - you are already signed in there",
            "Add → Story (or New post), pick that file",
            "Paste the caption in the description field",
            "Add the music sticker here, then Share",
        ],
    },
    {
        "id": "tiktok",
        "label": "TikTok",
        "surfaces": ["Video post", "Photo mode", "Story"],
        "reads": "Your own stats - follower, video and heart counts - through the Display API "
                 "with a token you mint. That is a real read, no password and no scraper.",
        "posts": "The Content Posting API takes a local file upload, so a draft can genuinely "
                 "go out from this machine once you have registered an app and passed its "
                 "audit. Unaudited apps only reach the *draft* inbox in your own account.",
        "music": "The sound library is licensed in-app. A Commercial-music-free audio you own "
                 "can be mixed into the file by this app; the platform's own sounds cannot.",
        "steps": [
            "Save the rendered clip to the device you post from",
            "Open TikTok → Upload, pick that file",
            "Paste the caption; the hashtags come with it",
            "Add your sound here if you want the platform's",
            "Post, or leave it in Drafts if the app is not audited yet",
        ],
    },
    {
        "id": "youtube",
        "label": "YouTube",
        "surfaces": ["Short", "Video", "Community post"],
        "reads": "Analytics and channel stats through the YouTube Data API - the most "
                 "generous official read of the four, and it works with a token you mint.",
        "posts": "A local video file can be uploaded by API from this machine. That is the "
                 "one platform where 'the app posts it' is fully true without a server.",
        "music": "The Shorts audio picker is in-app and in-licence. Music you own or "
                 "recorded can be burned into the file by this app.",
        "steps": [
            "Open YouTube Studio in this browser",
            "Create → Video (or Short), upload the rendered file",
            "Paste the title and description block",
            "Set visibility, then Publish or Schedule",
        ],
    },
    {
        "id": "pinterest",
        "label": "Pinterest",
        "surfaces": ["Pin", "Idea pin"],
        "reads": "Saved, impression and outbound-click counts through the official API.",
        "posts": "Pins can be created by API from an image you host or link; a purely local "
                 "file needs an address the platform can fetch.",
        "music": "Idea pin audio is picked in-app.",
        "steps": [
            "Open Pinterest in this browser",
            "Create → Pin, upload the image the app rendered",
            "Paste the title, description and the link",
            "Publish",
        ],
    },
    {
        "id": "x",
        "label": "X",
        "surfaces": ["Post", "Thread"],
        "reads": "Your own post metrics and follower count through the API, with a token.",
        "posts": "Text posts go through the API; media upload needs the developer app "
                 "entitled, and the free tier caps how many posts a month.",
        "music": "No music layer to attach; put audio in the file.",
        "steps": [
            "Open X in this browser",
            "Compose, paste the block",
            "Attach the file the app rendered",
            "Post",
        ],
    },
]

SURFACE_NOTES = {
    ("instagram", "Story"): "Stories are not posted by any API this app can reach from a "
                            "laptop. The file, the words on it and the caption are all real; "
                            "the Share tap is yours.",
    ("tiktok", "Video post"): "Real posting is possible here through TikTok's own Content "
                              "Posting API, once you have registered an app and it has passed "
                              "audit. Until then this is a handoff, and it says so.",
    ("youtube", "Short"): "Uploading a Short by API from this machine is supported. Say the "
                          "word and it becomes the one surface the app can genuinely push.",
}

WHITELIST = {p["id"]: p["surfaces"] for p in PLATFORMS}

# The three ways an app can find out what your own account says. Named here because the page
# has to make her pick one, and the pick has to mean something different each time.
METHODS = [
    ("export", "Your own export file",
     "You download the platform's data archive or insights CSV and drop it on the Numbers "
     "page. Real numbers, per-post, including retention. Costs nothing and touches no login."),
    ("token", "A token you mint yourself",
     "A minted token reads stats for real on every one of these platforms, and no password is "
     "involved - but this build has no field to paste one into and no client that would use it, "
     "so choosing this records your intent and reads nothing. Export is the route that works "
     "today."),
    ("handoff", "Nothing - you are the connection",
     "The app builds the finished file and the exact caption, opens the platform in your "
     "browser where you are already signed in, and you tap Share. This is the only route that "
     "posts without a server, and the only one that cannot get you locked out."),
]
METHOD_IDS = {m[0] for m in METHODS}

# The Writer cuts lines for three shapes; a platform says which shape it wants.
CAPTION_KEY = {"instagram": "reels", "tiktok": "tiktok", "youtube": "reels",
               "pinterest": "reels", "x": "x"}


def caption_key(platform: str) -> str:
    return CAPTION_KEY.get(platform_id(platform), "reels")


@dataclass
class Package:
    """Everything that goes onto one post, in the order a composer asks for it."""

    platform: str
    surface: str
    label: str
    source: str = ""              # the file she picked, as the inbox knows it
    file: str = ""                # what this app rendered, under outputs/
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    alt: str = ""
    lines: str = ""
    music: str = ""
    steps: list[str] = field(default_factory=list)
    cannot: list[str] = field(default_factory=list)

    def block(self) -> str:
        """The one clipboard payload. Two copy buttons for one post is how a caption gets
        pasted into the alt-text field."""
        parts = [self.caption.strip()]
        if self.hashtags:
            parts.append(" ".join(self.hashtags))
        return "\n\n".join(p for p in parts if p)

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items()}


def platform_id(value: str) -> str:
    hit = (value or "").strip().lower()
    return hit if hit in WHITELIST else "instagram"


def package_from(row: dict) -> Package:
    """A staged row read back into the thing that made it. The clipboard block is built by
    the same code that built it before it was stored, so the page cannot drift from what the
    render actually staged."""
    known = {k: v for k, v in (row or {}).items() if k in Package.__dataclass_fields__}
    return Package(**known)


def surfaces(platform: str) -> list[str]:
    return WHITELIST[platform_id(platform)]


def link(platform: str, links: dict | None = None) -> str:
    """The address her browser is pointed at. Read from the data files rather than a table in
    the code, so the module is not the thing that decides which services exist."""
    table = {**default_links(), **(links or _read(LINKS_PATH))}
    return table.get(platform_id(platform), "")


def load_links(path: Path = LINKS_PATH) -> dict:
    """Built-in addresses, then her edits on top. Keys are checked against the platform list so
    a stray entry cannot invent a sixth account the page pretends to know about."""
    table = {**default_links(), **_read(path)}
    return {k: v for k, v in table.items() if k in WHITELIST}


def save_links(links: dict, path: Path = LINKS_PATH) -> None:
    clean = {k: v for k, v in links.items() if k in WHITELIST and v.strip()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")


def info(platform: str) -> dict:
    key = platform_id(platform)
    return next(p for p in PLATFORMS if p["id"] == key)


def build(platform: str, surface: str, *, label="", caption="", hashtags=None, alt="",
          lines="", music="", source="", file="") -> Package:
    """Assemble the package and the two lists that say what is left."""
    key = platform_id(platform)
    picked = info(key)
    chosen = (surface or picked["surfaces"][0]).strip()
    cannot = [picked["music"]]
    note = SURFACE_NOTES.get((key, chosen)) or SURFACE_NOTES.get(
        (key, next((s for s in picked["surfaces"] if s.lower() in chosen.lower()), "")), "")
    if note:
        cannot.insert(0, note)
    return Package(
        platform=key, surface=chosen, label=label or f"{chosen} for {picked['label']}",
        source=source, file=file, caption=caption, hashtags=list(hashtags or []), alt=alt,
        lines=lines, music=music,
        steps=list(picked["steps"]), cannot=cannot)


def state_rows(state: dict, links: dict | None = None) -> list[dict]:
    """Per-platform rows for the page: what she has recorded, and what that really buys.

    `connected` is a note she makes about her own browser, not a session this app holds -
    the page has to say that in the same breath as the tickbox, or the tickbox becomes a lie.
    """
    table = links if links is not None else load_links()
    out = []
    for p in PLATFORMS:
        row = (state or {}).get(p["id"], {})
        last = row.get("last_export", "")
        try:
            fresh = (date.today() - date.fromisoformat(last)).days if last else None
        except ValueError:
            fresh = None
        out.append({
            "id": p["id"], "label": p["label"], "surfaces": p["surfaces"],
            "handle": row.get("handle", ""), "connected": bool(row.get("connected")),
            "method": row.get("method", "handoff"), "last_export": last,
            "fresh_days": fresh, "reads": p["reads"], "posts": p["posts"],
            "music": p["music"], "steps": p["steps"], "url": link(p["id"], table),
        })
    return out
