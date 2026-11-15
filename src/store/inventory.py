"""Which built packages are actually on this disk, and which of them may be handed out.

`data/packages/` is the one folder the store screens read. A file lands there the same way any other
output lands: she builds an APK with `scripts/build_apk.ps1` (or a CI run downloads it) and drops it
in, or the build script is pointed straight at it. Nothing writes a placeholder there, which is the
point - an empty folder means "no build yet" on the screen, and the screen has no way to say
"ready" when there is nothing to download.

Two suffixes count as packages, because those are the two an alternative store installs: `.apk` and
`.ipa`. Anything else in the folder is somebody's note, not an artifact, and is not listed or
served.

`resolve` is the only door to the bytes. It takes a bare filename, never a path, and checks the file
lands in the packages folder once symlinks are followed - so `/store/dl/..%2fapp.sqlite3` and a
symlink planted beside the packages both come back as nothing rather than as her database.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

KINDS = {".apk": "android", ".ipa": "ios"}
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Artifact:
    """One installable file, described only by what can be measured from its bytes."""

    name: str
    kind: str          # android | ios, from the suffix
    size: int          # bytes, stat'd
    sha256: str        # of those same bytes
    modified: str      # ISO date, so a stale build is visible as a date
    url: str           # /store/dl/<name>, the one path that serves it

    @property
    def megabytes(self) -> str:
        return f"{self.size / 1_048_576:.1f} MB"


def dir_for(state_dir: Path | str) -> Path:
    """The packages folder beside the database; created empty, never pre-filled."""
    top = Path(state_dir) / "packages"
    top.mkdir(parents=True, exist_ok=True)
    return top


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def scan(state_dir: Path | str) -> list[Artifact]:
    """Every real package, newest first. Empty list is the honest answer, not an error."""
    top = dir_for(state_dir)
    out: list[Artifact] = []
    for entry in sorted(top.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        kind = KINDS.get(entry.suffix.lower())
        if kind is None or not entry.is_file():
            continue
        stamp = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc).date().isoformat()
        out.append(Artifact(name=entry.name, kind=kind, size=entry.stat().st_size,
                            sha256=_hash(entry), modified=stamp,
                            url=f"/store/dl/{entry.name}"))
    return out


def resolve(state_dir: Path | str, name: str) -> Path | None:
    """The path of one served package, or None if that name is not a package here."""
    if not name or "/" in name or "\\" in name or "\x00" in name:
        return None
    top = dir_for(state_dir)
    if KINDS.get(Path(name).suffix.lower()) is None:
        return None
    candidate = top / name
    if not candidate.is_file():
        return None
    real = candidate.resolve()
    if real.parent != top.resolve() or real.name != name:
        return None
    return real
