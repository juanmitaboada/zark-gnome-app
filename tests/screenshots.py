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
"""Renders the window of each fixture case to a PNG, light and dark, wide
and narrow. Run under a display (``xvfb-run``), with ``GSK_RENDERER=cairo``
for stable pixels:

    xvfb-run -a env GSK_RENDERER=cairo python3 -m tests.screenshots OUTDIR

Each PNG is named ``<kind>-<case>[-<page>]-<width>-<style>.png``.
"""

import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

# pylint: disable=wrong-import-position
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from tests.harness import Case, any_case  # noqa: E402

FAKE = str(Path(__file__).resolve().parent / "fake_pkexec.py")
from zark_app.main import ZarkApp  # noqa: E402
from zark_app.window import ZarkWindow  # noqa: E402

# (case, page selected, by-id names connected) for zark's cases; the app's
# cases carry their own by-id.
SHOTS: list[tuple[str, str]] = [
    ("app:connected", "overview"),
    ("app:connected", "drive:black"),
    ("app:connected", "drive:blue"),
    ("app:pending", "overview"),
    ("app:pending", "pending:spare"),
    ("app:foreign-writer", "overview"),
    ("app:older-writer", "overview"),
    ("app:mounted", "drive:black"),
    ("app:running-connected", "run"),
    ("app:running-connected", "drive:black"),
    ("app:unplugged", "overview"),
    ("app:no-drives", "overview"),
    ("app:upgrade-risk", "overview"),
    ("app:zpool-fails", "overview"),
    ("app:exclusions", "exclusions"),
    ("app:no-zark", "overview"),
    ("app:too-old", "overview"),
    ("app:stale-timer-on", "overview"),
    ("zark:idle", "overview"),
    ("zark:no-status", "overview"),
    ("zark:newer-schema", "overview"),
    ("zark:stale", "overview"),
    ("zark:orphan", "overview"),
    ("zark:progress-unreadable", "overview"),
    ("zark:waiting", "run"),
    ("zark:stalled", "run"),
    ("zark:no-byte-counts", "run"),
    ("zark:partial-estimate", "run"),
    ("zark:fullcheck-running", "run"),
    ("zark:incomplete", "overview"),
    ("zark:not-verified", "drive:black"),
    ("zark:interrupted", "overview"),
    ("zark:overdue", "overview"),
    ("zark:boot-ext4", "overview"),
    ("zark:fullcheck-damage", "drive:black"),
    ("zark:drive-contents-partial", "drive:black"),
]
SIZES = ((1000, 760), (360, 760))


def settle(rounds: int = 40) -> None:
    """Let GTK lay out and draw."""
    ctx = GLib.MainContext.default()
    for _ in range(rounds):
        while ctx.pending():
            ctx.iteration(False)
        GLib.usleep(5000)


def render(window: Gtk.Window, path: Path) -> None:
    """The window, as drawn (its own background included), to ``path``."""
    widget = window
    width, height = widget.get_width(), widget.get_height()
    paintable = Gtk.WidgetPaintable.new(widget)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    native = window.get_native()
    renderer = native.get_renderer() if native is not None else None
    if node is None or renderer is None:
        raise RuntimeError(f"nothing drawn for {path.name}")
    renderer.render_texture(node, None).save_to_png(str(path))


def window_for(app: ZarkApp, case: Case, width: int, height: int) -> ZarkWindow:
    """A window on ``case`` at the given size."""
    window = ZarkWindow(app, case.sources, case.loaded, watch=False)
    window.set_default_size(width, height)
    window.present()
    settle()
    return window


def wait(until: Callable[[], bool], seconds: float = 15) -> None:
    """Run the main loop until ``until()`` or fail. A real loop: stepping
    the context by hand starves VTE's low-priority input source while a
    spinner animates."""
    loop = GLib.MainLoop()
    end = time.monotonic() + seconds

    def check() -> bool:
        if until() or time.monotonic() > end:
            loop.quit()
            return False
        return True

    GLib.timeout_add(20, check)
    loop.run()
    if not until():
        raise AssertionError("timed out")


def _run_shot(app: ZarkApp, out: Path, style: str, mode: str, name: str) -> int:
    case = any_case("app:connected")
    sources = replace(case.sources, pkexec_prefix=(sys.executable, "-I", FAKE, mode))
    window = ZarkWindow(app, sources, case.loaded, watch=False)
    app.window = window
    window.set_default_size(1000, 760)
    window.present()
    settle()
    window.ops.dispatch("backup", "black")
    run = window.ops.run
    if run is None:
        raise RuntimeError("the run did not start")
    if mode == "ask":
        wait(lambda: "Continue?" in run.terminal.get_text_format(1))
    else:
        wait(lambda: not run.alive)
    settle()
    render(window, out / f"run-terminal-{name}-1000-{style}.png")
    count = 1
    if run.alive:
        run.terminal.feed_child(list(b"no\n"))
        wait(lambda: not run.alive)
        settle()
        render(window, out / f"run-terminal-{name}-ended-1000-{style}.png")
        count += 1
    window.destroy()
    return count


def run_shots(app: ZarkApp, out: Path, style: str) -> int:
    """The run page with zark's terminal (A2), from tests/fake_pkexec.py:
    a run that asks and ends refused; one that fails."""
    return sum(
        _run_shot(app, out, style, mode, name) for mode, name in (("ask", "asking"), ("exit:1", "failed"))
    )


def main(out: Path) -> int:
    """Render every shot."""
    out.mkdir(parents=True, exist_ok=True)
    app = ZarkApp(watch=False)
    app.register(None)
    # GNOME's default title bar buttons; GTK's own default adds two more.
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-decoration-layout", ":close")
    manager = Adw.StyleManager.get_default()
    count = 0
    for dark in (False, True):
        manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
        for name, page in SHOTS:
            for width, height in SIZES:
                case = any_case(name)
                window = window_for(app, case, width, height)
                window.select(page)
                settle()
                tail = "" if page == "overview" else "-" + page.replace(":", "-")
                style = "dark" if dark else "light"
                render(window, out / f"{name.replace(':', '-')}{tail}-{width}-{style}.png")
                window.destroy()
                count += 1
        count += run_shots(app, out, "dark" if dark else "light")
    print(f"{count} screenshots in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "build/screenshots")))
