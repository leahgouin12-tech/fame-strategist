import json
from pathlib import Path

from .base import Engine


class OfflineEngine(Engine):
    """No key, no network. Returns one canned object so the pipeline stays testable.

    Deliberately not clever: its job is to be obviously a stub, so nobody mistakes
    offline output for researched advice.
    """

    name = "offline"

    def __init__(self, canned_path: Path | None = None):
        self.canned_path = canned_path

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        if self.canned_path:
            return json.loads(Path(self.canned_path).read_text(encoding="utf-8"))
        return {}
