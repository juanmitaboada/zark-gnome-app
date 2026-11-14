# Copyright 2026 Juanmi Taboada
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The terminal run, under a display, with tests/fake_pkexec.py in place of
pkexec: the spawn's environment (A2R-1), the exit table (A2R-2), Stop by
Ctrl+C, the window's run page, Close during a run."""

# pylint: disable=redefined-outer-name

import json
import os
import signal
import sys
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import gi
import pytest

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

# pylint: disable=wrong-import-position
from gi.repository import Gdk, Gtk  # noqa: E402

from tests.harness import app_case  # noqa: E402
from tests.screenshots import FAKE, settle, wait  # noqa: E402
from zark_app.commands import Command  # noqa: E402
from zark_app.main import ZarkApp  # noqa: E402
from zark_app.runner import Run, child_env, classify  # noqa: E402
from zark_app.window import ZarkWindow  # noqa: E402

if Gdk.Display.get_default() is None:
    pytest.skip("no display: run under xvfb-run", allow_module_level=True)


def status(code: int) -> int:
    """A wait status for an exit code."""
    return code << 8


def test_classify() -> None:
    """The A2 plan's exit table, A2R-2 included."""
    assert classify(status(0), True, False).kind == "done"
    assert classify(status(1), True, False).kind == "failed"
    assert classify(status(2), True, False).kind == "usage"
    assert classify(status(126), False, False).kind == "cancelled"
    assert classify(status(127), False, False).kind == "not_authorized"
    assert classify(status(75), False, True).kind == "busy"
    assert classify(status(75), False, False).kind == "updates"
    for code in (129, 130, 141, 143):
        assert classify(status(code), True, False).kind == "stopped"
    # A signal before zark started: a cancel (Stop during the password dialog).
    assert classify(signal.SIGINT, False, False).kind == "cancelled"
    killed = classify(signal.SIGKILL, True, False)
    assert killed.kind == "killed" and killed.signal == signal.SIGKILL


def test_child_env() -> None:
    """Only the locale passes; SHELL never does (A2R-1)."""
    env = child_env({"LANG": "es_ES.UTF-8", "LC_TIME": "C", "SHELL": "/opt/odd", "HOME": "/h", "PATH": "/x"})
    assert env == ["LANG=es_ES.UTF-8", "LC_TIME=C"]


def fake_run(mode: str, ended: list[Run], on_ctrl_c: Callable[[Run], None] | None = None) -> Run:
    """A Run of the fake in ``mode``."""
    argv = [sys.executable, "-I", FAKE, mode, "/usr/share/zark/zark", "backup", "--drive", "black"]
    return Run(
        Command("backup", ("backup", "--drive", "black"), "Backing Up to black", "black"),
        argv,
        ended.append,
        on_ctrl_c or (lambda _r: None),
        environ={"LANG": "C.UTF-8", "SHELL": "/opt/odd", "SECRET_TOKEN": "x"},
    )


def test_spawn_environment(tmp_path: Path) -> None:
    """The child gets the locale and VTE's own variables, nothing of the
    parent's (VTE_SPAWN_NO_PARENT_ENVV); a tty on stdin."""
    out = tmp_path / "env.json"
    ended: list[Run] = []
    run = fake_run(f"env:{out}", ended)
    os.environ["ZARK_APP_TEST_LEAK"] = "1"
    try:
        run.start()
        wait(lambda: bool(ended))
    finally:
        del os.environ["ZARK_APP_TEST_LEAK"]
    data = json.loads(out.read_text(encoding="utf-8"))
    env = data["env"]
    assert "SHELL" not in env and "SECRET_TOKEN" not in env and "ZARK_APP_TEST_LEAK" not in env
    assert env["LANG"] == "C.UTF-8" and env["TERM"].startswith("xterm")
    assert data["tty"] is True
    assert data["argv"][:2] == ["/usr/share/zark/zark", "backup"]
    assert run.status is not None and classify(run.status, True, False).kind == "done"


@pytest.mark.parametrize(("code", "kind"), [(0, "done"), (1, "failed"), (75, "updates"), (126, "cancelled")])
def test_exit_codes(code: int, kind: str) -> None:
    """The child's exit reaches the table."""
    ended: list[Run] = []
    run = fake_run(f"exit:{code}", ended)
    run.start()
    wait(lambda: bool(ended))
    assert run.status is not None and classify(run.status, True, False).kind == kind


def test_stop_by_ctrl_c() -> None:
    """Stop writes Ctrl+C to the pty; the fake traps SIGINT and exits 130;
    a second Stop does nothing."""
    ended: list[Run] = []
    run = fake_run("trap", ended)
    run.start()
    wait(lambda: run.pid is not None)
    wait(lambda: "running" in run.terminal.get_text_format(1))
    assert run.stop() is True
    assert run.stop() is False
    wait(lambda: bool(ended))
    assert run.status is not None and classify(run.status, True, False).kind == "stopped"


def test_terminal_ctrl_c_asks() -> None:
    """A2-2: Ctrl+C typed in the terminal asks; it does not reach zark."""
    asked: list[Run] = []
    ended: list[Run] = []
    run = fake_run("trap", ended, asked.append)
    run.start()
    wait(lambda: run.pid is not None)
    ctl = Gtk.EventControllerKey()
    handled = run._key(ctl, Gdk.KEY_c, 0, Gdk.ModifierType.CONTROL_MASK)  # pylint: disable=protected-access
    assert handled and asked == [run] and run.alive and not run.stopping
    run.stop()
    wait(lambda: bool(ended))


@pytest.fixture(scope="module")
def app() -> ZarkApp:
    """One registered application."""
    application = ZarkApp(watch=False)
    application.register(None)
    return application


@pytest.fixture
def window(app: ZarkApp) -> Iterator[ZarkWindow]:
    """The connected case's window, its pkexec replaced by the fake."""
    case = app_case("connected")
    sources = replace(case.sources, pkexec_prefix=(sys.executable, "-I", FAKE, "trap"))
    win = ZarkWindow(app, sources, case.loaded, watch=False)
    win.keep = case  # type: ignore[attr-defined]
    app.window = win
    win.present()
    settle()
    yield win
    if win.ops.run is not None and win.ops.run.alive:
        win.ops.stop()
        wait(lambda: not win.ops.alive())
    win.destroy()


def test_backup_from_the_overview(window: ZarkWindow) -> None:
    """Back Up runs, the run page shows the terminal, actions are disabled,
    Close asks, Stop stops, Done returns."""
    window.ops.dispatch("backup", "black")
    settle()
    run = window.ops.run
    assert run is not None and run.alive and window.selected == "run"
    assert run.argv[4:] == ["/usr/share/zark/zark", "backup", "--drive", "black"]
    assert not window.run_action.get_enabled()
    assert run.terminal.get_parent() is not None
    # Close during a run is refused and asks.
    assert window._close_request(window) is True  # pylint: disable=protected-access
    # Leaving the run page keeps the terminal (and zark) alive.
    window.select("overview")
    settle()
    assert run.alive
    window.select("run")
    settle()
    wait(lambda: "running" in run.terminal.get_text_format(1))
    window.ops.stop()
    wait(lambda: not run.alive)
    settle()
    assert run.outcome is not None and run.outcome.kind == "stopped"
    window.ops.done()
    settle()
    assert window.ops.run is None and window.selected == "overview"
    assert window.run_action.get_enabled()


class RecordingSleep:
    """Stands in for the logind inhibitor: records acquire and release."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def acquire(self, why: str) -> None:
        """A run started."""
        self.events.append(f"acquire {why}")

    def release(self) -> None:
        """A run ended."""
        self.events.append("release")


def test_sleep_inhibitor_follows_the_run(window: ZarkWindow) -> None:
    """A2E-5: logind's sleep inhibitor is asked at the spawn and let go at
    child-exited."""
    sleep = RecordingSleep()
    window.ops.sleep = sleep  # type: ignore[assignment]
    window.ops.dispatch("backup", "black")
    settle()
    run = window.ops.run
    assert run is not None and sleep.events == ["acquire " + run.command.title]
    window.ops.stop()
    wait(lambda: not run.alive)
    settle()
    assert sleep.events[-1] == "release"
    window.ops.done()
    settle()


def _mounted_window(app: ZarkApp) -> ZarkWindow:
    """The mounted case (black browsed), its pkexec a fake that ends 0."""
    case = app_case("mounted")
    sources = replace(case.sources, pkexec_prefix=(sys.executable, "-I", FAKE, "exit:0"))
    win = ZarkWindow(app, sources, case.loaded, watch=False)
    win.keep = case  # type: ignore[attr-defined]
    app.window = win
    win.present()
    settle()
    return win


def _tooltips(widget: Gtk.Widget) -> list[str]:
    found: list[str] = []
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Button) and (tip := child.get_tooltip_text()):
            found.append(tip)
        found.extend(_tooltips(child))
        child = child.get_next_sibling()
    return found


def _run_to_end(win: ZarkWindow, op: str, arg: str) -> None:
    win.ops.dispatch(op, arg)
    settle()
    run = win.ops.run
    assert run is not None
    wait(lambda: not run.alive)
    settle()


def test_mount_result_offers_open_and_unmount(app: ZarkApp) -> None:
    """A2E-7: a mount that ended 0 offers Open in Files and Unmount on its
    result row, for the drive left mounted; another run does not."""
    win = _mounted_window(app)
    win.select("drive:black")
    settle()
    _run_to_end(win, "mount", "black")
    assert win.selected == "run"
    assert {"Open in Files", "Unmount"} <= set(_tooltips(win.run_page.widget))  # type: ignore[union-attr]
    win.ops.done()
    settle()
    _run_to_end(win, "refresh", "")
    assert "Open in Files" not in _tooltips(win.run_page.widget)  # type: ignore[union-attr]
    win.ops.done()
    settle()
    win.destroy()


def test_done_returns_to_the_mounted_drive_page(app: ZarkApp) -> None:
    """A2E-7: after the app's own run and Done, the browsed drive's page
    keeps Open in Files and Unmount in its header, and its menu."""
    win = _mounted_window(app)
    win.select("drive:black")
    settle()
    _run_to_end(win, "refresh", "")
    win.ops.done()
    settle()
    assert win.selected == "drive:black"
    header = win._header_widgets  # pylint: disable=protected-access
    assert [w.get_tooltip_text() for w in header[1:3]] == ["Open in Files", "Unmount"]
    assert isinstance(header[-1], Gtk.MenuButton) and header[-1].get_mapped()
    win.destroy()


def test_refused_value_never_runs(window: ZarkWindow) -> None:
    """blue is not connected: Back Up refuses before any spawn."""
    window.ops.dispatch("backup", "blue")
    settle()
    assert window.ops.run is None
