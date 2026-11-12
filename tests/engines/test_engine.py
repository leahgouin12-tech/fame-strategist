import json

import pytest

from src.config import Config
from src.engines.base import Engine, _validate
from src.engines.offline import OfflineEngine

SCHEMA = {"type": "object", "required": ["reason"], "properties": {"reason": {"type": "string"}}}


def write_canned(tmp_path, obj):
    p = tmp_path / "canned.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_offline_engine_returns_schema_valid_json(tmp_path):
    out = OfflineEngine(canned_path=write_canned(tmp_path, {"reason": "no hook"})).complete_json(
        "sys", "user", SCHEMA
    )
    assert out == {"reason": "no hook"}


def test_offline_engine_without_a_canned_file_is_empty(tmp_path):
    assert OfflineEngine().complete_json("sys", "user", SCHEMA) == {}


def test_missing_key_leaves_config_usable_offline(tmp_path):
    cfg = Config.load(tmp_path / "absent.toml")
    assert cfg.api_key is None
    assert cfg.engine_name == "offline"


def test_key_present_selects_gemini(tmp_path):
    (tmp_path / "cfg.toml").write_text('api_key = "fake"\nengine = "gemini"\n', encoding="utf-8")
    cfg = Config.load(tmp_path / "cfg.toml")
    assert cfg.api_key == "fake"
    assert cfg.engine_name == "gemini"


def test_empty_key_in_config_is_not_a_key(tmp_path):
    (tmp_path / "cfg.toml").write_text('api_key = ""\n', encoding="utf-8")
    cfg = Config.load(tmp_path / "cfg.toml")
    assert cfg.api_key is None
    assert cfg.engine_name == "offline"


def test_validate_rejects_a_missing_required_key():
    with pytest.raises(ValueError, match="missing required key"):
        _validate({}, SCHEMA)


def test_validate_rejects_the_wrong_shape():
    with pytest.raises(ValueError, match="must be an object"):
        _validate([], SCHEMA)


def test_validate_walks_nested_arrays():
    schema = {
        "type": "object",
        "properties": {"shots": {"type": "array", "items": {"type": "object", "required": ["title"]}}},
    }
    with pytest.raises(ValueError, match=r"shots\[1\] missing required key"):
        _validate({"shots": [{"title": "a"}, {}]}, schema)


def test_engine_check_passes_data_through():
    class E(Engine):
        def complete_json(self, system, user, schema):
            return {"reason": "x"}

    assert E().complete_json("s", "u", SCHEMA) == {"reason": "x"}


class FakeResponse:
    def __init__(self, text, status=200):
        self._text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}


class FakeClient:
    def __init__(self, text, status=200):
        self.text = text
        self.status = status
        self.sent = []

    def post(self, url, params=None, json=None):
        self.sent.append((url, params, json))
        return FakeResponse(self.text, self.status)


def gemini(text, status=200):
    from src.engines.gemini import GeminiEngine

    client = FakeClient(text, status)
    return GeminiEngine(key="k", model="test-model", client=client), client


def test_gemini_engine_rejects_non_json_response():
    engine, _ = gemini("here is your answer: sure!")
    with pytest.raises(ValueError):
        engine.complete_json("s", "u", SCHEMA)


def test_gemini_engine_strips_code_fences():
    engine, _ = gemini('```json\n{"reason": "flat light"}\n```')
    assert engine.complete_json("s", "u", SCHEMA) == {"reason": "flat light"}


def test_gemini_engine_puts_the_schema_in_the_prompt():
    engine, client = gemini('{"reason": "ok"}')
    engine.complete_json("be terse", "rate this clip", SCHEMA)
    _, _, body = client.sent[0]
    assert body["systemInstruction"]["parts"][0]["text"] == "be terse"
    user_text = body["contents"][0]["parts"][0]["text"]
    assert "rate this clip" in user_text
    assert json.dumps(SCHEMA) in user_text


def test_gemini_engine_asks_for_json_output():
    engine, client = gemini('{"reason": "ok"}')
    engine.complete_json("s", "u", SCHEMA)
    assert client.sent[0][2]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_engine_raises_when_there_is_no_candidate():
    from src.engines.gemini import GeminiEngine

    class NoCandidates(FakeResponse):
        def json(self):
            return {"candidates": []}

    class EmptyClient(FakeClient):
        def post(self, *a, **k):
            return NoCandidates("")

    with pytest.raises(ValueError, match="no text"):
        GeminiEngine(key="k", client=EmptyClient("x")).complete_json("s", "u", SCHEMA)
