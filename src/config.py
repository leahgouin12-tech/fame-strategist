"""Where the engine's identity comes from: one optional file, config.toml.

Config.load reads it and treats a missing file, an empty api_key and an engine name it
does not know as the same answer - offline - so the app runs with nothing configured at
all. build_engine is the only place that chooses between GeminiEngine and OfflineEngine,
and mask is the only form the key is ever shown in: the last four characters, enough to
recognise, useless to take.

write saves the file with json.dumps doing the quoting, on purpose, so that a key
containing a quote cannot write extra settings beside itself. config.toml is gitignored
and nothing here logs the key it read.
"""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("config.toml")
DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class Config:
    """Where the engine comes from. Absent file is a valid state: offline mode.

    The api_key lives in config.toml, which is gitignored. Nothing here logs it.
    """

    api_key: str | None
    engine_name: str
    model: str
    path: Path = DEFAULT_PATH

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Config":
        if not path.exists():
            return cls(api_key=None, engine_name="offline", model=DEFAULT_MODEL, path=path)
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        key = raw.get("api_key") or None
        model = raw.get("model") or DEFAULT_MODEL
        if not key:
            return cls(api_key=None, engine_name="offline", model=model, path=path)
        return cls(api_key=key, engine_name=raw.get("engine", "gemini"), model=model, path=path)

    def build_engine(self):
        from src.engines.gemini import GeminiEngine
        from src.engines.offline import OfflineEngine

        if self.engine_name == "gemini" and self.api_key:
            return GeminiEngine(key=self.api_key, model=self.model)
        return OfflineEngine()

    @property
    def mask(self) -> str:
        """The only form of the key this app ever shows: enough to recognise, useless to steal."""
        if not self.api_key:
            return "none"
        if len(self.api_key) <= 8:
            return "set"
        return "...{}".format(self.api_key[-4:])

    def write(self, path: Path | None = None) -> None:
        """Save the choice. config.toml is gitignored, and json.dumps is doing the quoting
        here on purpose: a key with a quote in it must not be able to write extra settings."""
        path = Path(path or self.path)
        lines = [f"engine = {json.dumps(self.engine_name)}",
                 f"model = {json.dumps(self.model)}"]
        if self.api_key:
            lines.append(f"api_key = {json.dumps(self.api_key)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
