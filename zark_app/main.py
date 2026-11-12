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
"""The application: actions, shortcuts, one window."""

import sys
from collections.abc import Sequence

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

# pylint: disable=wrong-import-position
from gi.repository import Adw, Gio  # noqa: E402

from zark_app import APP_ID, reader  # noqa: E402
from zark_app.gio_runner import GioRunner  # noqa: E402
from zark_app.reader import Loaded  # noqa: E402
from zark_app.sources import Sources  # noqa: E402
from zark_app.window import ZarkWindow  # noqa: E402

ACCELS = {
    "app.quit": ["<Control>q"],
    "app.shortcuts": ["<Control>question"],
    "window.close": ["<Control>w"],
    "win.reload": ["<Control>r"],
    "win.back": ["<Alt>Left"],
    "win.backup-selected": ["<Control>b"],
    "win.mount-selected": ["<Control>m"],
}


class ZarkApp(Adw.Application):
    """zark's GNOME app."""

    def __init__(
        self, sources: Sources | None = None, loaded: Loaded | None = None, watch: bool = True
    ) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.sources = sources or Sources(runner=GioRunner())
        self.loaded = loaded
        self.watch = watch
        self.window: ZarkWindow | None = None
        self.connect("startup", self._startup)
        self.connect("activate", self._activate)

    def _startup(self, _app: Adw.Application) -> None:
        for name, callback in (
            ("quit", lambda *_a: self._quit()),
            ("present", lambda *_a: self.window.present() if self.window else None),
            ("about", lambda *_a: self.window.show_about() if self.window else None),
            ("shortcuts", lambda *_a: self.window.show_shortcuts() if self.window else None),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        for action_name, accels in ACCELS.items():
            self.set_accels_for_action(action_name, accels)
        for n in range(1, 10):
            self.set_accels_for_action(f"win.select-index({n})", [f"<Control>{n}"])

    def _activate(self, _app: Adw.Application) -> None:
        if self.window is None:
            loaded = self.loaded or reader.load(self.sources.zark_dir)
            self.window = ZarkWindow(self, self.sources, loaded, watch=self.watch)
        self.window.present()

    def _quit(self) -> None:
        """Ctrl+Q: while the app's run lasts, the window asks first (design 3.3)."""
        if self.window is not None and self.window.ops.alive():
            self.window.close()
            return
        self.quit()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the app."""
    return int(ZarkApp().run(list(argv if argv is not None else sys.argv)))
