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
"""A logind sleep inhibitor in ``block`` mode for the app's own run (A2E-5).

``Gtk.Application.inhibit`` reaches gnome-session, which takes logind's
``sleep`` inhibitor in ``block-weak`` mode as the user; GNOME Shell's Suspend
goes through gnome-session to ``SuspendWithFlags(SKIP_INHIBITORS)``, and
logind skips a weak inhibitor whose uid is the caller's, so the user's own
Suspend went through during a backup. A ``block`` inhibitor is not skipped
by uid: logind then asks polkit for ``suspend-ignore-inhibit``, and GNOME
Shell shows the administrator's password dialog. Polkit grants the inhibitor
itself to the active user (``inhibit-block-sleep``: ``allow_active yes``).

logind keeps the inhibitor while its file descriptor is open; closing it,
or the app's end, releases it. No GTK here.
"""

import os
import sys
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib

LOGIND = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_MANAGER = "org.freedesktop.login1.Manager"
WHO = "zark"


def system_bus() -> Any:
    """The system bus, or None when it cannot be reached."""
    try:
        return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except GLib.Error:
        return None


class SleepInhibitor:
    """Takes logind's ``sleep`` inhibitor in ``block`` mode and lets it go.
    Without a bus or when logind refuses, the run goes on with the weak
    inhibitor alone, and the reason goes to the journal (stderr)."""

    def __init__(self, bus: Callable[[], Any] = system_bus) -> None:
        self._bus = bus
        self._fd: int | None = None
        self._wanted = False

    @property
    def held(self) -> bool:
        """logind answered and the descriptor is open."""
        return self._fd is not None

    def acquire(self, why: str) -> None:
        """Ask logind for the inhibitor; the answer comes on the main loop."""
        if self._wanted:
            return
        self._wanted = True
        bus = self._bus()
        if bus is None:
            _log("no system bus: suspend is held by gnome-session's weak inhibitor only")
            return
        bus.call_with_unix_fd_list(
            LOGIND,
            LOGIND_PATH,
            LOGIND_MANAGER,
            "Inhibit",
            GLib.Variant("(ssss)", ("sleep", WHO, why, "block")),
            GLib.VariantType.new("(h)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
            self._answered,
            None,
        )

    def _answered(self, bus: Any, result: Gio.AsyncResult, _data: object = None) -> None:
        try:
            reply, fds = bus.call_with_unix_fd_list_finish(result)
            fd = fds.get(reply.unpack()[0])
        except (GLib.Error, TypeError, IndexError) as e:
            _log(f"logind refused the sleep inhibitor: {e}")
            return
        if not self._wanted:
            # The run ended before logind answered.
            os.close(fd)
            return
        self._fd = fd

    def release(self) -> None:
        """Let the inhibitor go (at the run's end)."""
        self._wanted = False
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def _log(text: str) -> None:
    print(f"zark-gnome-app: {text}", file=sys.stderr)
