"""The one file worth double-clicking. It never leaves two instances fighting over a port,
because that is how a browser tab ends up showing "can't reach this page" on a healthy app."""

import copy
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from src.app import DATA_DIR, create_app
from src import net

PORT = 8756
HOST = "0.0.0.0"
URL = f"http://127.0.0.1:{PORT}"
WINDOW_SIZE = "1280,900"

# Edge ships with Windows 10 and 11; Chrome is the other one worth looking for. Each entry
# is (name on PATH, paths relative to a program folder).
BROWSERS = [
    ("msedge", ("Microsoft/Edge/Application/msedge.exe",)),
    ("chrome", ("Google/Chrome/Application/chrome.exe",)),
]


def program_roots() -> list[Path]:
    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"),
             os.environ.get("LOCALAPPDATA")]
    return [Path(r) for r in roots if r and Path(r).is_dir()]


def app_window(url: str) -> list[str] | None:
    """A browser opened in app mode has no address bar, no tabs and its own taskbar
    button - the closest thing to an installed application that needs no store, no
    signing certificate and nothing exposed to the internet."""
    for exe, leaves in BROWSERS:
        found = shutil.which(exe)
        candidates = [Path(found)] if found else []
        candidates += [root / leaf for root in program_roots() for leaf in leaves]
        for path in candidates:
            if path.is_file():
                return [str(path), f"--app={url}", f"--window-size={WINDOW_SIZE}"]
    return None


def open_in_browser(url: str) -> None:
    command = app_window(url)
    if command:
        subprocess.Popen(command)
        return
    webbrowser.open(url)


def live_instance() -> str:
    """'app' if the app is already home, 'other' if some foreign process holds the port,
    '' if the port is free. A bare socket check cannot tell those two apart, and the
    difference is the whole message she needs."""
    try:
        with urllib.request.urlopen(URL, timeout=2) as response:
            body = response.read(8192).decode("utf-8", "replace")
    except urllib.error.HTTPError:
        return "other"          # something answered, but not with our home page
    except Exception:
        return ""
    return "app" if "Fame Strategist" in body else "other"


def serve() -> None:
    # Every request and every traceback also lands in data/app.log, so a page that fails
    # on her screen leaves a record here instead of becoming a guess later. It has to go
    # through uvicorn's own log config: a handler attached here is wiped the moment the
    # server configures logging.
    from uvicorn.config import LOGGING_CONFIG

    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg["handlers"]["file"] = {
        "class": "logging.FileHandler", "filename": str(DATA_DIR / "app.log"),
        "formatter": "default", "encoding": "utf-8",
    }
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        cfg["loggers"][name]["handlers"] = cfg["loggers"][name].get("handlers", []) + ["file"]
    import uvicorn

    # 0.0.0.0 is what lets a phone in at all, and the reason it is not a hole: the app
    # answers a wifi address with a PIN box and nothing else until she sets one on /phone.
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="info", log_config=cfg)


def phone_lines() -> list[str]:
    """What to type on the phone, or the one reason there is nothing to type yet."""
    addresses = net.lan_addresses()
    if not addresses:
        return ["Phone: this laptop is not joined to a network, so there is no address to type."]
    lines = [f"Phone: type http://{a}:{PORT} on it - steps and a PIN are on {URL}/phone"
             for a in addresses[:2]]
    if len(addresses) > 2:
        lines.append(f"Phone: {len(addresses) - 2} more network cards, listed on {URL}/phone")
    return lines


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    who = live_instance()
    if who == "app":
        print(f"Already running on {URL} - opening that one, not starting a second copy.")
        open_in_browser(URL)
        return
    if who == "other":
        print(f"Port {PORT} is held by something that is not this app, so nothing started.")
        print(f"Close that program, or change PORT at the top of run.py and start it again.")
        print(f"Until then the app is not reachable at {URL}.")
        return
    if os.environ.get("OPEN_WINDOW", "1") == "1":
        threading.Timer(1.2, lambda: open_in_browser(URL)).start()
    print(f"Fame Strategist is running on {URL}")
    for line in phone_lines():
        print(line)
    print("To keep it as an app with its own icon: browser menu > Apps > Install this site.")
    print("Nothing here is exposed to the internet. Close this window to stop the app.")
    print(f"Photos and clips are read from {DATA_DIR}\\inbox and {DATA_DIR}\\clips.")
    serve()


if __name__ == "__main__":
    main()
