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

import json
import shutil
from dataclasses import replace
from pathlib import Path

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


def _writer_case(tmp: Path, writer: str) -> Case:
    """older-writer with its status file written by zark ``writer``."""
    case = app_case("older-writer")
    root = tmp / "root"
    shutil.copytree(case.sources.root, root, symlinks=True)
    status = root / "var" / "lib" / "zark" / "status.json"
    doc = json.loads(status.read_text(encoding="utf-8"))
    status.write_text(json.dumps({**doc, "zark_version": writer}), encoding="utf-8")
    return replace(case, sources=replace(case.sources, root=root))


@pytest.mark.parametrize(
    ("writer", "installed", "banner"),
    [
        ("2.3.1-rc1", "2.3.1~rc1-1", None),
        ("2.3.1-rc1", "2.3.1~rc1-1~ubuntu24.04.1", None),
        ("2.3.0", "2.3.0-1", None),
        ("2.3.0", "2.3.1~rc1-1", "The status file was written by zark 2.3.0, not the installed 2.3.1-rc1"),
        ("2.3.1-rc1", "2.3.1-1", "The status file was written by zark 2.3.1-rc1, not the installed 2.3.1"),
    ],
)
def test_writer_against_installed(tmp_path: Path, writer: str, installed: str, banner: str | None) -> None:
    """A112E-1: a release candidate matches its Debian spelling; a real
    mismatch still has the banner."""
    case = _writer_case(tmp_path, writer)
    s, _ = model.build(case.loaded, case.sources, Live(zark_version=installed))
    assert (s.banner.text if s.banner is not None else None) == banner


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


def _with_transfer(base: Snapshot, **fields: object) -> Snapshot:
    """``base`` with its run's transfer block changed by ``fields``."""
    assert base.run is not None and base.run.transfer is not None
    return replace(base, run=replace(base.run, transfer={**base.run.transfer, **fields}))


def test_a_resume_whose_total_holds_keeps_the_percentage() -> None:
    """A112E-3: zark 2.3.1 estimates a resume's next stream in its round, so
    a resume alone keeps the percentage and the time left to the end."""
    totals: dict[model.RunKey, int | None] = {}
    base = snap(app_case("running-connected"))
    assert base.run is not None
    for state in ("resume", "incremental", "resume"):
        shown = model.with_rounds(_with_transfer(base, dataset_state=state), totals)
        assert shown.run is not None and not shown.run.rounds
        assert shown.run.fraction == base.run.fraction and shown.run.eta_s == base.run.eta_s


def test_a_total_that_grows_shows_bytes_only() -> None:
    """A112E-2: a second round raises bytes_total (zark 2.3.0 after a
    resume); from then on bytes only for the rest of the run, the data sent
    still shows 100 %, and another run starts afresh."""
    totals: dict[model.RunKey, int | None] = {}
    base = snap(app_case("running-connected"))
    assert base.run is not None and base.run.transfer is not None
    total = base.run.transfer["bytes_total"]
    assert not model.with_rounds(base, totals).run.rounds  # type: ignore[union-attr]
    grown = model.with_rounds(_with_transfer(base, bytes_total=total + 3 * 2**30), totals)
    assert grown.run is not None and grown.run.rounds
    assert grown.run.fraction is None and grown.run.eta_s is None
    assert model.progress_figure(grown.run) == (None, "7.00 GiB sent")
    later = model.with_rounds(base, totals)
    assert later.run is not None and later.run.rounds and later.run.fraction is None
    sent = replace(grown, run=replace(grown.run, transfer=None, sent=True))
    assert model.progress_figure(sent.run) == (1.0, "100 %")  # type: ignore[arg-type]
    other = replace(base, run=replace(base.run, pid=(base.run.pid or 0) + 1))
    fresh = model.with_rounds(other, totals)
    assert fresh.run is not None and not fresh.run.rounds and fresh.run.fraction is not None


def test_a_round_being_announced_is_not_growth() -> None:
    """A112E-2: before the first send zark adds each estimate in turn, so
    a growing total then is the first round's own announcement."""
    totals: dict[model.RunKey, int | None] = {}
    base = snap(app_case("running-connected"))
    announcing = _with_transfer(base, dataset=None, dataset_state=None, datasets_done=0, bytes_total=2**30)
    assert not model.with_rounds(announcing, totals).run.rounds  # type: ignore[union-attr]
    assert not model.with_rounds(base, totals).run.rounds  # type: ignore[union-attr]
    between = _with_transfer(base, dataset=None, dataset_state=None)
    assert not model.with_rounds(between, totals).run.rounds  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("case", "level"), [("interrupted", "error"), ("not-verified", "error"), ("incomplete", "warning")]
)
def test_attention_level(case: str, level: str) -> None:
    """A2E-4: how loud black's attention state is."""
    s = snap(zark_case(case))
    black = next(d for d in s.drives if d.name == "black")
    assert black.state == "attention" and black.level == level


def test_mounted_drive_offers_no_backup() -> None:
    """A1E-6: a drive mounted for browsing has no Back Up and says why."""
    s = snap(app_case("mounted"))
    black = next(d for d in s.drives if d.name == "black")
    assert black.mounted and black.backup is None
    assert black.line == "Mounted for browsing" and black.short == "Mounted"


def test_run_titles_name_the_drive() -> None:
    """A1E-6: a drive command's title names its drive once zark does."""
    assert model.run_title("mount", "backup2") == "Mounting backup2"
    assert model.run_title("umount", "backup2") == "Unmounting backup2"
    assert model.run_title("health", "backup2") == "Checking the Health of backup2"
    assert model.run_title("backup", "black") == "Backing Up to black"
    assert model.run_title("mount", None) == "Mounting a Drive"
    assert model.run_title("explore", "black") == "Looking for Drives"
    assert model.run_title("something-new", "black") == "zark Is Busy"
