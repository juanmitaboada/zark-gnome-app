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
"""The snapshot the window draws, from every case, without a display."""

import pytest

from tests.harness import Case, any_case, app_case, zark_case, zark_case_names
from zark_app import model
from zark_app.live import Fetcher, Live
from zark_app.model import Snapshot


def snap(case: Case, live: bool = True) -> Snapshot:
    """Build the snapshot, the live figures fetched from the case first."""
    got: list[Live] = [Live()]
    if live:
        first, _ = model.build(case.loaded, case.sources, Live())
        Fetcher(case.runner, case.sources.now).fetch(model.source_pool_names(first), got.append)
    s, _ = model.build(case.loaded, case.sources, got[-1])
    return s


@pytest.mark.parametrize("name", zark_case_names())
def test_zark_case_indicator(name: str) -> None:
    """The snapshot carries the reader's verdict for every zark case."""
    case = zark_case(name)
    s = snap(case, live=False)
    assert case.expected is not None
    assert (s.progress_class, s.status_class, s.indicator) == (
        case.expected["progress"],
        case.expected["status"],
        case.expected["indicator"],
    )


def test_no_status() -> None:
    """No status.json: the No Status Yet page."""
    assert snap(zark_case("no-status")).page == "no_status"


def test_newer_keeps_last_good() -> None:
    """A newer file is not read; the last good document stays."""
    good = zark_case("idle")
    first, last = model.build(good.loaded, good.sources, Live())
    newer = zark_case("newer-schema")
    s, kept = model.build(newer.loaded, newer.sources, Live(), last)
    assert first.page == "ok" and s.page == "ok" and kept is last
    assert s.banner is not None and "newer zark" in s.banner.text


def test_stale_without_timer() -> None:
    """Stale with the timer missing: Turn On... copies alerts install."""
    s = snap(zark_case("stale"))
    assert s.banner is not None and "hourly checks are off" in s.banner.text
    assert s.banner.action is not None and s.banner.action.op == "alerts-install"


def test_stale_with_timer() -> None:
    """Stale with the timer installed: Refresh."""
    s = snap(app_case("stale-timer-on"))
    assert s.banner is not None and s.banner.action is not None
    assert s.banner.action.op == "refresh"


def test_orphan() -> None:
    """An orphan run: Clean Up... copies zark clean."""
    s = snap(zark_case("orphan"))
    assert s.banner is not None and "without cleaning up (backup to black)" in s.banner.text
    assert s.banner.action is not None and s.banner.action.op == "clean"
    assert s.run is None


def test_running_connected() -> None:
    """A backup to a connected black: the run, the drive busy, no Back Up."""
    s = snap(app_case("running-connected"))
    assert s.run is not None and s.run.title == "Backing Up to black"
    assert s.run.fraction is not None and s.run.eta_s is not None
    black = next(d for d in s.drives if d.name == "black")
    assert black.state == "running" and black.backup is None
    assert s.banner is None


def test_unplugged() -> None:
    """The run's drive gone from by-id: the banner says so."""
    s = snap(app_case("unplugged"))
    assert s.banner is not None and "disconnected during the run" in s.banner.text


def test_waiting() -> None:
    """A question in the terminal."""
    case = zark_case("waiting", connected=["usb-JMicron_Generic_DISK00_0123456789ABCDEF-0:0"])
    s = snap(case)
    assert s.run is not None and s.run.waiting and s.run.waiting_for == "Passphrase for black"
    assert next(d for d in s.drives if d.name == "black").line == "Waiting for your answer"


def test_stalled() -> None:
    """No heartbeat for a while: the seconds are counted."""
    s = snap(zark_case("stalled"))
    assert s.run is not None and s.run.stalled_s is not None and s.run.stalled_s > 30


def test_attention_lines() -> None:
    """A drive whose last run needs attention."""
    for name, words in (
        ("incomplete", "Last run incomplete"),
        ("not-verified", "Last run not verified"),
        ("interrupted", "Last run interrupted"),
    ):
        s = snap(zark_case(name))
        black = next(d for d in s.drives if d.name == "black")
        assert black.state == "attention" and black.line.startswith(words), name


def test_connected() -> None:
    """A connected idle drive offers Back Up with --drive (zark 2.3.0)."""
    s = snap(app_case("connected"))
    black = next(d for d in s.drives if d.name == "black")
    assert black.connected and black.backup is not None
    assert (black.backup.op, black.backup.arg) == ("backup", "black")
    assert s.pools_live and s.pools[0].pct == 89 and s.pools[0].level == "warning"
    assert s.installed_zark == "2.3.0-1"
    assert s.banner is None


def test_pending() -> None:
    """drive_pending becomes a pending drive, not a notice."""
    s = snap(app_case("pending"))
    assert [p.name for p in s.pending] == ["spare"]
    assert (s.pending[0].action.op, s.pending[0].action.arg) == ("verify", "spare")
    assert all(n.code != "drive_pending" for n in s.notices)


def test_foreign_writer() -> None:
    """A status file from a stick's zark."""
    s = snap(app_case("foreign-writer"))
    assert s.banner is not None
    assert s.banner.text == (
        "The status file was written by zark 2.2.3 from /media/usb/zark, not the installed 2.3.0"
    )


def test_older_writer() -> None:
    """A status file from another version of zark at the usual registry."""
    s = snap(app_case("older-writer"))
    assert s.banner is not None and "zark 2.1.0, not the installed 2.3.0" in s.banner.text


def test_mounted() -> None:
    """black imported with no run: mounted for browsing."""
    s = snap(app_case("mounted"))
    assert s.banner is not None and s.banner.text.startswith("black is mounted for browsing")
    assert s.banner.action is not None and (s.banner.action.op, s.banner.action.arg) == ("umount", "black")
    assert next(d for d in s.drives if d.name == "black").mounted


def test_no_drives() -> None:
    """No drive and none pending."""
    s = snap(app_case("no-drives"))
    assert s.page == "ok" and not s.drives and not s.pending


def test_zpool_fails() -> None:
    """The live commands fail: the file's figures, dated."""
    s = snap(app_case("zpool-fails"))
    assert not s.pools_live and not s.pools[0].live and s.pools[0].measured_at is not None
    assert s.exclusions is None


def test_exclusions() -> None:
    """zfs get's local "no" values."""
    s = snap(app_case("exclusions"))
    assert s.exclusions is not None
    by_name = {e.dataset: e for e in s.exclusions}
    assert by_name["rpool/var/cache"].backups and not by_name["rpool/var/cache"].snapshots
    assert by_name["rpool/scratch"].backups and by_name["rpool/scratch"].snapshots
    assert by_name["rpool/scratch"].used == 90000000000


def test_no_zark_and_too_old() -> None:
    """The reader missing or too old: whole-page states."""
    assert snap(app_case("no-zark")).page == "no_zark"
    assert snap(app_case("too-old")).page == "too_old"


def test_upgrade_risk_is_a_notice() -> None:
    """A code the app knows by title, shown with zark's text as is."""
    s = snap(app_case("upgrade-risk"))
    notice = next(n for n in s.notices if n.code == "upgrade_risk")
    assert notice.title == "Upgrade Risk" and notice.text.startswith("this system's upgrade")


def test_boot_ext4() -> None:
    """26.10's ext4 /boot has its own row."""
    s = snap(zark_case("boot-ext4"))
    assert s.boot is not None and s.boot.name == "/boot" and s.boot.pct == 86


def test_drive_details() -> None:
    """The drive page's figures, from the drive contents case."""
    case = zark_case("drive-contents")
    s = snap(case)
    black = next(d for d in s.drives if d.name == "black")
    assert s.module is not None
    details = model.drive_details(s.module, black.doc, None, s.now)
    assert details.space is not None and details.space.margin == 387573822259
    assert details.months is not None and sum(len(m.points) for m in details.months) == 40
    assert details.months_add_up
    assert details.largest is not None and len(details.largest) == 5


def test_snapshot_equal_within_a_minute() -> None:
    """Two reads a few seconds apart draw the same (no redraw)."""
    case = any_case("app:connected")
    a, _ = model.build(case.loaded, case.sources, Live())
    b, _ = model.build(case.loaded, case.sources, Live())
    assert a == b


def test_drive_menu_operations() -> None:
    """The drive menu names every operation the design lists, each known to
    the command builder."""
    from zark_app.commands import OPS  # pylint: disable=import-outside-toplevel

    ops = [(a.op, a.arg) for part in model.drive_actions("black", False) for a in part]
    assert ("retention", "black") in ops and ("forget", "black") in ops and ("mount", "black") in ops
    assert ("umount", "black") in [(a.op, a.arg) for part in model.drive_actions("black", True) for a in part]
    assert all(op in OPS for op, _arg in ops)


def test_progress_figure_is_bytes_only() -> None:
    """A1E-3: a percentage from bytes; a step alone gives none."""
    s = snap(app_case("running-connected"))
    assert s.run is not None
    fraction, text = model.progress_figure(s.run)
    assert fraction is not None and text == f"{int(fraction * 100)} %"
    s = snap(app_case("running-step5"))
    assert s.run is not None and s.run.step_index == 5 and s.run.transfer is None
    assert model.progress_figure(s.run) == (None, "")


def test_sent_after_this_runs_transfer() -> None:
    """A1E-3: once a run seen with a transfer has none, its data is sent;
    a reader that never saw the transfer cannot tell (the step only)."""
    seen: set[model.RunKey] = set()
    during = model.with_sent(snap(app_case("running-connected")), seen)
    assert during.run is not None and not during.run.sent and len(seen) == 1
    after = model.with_sent(snap(app_case("running-after-transfer")), seen)
    assert after.run is not None and after.run.sent
    assert model.progress_figure(after.run) == (1.0, "100 %")
    fresh = model.with_sent(snap(app_case("running-after-transfer")), set())
    assert fresh.run is not None and not fresh.run.sent
    assert model.progress_figure(fresh.run) == (None, "")
