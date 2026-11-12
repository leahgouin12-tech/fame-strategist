from datetime import date
from pathlib import Path

from .schema import Confidence, PlaybookEntry, Source, SourceTier, validate_entry


class PlaybookError(Exception):
    pass


def _split_list(text: str) -> list[str]:
    return [part.strip().strip("[]") for part in text.split(",") if part.strip().strip("[]")]


def _parse(path: Path) -> PlaybookEntry:
    text = path.read_text(encoding="utf-8")
    try:
        _, front, body = text.split("---", 2)
    except ValueError:
        raise PlaybookError(f"{path.name}: missing --- front matter ---")

    meta: dict[str, str] = {}
    sources: list[Source] = []
    in_sources = False
    for raw in front.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            if not in_sources:
                raise PlaybookError(f"{path.name}: '- ' line outside a sources: block")
            fields = [f.strip() for f in line[2:].split("|")]
            if len(fields) != 3:
                raise PlaybookError(f"{path.name}: source must be 'url | title | tier'")
            try:
                sources.append(Source(fields[0], fields[1], SourceTier(fields[2])))
            except ValueError:
                raise PlaybookError(f"{path.name}: unknown source tier {fields[2]!r}")
            continue
        if line.endswith(":") and not line.startswith(("claim", "mechanism")):
            key = line[:-1].strip()
            in_sources = key == "sources"
            if in_sources:
                meta[key] = ""
            continue
        in_sources = False
        if ":" not in line:
            raise PlaybookError(f"{path.name}: cannot parse line {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()

    body_fields = {"claim": "", "mechanism": ""}
    for line in body.strip().splitlines():
        for key in body_fields:
            if line.startswith(key + ":"):
                body_fields[key] = line.split(":", 1)[1].strip()

    try:
        return PlaybookEntry(
            id=meta["id"],
            claim=body_fields["claim"],
            mechanism=body_fields["mechanism"],
            confidence=Confidence(meta["confidence"]),
            sources=sources,
            applies_to=_split_list(meta.get("applies_to", "")),
            as_of=date.fromisoformat(meta["as_of"]),
            does_not_claim=meta.get("does_not_claim", ""),
            tags=_split_list(meta.get("tags", "")),
        )
    except KeyError as exc:
        raise PlaybookError(f"{path.name}: missing required key {exc}")
    except ValueError as exc:
        raise PlaybookError(f"{path.name}: {exc}")


class Store:
    """Reads the playbook, and refuses to return a playbook that failed validation.

    Refusing to load is the point: a broken citation cannot be silently advised around.
    """

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def load(self, dirpath: Path, allow_pending: bool = False) -> list[PlaybookEntry]:
        entries, problems = [], []
        for path in sorted(Path(dirpath).glob("*.md")):
            try:
                entry = _parse(path)
            except PlaybookError as exc:
                problems.append(str(exc))
                continue
            bad = validate_entry(entry, self.today)
            if bad:
                problems.extend(f"{entry.id}: {p}" for p in bad)
            if not allow_pending and entry.has_placeholder_source():
                problems.append(f"{entry.id}: source {entry.sources[0].url} is still a placeholder")
            entries.append(entry)
        if problems:
            raise PlaybookError("playbook rejected:\n" + "\n".join(f"  - {p}" for p in problems))
        return entries

    def by_id(self, entries: list[PlaybookEntry]) -> dict[str, PlaybookEntry]:
        return {e.id: e for e in entries}
