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
"""The window drawn from the fixtures, under a display (``xvfb-run``):
which page, which texts, the two run-time switches and the narrow layout.
Assertions are on the widget tree, not on pixels."""

# pylint: disable=redefined-outer-name

from collections.abc import Iterator
from datetime import timedelta

import gi
import pytest

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

# pylint: disable=wrong-import-position
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from tests.harness import any_case  # noqa: E402
from tests.screenshots import settle  # noqa: E402
from zark_app import compat, shortcuts  # noqa: E402
from zark_app.main import ZarkApp  # noqa: E402
from zark_app.window import ZarkWindow  # noqa: E402

if Gdk.Display.get_default() is None:
    pytest.skip("no display: run under xvfb-run", allow_module_level=True)


@pytest.fixture(scope="module")
def app() -> ZarkApp:
    """One registered application for every window."""
    application = ZarkApp(watch=False)
    application.register(None)
    return application


def texts(widget: Gtk.Widget) -> list[str]:
    """Every text the widget tree shows."""
    out: list[str] = []

    def walk(w: Gtk.Widget) -> None:
        for getter in ("get_label", "get_title", "get_subtitle", "get_description", "get_button_label"):
            if hasattr(w, getter) and not isinstance(w, Gtk.Window):
                value = getattr(w, getter)()
                if isinstance(value, str) and value:
                    out.append(value)
        child = w.get_first_child()
        while child is not None:
            walk(child)
            child = child.get_next_sibling()

    walk(widget)
    return out


def open_window(app: ZarkApp, name: str, page: str = "overview", width: int = 1000) -> ZarkWindow:
    """A window on a case, the page selected."""
    case = any_case(name)
    window = ZarkWindow(app, case.sources, case.loaded, watch=False)
    window.keep = case  # type: ignore[attr-defined]
    window.set_default_size(width, 760)
    window.present()
    settle()
    window.select(page)
    settle()
    return window


@pytest.fixture
def windows() -> Iterator[list[ZarkWindow]]:
    """Windows opened by a test, destroyed after it."""
    opened: list[ZarkWindow] = []
    yield opened
    for w in opened:
        w.destroy()


@pytest.mark.parametrize(
    ("name", "page", "expected"),
    [
        (
            "app:connected",
            "overview",
            ["This Computer", "Live figures from zpool list", "Back Up", "Notices"],
        ),
        (
            "app:connected",
            "drive:black",
            ["Status", "Space", "Backup Points", "Retention", "Largest Datasets"],
        ),
        ("app:pending", "overview", ["spare", "Finish Registration..."]),
        ("app:pending", "pending:spare", ["Finish Registration..."]),
        ("app:foreign-writer", "overview", ["from /media/usb/zark, not the installed 2.3.0"]),
        ("app:mounted", "overview", ["black is mounted for browsing", "Unmount"]),
        ("app:running-connected", "run", ["Running in a Terminal", "Step 7 of 8", "9 of 21 datasets"]),
        ("app:unplugged", "overview", ["was disconnected during the run"]),
        ("app:no-drives", "overview", ["No Backup Drives Yet", "Prepare a New Drive..."]),
        ("app:zpool-fails", "overview", ["Figures from zark's status file", "measured"]),
        ("app:exclusions", "exclusions", ["Left Out of Backups", "rpool/scratch", "Never Excluded"]),
        ("app:no-zark", "overview", ["zark Is Not Installed"]),
        ("app:too-old", "overview", ["zark Is Too Old"]),
        ("app:upgrade-risk", "overview", ["Upgrade Risk"]),
        ("zark:no-status", "overview", ["No Status Yet", "Refresh Status"]),
        ("zark:newer-schema", "overview", ["from a newer zark"]),
        ("zark:stale", "overview", ["the hourly checks are off", "Turn On..."]),
        ("zark:orphan", "overview", ["without cleaning up", "Clean Up..."]),
        ("zark:progress-unreadable", "overview", ["progress file could not be read"]),
        ("zark:waiting", "run", ["Answer its questions there", "Passphrase for black"]),
        ("zark:stalled", "run", ["No update for"]),
        ("zark:no-byte-counts", "run", ["Running in a Terminal"]),
        ("zark:partial-estimate", "run", ["at least"]),
        ("zark:boot-ext4", "overview", ["/boot"]),
        ("zark:drive-contents-partial", "drive:black", ["Space"]),
        ("zark:fullcheck-damage", "drive:black", ["Last full check", "Damage found"]),
    ],
)
def test_page_texts(
    app: ZarkApp, windows: list[ZarkWindow], name: str, page: str, expected: list[str]
) -> None:
    """Each state's page says what the design says."""
    window = open_window(app, name, page)
    windows.append(window)
    shown_text = "\n".join(texts(window.content_view))
    for item in expected:
        assert item in shown_text, (name, page, item)


def test_banner_runs(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """The banner's button runs the design's action through win.run."""
    window = open_window(app, "zark:orphan")
    windows.append(window)
    assert window.banner.get_revealed()
    assert window.banner.get_action_name() == "win.run"
    target = window.banner.get_action_target_value()
    assert target is not None and target.unpack() == ("clean", "")


def test_sidebar_rows(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """Overview, the drives, the pending drive, Exclusions; a run on top."""
    window = open_window(app, "app:pending")
    windows.append(window)
    keys = []
    i = 0
    while (row := window.list.get_row_at_index(i)) is not None:
        keys.append(row.key)  # type: ignore[attr-defined]
        i += 1
    assert keys == ["overview", "drive:black", "drive:blue", "pending:spare", "exclusions"]
    running = open_window(app, "app:running-connected")
    windows.append(running)
    assert running.list.get_row_at_index(0).key == "run"  # type: ignore[union-attr]


def test_select_index(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """Ctrl+2 selects the first drive."""
    window = open_window(app, "app:connected")
    windows.append(window)
    window.select_index(2)
    settle()
    assert window.selected == "drive:black"


def test_drive_header_disabled_when_disconnected(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """Back Up is disabled with a reason on a drive that is not connected."""
    window = open_window(app, "app:connected", "drive:blue")
    windows.append(window)
    back = window._header_widgets[0]  # pylint: disable=protected-access
    assert isinstance(back, Gtk.Button) and not back.get_sensitive()
    assert back.get_tooltip_text() == "Connect blue to back up"


@pytest.mark.parametrize("minor", [5, 10])
def test_spinner_switch(minor: int) -> None:
    """Gtk.Spinner before 1.6, Adw.Spinner from 1.6 where the gir has it."""
    widget = compat.spinner(minor)
    if minor >= 6 and hasattr(Adw, "Spinner"):
        assert type(widget).__name__ == "Spinner" and isinstance(widget, Adw.Spinner)
    else:
        assert isinstance(widget, Gtk.Spinner)


@pytest.mark.parametrize("minor", [5, 10])
def test_shortcuts_switch(app: ZarkApp, windows: list[ZarkWindow], minor: int) -> None:
    """Gtk.ShortcutsWindow before 1.8, Adw.ShortcutsDialog from 1.8."""
    window = open_window(app, "app:connected")
    windows.append(window)
    help_ = shortcuts.show(window, minor)
    settle()
    if minor >= 8 and hasattr(Adw, "ShortcutsDialog"):
        assert isinstance(help_, Adw.ShortcutsDialog)
        help_.close()
    else:
        assert isinstance(help_, Gtk.ShortcutsWindow)
        help_.destroy()


def test_about(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """About names the app and carries the versions."""
    window = open_window(app, "app:connected")
    windows.append(window)
    window.show_about()
    settle()
    from zark_app import about  # pylint: disable=import-outside-toplevel

    assert window.snapshot is not None
    info = about.debug_info(window.snapshot)
    assert "zark (installed): 2.3.0-1" in info and "libadwaita 1." in info


def test_narrow(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """Under 600 sp the split view collapses to one column."""
    window = open_window(app, "app:connected", width=360)
    windows.append(window)
    settle(80)
    if not window.split.get_collapsed():
        pytest.skip("the breakpoint did not apply on this backend (checked on eli)")
    window.select("drive:black")
    settle()
    assert window.split.get_show_content()


def _shown(window: ZarkWindow) -> Gtk.Widget:
    """The content page on show."""
    page = window.content_view.get_content()
    assert page is not None
    return page


def _scrolled(widget: Gtk.Widget) -> Gtk.ScrolledWindow:
    stack = [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, Gtk.ScrolledWindow):
            return w
        child = w.get_last_child()
        while child is not None:
            stack.append(child)
            child = child.get_prev_sibling()
    raise AssertionError("no scrolled window")


def _move_clock(window: ZarkWindow, seconds: int) -> None:
    """The fixture's clock, ``seconds`` later (Sources is frozen: tests only)."""
    later = window.sources.now() + timedelta(seconds=seconds)
    object.__setattr__(window.sources, "now", lambda: later)


def test_redraw_keeps_scroll_and_months(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """A1E-2: the minute's redraw keeps the drive page's scroll position and
    its open month; another page and back starts at the top."""
    window = open_window(app, "app:connected", "drive:black")
    windows.append(window)
    window.set_default_size(1000, 420)
    settle(80)
    page = _shown(window)
    month = next(w for w in _all(page) if isinstance(w, Adw.ExpanderRow))
    month.set_expanded(True)
    settle(80)
    adj = _scrolled(page).get_vadjustment()
    target = (adj.get_upper() - adj.get_page_size()) / 2
    assert target > 50, "the page must scroll for this test"
    adj.set_value(target)
    settle()
    _move_clock(window, 61)
    window.refresh()
    settle(80)
    new = _shown(window)
    assert new is not page
    assert abs(_scrolled(new).get_vadjustment().get_value() - target) < 1
    again = next(
        w for w in _all(new) if isinstance(w, Adw.ExpanderRow) and w.get_title() == month.get_title()
    )
    assert again.get_expanded()
    window.select("overview")
    settle()
    window.select("drive:black")
    settle(80)
    assert _scrolled(_shown(window)).get_vadjustment().get_value() == 0


def _all(widget: Gtk.Widget) -> list[Gtk.Widget]:
    out: list[Gtk.Widget] = []
    child = widget.get_first_child()
    while child is not None:
        out.append(child)
        out.extend(_all(child))
        child = child.get_next_sibling()
    return out


def _bar(widget: Gtk.Widget) -> Gtk.ProgressBar:
    return next(w for w in _all(widget) if isinstance(w, Gtk.ProgressBar))


def _sidebar_texts(window: ZarkWindow) -> list[str]:
    return texts(window.list)


def test_step_is_not_a_percentage(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """A1E-3: at step 5 of 8 before data moves, no percentage anywhere."""
    window = open_window(app, "app:running-step5", "run")
    windows.append(window)
    page = _shown(window)
    progress = _bar(page)
    assert not progress.get_show_text() and "%" not in (progress.get_text() or "")
    assert "Step 5 of 8" in _sidebar_texts(window)
    assert not any("%" in t for t in _sidebar_texts(window))
    assert "No data is moving yet" in texts(page)


def test_sent_shows_complete(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """A1E-3: the transfer seen, then gone: the bar full, "data sent"."""
    window = open_window(app, "app:running-connected", "run")
    windows.append(window)
    progress = _bar(_shown(window))
    assert progress.get_show_text() and (progress.get_text() or "").endswith(" %")
    assert progress.get_fraction() < 1
    after = any_case("app:running-after-transfer")
    window.keep2 = after  # type: ignore[attr-defined]
    object.__setattr__(window.sources, "root", after.sources.root)
    window.refresh()
    settle()
    page = _shown(window)
    progress = _bar(page)
    assert progress.get_fraction() == 1.0 and progress.get_text() == "100 %"
    assert "All data sent" in texts(page)
    assert "Step 8 of 8, data sent" in _sidebar_texts(window)


def test_after_transfer_unseen_shows_step_only(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """A1E-3: a window opened after the transfer shows the step only."""
    window = open_window(app, "app:running-after-transfer", "run")
    windows.append(window)
    progress = _bar(_shown(window))
    assert not progress.get_show_text()
    assert "Step 8 of 8" in _sidebar_texts(window)


def test_points_in_local_time(app: ZarkApp, windows: list[ZarkWindow]) -> None:
    """A1E-5: each point's title is its local time, its name below; the last
    run's point too (TZ=Europe/Madrid in the suite)."""
    window = open_window(app, "zark:drive-contents", "drive:black")
    windows.append(window)
    page = _shown(window)
    rows = [w for w in _all(page) if isinstance(w, Adw.ActionRow) and not isinstance(w, Adw.ExpanderRow)]
    first = next(r for r in rows if (r.get_subtitle() or "").startswith("zark_2025-11-30_21:24:14Z"))
    assert first.get_title() == "30 Nov 2025, 22:24:38"
    assert any("22 Oct 2026, 23:32:42 (zark_2026-10-22_21:32:18Z)" in t for t in texts(page))
