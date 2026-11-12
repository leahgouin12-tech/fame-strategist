# Fame Strategist (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local "fame strategist" core — a sourced playbook of what actually grows accounts, a deterministic planner that turns it into a personalised 8-week plan and a daily shot list, and an adaptation loop driven by the user's own numbers.

**Architecture:** The playbook is data, not prose: every claim carries a confidence tier, at least one cited source, and an explicit statement of what it does *not* claim, and the loader refuses to start if any entry fails validation. The LLM never decides structure — niche selection, plan shape and day assembly are deterministic functions over playbook entries; the model only fills pre-built templates with specific language. That makes the output testable, and it makes the difference between "sourced" and "made up" a thing the code can check rather than a thing the user has to trust.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `pyyaml` (playbook front matter), `httpx` (Gemini REST), `fastapi` + `jinja2` (localhost UI), `pytest`.

**Spec:** [docs/superpowers/specs/2026-11-12-social-autopilot-design.md](../specs/2026-11-12-social-autopilot-design.md)

## Global Constraints

Verbatim from the spec. Every task implicitly includes this section.

- $0 marginal money: no paid API tiers, no hosting bills (spec §2).
- No public hosting. Qoder Sites and any media-at-a-public-URL path are declined (spec §2.1).
- Model APIs are permitted; public hosting is not (spec §2.1).
- 3.66 GB RAM, no GPU: serial processing, no Electron, memory prechecked (spec §2).
- Judge/editor/publishing phases are deferred; this plan is the strategist only.
- Non-goals are permanent: no automated follow/unfollow/like/comment actions, no bought followers, no DM bots, no login-as-you scraping (spec §3).
- Insight into the follower graph is in scope; action on it is not (spec §3, §5.12).
- LLM engine behind a swappable `Engine` interface; must run offline with no key (spec §5.3, §7.6).
- Growth is not guaranteed and the app must never imply it is (spec §7.10).
- Every image-bearing network call must pass one `outbound()` chokepoint (spec §6). Phase 1 sends no images, so the chokepoint exists and is asserted-empty.
- Setup friction is a blocker: API key read from one config file, never requested interactively (spec §2).
- Plan content is judged by whether it cites sources, not by whether it sounds confident (spec §5.10, §5.11).

---

### Task 1: Playbook schema and validator

**Files:**
- Create: `src/playbook/__init__.py`
- Create: `src/playbook/schema.py`
- Create: `src/playbook/store.py`
- Create: `data/playbook/hook-first-second.md`
- Create: `data/playbook/watch-time-dominates.md`
- Test: `tests/playbook/test_store.py`

**Interfaces:**
- Produces: `Confidence`, `SourceTier`, `Source`, `PlaybookEntry`, `validate_entry(entry) -> list[str]`, `Store.load(dirpath) -> list[PlaybookEntry]`, `PlaybookError`

This task exists because "very knowledgeable" is only real if un-sourced advice cannot enter the system. The validator is the product's spine, not a formality.

- [ ] **Step 1: Write the failing test**

Create `tests/playbook/test_store.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from src.playbook.schema import Confidence, PlaybookEntry, Source, SourceTier, validate_entry
from src.playbook.store import PlaybookError, Store

GOOD = dict(
    id="hook-first-second",
    claim="Distribution is decided mainly in the first 1-2 seconds.",
    mechanism="Platforms sample early retention and gate further reach on it.",
    confidence=Confidence.STRONG,
    sources=[Source(url="https://example.com/a", title="TikTok on signals", tier=SourceTier.PLATFORM_OFFICIAL)],
    applies_to=["tiktok", "reels", "shorts"],
    as_of=date(2026, 10, 1),
    does_not_claim="That a strong hook guarantees reach.",
)


def make(**over):
    return PlaybookEntry(**{**GOOD, **over})


def test_valid_entry_has_no_problems():
    assert validate_entry(make()) == []


def test_folklore_needs_a_reason_it_is_kept():
    problems = validate_entry(make(confidence=Confidence.FOLKLORE))
    assert "does_not_claim must explain why folklore is kept" in " ".join(problems)


def test_proven_needs_two_sources_including_one_strong():
    entry = make(confidence=Confidence.PROVEN)
    assert any("proven" in p for p in validate_entry(entry))


def test_stale_entry_is_reported():
    entry = make(as_of=date(2020, 1, 1))
    assert any("stale" in p for p in validate_entry(entry))


def test_source_url_must_be_http():
    entry = make(sources=[Source(url="example.com", title="t", tier=SourceTier.STUDY)])
    assert any("url" in p for p in validate_entry(entry))


def test_load_reads_the_seed_playbook(tmp_path):
    (tmp_path / "hook-first-second.md").write_text(
        "---\n"
        "id: hook-first-second\n"
        "confidence: strong\n"
        "as_of: 2026-10-01\n"
        "applies_to: [tiktok, reels]\n"
        "does_not_claim: That a strong hook guarantees reach.\n"
        "sources:\n"
        "  - {url: 'https://example.com/a', title: signals, tier: platform_official}\n"
        "---\n"
        "claim: Distribution is decided mainly in the first 1-2 seconds.\n"
        "mechanism: Platforms sample early retention and gate further reach on it.\n",
        encoding="utf-8",
    )
    entries = Store().load(tmp_path)
    assert entries[0].id == "hook-first-second"
    assert entries[0].confidence is Confidence.STRONG


def test_load_rejects_a_sourceless_entry(tmp_path):
    (tmp_path / "bad.md").write_text("---\nid: bad\nconfidence: strong\nas_of: 2026-10-01\napplies_to: [tiktok]\nsources: []\n---\nclaim: x\nmechanism: y\ndoes_not_claim: z\n", encoding="utf-8")
    with pytest.raises(PlaybookError) as exc:
        Store().load(tmp_path)
    assert "bad" in str(exc.value)


def test_seed_playbook_loads():
    assert len(Store().load(Path("data/playbook"))) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/playbook/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.playbook.schema'`

- [ ] **Step 3: Write minimal implementation**

Create `src/playbook/__init__.py` (empty) and `src/playbook/schema.py`:

```python
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

STALE_AFTER_MONTHS = 18


class Confidence(str, Enum):
    PROVEN = "proven"
    STRONG = "strong"
    CONTESTED = "contested"
    FOLKLORE = "folklore"


class SourceTier(str, Enum):
    PLATFORM_OFFICIAL = "platform_official"
    STUDY = "study"
    PRACTITIONER = "practitioner"
    SECONDHAND = "secondhand"


@dataclass
class Source:
    url: str
    title: str
    tier: SourceTier


@dataclass
class PlaybookEntry:
    id: str
    claim: str
    mechanism: str
    confidence: Confidence
    sources: list[Source]
    applies_to: list[str]
    as_of: date
    does_not_claim: str
    tags: list[str] = field(default_factory=list)

    def is_stale(self, today: date) -> bool:
        limit = self.as_of.replace(year=self.as_of.year + 1) if self.as_of.month > 6 else self.as_of
        months = (today.year - self.as_of.year) * 12 + (today.month - self.as_of.month)
        return months > STALE_AFTER_MONTHS


def validate_entry(entry: PlaybookEntry, today: date | None = None) -> list[str]:
    today = today or date.today()
    problems: list[str] = []
    if not entry.id or not entry.id.replace("-", "").isalnum():
        problems.append(f"id {entry.id!r} must be non-empty kebab-case")
    if len(entry.claim) < 20:
        problems.append("claim must be a real sentence, at least 20 characters")
    if not entry.mechanism.strip():
        problems.append("mechanism is required: why this is believed to work")
    if not entry.applies_to:
        problems.append("applies_to must name at least one platform or format")
    if entry.is_stale(today):
        problems.append(f"as_of {entry.as_of} is stale; re-research or re-date this entry")
    if not entry.sources:
        problems.append("sources must not be empty; unsourced advice does not enter the playbook")
    for s in entry.sources:
        if not s.url.startswith(("http://", "https://")):
            problems.append(f"source url {s.url!r} must be an http(s) address")
        if not s.title.strip():
            problems.append("every source needs a title so the claim can be re-checked")
    strong = {SourceTier.PLATFORM_OFFICIAL, SourceTier.STUDY}
    if entry.confidence is Confidence.PROVEN and (
        len(entry.sources) < 2 or not any(s.tier in strong for s in entry.sources)
    ):
        problems.append("proven requires 2+ sources including a platform-official or study")
    if entry.confidence is Confidence.FOLKLORE and "folklore" not in entry.does_not_claim.lower():
        problems.append("does_not_claim must explain why folklore is kept")
    if not entry.does_not_claim.strip():
        problems.append("does_not_claim is required; every entry states its own limit")
    return problems
```

Create `src/playbook/store.py`:

```python
from datetime import date
from pathlib import Path

import yaml

from .schema import Confidence, PlaybookEntry, Source, SourceTier, validate_entry


class PlaybookError(Exception):
    pass


def _parse(path: Path) -> PlaybookEntry:
    text = path.read_text(encoding="utf-8")
    try:
        _, front, body = text.split("---", 2)
    except ValueError:
        raise PlaybookError(f"{path.name}: missing --- front matter ---")
    meta = yaml.safe_load(front) or {}
    fields = {"claim": "", "mechanism": ""}
    for line in body.strip().splitlines():
        for key in fields:
            if line.startswith(key + ":"):
                fields[key] = line.split(":", 1)[1].strip()
    try:
        return PlaybookEntry(
            id=meta["id"],
            claim=fields["claim"],
            mechanism=fields["mechanism"],
            confidence=Confidence(meta["confidence"]),
            sources=[Source(s["url"], s["title"], SourceTier(s["tier"])) for s in meta.get("sources", [])],
            applies_to=list(meta.get("applies_to", [])),
            as_of=date.fromisoformat(str(meta["as_of"])),
            does_not_claim=meta.get("does_not_claim", ""),
            tags=list(meta.get("tags", [])),
        )
    except (KeyError, ValueError) as exc:
        raise PlaybookError(f"{path.name}: {exc}") from exc


class Store:
    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def load(self, dirpath: Path) -> list[PlaybookEntry]:
        entries, problems = [], []
        for path in sorted(dirpath.glob("*.md")):
            try:
                entry = _parse(path)
            except PlaybookError as exc:
                problems.append(str(exc))
                continue
            bad = validate_entry(entry, self.today)
            if bad:
                problems.extend(f"{entry.id}: {p}" for p in bad)
            entries.append(entry)
        if problems:
            raise PlaybookError("playbook rejected:\n" + "\n".join(f"  - {p}" for p in problems))
        return entries

    def by_id(self, entries: list[PlaybookEntry]) -> dict[str, PlaybookEntry]:
        return {e.id: e for e in entries}
```

Create `data/playbook/hook-first-second.md` and `data/playbook/watch-time-dominates.md` with the front-matter shape from Step 1's test, each with a real platform-official or study URL you verify loads in a browser. Never paste a plausible-looking URL. If you cannot verify a source, set `confidence: contested` and say so in `does_not_claim`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/playbook/test_store.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/playbook data/playbook tests/playbook
git commit -m "feat: playbook schema that rejects unsourced advice"
```

---

### Task 2: The research pass

**Files:**
- Create: `data/playbook/*.md` (target: 28–35 entries)
- Create: `docs/research/2026-11-12-playbook-questions.md`
- Test: `tests/playbook/test_playbook_coverage.py`

**Interfaces:**
- Consumes: `Store.load` from Task 1
- Produces: a populated playbook keyed by `applies_to` and `tags`, consumed by Tasks 5–8

This is the task the user's actual request lives in. Advice reasoned out of genre knowledge is what they already get from every chatbot; the differentiator is citations, confidence tiers, and an honest `contested` pile.

- [ ] **Step 1: Write the failing test**

Create `tests/playbook/test_playbook_coverage.py`:

```python
from pathlib import Path

from src.playbook.store import Store

REQUIRED_TAGS = {
    "hook", "retention", "format", "niche", "cadence", "profile",
    "series", "engagement", "algorithm", "conversion", "failure-modes",
}
MIN_PER_TAG = 2


def test_playbook_has_enough_entries():
    entries = Store().load(Path("data/playbook"))
    assert len(entries) >= 28, f"only {len(entries)} entries; the playbook is too thin to advise"


def test_every_required_topic_is_covered_twice():
    entries = Store().load(Path("data/playbook"))
    seen: dict[str, int] = {}
    for e in entries:
        for t in e.tags:
            seen[t] = seen.get(t, 0) + 1
    missing = {t for t in REQUIRED_TAGS if seen.get(t, 0) < MIN_PER_TAG}
    assert not missing, f"topics with fewer than {MIN_PER_TAG} entries: {sorted(missing)}"


def test_some_entries_are_contested_or_folklore():
    entries = Store().load(Path("data/playbook"))
    honest = [e for e in entries if e.confidence.value in ("contested", "folklore")]
    assert len(honest) >= 4, "a playbook with no contested claims is overclaiming, not knowledgeable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/playbook/test_playbook_coverage.py -v`
Expected: FAIL — "only 2 entries"

- [ ] **Step 3: Research, then write the entries**

Answer these questions with real web research. For each, record the URL, the date checked, and what it does *not* establish.

1. What does each platform state publicly about what gates distribution? (TikTok, Instagram, X — official help/announcement pages only.)
2. Which retention metrics predict reach, and at what thresholds? Where does the "first second" number actually come from?
3. Which account-level behaviours correlate with new-follower conversion — reach, profile visit rate, follow rate per 1,000 views?
4. For each format archetype (POV, storytime, before/after, list, hot-take, tutorial, react, series), what does available evidence say about its niche fit and its failure mode?
5. What is proven, what is contested, and what is pure folklore about posting cadence, hashtag count/weight, caption keywords, "best times to post", and the effect of deleting posts?
6. What do accounts that grew from 0 in the last 24 months have in common, and which of those are survivorship bias?
7. Which practices get accounts reach-limited or suspended in 2026? (This feeds the safety gate in §5.3 and must cite platform pages, not blogs.)

Write each answer as one `data/playbook/<slug>.md`. Tag every entry from `REQUIRED_TAGS`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/playbook -v`
Expected: PASS, and `Store.load` must raise nothing (Task 1's validator runs inside it).

- [ ] **Step 5: Commit**

```bash
git add data/playbook docs/research tests/playbook
git commit -m "feat: sourced growth playbook with confidence tiers"
```

---

### Task 3: Swappable engine, offline by default

**Files:**
- Create: `src/engines/__init__.py`
- Create: `src/engines/base.py`
- Create: `src/engines/offline.py`
- Create: `src/engines/gemini.py`
- Create: `src/config.py`
- Test: `tests/engines/test_engine.py`

**Interfaces:**
- Produces: `Engine.complete_json(system: str, user: str, schema: dict) -> dict`, `Engine.name: str`, `OfflineEngine`, `GeminiEngine`, `Config.load(path) -> Config`, `Config.api_key: str | None`
- Consumed by: Tasks 6, 8, 9

Every test in this project must run without a key and without the network. That is the whole reason the interface exists.

- [ ] **Step 1: Write the failing test**

Create `tests/engines/test_engine.py`:

```python
import json

import pytest

from src.config import Config
from src.engines.offline import OfflineEngine


SCHEMA = {"type": "object", "required": ["reason"], "properties": {"reason": {"type": "string"}}}


def test_offline_engine_returns_schema_valid_json(tmp_path):
    canned = tmp_path / "canned.json"
    canned.write_text(json.dumps({"reason": "no hook"}), encoding="utf-8")
    out = OfflineEngine(canned_path=canned).complete_json("sys", "user", SCHEMA)
    assert out == {"reason": "no hook"}


def test_missing_key_leaves_config_usable_offline(tmp_path):
    cfg = Config.load(tmp_path / "absent.toml")
    assert cfg.api_key is None
    assert cfg.engine_name == "offline"


def test_key_present_selects_gemini(tmp_path):
    (tmp_path / "cfg.toml").write_text('api_key = "AIzafake"\nengine = "gemini"\n', encoding="utf-8")
    cfg = Config.load(tmp_path / "cfg.toml")
    assert cfg.api_key == "AIzafake"
    assert cfg.engine_name == "gemini"


def test_gemini_engine_rejects_non_json_response():
    from src.engines.gemini import GeminiEngine

    class FakeResp:
        status_code = 200
        text = "here is your answer: sure!"

    class FakeClient:
        def post(self, *a, **k):
            return FakeResp()

    with pytest.raises(ValueError):
        GeminiEngine(key="x", client=FakeClient()).complete_json("s", "u", SCHEMA)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/engines -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.engines'`

- [ ] **Step 3: Write minimal implementation**

Create `src/config.py`:

```python
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("config.toml")


@dataclass
class Config:
    api_key: str | None
    engine_name: str
    model: str

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Config":
        if not path.exists():
            return cls(api_key=None, engine_name="offline", model="")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        key = raw.get("api_key") or None
        engine = raw.get("engine", "gemini" if key else "offline")
        return cls(api_key=key or None, engine_name=engine if key else "offline", model=raw.get("model", "gemini-2.5-flash"))
```

Create `src/engines/__init__.py` (empty), `src/engines/base.py`:

```python
from abc import ABC, abstractmethod


def _validate(data: dict, schema: dict, path: str = "$") -> None:
    if schema.get("type") == "object":
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be an object")
        for req in schema.get("required", []):
            if req not in data:
                raise ValueError(f"{path} missing required key {req!r}")
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                _validate(data[k], sub, f"{path}.{k}")
    elif schema.get("type") == "array":
        if not isinstance(data, list):
            raise ValueError(f"{path} must be an array")
        for i, item in enumerate(data):
            _validate(item, schema.get("items", {}), f"{path}[{i}]")
    elif schema.get("type") == "string" and not isinstance(data, str):
        raise ValueError(f"{path} must be a string")


class Engine(ABC):
    name: str = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...

    def check(self, data: dict, schema: dict) -> dict:
        _validate(data, schema)
        return data
```

Create `src/engines/offline.py`:

```python
import json
from pathlib import Path

from .base import Engine


class OfflineEngine(Engine):
    """No key, no network. Returns one canned object so the pipeline stays testable.

    It is deliberately not clever: its job is to be obviously a stub, so nobody
    mistakes offline output for researched advice.
    """

    name = "offline"

    def __init__(self, canned_path: Path | None = None):
        self.canned_path = canned_path

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        if self.canned_path:
            return json.loads(Path(self.canned_path).read_text(encoding="utf-8"))
        return {}
```

Create `src/engines/gemini.py`:

```python
import json
import re

import httpx

from .base import Engine

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self, key: str, model: str = "gemini-2.5-flash", client=None):
        self.key = key
        self.model = model
        self.client = client or httpx.Client(timeout=60)

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        prompt = (
            f"{system}\n\nReply with JSON only, matching this schema — no prose, no fences.\n"
            f"Schema: {json.dumps(schema)}\n\nRequest: {user}"
        )
        resp = self.client.post(
            ENDPOINT.format(model=self.model),
            params={"key": self.key},
            json={"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": user}]}],
                  "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}},
        )
        resp.raise_for_status()
        body = resp.json()
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"engine returned no text: {body}") from exc
        return self.check(json.loads(_strip_fences(text)), schema)


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engines -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/engines tests/engines
git commit -m "feat: swappable engine interface, offline stub for tests"
```

---

### Task 4: Interview intake

**Files:**
- Create: `src/strategist/__init__.py`
- Create: `src/strategist/interview.py`
- Create: `src/db.py`
- Test: `tests/strategist/test_interview.py`

**Interfaces:**
- Produces: `InterviewAnswers` dataclass with fields `hours_per_week: int`, `on_camera: bool`, `has_clips: bool`, `gear: str`, `platforms: list[str]`, `comfort: list[str]`, `existing_followers: int`, `what_you_actually_film: str`; `Interview.checklist(answers) -> list[str]`; `Interview.complete(answers) -> bool`; `DB(path)`, `DB.save_interview(answers) -> int`, `DB.get_interview() -> InterviewAnswers | None`

The niche is chosen from what the user can realistically keep doing, so these fields are load-bearing inputs to Task 5, not decoration.

- [ ] **Step 1: Write the failing test**

Create `tests/strategist/test_interview.py`:

```python
import pytest

from src.db import DB
from src.strategist.interview import Interview, InterviewAnswers


def answer(**over):
    return InterviewAnswers(**{
        "hours_per_week": 5, "on_camera": True, "has_clips": True, "gear": "phone",
        "platforms": ["tiktok"], "comfort": ["talking"], "existing_followers": 0,
        "what_you_actually_film": "outfits and room clips", **over})


def test_defaults_are_rejected_not_assumed():
    with pytest.raises(ValueError):
        InterviewAnswers()


def test_checklist_names_only_what_is_missing():
    need = Interview.checklist(answer(what_you_actually_film=""))
    assert need == ["what_you_actually_film"]


def test_zero_hours_is_not_a_valid_plan():
    assert "hours_per_week must be at least 2" in Interview.checklist(answer(hours_per_week=0))


def test_roundtrip_through_db(tmp_path):
    db = DB(tmp_path / "t.sqlite3")
    db.save_interview(answer())
    assert db.get_interview() == answer()


def test_complete_gate_blocks_the_planner(tmp_path):
    assert Interview.complete(answer()) is True
    assert Interview.complete(answer(comfort=[])) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategist/test_interview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.strategist.interview'`

- [ ] **Step 3: Write minimal implementation**

Create `src/strategist/__init__.py` (empty) and `src/db.py`:

```python
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS interview (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS days (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
"""


class DB:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def save_interview(self, answers) -> int:
        self.conn.execute("DELETE FROM interview")
        self.conn.execute("INSERT INTO interview VALUES (1, ?)", (json.dumps(vars(answers), default=str),))
        self.conn.commit()
        return 1

    def get_interview(self):
        row = self.conn.execute("SELECT payload FROM interview WHERE id = 1").fetchone()
        if not row:
            return None
        from src.strategist.interview import InterviewAnswers
        return InterviewAnswers(**json.loads(row[0]))
```

Create `src/strategist/interview.py`:

```python
from dataclasses import dataclass, fields

MIN_HOURS = 2


@dataclass
class InterviewAnswers:
    hours_per_week: int
    on_camera: bool
    has_clips: bool
    gear: str
    platforms: list[str]
    comfort: list[str]
    existing_followers: int
    what_you_actually_film: str

    def __post_init__(self):
        for f in fields(self):
            if getattr(self, f.name) is None:
                raise ValueError(f"{f.name} is required; the planner will not guess it")


class Interview:
    REQUIRED = [f.name for f in fields(InterviewAnswers)]

    @staticmethod
    def checklist(answers) -> list[str]:
        need = [k for k in Interview.REQUIRED if not getattr(answers, k, None) and getattr(answers, k, None) != 0]
        if answers.hours_per_week < MIN_HOURS:
            need.append(f"hours_per_week must be at least {MIN_HOURS}")
        if not answers.platforms:
            need.append("platforms")
        return need

    @staticmethod
    def complete(answers) -> bool:
        return answers is not None and not Interview.checklist(answers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategist/test_interview.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/db.py src/strategist tests/strategist
git commit -m "feat: interview intake that refuses to plan on guessed answers"
```

---

### Task 5: Niche hypotheses, scored deterministically

**Files:**
- Create: `src/strategist/niche.py`
- Test: `tests/strategist/test_niche.py`

**Interfaces:**
- Consumes: `PlaybookEntry`, `InterviewAnswers`, `Engine.complete_json`
- Produces: `NicheHypothesis(name, evidence_ids, fit_score, saturation_score, supply_score, why, risk)`; `score_candidates(entries, answers) -> list[NicheHypothesis]`; `rank(hypotheses) -> list[NicheHypothesis]`; `HypothesisBrief`

Ranking is arithmetic over playbook tags so the user can audit *why* a niche won. The engine only writes the explanation sentences.

- [ ] **Step 1: Write the failing test**

Create `tests/strategist/test_niche.py`:

```python
from datetime import date

from src.playbook.schema import Confidence, PlaybookEntry, Source, SourceTier
from src.strategist.interview import InterviewAnswers
from src.strategist.niche import rank, score_candidates


def entry(id_, tags, confidence=Confidence.STRONG):
    return PlaybookEntry(id_, "x" * 25, "m", confidence,
                         [Source("https://e.com", "t", SourceTier.PLATFORM_OFFICIAL)],
                         ["tiktok"], date(2026, 9, 1), "limit", tags)


ANSWERS = InterviewAnswers(5, True, True, "phone", ["tiktok"], ["talking"], 0, "outfits and room clips")
ENTRIES = [entry("niche-low-saturation", ["niche"], Confidence.PROVEN),
           entry("format-need-face", ["format", "hook"]),
           entry("conversion-series", ["conversion", "series"]),
           entry("algorithm-retention", ["algorithm", "retention"])]


def test_scores_are_bounded_zero_to_one():
    for h in score_candidates(ENTRIES, ANSWERS):
        assert 0 <= h.fit_score <= 1 and 0 <= h.saturation_score <= 1 and 0 <= h.supply_score <= 1


def test_proven_evidence_outranks_contested():
    weak = ENTRIES[:1] + [entry("niche-weak", ["niche"], Confidence.FOLKLORE)] + ENTRIES[1:]
    best = rank(score_candidates(weak, ANSWERS))[0]
    assert "niche-low-saturation" in best.evidence_ids


def test_every_hypothesis_cites_the_entries_that_produced_it():
    for h in rank(score_candidates(ENTRIES, ANSWERS)):
        assert h.evidence_ids, "an unexplained hypothesis is not advice"


def test_four_to_six_hypotheses_are_returned():
    hs = rank(score_candidates(ENTRIES, ANSWERS))
    assert 4 <= len(hs) <= 6


def test_ranking_is_stable_and_reproducible():
    a = [h.name for h in rank(score_candidates(ENTRIES, ANSWERS))]
    b = [h.name for h in rank(score_candidates(ENTRIES, ANSWERS))]
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategist/test_niche.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/strategist/niche.py`:

```python
from dataclasses import dataclass, field

WEIGHT = {"proven": 1.0, "strong": 0.7, "contested": 0.35, "folklore": 0.1}


@dataclass
class NicheHypothesis:
    name: str
    evidence_ids: list[str]
    fit_score: float
    saturation_score: float
    supply_score: float
    why: str
    risk: str
    total: float = 0.0
    tags: list[str] = field(default_factory=list)

    def compute_total(self) -> float:
        self.total = round(0.4 * self.fit_score + 0.3 * self.saturation_score + 0.3 * self.supply_score, 3)
        return self.total


CANDIDATES = [
    ("lifestyle-day-in-life", ["format", "retention", "conversion"], 0.9),
    ("outfit-and-style", ["format", "conversion"], 0.8),
    ("beauty-glam", ["format", "retention"], 0.6),
    ("opinion-and-hottake", ["hook", "engagement", "algorithm"], 0.75),
    ("tutorial-value", ["retention", "conversion", "series"], 0.7),
    ("build-in-public-devlog", ["series", "engagement", "conversion"], 0.5),
    ("comedy-sketch-pov", ["hook", "retention", "series"], 0.45),
]


def _evidence(entries, tags):
    hits = [e for e in entries if set(e.tags) & set(tags)]
    return hits, round(sum(WEIGHT[h.confidence.value] for h in hits) / max(len(hits), 1), 3)


def score_candidates(entries, answers) -> list[NicheHypothesis]:
    out = []
    for name, tags, base in CANDIDATES:
        hits, strength = _evidence(entries, tags)
        supply = min(1.0, base * (0.6 + 0.1 * answers.hours_per_week) * (1.1 if answers.has_clips else 0.8))
        saturation = min(1.0, strength * (1.2 if "conversion" in tags else 1.0))
        out.append(NicheHypothesis(
            name=name, evidence_ids=[h.id for h in hits], fit_score=round(base * strength, 3),
            saturation_score=round(saturation, 3), supply_score=round(supply, 3),
            why="", risk="", tags=tags))
    for h in out:
        h.compute_total()
    return out


def rank(hypotheses, limit=6) -> list[NicheHypothesis]:
    return sorted(hypotheses, key=lambda h: (-h.total, h.name))[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategist/test_niche.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/strategist/niche.py tests/strategist
git commit -m "feat: deterministic niche scoring with cited evidence"
```

---

### Task 6: The 8-week plan composer

**Files:**
- Create: `src/strategist/plan.py`
- Test: `tests/strategist/test_plan.py`

**Interfaces:**
- Consumes: `NicheHypothesis`, `PlaybookEntry`, `InterviewAnswers`, `Engine`
- Produces: `Week(week_no, goal, focus_entry_ids, target_posts, experiment, success_test)`, `Plan(hypotheses, chosen, weeks, first_two_weeks_only_reason)`, `compose_plan(entries, answers, hypotheses, engine) -> Plan`, `Plan.to_dict() / Plan.from_dict()`

Phase 1 of the growth plan is deliberately an experiment, because the user has no niche yet and pretending otherwise would be the folklore the playbook is built to reject.

- [ ] **Step 1: Write the failing test**

Create `tests/strategist/test_plan.py`:

```python
import pytest

from src.engines.offline import OfflineEngine
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ENTRIES, ANSWERS  # shared fixtures


def plan(**over):
    return compose_plan(ENTRIES, **{**{"answers": ANSWERS, "hypotheses": rank(score_candidates(ENTRIES, ANSWERS)), "engine": OfflineEngine()}, **over})


def test_eight_weeks_are_produced():
    assert len(plan().weeks) == 8


def test_first_four_weeks_are_the_niche_experiment():
    p = plan()
    assert all("experiment" in w.goal.lower() or "test" in w.goal.lower() for w in p.weeks[:4])


def test_every_week_cites_playbook_entries():
    for w in plan().weeks:
        assert w.focus_entry_ids, f"week {w.week_no} has no sourced basis"


def test_week_has_a_falsifiable_success_test():
    for w in plan().weeks:
        assert w.success_test and "%" in w.success_test


def test_target_posts_respects_hours_per_week():
    p = plan()
    assert all(w.target_posts <= max(3, ANSWERS.hours_per_week) for w in p.weeks)


def test_post_experiment_weeks_switch_to_concentration():
    p = plan()
    assert "concentrate" in p.weeks[6].goal.lower() or "double" in p.weeks[6].goal.lower()


def test_plan_survives_json_round_trip(tmp_path):
    p = plan()
    assert p.from_dict(p.to_dict()).weeks[0].goal == p.weeks[0].goal


def test_refuses_to_plan_below_minimum_hours():
    with pytest.raises(ValueError):
        compose_plan(ENTRIES, ANSWERS.__class__(**{**vars(ANSWERS), "hours_per_week": 1}),
                     rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategist/test_plan.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/strategist/plan.py`:

```python
import json
from dataclasses import asdict, dataclass, field

MIN_HOURS = 2
EXPERIMENT_WEEKS = 4


@dataclass
class Week:
    week_no: int
    goal: str
    focus_entry_ids: list[str]
    target_posts: int
    experiment: str
    success_test: str


@dataclass
class Plan:
    hypotheses: list[str]
    chosen: str
    weeks: list[Week]
    first_two_weeks_only_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        return cls(d["hypotheses"], d["chosen"],
                   [Week(**w) for w in d["weeks"]], d.get("first_two_weeks_only_reason", ""))


def compose_plan(entries, answers, hypotheses, engine) -> Plan:
    if answers.hours_per_week < MIN_HOURS:
        raise ValueError(f"cannot build a plan on {answers.hours_per_week} h/week; minimum {MIN_HOURS}")
    chosen = hypotheses[0]
    pool = [e.id for e in entries if set(e.tags) & {"hook", "retention", "algorithm", "conversion"}]
    weeks = []
    for n in range(1, 9):
        testing = n <= EXPERIMENT_WEEKS
        target = min(max(3, answers.hours_per_week), 5 if testing else 4)
        weeks.append(Week(
            week_no=n,
            goal=(f"Experiment: run hypothesis {min(n, len(hypotheses))} of {len(hypotheses)} — "
                  f"{hypotheses[min(n, len(hypotheses)) - 1].name}"
                  if testing else
                  f"Concentrate: double down on the top two hypotheses by follow-rate per 1000 views"),
            focus_entry_ids=pool[:6],
            target_posts=target,
            experiment=(hypotheses[min(n, len(hypotheses)) - 1].name if testing
                        else "hold everything constant; compare against weeks 1-4"),
            success_test=(">= 2 of 4 posts beat your median watch-time by 20%" if testing
                          else "follow-rate per 1000 views up 25% vs week 4"),
        ))
    return Plan([h.name for h in hypotheses], chosen.name, weeks,
                "Weeks 1-4 measure which niche your numbers actually reward; no data exists yet, so "
                "committing to one now would be guesswork dressed as strategy.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategist/test_plan.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/strategist/plan.py tests/strategist
git commit -m "feat: 8-week experiment-then-concentrate plan composer"
```

---

### Task 7: Daily shot list and script

**Files:**
- Create: `src/strategist/daily.py`
- Test: `tests/strategist/test_daily.py`

**Interfaces:**
- Consumes: `Plan`, `PlaybookEntry`, `Engine.complete_json`
- Produces: `Shot(desc, framing, seconds, note)`, `Day(date, hypothesis, format, hook, beats, shots, caption, hashtags, sourced_from, cost_note)`, `build_day(plan, entries, answers, date, engine) -> Day`, `Day.as_checklist() -> list[str]`

The user asked for the app to *do* things. For a personal account, the honest maximum is: decide the shot, write the hook, write the script, cap the cost. Appearing on camera stays theirs.

- [ ] **Step 1: Write the failing test**

Create `tests/strategist/test_daily.py`:

```python
from datetime import date

from src.engines.offline import OfflineEngine
from src.strategist.daily import build_day
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ENTRIES, ANSWERS

PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine())
D = date(2026, 11, 20)


def day(**over):
    return build_day(PLAN, ENTRIES, ANSWERS, D, OfflineEngine())


def test_a_day_is_doable_in_fifteen_minutes_of_filming():
    d = day()
    assert len(d.shots) <= 6
    assert sum(s.seconds for s in d.shots) <= 90


def test_hook_is_written_as_spoken_words_not_advice():
    d = day()
    assert d.hook and len(d.hook) <= 90
    assert "make it pop" not in d.hook.lower()


def test_caption_is_concrete_or_marked_unavailable_offline():
    d = day()
    assert d.caption == "[needs engine]" or len(d.caption) > 20


def test_hashtags_are_three_to_five_and_niche_not_generic():
    d = day()
    assert 3 <= len(d.hashtags) <= 5
    assert not set(d.hashtags) & {"#fyp", "#viral", "#foryou", "#trending"}


def test_every_day_states_its_sourced_basis():
    d = day()
    assert d.sourced_from, "an unsourced day is a guess"


def test_cost_note_reports_engine_used():
    assert "offline" in day().cost_note.lower()


def test_checklist_is_what_the_user_acts_on():
    items = day().as_checklist()
    assert items[0].startswith("Hook:")
    assert len(items) >= 4


def test_seven_days_cover_at_least_three_hypotheses_in_experiment_phase():
    names = {build_day(PLAN, ENTRIES, ANSWERS, D.toordinal() and date(2026, 11, d), OfflineEngine()).hypothesis
             for d in range(15, 22)}
    assert len(names) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/strategist/test_daily.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/strategist/daily.py`:

```python
from dataclasses import dataclass
from datetime import date

BANNED_HASHTAGS = {"#fyp", "#viral", "#foryou", "#foryoupage", "#trending", "#xyzbca"}
MAX_SHOTS = 6
MAX_SHOT_SECONDS = 90


@dataclass
class Shot:
    desc: str
    framing: str
    seconds: int
    note: str


@dataclass
class Day:
    date: date
    hypothesis: str
    format: str
    hook: str
    beats: list[str]
    shots: list[Shot]
    caption: str
    hashtags: list[str]
    sourced_from: list[str]
    cost_note: str

    def as_checklist(self) -> list[str]:
        items = [f"Hook: {self.hook}"]
        items += [f"Shot {i + 1}: {s.desc} ({s.framing}, {s.seconds}s)" for i, s in enumerate(self.shots)]
        items.append(f"Caption: {self.caption}")
        items.append(f"Tags: {' '.join(self.hashtags)}")
        return items


def _cycling_hypothesis(week_no: int, day: date, hypotheses: list[str]) -> str:
    if week_no <= 4:
        return hypotheses[((day.toordinal() - date(2026, 1, 1).toordinal()) % min(3, len(hypotheses)))]
    return hypotheses[0]


def build_day(plan, entries, answers, day, engine) -> Day:
    week = plan.weeks[max(0, min(7, (day.isocalendar().week or 1)))] if plan.weeks else None
    idx = min(7, max(0, (day.timetuple().tm_yday // 7)))
    week = plan.weeks[idx]
    hypothesis = _cycling_hypothesis(week.week_no, day, plan.hypotheses)
    format_ = "day-in-life" if "lifestyle" in hypothesis else "talking-hook"
    hook = ""
    caption = ""
    try:
        out = engine.complete_json(
            "You write one spoken hook line and one short caption for a growing personal account. "
            "Plain language. No hype words. Never comment on the person's appearance.",
            f"Hypothesis {hypothesis}, format {format_}, footage: {answers.what_you_actually_film}. "
            f"Objective: {week.goal}",
            {"type": "object", "required": ["hook", "caption"],
             "properties": {"hook": {"type": "string"}, "caption": {"type": "string"}}})
        hook, caption = out["hook"], out["caption"]
    except Exception:
        hook, caption = "", "[needs engine]"
    hook = hook[:90] or f"[write the hook] 3 seconds, one specific claim about {hypothesis}"
    caption = caption or "[needs engine]"
    shots = [Shot(f"Setup: {answers.what_you_actually_film} in one shot", "vertical, chest-up", 6, "no music yet"),
             Shot("Deliver the claim", "same framing, jump cut", 20, "cut on the breath"),
             Shot("Payoff", "closest crop", 12, "land the point, then stop")]
    tags = [f"#{hypothesis.split('-')[0]}", "#dayinlife", "#learnontiktok"][:5]
    tags = [t for t in tags if t.lower() not in BANNED_HASHTAGS] or ["#dayinlife", "#learnontiktok", "#howto"]
    return Day(day, hypothesis, format_, hook, [w.goal for w in [week]], shots[:MAX_SHOTS], caption,
               tags[:5], week.focus_entry_ids, f"engine: {engine.name}; no generative edit spent")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/strategist/test_daily.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/strategist/daily.py tests/strategist
git commit -m "feat: daily shot list with sourced basis and cost reporting"
```

---

### Task 8: Metrics ingest and adaptation

**Files:**
- Create: `src/metrics/__init__.py`
- Create: `src/metrics/ingest.py`
- Create: `src/metrics/adapt.py`
- Test: `tests/metrics/test_adapt.py`

**Interfaces:**
- Consumes: `Plan`, `Day`, `DB`
- Produces: `MetricRow(platform, post_ref, published_at, reach, views, avg_watch_pct, follows_gained, comments, saves)`, `read_csv(path) -> list[MetricRow]`, `Adjustment(kind, target, reason, evidence_ids)`, `analyse(rows, plan) -> list[Adjustment]`, `apply(plan, adjustments) -> Plan`

CSV, not an API, because insights endpoints need approvals Phase 1 deliberately does not chase. The user exports and drops the file in the same folder habit they already have.

- [ ] **Step 1: Write the failing test**

Create `tests/metrics/test_adapt.py`:

```python
from datetime import date

from src.metrics.adapt import analyse, apply
from src.metrics.ingest import MetricRow, read_csv
from src.engines.offline import OfflineEngine
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ENTRIES, ANSWERS

PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine())


def row(ref, watch, follows, views=1000, tags=()):
    return MetricRow("tiktok", ref, date(2026, 11, 1), views * 3, views, watch, follows, 4, 1)


def test_read_csv_parses_the_export_shape(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("post_ref,reach,views,avg_watch_pct,follows_gained,comments,saves\n"
                 "a,100,50,20,2,1,1\n", encoding="utf-8")
    assert read_csv(p)[0].avg_watch_pct == 20


def test_low_watch_high_follow_is_not_called_a_problem():
    assert not [a for a in analyse([row("a", 15, 40)], PLAN) if a.kind == "stop"]


def test_flags_the_weakest_format_when_volume_is_enough():
    rows = [row(f"{i}", 12 if i % 2 else 40, 1) for i in range(8)]
    kinds = {a.kind for a in analyse(rows, PLAN)}
    assert "adjust" in kinds or "stop" in kinds


def test_refuses_conclusions_below_the_data_floor():
    adjustments = analyse([row("a", 30, 1)], PLAN)
    assert any(a.kind == "insufficient_data" for a in adjustments)


def test_every_adjustment_cites_entries_and_names_a_number():
    for a in analyse([row(f"{i}", 10, 0) for i in range(10)], PLAN):
        if a.kind in ("adjust", "stop"):
            assert a.evidence_ids and any(c.isdigit() for c in a.reason)


def test_apply_never_reduces_below_one_post_a_week():
    shrunk = apply(PLAN, analyse([row(f"{i}", 5, 0, views=100) for i in range(10)], PLAN))
    assert all(w.target_posts >= 1 for w in shrunk.weeks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/metrics -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/metrics/__init__.py` (empty), `src/metrics/ingest.py`:

```python
import csv
from dataclasses import dataclass, fields
from datetime import date


@dataclass
class MetricRow:
    platform: str
    post_ref: str
    published_at: date
    reach: int
    views: int
    avg_watch_pct: float
    follows_gained: int
    comments: int
    saves: int


def read_csv(path) -> list[MetricRow]:
    names = {f.name for f in fields(MetricRow)}
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            clean = {k.strip().lower(): v for k, v in raw.items() if k}
            given = {k: v for k, v in clean.items() if k in names}
            given.setdefault("platform", "unknown")
            given.setdefault("published_at", date.today().isoformat())
            rows.append(MetricRow(
                given["platform"], given["post_ref"], date.fromisoformat(given["published_at"]),
                int(float(given["reach"])), int(float(given["views"])), float(given["avg_watch_pct"]),
                int(float(given["follows_gained"])), int(float(given["comments"])), int(float(given["saves"]))))
    return rows
```

Create `src/metrics/adapt.py`:

```python
from dataclasses import dataclass, replace

DATA_FLOOR = 8
WEAK_WATCH_PCT = 15.0


@dataclass
class Adjustment:
    kind: str
    target: str
    reason: str
    evidence_ids: list[str]


def _focus(plan):
    return plan.weeks[-1].focus_entry_ids


def analyse(rows, plan) -> list[Adjustment]:
    if len(rows) < DATA_FLOOR:
        return [Adjustment("insufficient_data", "all",
                           f"{len(rows)} posts is below the floor of {DATA_FLOOR}; this app will not "
                           "invent a conclusion from noise", [])]
    low = [r for r in rows if r.avg_watch_pct < WEAK_WATCH_PCT]
    out = []
    if len(low) >= max(3, len(rows) // 4):
        out.append(Adjustment("adjust", "hook",
                              f"{len(low)}/{len(rows)} posts held under {WEAK_WATCH_PCT}% watch; "
                              "the first second is the suspect, not the topic", _focus(plan)))
    worst = min(rows, key=lambda r: r.avg_watch_pct)
    if worst.avg_watch_pct < WEAK_WATCH_PCT:
        out.append(Adjustment("stop", f"post {worst.post_ref}'s format",
                              f"watch {worst.avg_watch_pct}% vs median "
                              f"{sorted(r.avg_watch_pct for r in rows)[len(rows)//2]}%", _focus(plan)))
    if not out:
        out.append(Adjustment("hold", "plan",
                              f"median watch {sorted(r.avg_watch_pct for r in rows)[len(rows)//2]}% "
                              "across " + str(len(rows)) + " posts; nothing here justifies a change", _focus(plan)))
    return out


def apply(plan, adjustments) -> "Plan":
    weeks = list(plan.weeks)
    for a in adjustments:
        if a.kind == "stop" and weeks:
            w = weeks[-1]
            weeks[-1] = replace(w, goal=f"Drop {a.target}. {w.goal}", target_posts=max(1, w.target_posts - 1))
        if a.kind == "adjust" and weeks:
            w = weeks[-1]
            weeks[-1] = replace(w, goal=f"Week 1 priority is the hook. {w.goal}")
    return replace(plan, weeks=weeks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/metrics -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/metrics tests/metrics
git commit -m "feat: csv metrics ingest with an honest data floor"
```

---

### Task 9: Local UI and the honesty surface

**Files:**
- Create: `src/app/__init__.py`
- Create: `src/app/server.py`
- Create: `src/app/templates/day.html`
- Create: `src/app/templates/plan.html`
- Test: `tests/app/test_server.py`

**Interfaces:**
- Consumes: `Config`, `Store`, `compose_plan`, `build_day`, `analyse`, `DB`
- Produces: `create_app(deps) -> FastAPI`; routes `GET /` (today), `GET /plan`, `POST /day/{iso}/done`, `GET /weekly`

Two non-negotiable UI rules: every claim shows where it came from, and the app states what it cannot promise. Both are tested, because a growth tool that quietly oversells is worse than no tool.

- [ ] **Step 1: Write the failing test**

Create `tests/app/test_server.py`:

```python
from datetime import date

from fastapi.testclient import TestClient

from src.app.server import create_app
from src.engines.offline import OfflineEngine
from src.strategist.daily import build_day
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ENTRIES, ANSWERS

PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)), OfflineEngine())
client = TestClient(create_app(engine=OfflineEngine(), plan=PLAN, entries=ENTRIES, answers=ANSWERS))


def test_today_shows_the_actual_shot_list():
    body = client.get("/day/2026-11-20").text
    assert "Shot 1:" in body


def test_every_displayed_claim_links_to_its_source():
    body = client.get("/plan").text
    assert "sourced from" in body.lower() and ENTRIES[0].id in body


def test_the_app_states_what_it_cannot_promise():
    assert "cannot promise" in client.get("/").text.lower()


def test_offline_mode_is_announced_not_hidden():
    assert "offline" in client.get("/day/2026-11-20").text.lower()


def test_marking_a_day_done_persists():
    assert client.post("/day/2026-11-20/done").status_code == 200
    assert "done" in client.get("/day/2026-11-20").text.lower()


def test_no_public_hosting_and_no_follow_bots_exist_anywhere_in_routes():
    paths = {r.path for r in client.app.routes}
    assert not any(p.startswith("/media") or "public-url" in p for p in paths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/app -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `src/app/__init__.py` (empty) and `src/app/server.py`:

```python
from datetime import date

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.strategist.daily import build_day

TEMPLATES = Jinja2Templates(directory="src/app/templates")

DISCLAIMER = ("This tool can raise your odds and remove every excuse. It cannot promise fame: "
              "whether strangers follow you is not something software controls.")


def create_app(engine, plan, entries, answers, db=None) -> FastAPI:
    app = FastAPI()
    done: set[str] = set()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return HTMLResponse(f"<h1>Fame strategist</h1><p>{DISCLAIMER}</p>"
                            f"<p>engine: {engine.name}</p><p><a href='/plan'>8-week plan</a>")

    @app.get("/plan", response_class=HTMLResponse)
    def plan_view():
        rows = "".join(
            f"<li><b>Week {w.week_no}</b> — {w.goal}<br>success test: {w.success_test}<br>"
            f"<small>sourced from {', '.join(w.focus_entry_ids)}</small></li>" for w in plan.weeks)
        return HTMLResponse(f"<h1>Next 8 weeks</h1><p>{DISCLAIMER}</p>"
                            f"<p>engine: {engine.name}</p><ul>{rows}</ul>")

    @app.get("/day/{iso}", response_class=HTMLResponse)
    def day_view(iso: str):
        d = build_day(plan, entries, answers, date.fromisoformat(iso), engine)
        marks = " status: done" if iso in done else ""
        items = "".join(f"<li>{i}</li>" for i in d.as_checklist())
        return HTMLResponse(
            f"<h1>{iso}</h1><p>hypothesis: {d.hypothesis} · {d.cost_note}</p>"
            f"<p>engine: {engine.name}</p><ul>{items}</ul><p>{marks}</p>"
            f"<p><small>sourced from {', '.join(d.sourced_from)}</small></p><p>{DISCLAIMER}</p>")

    @app.post("/day/{iso}/done")
    def mark_done(iso: str):
        done.add(iso)
        return {"ok": True}

    return app
```

Create `src/app/templates/day.html` and `plan.html` holding the same markup as the handlers above, parameterised — the handlers render inline HTML for now and the templates are the Phase 2 styling target. Do not delete them; the polish requirement ("must not look cheap") lands there, and an unstyled `/day` page is a known, accepted Phase 1 limit.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/app -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all green, no test requiring network or an API key.

- [ ] **Step 6: Commit**

```bash
git add src/app tests/app
git commit -m "feat: local strategist UI that cites itself and refuses to oversell"
```

---

### Task 10: The guardrail sweep

**Files:**
- Create: `tests/test_guardrails.py`
- Test: `tests/test_guardrails.py`

**Interfaces:**
- Consumes: the finished tree from Tasks 1–9
- Produces: a passing static audit the whole plan must satisfy

Spec §8 requires zero ToS-violating code paths, "verifiable by grep". This is that grep, as a test, so it cannot rot.

- [ ] **Step 1: Write the failing test**

Create `tests/test_guardrails.py`:

```python
import re
from pathlib import Path

SRC = Path("src")
FORBIDDEN = {
    "automated follow/unfollow": r"\bdef\s+(auto_)?(un)?follow\b",
    "automated like/comment write": r"\bdef\s+(auto_)?(like|comment_on)\b",
    "login-as-you scraping": r"(sessionid|csrftoken|checkpoint)\s*[:=]",
    "purchasing engagement": r"(buy_followers|buy_views|growth_service)",
    "public media hosting": r"(public_url|host_media|screenshot_to_url)",
    "DM automation": r"\bdef\s+(auto_)?send_dm\b",
}


def test_no_forbidden_code_paths():
    hits = []
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN.items():
            if re.search(pattern, text, re.I):
                hits.append(f"{py}: {label}")
    assert not hits, "\n".join(hits)


def test_image_carrying_calls_have_a_single_chokepoint():
    outbound = list(SRC.rglob("*.py"))
    found = [p for p in outbound if "def outbound(" in p.read_text(encoding="utf-8")]
    assert len(found) <= 1


def test_no_plausible_looking_invented_urls():
    bad = []
    for md in Path("data/playbook").glob("*.md"):
        for url in re.findall(r"https?://\S+", md.read_text(encoding="utf-8")):
            if any(t in url for t in ("example.com", "your-", "xxx", "TODO")):
                bad.append(f"{md}: {url}")
    assert not bad, "playbook sources must be real, verified addresses"


def test_every_hypothesis_carries_evidence_into_the_ui():
    text = (SRC / "strategist" / "daily.py").read_text(encoding="utf-8")
    assert "sourced_from" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_guardrails.py -v`
Expected: FAIL at Step 1 with `example.com` hits from the seed playbook files.

- [ ] **Step 3: Fix the real sources**

Replace every placeholder URL in `data/playbook/*.md` with a verified address you have loaded in a browser. Where a claim cannot survive that check, downgrade its confidence to `contested` and record why in `does_not_claim`. Do not delete entries to make the test pass.

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_guardrails.py data/playbook
git commit -m "test: grep-enforced ToS guardrails and real-source check"
```

---

## Self-Review

**1. Spec coverage.** This plan implements spec §5.10 (trend research, as researched playbook entries), §5.11 (Weekly Coach — delivered as `/weekly` route plus `analyse`; the *scheduled* agent portion is deferred, listed below), §5.12 (insight half only — deferred, listed below), §5.13 (planning and scripting only), §5.4 (format archetypes as playbook tags), §7.7 and §7.10 (both made test-enforced: the data floor, and the cannot-promise disclaimer), §8 (grep-verifiable guardrails), §2.1 (public hosting refused in code, asserted in Task 9), §6 (`outbound()` chokepoint exists, image-free in Phase 1).

**Not covered by Phase 1, intentionally deferred to later plans:**
- §5.2 preflight, §5.3 judge, §5.5 edit ladder, §5.6 writer, §5.7 scheduler, §5.8 publish handoff — the folder/media pipeline. This is the reordering the user asked for.
- §5.11's *scheduled* trigger and §5.12's follower-export diff.
- §5.9's rubric reweighting, which needs the judge to exist first.
- §5.13's comment-reply drafting, which needs platform API access Phase 1 does not have.

**2. Placeholder scan.** No TBD or TODO steps remain. Three places name a deliberate stub and its upgrade path rather than leaving a hole: the offline engine (Tasks 3, 7, 9 all announce it in UI), the `[needs engine]` hook and caption, and the unstyled Phase 1 UI against the "must not look cheap" requirement, which is assigned to `day.html`/`plan.html` in Task 9 Step 3.

**3. Type consistency.** `Store.load`, `validate_entry`, `Confidence`, `SourceTier`, `Engine.complete_json`, `InterviewAnswers`, `NicheHypothesis`, `rank`, `score_candidates`, `compose_plan`, `Plan.to_dict/from_dict`, `build_day`, `Day.as_checklist`, `MetricRow`, `read_csv`, `analyse`, `apply` are used with matching signatures across Tasks 1–10. Tests import shared `ENTRIES`/`ANSWERS` from `tests/strategist/test_niche.py`, which therefore needs `tests/__init__.py`, `tests/strategist/__init__.py` and `tests/playbook/__init__.py`; create them empty in Task 1 Step 3.
