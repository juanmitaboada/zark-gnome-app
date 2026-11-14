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
"""logind's sleep inhibitor (A2E-5), with a bus that records and answers."""

import os
from typing import Any

from gi.repository import Gio, GLib

from zark_app.sleep import LOGIND, LOGIND_MANAGER, LOGIND_PATH, SleepInhibitor


class FakeBus:
    """Records ``Inhibit`` and answers when told: a pipe's end as the descriptor."""

    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.calls: list[tuple[Any, ...]] = []
        self.callback: Any = None
        self.read_end, self.write_end = os.pipe()

    def call_with_unix_fd_list(self, *args: Any) -> None:
        """As Gio.DBusConnection's: keep the call and its callback."""
        self.calls.append(args)
        self.callback = args[10]

    def answer(self) -> None:
        """logind's reply."""
        self.callback(self, None)

    def call_with_unix_fd_list_finish(self, _result: object) -> tuple[GLib.Variant, Gio.UnixFDList]:
        """The reply: one handle, index 0 of the descriptor list."""
        if self.refuse:
            raise GLib.Error("Access denied")
        fds = Gio.UnixFDList.new()
        fds.append(self.write_end)
        return GLib.Variant("(h)", (0,)), fds

    def close(self) -> None:
        """The test's own ends."""
        for fd in (self.read_end, self.write_end):
            try:
                os.close(fd)
            except OSError:
                pass


def _open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def test_inhibit_call_and_release() -> None:
    """``Inhibit("sleep", "zark", why, "block")`` on logind; the descriptor
    kept until release, then closed."""
    bus = FakeBus()
    inhibitor = SleepInhibitor(lambda: bus)
    inhibitor.acquire("Backing Up to black")
    assert len(bus.calls) == 1
    name, path, iface, method, params = bus.calls[0][:5]
    assert (name, path, iface, method) == (LOGIND, LOGIND_PATH, LOGIND_MANAGER, "Inhibit")
    assert params.unpack() == ("sleep", "zark", "Backing Up to black", "block")
    assert not inhibitor.held
    bus.answer()
    assert inhibitor.held
    fd = inhibitor._fd  # pylint: disable=protected-access
    assert fd is not None and _open(fd)
    inhibitor.release()
    assert not inhibitor.held and not _open(fd)
    bus.close()


def test_ended_before_the_answer() -> None:
    """The run ends before logind answers: the descriptor is closed at once."""
    bus = FakeBus()
    inhibitor = SleepInhibitor(lambda: bus)
    inhibitor.acquire("Backing Up to black")
    inhibitor.release()
    bus.answer()
    assert not inhibitor.held
    bus.close()


def test_refused_or_no_bus() -> None:
    """logind refuses, or there is no system bus: nothing held, nothing raised."""
    bus = FakeBus(refuse=True)
    inhibitor = SleepInhibitor(lambda: bus)
    inhibitor.acquire("Backing Up to black")
    bus.answer()
    assert not inhibitor.held
    inhibitor.release()
    bus.close()
    alone = SleepInhibitor(lambda: None)
    alone.acquire("Backing Up to black")
    assert not alone.held
    alone.release()


def test_one_request_per_run() -> None:
    """A second acquire while the first stands asks nothing more."""
    bus = FakeBus()
    inhibitor = SleepInhibitor(lambda: bus)
    inhibitor.acquire("a")
    inhibitor.acquire("b")
    assert len(bus.calls) == 1
    bus.answer()
    inhibitor.release()
    bus.close()
