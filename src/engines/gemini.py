import json
import re

import httpx

from .base import Engine

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self, key: str, model: str = "gemini-2.5-flash", client=None):
        self.key = key
        self.model = model
        self.client = client or httpx.Client(timeout=60)

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        text = (
            f"{user}\n\nReply with JSON only, matching this schema - no prose, no fences.\n"
            f"Schema: {json.dumps(schema)}"
        )
        resp = self.client.post(
            ENDPOINT.format(model=self.model),
            params={"key": self.key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
            },
        )
        resp.raise_for_status()
        body = resp.json()
        try:
            raw = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"engine returned no text: {body}") from exc
        try:
            data = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"engine returned non-JSON: {raw[:200]!r}") from exc
        return self.check(data, schema)


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
