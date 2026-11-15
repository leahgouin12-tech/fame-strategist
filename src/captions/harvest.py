"""Her own past captions, read out of the archive a platform hands her - not retyped by hand.

The register needs one thing and has never had it: sentences she actually wrote. Everything the
caption engine knows about her casing, her punctuation, her abbreviations and her emoji comes from
`db.get_voice()`, and until now the only way to fill it was to retype old posts into a textarea -
which is why every card on `/captions` says the voice is unlearned. The data is not scarce: Instagram,
TikTok and X will each hand her every caption she ever wrote, free, in an official archive that
arrives as a zip on this machine.

**Why this parser refuses to know a schema.** Meta and TikTok document how to request the archive and
do not publish the layout of what comes back, so a parser that hard-coded one filename and one nesting
depth would either return zero on her file or return a structure somebody's blog post claimed. This
walks the JSON instead, takes any string sitting under a caption-shaped key, and reports the key path
each line came from. The page can then quote her own file back to her - `captions[0].mediaList[0].
description` - which is the honest version of the same feature: if the layout is different than
anybody said, she sees the path, not a silent empty list.

Two rules that are not about parsing:

* **other people's words are never her voice.** A key that looks like a conversation (comments,
  replies, messages, followers) is skipped whole and counted, because a stranger's reply would teach
  the generator to sound like a stranger.
* **nothing here is invented.** A line either appears in her file verbatim or it is not in the report,
  and a file with nothing usable returns an error naming the keys it looked for. The app keeps the
  voice state it already had rather than filling the gap with copy the generator thought up.

Everything is read on this machine and nothing is uploaded: the report's lines go into the same
`db.save_voice()` table the paste box writes, with one note row recording where they came from so a
caption card can say so.

The ceilings are real because her machine is small (3.66 GB of RAM): one file at a time, a cap on
bytes, a cap on archive members, a cap on kept lines - and when a cap is hit, `truncated` is set so
the page says how much of it it actually read instead of presenting a partial list as a complete one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import io
import json
import re
import zipfile
from pathlib import Path

# Keys that hold what she wrote. Matched as substrings, case-insensitively, because exports name the
# same idea "caption", "Caption" and "description" in different years.
CANDIDATES = ("caption", "description", "title", "text", "content", "share_text", "post_text", "body")

# Keys that hold what other people wrote, or who follows whom. Checked first, and the whole subtree
# is skipped: a banned key wins over a candidate key, because "text" inside "comments" is not hers.
CONVERSATION = ("comment", "reply", "replies", "response", "message", "direct_message", "reaction",
                "follower", "following", "chat", "review", "dms", "connections")

MAX_BYTES = 40 * 1024 * 1024      # one read on a machine with no headroom to spare
MAX_MEMBERS = 400                 # archive files opened before it stops and says so
MAX_SAMPLES = 400                 # lines kept: past this the register cannot measure more detail
MIN_WORDS = 2
MIN_CHARS = 8
MAX_DROPPED = 60                  # what the page is shown, not what was ignored

TAG = re.compile(r"^\s*(?:#[\w\u00C0-\u024F]+[\s,]*)+$")
LINK = re.compile(r"^\s*(?:(?:https?://|www\.)\S+)(?:\s+(?:https?://|www\.)\S+)*\s*$", re.I)
HAS_WORD = re.compile(r"[A-Za-z0-9\u00C0-\u024F]")
SCHEMA_SUFFIXES = (".json", ".csv", ".txt")


@dataclass
class Report:
    """What a file yielded, what it refused, and what it had to skip to get there."""
    kind: str = ""
    name: str = ""
    samples: list = field(default_factory=list)     # [{"text": ..., "from": path}]
    dropped: list = field(default_factory=list)     # [{"text": ..., "why": ...}]
    files: list = field(default_factory=list)       # archive members actually read
    blocked: list = field(default_factory=list)     # conversation-shaped keys left alone
    truncated: bool = False
    error: str = ""

    @property
    def lines(self) -> list:
        return [s["text"] for s in self.samples]

    def provenance(self) -> str:
        """The one sentence that goes beside the voice, so a caption card can say where her
        register was measured from instead of claiming it learned nothing."""
        n = len(self.samples)
        if not n:
            return ""
        where = f"{len(self.files)} files inside it" if self.files else "one file"
        said = (f"{n} line{'s' if n != 1 else ''} of your own writing, read from "
                f"{self.name or 'a file you handed over'} ({where})")
        if self.blocked:
            said += f", with {len(self.blocked)} conversation key{'s' if len(self.blocked) != 1 else ''} left alone"
        if self.truncated:
            said += f", stopped at the {MAX_SAMPLES}-line ceiling"
        return said + ". Nothing was invented and nothing was uploaded."


def classify(line: str) -> str:
    """Why a string is not a sample, or "" when it is one.

    Length is checked last on purpose: a hashtag wall is long, and it still measures nothing about how
    somebody writes sentences.
    """
    text = (line or "").strip()
    if not text:
        return "nothing in it"
    if not HAS_WORD.search(text):
        return "emoji and punctuation only, which says nothing about how you type a sentence"
    if TAG.match(text):
        return "hashtags only, which says nothing about how you type a sentence"
    if LINK.match(text):
        return "links only"
    if len(text) < MIN_CHARS or len(text.split()) < MIN_WORDS:
        return f"too short to measure anything ({len(text.split())} word" \
               f"{'s' if len(text.split()) != 1 else ''})"
    return ""


def _segments(raw: str) -> list:
    """One caption as the lines it actually is.

    A five-line caption counted as one sample flattens four numbers at once - casing, the terminal
    period, the question rate and emoji per sample are all counted per line - so a caption is split
    and each line earns its own place.
    """
    text = (raw or "").replace("\r\n", "\n").replace("\\r\n", "\n")
    return [part.strip() for part in text.split("\n") if part.strip()]


def _walk(node, path: str, hits: list, blocked: list) -> None:
    """Every string under a caption-shaped key, with the path it sat at."""
    if isinstance(node, dict):
        for key, val in node.items():
            low = str(key).lower()
            here = f"{path}.{key}" if path else str(key)
            if any(word in low for word in CONVERSATION):
                blocked.append(here)
                continue
            if any(cand in low for cand in CANDIDATES):
                if isinstance(val, str):
                    hits.append((here, val))
                    continue
                if isinstance(val, list):
                    for i, item in enumerate(val):
                        if isinstance(item, str):
                            hits.append((f"{here}[{i}]", item))
                        else:
                            _walk(item, f"{here}[{i}]", hits, blocked)
            _walk(val, here, hits, blocked)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path or 'rows'}[{i}]", hits, blocked)


def _from_json(text: str, path: str, hits: list, blocked: list) -> bool:
    try:
        node = json.loads(text)
    except ValueError:
        return False
    _walk(node, "", hits, blocked)
    return True


def _from_csv(text: str, path: str, hits: list, blocked: list) -> bool:
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return False
    except (csv.Error, UnicodeDecodeError):
        return False
    wanted = [col for col in reader.fieldnames if col and
              any(cand in col.lower() for cand in CANDIDATES) and
              not any(word in col.lower() for word in CONVERSATION)]
    skipped = [col for col in reader.fieldnames if col and
               any(word in col.lower() for word in CONVERSATION)]
    blocked.extend(f"{path}.{col}" for col in skipped)
    for n, row in enumerate(reader):
        if n >= MAX_SAMPLES * 2:
            break
        for col in wanted:
            value = (row.get(col) or "").strip()
            if value:
                hits.append((f"{path}[{n + 2}].{col}", value))
    return True


def _digest(text: str, hits: list, blocked: list, name: str) -> str:
    """Read one file's text, whichever way it is shaped; return the kind it turned out to be."""
    stripped = (text or "").strip()
    if not stripped:
        return "empty"
    if _from_json(stripped, name, hits, blocked):
        return "json"
    first = stripped.split("\n", 1)[0]
    if "," in first or name.lower().endswith(".csv"):
        if _from_csv(stripped, name, hits, blocked):
            return "csv"
    hits.append((name, stripped))
    return "text"


EXPORT_SUFFIXES = SCHEMA_SUFFIXES + (".zip",)


def stage(root, report) -> None:
    """Park the read lines where the Writer page can show them for her tick.

    A file, not a note row: `db.remember` truncates a body at 2000 characters and a real caption
    archive runs to hundreds of lines, so the list cannot live in the notes table. The one-sentence
    provenance can, and does - once she has kept something.
    """
    Path(root).mkdir(parents=True, exist_ok=True)
    (Path(root) / "harvest.json").write_text(json.dumps({
        "name": report.name, "kind": report.kind, "provenance": report.provenance(),
        "truncated": report.truncated, "lines": report.samples,
        "dropped": report.dropped, "blocked": report.blocked,
        "files": report.files}, ensure_ascii=False), encoding="utf-8")


def staged(root) -> dict | None:
    """The batch waiting for her decision, or None if there is nothing staged."""
    try:
        return json.loads((Path(root) / "harvest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clear(root) -> None:
    (Path(root) / "harvest.json").unlink(missing_ok=True)


def read(data, name: str = "") -> Report:
    """Every caption this file really contains, with the path each one was read from.

    `data` is the bytes or text of one upload: an archive as delivered, or a single JSON/CSV/text
    file. `name` is only used to say where the lines came from and to pick the reader when the
    content is ambiguous.
    """
    got = Report(name=name or "your file")
    raw = data if isinstance(data, bytes) else str(data or "").encode("utf-8")
    if not raw:
        got.error = ("Nothing arrived - no file was chosen, or the file was empty. Your voice "
                     "profile is unchanged.")
        return got
    if len(raw) > MAX_BYTES:
        got.error = (f"That file is too big to read here ({len(raw) // 1024 // 1024} MB; this "
                     f"machine stops at {MAX_BYTES // 1024 // 1024} MB). Open the archive and hand "
                     f"over the captions file inside it instead of the whole thing.")
        return got

    hits: list = []
    blocked: list = []
    if zipfile.is_zipfile(io.BytesIO(raw)) or (name or "").lower().endswith(".zip"):
        got.kind = "zip"
        try:
            book = zipfile.ZipFile(io.BytesIO(raw))
        except (zipfile.BadZipFile, OSError):
            got.error = ("That is not an archive this can open, so nothing was read and your voice "
                         "profile is unchanged.")
            return got
        with book:
            for i, member in enumerate(book.infolist()):
                if member.is_dir() or i >= MAX_MEMBERS:
                    continue
                low = member.filename.lower()
                if not any(low.endswith(suffix) for suffix in SCHEMA_SUFFIXES):
                    continue
                try:
                    body = book.read(member)
                except (zipfile.BadZipFile, OSError, RuntimeError):
                    got.dropped.append({"text": member.filename,
                                        "why": "the archive would not give up that file"})
                    continue
                if len(body) > MAX_BYTES:
                    got.dropped.append({"text": member.filename, "why": "that file is too big here"})
                    continue
                got.files.append(member.filename)
                _digest(body.decode("utf-8", "replace"), hits, blocked, member.filename)
    else:
        got.kind = _digest(raw.decode("utf-8", "replace"), hits, blocked, got.name)

    seen: set = set()
    for path, blob in hits:
        for line in _segments(blob):
            why = classify(line)
            if why:
                if len(got.dropped) < MAX_DROPPED:
                    got.dropped.append({"text": line[:180], "why": why})
                continue
            if line.lower() in seen:
                if len(got.dropped) < MAX_DROPPED:
                    got.dropped.append({"text": line[:180], "why": "a line you had already given"})
                continue
            seen.add(line.lower())
            if len(got.samples) >= MAX_SAMPLES:
                got.truncated = True
                break
            got.samples.append({"text": line, "from": path})
        if got.truncated:
            break

    got.blocked = blocked
    if not got.samples:
        looked = ", ".join(CANDIDATES)
        where = f" in {got.name}" if got.files or got.kind != "zip" else ""
        got.error = (f"Nothing that could be a caption of yours sat under a caption-shaped key"
                     f"{where}. It looked for: {looked}. "
                     f"{len(got.files)} file{'s' if len(got.files) != 1 else ''} read, "
                     f"{len(blocked)} conversation key{'' if len(blocked) == 1 else 's'} left alone. "
                     "Your voice profile is unchanged, so the generator still has no measurement of "
                     "you - and it will keep saying so rather than inventing one.")
    return got
