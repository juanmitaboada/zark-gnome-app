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
"""The alert when a backup's drive goes away (``drive_gone``, zark 2.3.1).

zark sends its own desktop notification when it sees the drive gone; the
user then gets one dialog more: the extension's when zark's GNOME Shell
extension 1.3 or later is active, this app's otherwise. So before its
dialog the app asks GNOME Shell (``org.gnome.Shell.Extensions``,
``GetExtensionInfo``) for the extension's state: ``state`` 1 is
``ExtensionState.ACTIVE`` in GNOME Shell 46, 50 and 51
(``js/misc/extensionUtils.js``), and ``version-name`` comes from its
``metadata.json``. No answer (another desktop, no session bus, an error,
a timeout) means the dialog shows.

Once per run and drive: the key ``<pid>:<started_at>:<pool>`` is taken the
first time it is seen and kept for the app's life. No GTK here.
"""

import re
import sys
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib

from zark_app.model import DriveGone, RunView

EXTENSION_UUID = "zark@juanmitaboada.com"
SHELL = "org.gnome.Shell"
SHELL_PATH = "/org/gnome/Shell"
SHELL_EXTENSIONS = "org.gnome.Shell.Extensions"
ACTIVE = 1
# The first extension version that shows this alert itself.
EXTENSION_ALERTS_FROM = (1, 3)
TIMEOUT_MS = 2000

Present = Callable[[str, DriveGone], None]


def session_bus() -> Any:
    """The session bus, or None when it cannot be reached."""
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return None


def _version(text: object) -> tuple[int, ...] | None:
    """``(1, 3)`` from ``"1.3"``; None for anything else."""
    if not isinstance(text, str) or not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


def extension_alerts(info: dict[str, Any]) -> bool:
    """The extension is active and old enough to show the alert itself."""
    version = _version(info.get("version-name"))
    return info.get("state") == ACTIVE and version is not None and version >= EXTENSION_ALERTS_FROM


class DriveGoneAlert:
    """Decides once per run and drive whether the app shows the dialog."""

    def __init__(self, present: Present, bus: Callable[[], Any] = session_bus) -> None:
        self._present = present
        self._bus = bus
        self._seen: set[str] = set()

    def see(self, run: RunView | None) -> None:
        """Called with every snapshot's run."""
        if run is None or run.drive_gone is None:
            return
        gone = run.drive_gone
        if gone.key in self._seen:
            return
        # Taken now: a snapshot that comes before Shell answers asks nothing.
        self._seen.add(gone.key)
        drive = run.drive or gone.pool
        bus = self._bus()
        if bus is None:
            self._present(drive, gone)
            return
        bus.call(
            SHELL,
            SHELL_PATH,
            SHELL_EXTENSIONS,
            "GetExtensionInfo",
            GLib.Variant("(s)", (EXTENSION_UUID,)),
            GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            TIMEOUT_MS,
            None,
            self._answered,
            (drive, gone),
        )

    def _answered(self, bus: Any, result: Gio.AsyncResult, data: tuple[str, DriveGone]) -> None:
        drive, gone = data
        try:
            info = bus.call_finish(result).unpack()[0]
        except (GLib.Error, TypeError, IndexError) as e:
            _log(f"GNOME Shell did not answer about the extension ({e}): the app shows the alert")
            info = {}
        if extension_alerts(info):
            return
        self._present(drive, gone)


def _log(text: str) -> None:
    print(f"zark-gnome-app: {text}", file=sys.stderr)
