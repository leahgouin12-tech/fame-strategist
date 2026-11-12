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

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Config":
        if not path.exists():
            return cls(api_key=None, engine_name="offline", model=DEFAULT_MODEL)
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        key = raw.get("api_key") or None
        model = raw.get("model") or DEFAULT_MODEL
        if not key:
            return cls(api_key=None, engine_name="offline", model=model)
        return cls(api_key=key, engine_name=raw.get("engine", "gemini"), model=model)

    def build_engine(self):
        from src.engines.gemini import GeminiEngine
        from src.engines.offline import OfflineEngine

        if self.engine_name == "gemini" and self.api_key:
            return GeminiEngine(key=self.api_key, model=self.model)
        return OfflineEngine()
