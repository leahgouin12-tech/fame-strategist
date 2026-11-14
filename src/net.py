"""The phone half: which address to type, and what stands in the doorway once it is typed.

The app used to bind 127.0.0.1, which is why a phone could not see it - and also why nothing
else could. Reaching a phone means listening on the wifi adapter, so the key gets built in the
same breath as the door: this file holds the address list, the PIN, and the cookie that means
she only types it once. It opens no sockets of its own; run.py and src/app.py call into it.
"""

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

COOKIE = "fame_phone"
MIN_PIN = 4
MAX_PIN = 12
MAX_WRONG = 5
COOLDOWN_MINUTES = 15
SESSION_LIMIT = 8          # one per device she unlocks, so emptying the list locks them all at once


def lan_addresses() -> list[str]:
    """Every address a phone on the same wifi could type, the live one first.

    The connected-UDP probe names the adapter that actually carries her traffic; getaddrinfo
    fills in the rest, because a laptop on both wifi and ethernet has two answers and only one
    of them is on the network the phone is joined to.
    """
    out: list[str] = []

    def add(value: str) -> None:
        if value and not value.startswith("127.") and value not in out:
            out.append(value)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(row[4][0])
    except OSError:
        pass
    return out


def is_foreign(host: str) -> bool:
    """True only for an address that arrived from another machine.

    The gate keys on IP literals because that is all a browser can ever arrive as, and a
    machine reading its own loopback is not somebody else's phone. Anything that is not an
    address at all - a test harness, a socket with no peer name - is treated as the laptop.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)


def clean_pin(raw: str) -> str:
    """The PIN as it will be stored, or "" when it is not usable. Spaces are stripped at the
    ends and forbidden inside so a phone keyboard cannot quietly add one."""
    pin = (raw or "").strip()
    if len(pin) < MIN_PIN or len(pin) > MAX_PIN or any(c.isspace() for c in pin):
        return ""
    return pin


class PhoneGate:
    """A PIN and the devices that have answered it, kept in one small file.

    Only a salted hash of the PIN is ever written down, and the unlock answer is a random
    token handed back as a cookie - so the phone never resends the PIN, and a stolen
    phone.json still does not contain it.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def state(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def has_pin(self) -> bool:
        state = self.state()
        return bool(state.get("salt") and state.get("hash"))

    def set_pin(self, raw: str) -> str:
        """Store a new PIN. Returns "" on success or the reason it was refused."""
        pin = clean_pin(raw)
        if not pin:
            return f"a PIN has to be {MIN_PIN} to {MAX_PIN} characters, with no spaces"
        salt = secrets.token_hex(16)
        state = self.state()
        state.update({"salt": salt, "hash": _digest(pin, salt), "wrong": 0, "locked_until": ""})
        state.setdefault("sessions", [])
        self._write(state)
        return ""

    def seconds_locked(self) -> int:
        raw = self.state().get("locked_until") or ""
        try:
            until = datetime.fromisoformat(raw)
        except ValueError:
            return 0
        left = (until - datetime.now(timezone.utc)).total_seconds()
        return int(left) if left > 0 else 0

    def unlock(self, raw: str) -> str:
        """A new session token when the PIN is right, "" when it is not."""
        state = self.state()
        if not self.has_pin() or self.seconds_locked():
            return ""
        pin = clean_pin(raw)
        if pin and hmac.compare_digest(_digest(pin, state["salt"]), state["hash"]):
            token = secrets.token_urlsafe(24)
            sessions = (state.get("sessions") or [])[-(SESSION_LIMIT - 1):] + [token]
            state.update({"sessions": sessions, "wrong": 0, "locked_until": ""})
            self._write(state)
            return token
        wrong = int(state.get("wrong") or 0) + 1
        state["wrong"] = wrong if wrong < MAX_WRONG else 0
        if wrong >= MAX_WRONG:
            state["locked_until"] = (datetime.now(timezone.utc)
                                     + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
        self._write(state)
        return ""

    def accepts(self, token: str) -> bool:
        if not token:
            return False
        return any(hmac.compare_digest(token, held) for held in (self.state().get("sessions") or []))

    def revoke(self) -> None:
        state = self.state()
        state["sessions"] = []
        self._write(state)

    def status(self) -> dict:
        locked = self.seconds_locked()
        return {
            "has_pin": self.has_pin(),
            "devices": len(self.state().get("sessions") or []),
            "wrong": int(self.state().get("wrong") or 0),
            "locked": bool(locked),
            "locked_minutes": -(-locked // 60) if locked else 0,
        }


def _digest(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
