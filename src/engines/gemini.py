"""The one place this app talks to a model, and the one address it is allowed to reach.

GeminiEngine.complete_json posts the system text, the user text and the schema to
generativelanguage.googleapis.com/v1beta/models/{model}:generateContent with the key in
x-goog-api-key, responseMimeType application/json and temperature 0.4; pictures go in as
inline base64 rather than being described from a filename, and _strip_fences removes the
markdown fences a JSON-mode endpoint still returns now and then.

The httpx client is built on the first call rather than at construction, with
trust_env=False and a 60-second timeout, because a malformed proxy variable in the
environment used to crash create_app and leave no page rendering at all - now it fails
only the one call that needed the network. Reading is strict in two ways: only
candidates[0].content.parts[0].text is taken, so an answer split across parts loses
everything after the first, and text that will not parse as JSON raises ValueError
carrying its first 200 characters. Nothing else in this file makes a request.
"""

import base64 as b64
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
        self._client = client

    @property
    def client(self):
        """Built on the first call, not at startup.

        httpx reads the proxy variables out of the environment while it is constructing a
        client, and a malformed one used to take the whole app down the moment a key was
        saved - the crash was in `create_app`, so no page rendered afterwards. Now the bad
        variable surfaces as an error on the call that needed the network, which is the only
        place it belongs.
        """
        if self._client is None:
            self._client = httpx.Client(timeout=60, trust_env=False)
        return self._client

    def complete_json(self, system: str, user: str, schema: dict,
                      images: list | None = None) -> dict:
        text = (
            f"{user}\n\nReply with JSON only, matching this schema - no prose, no fences.\n"
            f"Schema: {json.dumps(schema)}"
        )
        parts: list[dict] = [{"text": text}]
        # A picture goes in as the picture. Describing a face from a filename is the
        # sort of confident nonsense this app is built to avoid.
        for mime, blob in images or []:
            parts.append({"inline_data": {"mime_type": mime, "data": b64.b64encode(blob).decode()}})
        resp = self.client.post(
            ENDPOINT.format(model=self.model),
            headers={"x-goog-api-key": self.key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
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
