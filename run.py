"""The one file worth double-clicking. It never leaves two instances fighting over a port,
because that is how a browser tab ends up showing "can't reach this page" on a healthy app."""

import copy
import os
import threading
import urllib.error
import urllib.request
import webbrowser

from src.app import DATA_DIR, create_app

PORT = 8756
URL = f"http://127.0.0.1:{PORT}"


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


def open_in_browser(url: str) -> None:
    webbrowser.open(url)


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

    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="info", log_config=cfg)


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
    print("Nothing here is exposed to the internet. Close this window to stop the app.")
    print(f"Photos and clips are read from {DATA_DIR}\\inbox and {DATA_DIR}\\clips.")
    serve()


if __name__ == "__main__":
    main()
