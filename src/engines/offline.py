"""The engine that answers without asking anything: no key, no network, no model.

OfflineEngine.complete_json returns an empty dict, or the JSON sitting in canned_path
when one was passed to the constructor and no images came with the call. That is the
whole behaviour, and it is a stub deliberately - offline output must not be mistaken for
researched advice, so the pages check engine.name == "offline" and say so.

A call carrying pictures gets an empty dict however canned_path is set: a stub that
answered about a picture it never saw would be the one thing this app must not do.
"""

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

    def complete_json(self, system: str, user: str, schema: dict,
                      images: list | None = None) -> dict:
        # A stub that answered about a picture it never saw would be the one thing
        # this app must never do, so images get the same empty answer as text.
        if self.canned_path and not images:
            return json.loads(Path(self.canned_path).read_text(encoding="utf-8"))
        return {}
