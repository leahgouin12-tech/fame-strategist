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
    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...

    def check(self, data: dict, schema: dict) -> dict:
        _validate(data, schema)
        return data
