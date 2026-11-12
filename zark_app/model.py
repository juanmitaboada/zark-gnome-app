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
"""One immutable view of everything the window shows, built from zark's
reader, the status files and the live figures. No GTK here: every rule of
the app's design (its sections 2 and 5: screens, states and errors) is
applied here and tested without a display.

The people-only strings (``step.label``, ``waiting_for``,
``last_run.message``, a notice's ``text``) are shown as they are, never
parsed.
"""

# The view types mirror the design's tables one field per figure.
# pylint: disable=too-many-instance-attributes

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from zark_app.i18n import N_, _
from zark_app.live import Exclusion, Live
from zark_app.reader import Loaded
from zark_app.sources import MOUNT_ROOT, REGISTRY_PATH, Sources
from zark_app.units import fmt_bytes, fmt_since, upstream_version

Doc = Mapping[str, Any]
Level = Literal["ok", "warning", "critical"]
PageState = Literal["no_zark", "too_old", "no_status", "ok"]
DriveState = Literal["running", "waiting", "attention", "connected", "disconnected"]


@dataclass(frozen=True)
class Action:
    """A button or menu item: it runs operation ``op`` (one of
    :data:`zark_app.commands.OPS`) with ``arg``, a drive name, a dataset or
    nothing. The argv is built and checked only when it runs."""

    label: str
    op: str
    arg: str = ""


@dataclass(frozen=True)
class PoolView:
    """A source pool's or ``/boot``'s row."""

    name: str
    used: int | None
    size: int | None
    pct: int | None
    level: Level
    live: bool
    measured_at: datetime | None


@dataclass(frozen=True)
class DriveView:
    """A registered drive's rows in the sidebar and the Overview."""

    name: str
    connected: bool
    state: DriveState
    line: str
    short: str
    mounted: bool
    doc: Doc = field(compare=True)
    backup: Action | None = None


@dataclass(frozen=True)
class PendingView:
    """A drive ``prepare`` wrote and could not read back (``drive_pending``)."""

    name: str
    text: str
    action: Action


@dataclass(frozen=True)
class NoticeView:
    """One notice of ``status.json`` the Notices group shows."""

    code: str
    level: str
    title: str
    text: str
    action: Action | None


@dataclass(frozen=True)
class BannerView:
    """The one banner, the most urgent."""

    text: str
    action: Action | None = None


@dataclass(frozen=True)
class RunView:
    """A run in ``progress.json``; the app started none in A1."""

    command: str
    title: str
    drive: str | None
    started_at: datetime | None
    step_index: int | None
    step_total: int | None
    label: str
    transfer: Doc | None
    fraction: float | None
    eta_s: int | None
    stalled_s: int | None
    waiting: bool
    waiting_for: str
    check: Doc | None
    drive_space: Doc | None
    pid: int | None = None
    # This run had a transfer block and no longer has one: its data is sent.
    sent: bool = False


@dataclass(frozen=True)
class Snapshot:
    """What the window draws. ``now`` is not compared: two snapshots that
    differ only in the clock draw the same, ``minute`` included."""

    page: PageState
    detail: str
    indicator: str
    status_class: str
    progress_class: str
    generated_at: datetime | None
    minute: datetime | None
    pools: tuple[PoolView, ...]
    pools_live: bool
    boot: PoolView | None
    drives: tuple[DriveView, ...]
    pending: tuple[PendingView, ...]
    notices: tuple[NoticeView, ...]
    banner: BannerView | None
    run: RunView | None
    exclusions: tuple[Exclusion, ...] | None
    datasets: tuple[str, ...]
    installed_zark: str | None
    timer_installed: bool
    writer_version: str | None
    status: Doc | None
    now: datetime = field(compare=False)
    module: ModuleType | None = field(default=None, compare=False)


# --- words ---

COMMAND_TITLES = {
    "backup": N_("Backing Up"),
    "prune": N_("Reclaiming Space"),
    "prepare": N_("Preparing a Drive"),
    "purge": N_("Erasing a Drive"),
    "health": N_("Checking Health"),
    "fullcheck": N_("Verifying a Drive"),
    "mount": N_("Mounting a Drive"),
    "umount": N_("Unmounting a Drive"),
    "explore": N_("Looking for Drives"),
    "registry": N_("Changing the Registry"),
    "exclude": N_("Changing Exclusions"),
    "clean": N_("Cleaning Up"),
    "recover": N_("Recovering"),
    "setup": N_("Setting Up zark"),
    "selftest": N_("Testing zark"),
}

RESULT_WORDS = {
    "completed": N_("Completed"),
    "incomplete": N_("Incomplete"),
    "not_verified": N_("Not verified"),
    "aborted": N_("Aborted"),
    "interrupted": N_("Interrupted"),
}

CHECK_WORDS = {
    "clean": N_("Clean"),
    "damage": N_("Damage found"),
    "not_finished": N_("Not finished"),
    "failed": N_("Failed"),
}

NOTICE_TITLES = {
    "boot_capacity": N_("/boot Space"),
    "backup_age": N_("Backups"),
    "no_anchor": N_("No Anchor"),
    "read_error": N_("Could Not Read"),
    "origin_residues": N_("Leftover Snapshots"),
    "drive_check": N_("Drive Check"),
    "selftest": N_("Self-Test"),
    "upgrade_risk": N_("Upgrade Risk"),
}

# Shown elsewhere: capacity on its pool's row, drive_pending as a drive row.
NOTICES_ELSEWHERE = ("capacity", "drive_pending")


def run_title(command: str, drive: str | None) -> str:
    """``Backing Up to black``; a command the app does not know is the
    contract's generic case."""
    if command not in COMMAND_TITLES:
        return _("zark Is Busy")
    title = _(COMMAND_TITLES[command])
    return (
        _("{title} to {drive}").format(title=title, drive=drive) if drive and command == "backup" else title
    )


def result_words(result: object) -> str:
    """A ``last_run.result`` in words; an unknown one as it is."""
    return _(RESULT_WORDS[result]) if isinstance(result, str) and result in RESULT_WORDS else str(result)


# --- the operations behind the buttons (design 3.1) ---


def drive_actions(name: str, mounted: bool) -> list[list[Action]]:
    """The drive menu's sections (design 3.2)."""
    browse = [Action(_("Unmount"), "umount", name)] if mounted else [Action(_("Browse Files"), "mount", name)]
    return [
        [
            *browse,
            Action(_("Reclaim Space..."), "prune", name),
            Action(_("Check Health..."), "health", name),
            Action(_("Verify Drive..."), "fullcheck", name),
            Action(_("Retention..."), "retention", name),
        ],
        [
            Action(_("Repair Entry"), "fix", name),
            Action(_("Forget Drive..."), "forget", name),
            Action(_("Erase Drive..."), "purge", name),
        ],
    ]


def primary_actions(timer_installed: bool) -> list[list[Action]]:
    """The primary menu's zark items (design 3.2)."""
    hourly = (
        Action(_("Turn Off Hourly Checks"), "alerts-remove")
        if timer_installed
        else Action(_("Turn On Hourly Checks"), "alerts-install")
    )
    return [
        [
            Action(_("Refresh Status"), "refresh"),
            Action(_("Look for Drives..."), "explore"),
            Action(_("Prepare a New Drive..."), "prepare"),
        ],
        [hourly, Action(_("Clean Up After a Stopped Run..."), "clean")],
    ]


# --- building ---


def _dicts(value: object) -> list[Doc]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def obj(value: object) -> Doc:
    """``value`` when it is a JSON object, else an empty one."""
    return value if isinstance(value, dict) else {}


def opt_obj(value: object) -> Doc | None:
    """``value`` when it is a JSON object, else None."""
    return value if isinstance(value, dict) else None


def _level(value: object) -> Level:
    if value == "warning":
        return "warning"
    if value == "critical":
        return "critical"
    return "ok"


@dataclass
class _Ctx:
    mod: ModuleType
    sources: Sources
    now: datetime
    live: Live
    status: Doc | None
    progress: Doc | None
    progress_class: str


def _pool_view(ctx: _Ctx, entry: Doc, thresholds: Doc) -> PoolView:
    name = str(entry.get("name", "?"))
    live = ctx.live.pools.get(name) if ctx.live.pools is not None else None
    if live is not None:
        level = _level(ctx.mod.capacity_level(live.capacity, thresholds))
        return PoolView(name, live.allocated, live.size, live.capacity, level, True, ctx.live.measured_at)
    space = opt_obj(entry.get("space"))
    level = _level(entry.get("level"))
    if space is None:
        return PoolView(name, None, None, None, level, False, None)
    return PoolView(
        name,
        _int(space.get("pool_alloc_bytes")),
        _int(space.get("pool_size_bytes")),
        _int(space.get("capacity_pct")),
        level,
        False,
        ctx.mod.parse_timestamp(space.get("measured_at")),
    )


def _boot_view(ctx: _Ctx, boot: object) -> PoolView | None:
    if not isinstance(boot, dict):
        return None
    space = opt_obj(boot.get("space"))
    level = _level(boot.get("level"))
    name = str(boot.get("mountpoint") or "/boot")
    if space is None:
        return PoolView(name, None, None, None, level, False, None)
    return PoolView(
        name,
        _int(space.get("used_bytes")),
        _int(space.get("size_bytes")),
        _int(space.get("capacity_pct")),
        level,
        False,
        ctx.mod.parse_timestamp(space.get("measured_at")),
    )


def _running(ctx: _Ctx) -> bool:
    return ctx.progress_class in ("running", "stalled") and ctx.progress is not None


def _running_drive(ctx: _Ctx) -> str | None:
    if not _running(ctx) or ctx.progress is None:
        return None
    drive = ctx.progress.get("drive")
    return drive.get("name") if isinstance(drive, dict) and isinstance(drive.get("name"), str) else None


def _mounted(ctx: _Ctx, names: Sequence[str]) -> set[str]:
    if ctx.live.pools is None or _running(ctx):
        return set()
    return {n for n in names if n in ctx.live.pools}


# One local per figure of the design's drive row.
def _drive_view(  # pylint: disable=too-many-locals
    ctx: _Ctx, doc: Doc, mounted: set[str]
) -> DriveView:
    name = str(doc.get("name", "?"))
    connected = bool(ctx.mod.drive_connected(doc.get("drive_id"), by_id=ctx.sources.by_id))
    last = ctx.mod.parse_timestamp(doc.get("last_backup_at"))
    age = fmt_since(last, ctx.now) if last is not None else None
    run = opt_obj(doc.get("last_run"))
    result = run.get("result") if run is not None else None
    backup = Action(_("Back Up"), "backup", name)
    if _running_drive(ctx) == name and ctx.progress is not None:
        waiting = ctx.progress.get("waiting_for_input") is True
        busy = _("Backing up now") if ctx.progress.get("command") == "backup" else _("In use by zark now")
        line = _("Waiting for your answer") if waiting else busy
        state: DriveState = "waiting" if waiting else "running"
        return DriveView(name, connected, state, line, line, name in mounted, doc)
    if result in ctx.mod.ATTENTION_RESULTS and run is not None:
        ended = ctx.mod.parse_timestamp(run.get("ended_at"))
        words = {
            "incomplete": _("Last run incomplete"),
            "not_verified": _("Last run not verified"),
            "interrupted": _("Last run interrupted"),
        }[str(result)]
        line = f"{words}, {fmt_since(ended, ctx.now)}" if ended is not None else words
        return DriveView(
            name, connected, "attention", line, words, name in mounted, doc, backup if connected else None
        )
    if connected:
        line = _("Connected - last backup {age}").format(age=age) if age else _("Connected - no backup yet")
        return DriveView(name, True, "connected", line, _("Connected"), name in mounted, doc, backup)
    line = _("Not connected - last backup {age}").format(age=age) if age else _("No backup yet")
    return DriveView(name, False, "disconnected", line, _("Not connected"), name in mounted, doc)


def _run_view(ctx: _Ctx) -> RunView | None:
    if not _running(ctx) or ctx.progress is None:
        return None
    p = ctx.progress
    command = str(p.get("command") or "")
    drive = _running_drive(ctx)
    step = obj(p.get("step"))
    transfer = opt_obj(p.get("transfer"))
    updated = ctx.mod.parse_timestamp(p.get("updated_at"))
    stalled = None
    if ctx.progress_class == "stalled" and updated is not None:
        stalled = int((ctx.now - updated).total_seconds())
    return RunView(
        command=command,
        title=run_title(command, drive),
        drive=drive,
        started_at=ctx.mod.parse_timestamp(p.get("started_at")),
        step_index=_int(step.get("index")),
        step_total=_int(step.get("total")),
        label=str(step.get("label") or ""),
        transfer=transfer,
        fraction=ctx.mod.byte_fraction(transfer) if transfer is not None else None,
        eta_s=ctx.mod.eta_seconds(transfer) if transfer is not None else None,
        stalled_s=stalled,
        waiting=p.get("waiting_for_input") is True,
        waiting_for=str(p.get("waiting_for") or ""),
        check=opt_obj(p.get("check")),
        drive_space=_drive_space(p),
        pid=_int(p.get("pid")),
    )


def _drive_space(progress: Doc) -> Doc | None:
    drive = progress.get("drive")
    space = drive.get("space") if isinstance(drive, dict) else None
    return space if isinstance(space, dict) else None


def _notices(status: Doc) -> tuple[NoticeView, ...]:
    out = []
    for n in _dicts(status.get("notices")):
        code = str(n.get("code") or "")
        if code in NOTICES_ELSEWHERE:
            continue
        action = Action(_("Reclaim Space..."), "prune") if code == "origin_residues" else None
        title = _(NOTICE_TITLES[code]) if code in NOTICE_TITLES else _("Notice")
        out.append(NoticeView(code, str(n.get("level") or "info"), title, str(n.get("text") or ""), action))
    return tuple(out)


def _pending(status: Doc) -> tuple[PendingView, ...]:
    out = []
    for n in _dicts(status.get("notices")):
        if n.get("code") == "drive_pending" and isinstance(n.get("subject"), str):
            name = n["subject"]
            out.append(
                PendingView(
                    name,
                    str(n.get("text") or ""),
                    Action(_("Finish Registration..."), "verify", name),
                )
            )
    return tuple(out)


def _writer_dir(registry: str) -> str:
    suffix = "/etc/known_drives.json"
    return registry[: -len(suffix)] if registry.endswith(suffix) else registry


def _foreign_banner(status: Doc, installed: str | None) -> BannerView | None:
    registry = status.get("registry")
    writer = status.get("zark_version")
    inst = upstream_version(installed) if installed else None
    if isinstance(registry, str) and registry != REGISTRY_PATH:
        text = _("The status file was written by zark {writer} from {where}, not the installed {installed}")
        return BannerView(
            text.format(writer=writer or "?", where=_writer_dir(registry), installed=inst or "?")
        )
    if isinstance(writer, str) and inst is not None and writer != inst:
        text = _("The status file was written by zark {writer}, not the installed {installed}")
        return BannerView(text.format(writer=writer, installed=inst))
    return None


# One return per banner, in the design's order of urgency.
def _banner(  # pylint: disable=too-many-return-statements
    ctx: _Ctx, status_class: str, status_error: str, drives: Sequence[DriveView]
) -> BannerView | None:
    # The design's "most urgent first": what hides data, then a run gone
    # wrong, then what blocks updates, then what is old or foreign.
    if status_class == "newer":
        return BannerView(
            _("The status file is from a newer zark than the installed one: update zark to read it")
        )
    if status_class == "unreadable":
        return BannerView(
            _("The status file could not be read ({error})").format(error=status_error),
            Action(_("Refresh"), "refresh"),
        )
    if ctx.progress_class == "unknown":
        return BannerView(_("zark's progress file could not be read"))
    if ctx.progress_class == "orphan" and ctx.progress is not None:
        command = str(ctx.progress.get("command") or "zark")
        drive = ctx.progress.get("drive")
        name = drive.get("name") if isinstance(drive, dict) else None
        what = _("{command} to {drive}").format(command=command, drive=name) if name else command
        return BannerView(
            _("A zark run ended without cleaning up ({what})").format(what=what),
            Action(_("Clean Up..."), "clean"),
        )
    if _running(ctx) and ctx.progress is not None:
        drive = ctx.progress.get("drive")
        if isinstance(drive, dict) and isinstance(drive.get("drive_id"), str):
            if not ctx.mod.drive_connected(drive["drive_id"], by_id=ctx.sources.by_id):
                return BannerView(
                    _("{drive} was disconnected during the run: zark records the result when it ends").format(
                        drive=drive.get("name", "?")
                    )
                )
    for d in drives:
        if d.mounted:
            return BannerView(
                _(
                    "{drive} is mounted for browsing: "
                    "kernel, GRUB and ZFS updates are blocked until it is unmounted"
                ).format(drive=d.name),
                Action(_("Unmount"), "umount", d.name),
            )
    if status_class == "stale" and ctx.status is not None:
        generated = ctx.mod.parse_timestamp(ctx.status.get("generated_at"))
        age = fmt_since(generated, ctx.now) if generated is not None else "?"
        if not ctx.sources.timer_path.exists():
            return BannerView(
                _("Status from {age}: the hourly checks are off").format(age=age),
                Action(_("Turn On..."), "alerts-install"),
            )
        return BannerView(_("Status from {age}").format(age=age), Action(_("Refresh"), "refresh"))
    if ctx.status is not None:
        return _foreign_banner(ctx.status, ctx.live.zark_version)
    return None


RunKey = tuple[int | None, datetime | None]


def with_sent(snapshot: Snapshot, seen: set[RunKey]) -> Snapshot:
    """Mark the run whose data is sent (A1E-3). zark drops ``transfer`` from
    ``progress.json`` once the data is sent; only a reader that saw it can
    tell that from a run that has not started sending, so ``seen`` keeps the
    runs (pid, start) seen with a transfer, as the extension does."""
    run = snapshot.run
    if run is None:
        return snapshot
    key = (run.pid, run.started_at)
    if run.transfer is not None:
        seen.add(key)
        return snapshot
    if key in seen:
        return replace(snapshot, run=replace(run, sent=True))
    return snapshot


def progress_figure(run: RunView) -> tuple[float | None, str]:
    """The bar's fraction and text: bytes only, full once the data is sent,
    nothing (a pulsing bar) before data moves; never the step as a percent."""
    if run.fraction is not None:
        return run.fraction, f"{int(run.fraction * 100)} %"
    if run.sent:
        return 1.0, "100 %"
    return None, ""


def build(  # pylint: disable=too-many-locals
    loaded: Loaded,
    sources: Sources,
    live: Live,
    last_good: Doc | None = None,
) -> tuple[Snapshot, Doc | None]:
    """Read both files and build the snapshot. ``last_good`` is the last
    status document read; it is kept while the file is newer or unreadable
    (the contract's rule), and returned updated."""
    now = sources.now()
    timer = sources.timer_path.exists()
    installed = live.zark_version
    if loaded.problem != "ok" or loaded.module is None:
        page: PageState = "no_zark" if loaded.problem in ("absent", "shadowed") else "too_old"
        return _empty(page, loaded.detail, now, installed, timer), last_good
    mod = loaded.module
    progress_path, status_path = mod.paths(sources.root)
    progress = mod.read_progress(progress_path)
    status = mod.read_status(status_path)

    def alive(doc: Doc) -> bool:
        if sources.alive is not None:
            return sources.alive(doc)
        return bool(mod.process_alive(doc, proc=sources.proc, boot_id_path=sources.boot_id_path))

    pc = mod.classify_progress(progress, now, alive)
    sc = mod.classify_status(status, now)
    indicator = mod.indicator(pc, progress.doc, sc, status.doc)
    if status.state == "ok" and status.doc is not None:
        last_good = status.doc
    doc = status.doc if status.state == "ok" else last_good
    ctx = _Ctx(mod, sources, now, live, doc, progress.doc if progress.state == "ok" else None, pc)
    if doc is None:
        snap = _empty("no_status", "", now, installed, timer)
        banner = _banner(ctx, sc, status.error, ()) if sc in ("newer", "unreadable") else None
        return (
            replace(
                snap,
                banner=banner,
                run=_run_view(ctx),
                indicator=indicator,
                status_class=sc,
                progress_class=pc,
                module=mod,
            ),
            last_good,
        )
    thresholds = obj(doc.get("thresholds"))
    names = [str(d.get("name")) for d in _dicts(doc.get("drives"))]
    mounted = _mounted(ctx, names)
    drives = tuple(_drive_view(ctx, d, mounted) for d in _dicts(doc.get("drives")))
    return (
        Snapshot(
            page="ok",
            detail="",
            indicator=indicator,
            status_class=sc,
            progress_class=pc,
            generated_at=mod.parse_timestamp(doc.get("generated_at")),
            minute=now.replace(second=0, microsecond=0),
            pools=tuple(_pool_view(ctx, p, thresholds) for p in _dicts(doc.get("source_pools"))),
            pools_live=live.pools is not None,
            boot=_boot_view(ctx, doc.get("boot")),
            drives=drives,
            pending=_pending(doc),
            notices=_notices(doc),
            banner=_banner(ctx, sc, status.error, drives),
            run=_run_view(ctx),
            exclusions=live.exclusions,
            datasets=tuple(sorted(live.used)) if live.used is not None else (),
            installed_zark=installed,
            timer_installed=timer,
            writer_version=doc.get("zark_version") if isinstance(doc.get("zark_version"), str) else None,
            status=doc,
            now=now,
            module=mod,
        ),
        last_good,
    )


def _empty(page: PageState, detail: str, now: datetime, installed: str | None, timer: bool) -> Snapshot:
    return Snapshot(
        page=page,
        detail=detail,
        indicator="none",
        status_class="absent",
        progress_class="idle",
        generated_at=None,
        minute=now.replace(second=0, microsecond=0),
        pools=(),
        pools_live=False,
        boot=None,
        drives=(),
        pending=(),
        notices=(),
        banner=None,
        run=None,
        exclusions=None,
        datasets=(),
        installed_zark=installed,
        timer_installed=timer,
        writer_version=None,
        status=None,
        now=now,
    )


def source_pool_names(snapshot: Snapshot) -> list[str]:
    """The source pools named by the status file, for the live commands."""
    if snapshot.status is None:
        return []
    return [str(p.get("name")) for p in _dicts(snapshot.status.get("source_pools")) if p.get("name")]


# --- the drive page ---


@dataclass(frozen=True)
class MonthView:
    """One month of backup points (design 2.2)."""

    key: str
    points: tuple[Doc, ...]
    incomplete: int
    all_whole: bool
    held_alone: int
    inside_window: bool
    frees: int | None
    has_entry: bool


@dataclass(frozen=True)
class SpaceView:
    """The drive's space bar."""

    used: int
    available: int
    reserved: int
    total: int
    margin: int | None
    measured_at: datetime | None
    live: bool


@dataclass(frozen=True)
class DriveDetails:
    """What a drive page shows, from the drive's entry and, while zark has
    the drive imported, ``progress.json``'s ``drive.space``."""

    space: SpaceView | None
    after_free: int | None
    after_reclaim: int | None
    after_points: int | None
    after_snapshots: int | None
    after_floor: bool
    months: tuple[MonthView, ...] | None
    months_add_up: bool
    largest: tuple[tuple[str, int], ...] | None
    other: Doc | None


def _space_view(mod: ModuleType, drive: Doc, live_space: Doc | None) -> SpaceView | None:
    space = live_space if live_space is not None else drive.get("space")
    if not isinstance(space, dict):
        return None
    used = _int(space.get("used_bytes")) or 0
    avail = _int(space.get("available_bytes")) or 0
    return SpaceView(
        used=used,
        available=avail,
        reserved=int(mod.reserved_bytes(space)),
        total=used + avail + int(mod.reserved_bytes(space)),
        margin=mod.drive_margin_bytes({**drive, "space": space}),
        measured_at=mod.parse_timestamp(space.get("measured_at")),
        live=live_space is not None,
    )


def _months(  # pylint: disable=too-many-locals
    mod: ModuleType, drive: Doc, now: datetime
) -> tuple[tuple[MonthView, ...], bool] | None:
    points = drive.get("points")
    if not isinstance(points, list):
        return None
    by_month: dict[str, list[Doc]] = {}
    for p in _dicts(points):
        when = mod.parse_timestamp(p.get("created_at"))
        if when is not None:
            by_month.setdefault(when.strftime("%Y-%m"), []).append(p)
    contents = mod.drive_contents(drive)
    frees = contents.frees_if_older if contents is not None else None
    retention = obj(drive.get("retention"))
    window = _int(retention.get("window_days"))
    edge = now - timedelta(days=window) if window else None
    months = []
    for key in sorted(by_month, reverse=True):
        pts = by_month[key]
        inside = edge is not None and any(
            (t := mod.parse_timestamp(p.get("created_at"))) is not None and t >= edge for p in pts
        )
        months.append(
            MonthView(
                key=key,
                points=tuple(pts),
                incomplete=sum(1 for p in pts if p.get("complete") is False),
                all_whole=all(p.get("whole") is True for p in pts),
                held_alone=sum(_int(p.get("used_bytes")) or 0 for p in pts),
                inside_window=inside,
                frees=frees.get(key) if frees is not None else None,
                has_entry=frees is not None and key in frees,
            )
        )
    return tuple(months), frees is not None


def drive_details(mod: ModuleType, drive: Doc, progress: Doc | None, now: datetime) -> DriveDetails:
    """The drive page's figures (design 2.2)."""
    live_space = None
    if progress is not None and isinstance(progress.get("drive"), dict):
        pd = progress["drive"]
        if pd.get("name") == drive.get("name") and isinstance(pd.get("space"), dict):
            live_space = pd["space"]
    space = _space_view(mod, drive, live_space)
    nxt = opt_obj(drive.get("retention_next"))
    contents = mod.drive_contents(drive)
    months = _months(mod, drive, now)
    datasets = drive.get("datasets")
    largest = None
    if isinstance(datasets, list):
        shares = sorted(
            ((str(d.get("name")), int(mod.own_share(d))) for d in _dicts(datasets)),
            key=lambda x: x[1],
            reverse=True,
        )
        largest = tuple(shares[:5])
    other = drive.get("non_point_snapshots")
    return DriveDetails(
        space=space,
        after_free=contents.available_after_policy_bytes if contents is not None else None,
        after_reclaim=contents.next_reclaim_bytes if contents is not None else None,
        after_points=contents.next_points if contents is not None else None,
        after_snapshots=_int(nxt.get("snapshots")) if nxt is not None else None,
        after_floor=bool(mod.retention_next_is_floor(drive, now)) if nxt is not None else False,
        months=months[0] if months is not None else None,
        months_add_up=months[1] if months is not None else False,
        largest=largest,
        other=other if isinstance(other, dict) else None,
    )


def eject_words(autoeject: object) -> str:
    """``autoeject`` in words (design 2.2)."""
    return _("Ask with a countdown") if autoeject is True else _("Ask")


def size_line(used: int | None, size: int | None, pct: int | None) -> str:
    """``412 GiB used of 1.79 TiB (23 %)``."""
    if used is None or size is None:
        return _("Could not be read")
    pct_text = f" ({pct} %)" if pct is not None else ""
    return _("{used} used of {size}").format(used=fmt_bytes(used), size=fmt_bytes(size)) + pct_text


def mount_dir(pool: str) -> Path:
    """Where ``zark mount`` puts a drive (``commands/mount.py``)."""
    return MOUNT_ROOT / pool
