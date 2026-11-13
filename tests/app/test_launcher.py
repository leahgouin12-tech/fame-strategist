import pytest

import run as launcher


@pytest.fixture
def quiet(monkeypatch):
    """No browser, no server, no port probe while testing the decision made above them."""
    opened, started = [], []
    monkeypatch.setattr(launcher, "open_in_browser", opened.append)
    monkeypatch.setattr(launcher, "serve", lambda: started.append(True))
    return opened, started


def test_a_second_launch_opens_the_running_app_instead_of_crashing(monkeypatch, quiet, capsys):
    opened, started = quiet
    monkeypatch.setattr(launcher, "live_instance", lambda: "app")
    launcher.main()
    assert opened == [launcher.URL], "she gets the app, not an error page"
    assert started == [], "a second server on a bound port is exactly the crash she saw"
    assert "already running" in capsys.readouterr().out.lower()


def test_a_foreign_process_on_the_port_is_named_instead_of_a_socket_traceback(
        monkeypatch, quiet, capsys):
    opened, started = quiet
    monkeypatch.setattr(launcher, "live_instance", lambda: "other")
    launcher.main()
    out = capsys.readouterr().out.lower()
    assert "not this app" in out and "port" in out
    assert started == [] and opened == []


def test_a_free_port_starts_the_server_and_tells_her_where_it_is(monkeypatch, quiet, capsys):
    opened, started = quiet
    monkeypatch.setattr(launcher, "live_instance", lambda: "")
    monkeypatch.setenv("OPEN_WINDOW", "1")
    launcher.main()
    assert started == [True]
    out = capsys.readouterr().out
    assert launcher.URL in out and "exposed to the internet" in out.lower()
    assert str(launcher.DATA_DIR) in out, "the folder she has to drop files into is named up front"


def test_it_opens_a_window_with_no_address_bar_when_a_chromium_browser_exists(tmp_path, monkeypatch):
    """App mode is the difference between "a tab among my tabs" and a program with its
    own taskbar button, which is what she asked for when she said she wanted an app."""
    fake = tmp_path / "msedge.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(launcher.shutil, "which",
                        lambda name: str(fake) if name == "msedge" else None)
    launched = []
    monkeypatch.setattr(launcher.subprocess, "Popen", launched.append)
    launcher.open_in_browser(launcher.URL)
    assert launched == [[str(fake), f"--app={launcher.URL}",
                         f"--window-size={launcher.WINDOW_SIZE}"]]


def test_a_machine_with_neither_browser_still_opens_the_default_one(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: None)
    monkeypatch.setattr(launcher, "program_roots", lambda: [tmp_path])
    launched = []
    monkeypatch.setattr(launcher.subprocess, "Popen", launched.append)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    launcher.open_in_browser(launcher.URL)
    assert launched == [] and opened == [launcher.URL]


def test_the_probe_tells_a_live_app_from_a_stranger(monkeypatch):
    class Response:
        def __init__(self, body):
            self.body = body

        def read(self, _n):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(launcher.urllib.request, "urlopen",
                        lambda *_a, **_k: Response(b"<title>Fame Strategist</title>"))
    assert launcher.live_instance() == "app"
    monkeypatch.setattr(launcher.urllib.request, "urlopen",
                        lambda *_a, **_k: Response(b"<title>Some other tool</title>"))
    assert launcher.live_instance() == "other"

    def refused(*_a, **_k):
        raise ConnectionRefusedError("nothing there")

    monkeypatch.setattr(launcher.urllib.request, "urlopen", refused)
    assert launcher.live_instance() == ""
