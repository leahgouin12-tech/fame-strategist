import os
import threading
import webbrowser

import uvicorn

from src.app import DATA_DIR, create_app

PORT = 8756


def main():
    DATA_DIR.mkdir(exist_ok=True)
    if os.environ.get("OPEN_WINDOW", "1") == "1":
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"Fame Strategist is running on http://127.0.0.1:{PORT}")
    print("Nothing here is exposed to the internet. Close this window to stop the app.")
    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
