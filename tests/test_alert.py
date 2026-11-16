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
"""The drive-gone alert: read from ``progress.json``, once per run and drive,
and quiet only when zark's extension 1.3 or later is active. GNOME Shell is
a fake bus here; nothing reaches a real one."""

import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from gi.repository import GLib

from tests.harness import app_case
from tests.test_model import snap
from zark_app import alert, model
from zark_app.model import DriveGone, RunView

HINT = (
    "black's drive went away. Safer: unplug it, then: sudo sh -c 'zpool sync rpool bpool; "
    "systemctl reboot --force --force' (a plain reboot can hang). Or plug it back in and run: "
    "sudo zpool clear black (can crash OpenZFS 2.4: man zark)"
)


@dataclass(frozen=True)
class FakeResult:
    """What ``call_finish`` returns: a reply or an error."""

    info: dict[str, Any] | None
    error: bool = False


class FakeShell:
    """A session bus whose GNOME Shell answers ``GetExtensionInfo`` at once."""

    def __init__(self, info: dict[str, Any] | None = None, error: bool = False) -> None:
        self.info = info if info is not None else {}
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    def call(self, *args: Any) -> None:
        """Gio.DBusConnection.call: record it, answer through its callback."""
        self.calls.append(args[:8])
        callback, data = args[9], args[10]
        callback(self, FakeResult(self.info, self.error), data)

    def call_finish(self, result: FakeResult) -> GLib.Variant:
        """The reply, or Shell's absence as a GLib.Error."""
        if result.error:
            raise GLib.Error("org.freedesktop.DBus.Error.ServiceUnknown")
        # As GNOME Shell packs them (serializeExtension): numbers as doubles.
        packed = {
            k: GLib.Variant("d", float(v)) if isinstance(v, (int, float)) else GLib.Variant("s", str(v))
            for k, v in (result.info or {}).items()
        }
        return GLib.Variant("(a{sv})", (packed,))


def _run() -> RunView:
    run = snap(app_case("running-drive-gone")).run
    assert run is not None
    return run


def _watch(bus: Any) -> tuple[alert.DriveGoneAlert, list[tuple[str, DriveGone]]]:
    shown: list[tuple[str, DriveGone]] = []
    return alert.DriveGoneAlert(lambda drive, gone: shown.append((drive, gone)), lambda: bus), shown


def test_drive_gone_read() -> None:
    """zark 2.3.1's fields: the pool, the time, the hint as written, the key."""
    gone = _run().drive_gone
    assert gone is not None
    assert gone.pool == "black"
    assert gone.since is not None and gone.since.isoformat() == "2026-10-24T09:20:41+00:00"
    assert gone.hint == HINT
    assert gone.key == "48213:2026-10-24T09:02:11Z:black"


def test_no_drive_gone() -> None:
    """Absent (an older zark), null or malformed: nothing to alert."""
    assert snap(app_case("running-connected")).run.drive_gone is None  # type: ignore[union-attr]


def test_once_per_run_and_drive() -> None:
    """Once at the first sight; not at the next poll, nor when the drive is
    back; again for another run and for another pool."""
    watch, shown = _watch(None)
    run = _run()
    gone = run.drive_gone
    assert gone is not None
    watch.see(run)
    assert [d for d, _ in shown] == ["black"]
    watch.see(run)
    watch.see(replace(run, drive_gone=replace(gone, hint=gone.hint + " back")))
    assert len(shown) == 1
    watch.see(replace(run, pid=1, drive_gone=replace(gone, key="1:2026-10-24T09:02:11Z:black")))
    watch.see(replace(run, drive_gone=replace(gone, pool="blue", key="48213:2026-10-24T09:02:11Z:blue")))
    assert len(shown) == 3
    watch.see(None)
    watch.see(replace(run, drive_gone=None))
    assert len(shown) == 3


def test_drive_name_from_the_run() -> None:
    """The run's drive name, else the pool."""
    watch, shown = _watch(None)
    watch.see(replace(_run(), drive=None))
    assert shown[0][0] == "black"


@pytest.mark.parametrize(
    ("info", "error", "alerts"),
    [
        ({"state": 1.0, "version-name": "1.3"}, False, False),
        ({"state": 1.0, "version-name": "1.10"}, False, False),
        ({"state": 1.0, "version-name": "2.0"}, False, False),
        ({"state": 1.0, "version-name": "1.2"}, False, True),
        ({"state": 1.0}, False, True),
        ({"state": 1.0, "version-name": "beta"}, False, True),
        ({"state": 2.0, "version-name": "1.3"}, False, True),
        ({"state": 3.0, "version-name": "1.3"}, False, True),
        ({}, False, True),
        (None, True, True),
    ],
)
def test_extension_check(info: dict[str, Any] | None, error: bool, alerts: bool) -> None:
    """Quiet only for an active extension 1.3 or later; an inactive or older
    one, an unknown extension (Shell's empty dict) or no answer: the alert."""
    bus = FakeShell(info, error)
    watch, shown = _watch(bus)
    watch.see(_run())
    assert len(shown) == (1 if alerts else 0)
    assert len(bus.calls) == 1
    name, path, iface, method, args = bus.calls[0][:5]
    assert (name, path, iface, method) == (
        "org.gnome.Shell",
        "/org/gnome/Shell",
        "org.gnome.Shell.Extensions",
        "GetExtensionInfo",
    )
    assert args.unpack() == ("zark@juanmitaboada.com",)
    watch.see(_run())
    assert len(bus.calls) == 1


def test_no_session_bus() -> None:
    """No session bus (another desktop): the alert."""
    watch, shown = _watch(None)
    watch.see(_run())
    assert len(shown) == 1


@pytest.mark.parametrize(
    "value",
    [None, "gone", [], {"since": "2026-10-24T09:20:41Z"}, {"pool": ""}, {"pool": 7}],
)
def test_malformed_drive_gone(tmp_path: Path, value: object) -> None:
    """Null, not an object, or without a pool: no alert."""
    assert _case_with(tmp_path, value).run.drive_gone is None  # type: ignore[union-attr]


def test_hint_not_text(tmp_path: Path) -> None:
    """A hint that is not a string is dropped, never composed by the app."""
    gone = _case_with(tmp_path, {"pool": "black", "hint": 3}).run.drive_gone  # type: ignore[union-attr]
    assert gone is not None and gone.hint == "" and gone.since is None


def _case_with(tmp: Path, value: object) -> model.Snapshot:
    """running-drive-gone with its ``drive_gone`` replaced by ``value``."""
    case = app_case("running-drive-gone")
    root = tmp / "root"
    shutil.copytree(case.sources.root, root, symlinks=True)
    progress = root / "run" / "zark" / "progress.json"
    doc = json.loads(progress.read_text(encoding="utf-8"))
    progress.write_text(json.dumps({**doc, "drive_gone": value}), encoding="utf-8")
    return snap(replace(case, sources=replace(case.sources, root=root)))
