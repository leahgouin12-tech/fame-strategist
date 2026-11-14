"""The contract every engine is held to, and the two lines of checking that hold it.

Engine declares one abstract method, complete_json(system, user, schema, images), and
check runs _validate over whatever comes back, so a model answering in the wrong shape
fails at the engine boundary instead of three screens later. _validate is a deliberate
subset of JSON Schema - object, array, string, integer, required keys - which means a
schema asking for an enum, a minimum or a format goes unchecked and passes.

Live is the indirection every route and tool holds: swap the engine underneath it and
the next question goes to somebody else, with nothing rebuilt.
"""

from abc import ABC, abstractmethod


def _validate(data, schema: dict, path: str = "$") -> None:
    """Tiny JSON-Schema subset. Enough to hold an engine to its word, not a library."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be an object")
        for req in schema.get("required", []):
            if req not in data:
                raise ValueError(f"{path} missing required key {req!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                _validate(data[key], sub, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(data, list):
            raise ValueError(f"{path} must be an array")
        for i, item in enumerate(data):
            _validate(item, schema.get("items", {}), f"{path}[{i}]")
    elif kind == "string" and not isinstance(data, str):
        raise ValueError(f"{path} must be a string")
    elif kind == "integer" and not isinstance(data, int):
        raise ValueError(f"{path} must be an integer")


class Engine(ABC):
    name = "base"

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: dict,
                      images: list | None = None) -> dict: ...

    def check(self, data: dict, schema: dict) -> dict:
        _validate(data, schema)
        return data


class Live(Engine):
    """A stand-in you can swap the model under without rebuilding the app.

    Every route and every tool holds this object, so saving a key in Settings changes
    who answers the next question instead of needing a restart nobody asked for.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    @property
    def name(self) -> str:
        return self.engine.name

    def complete_json(self, system: str, user: str, schema: dict,
                      images: list | None = None) -> dict:
        return self.engine.complete_json(system, user, schema, images)
