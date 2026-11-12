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
"""The only place that builds a privileged argv (A2 plan, section 2).

Every operation is ``pkexec --disable-internal-agent /usr/share/zark/zark
<command> [<args>]``: absolute paths, no shell, the command word at index 3
(pkexec matches the polkit action on ``argv[1]`` of the program it runs,
``com.juanmitaboada.Zark.policy``), and every value checked against the
status file, ``/dev/disk/by-id`` or ``zfs list`` before the spawn. zark
checks everything again. No GTK here.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zark_app.i18n import N_, _
from zark_app.units import fmt_bytes

PKEXEC = "/usr/bin/pkexec"
# Without a session agent pkexec would ask in the terminal; with it, only
# GNOME Shell's dialog asks.
PKEXEC_PREFIX: tuple[str, ...] = (PKEXEC, "--disable-internal-agent")
# The real path: pkexec 127 resolves the program before the lookup, 124
# does not; the policy names this one.
ZARK = "/usr/share/zark/zark"

# The policy's argv1 values, one action each (data/com.juanmitaboada.Zark.policy).
POLICY_WORDS = frozenset(
    {
        "backup",
        "prune",
        "registry",
        "exclude",
        "mount",
        "umount",
        "explore",
        "clean",
        "status",
        "alerts",
        "fullcheck",
        "prepare",
        "purge",
        "health",
    }
)

# Options zark declares for the commands the app runs (lib/cli_spec.py).
OPTIONS = frozenset({"--drive", "--refresh"})

# ZFS pool name characters; a leading letter or digit, never "-".
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
# A /dev/disk/by-id name: no "/", never a leading "-".
DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+@-]{0,254}$")
# A ZFS dataset name.
DATASET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*(/[A-Za-z0-9_.:-]+)*$")
EXCLUDE_WORDS = ("backups", "snapshots", "both")
# zark's limits (lib/registry.py RETENTION_LIMITS).
WINDOW = (1, 3650)
MAX_AGE = (0, 36500)
MARGIN = (0, 50)
# Whole-disk names under /dev/disk/by-id the Prepare picker offers.
DISK_PREFIXES = ("usb-", "ata-", "nvme-", "scsi-")


class CommandError(ValueError):
    """A value the app refuses to send to zark; the message is for people."""


@dataclass(frozen=True)
class Command:
    """One zark command, checked; :func:`argv` makes the privileged list."""

    op: str
    words: tuple[str, ...]
    title: str
    drive: str | None = None

    @property
    def word(self) -> str:
        """The command word, ``argv1`` for pkexec."""
        return self.words[0]


@dataclass(frozen=True)
class Context:
    """What the checks read: the registered drives (name to entry), the
    pending drives, the by-id directory, the datasets of the source pools
    and the exclusions in force."""

    drives: Mapping[str, Mapping[str, Any]]
    pending: frozenset[str] = frozenset()
    by_id: Path = Path("/dev/disk/by-id")
    datasets: frozenset[str] = frozenset()
    excluded: Mapping[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Retention:
    """The Retention dialog's three values; ``max_age`` 0 is no limit."""

    window: int
    max_age: int
    margin: int


TITLES = {
    "backup": N_("Backing Up"),
    "refresh": N_("Refreshing the Status"),
    "explore": N_("Looking for Drives"),
    "prepare": N_("Preparing a Drive"),
    "verify": N_("Finishing a Registration"),
    "alerts-install": N_("Turning On Hourly Checks"),
    "alerts-remove": N_("Turning Off Hourly Checks"),
    "clean": N_("Cleaning Up"),
    "mount": N_("Mounting a Drive"),
    "umount": N_("Unmounting a Drive"),
    "prune": N_("Reclaiming Space"),
    "health": N_("Checking Health"),
    "fullcheck": N_("Verifying a Drive"),
    "retention": N_("Changing Retention"),
    "fix": N_("Repairing an Entry"),
    "forget": N_("Forgetting a Drive"),
    "purge": N_("Erasing a Drive"),
    "exclude-add": N_("Excluding a Dataset"),
    "exclude-remove": N_("Including a Dataset Again"),
    "exclude-list": N_("Listing Exclusions"),
}
OPS = frozenset(TITLES)


def _title(op: str, drive: str | None = None) -> str:
    title = _(TITLES[op])
    return _("{title} to {drive}").format(title=title, drive=drive) if op == "backup" and drive else title


def check_name(name: str) -> str:
    """A drive name as zark's registry and ZFS allow it."""
    if not NAME_RE.fullmatch(name):
        raise CommandError(_("{name!r} is not a drive name").format(name=name))
    return name


def _drive(ctx: Context, name: str) -> Mapping[str, Any]:
    check_name(name)
    entry = ctx.drives.get(name)
    if entry is None:
        raise CommandError(_("{name} is not a registered drive").format(name=name))
    return entry


def _device(ctx: Context, name: str) -> str:
    """``/dev/disk/by-id/<name>``, a link to a block device that exists."""
    if not DEVICE_RE.fullmatch(name):
        raise CommandError(_("{name!r} is not a disk name").format(name=name))
    path = ctx.by_id / name
    if not path.is_symlink() or not path.exists():
        raise CommandError(_("{name} is not connected").format(name=name))
    return str(Path("/dev/disk/by-id") / name)


def _drive_device(ctx: Context, name: str) -> str:
    entry = _drive(ctx, name)
    drive_id = entry.get("drive_id")
    if not isinstance(drive_id, str):
        raise CommandError(_("{name} has no disk name in the status file").format(name=name))
    return _device(ctx, drive_id)


def _int_in(value: int, limits: tuple[int, int], what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not limits[0] <= value <= limits[1]:
        raise CommandError(
            _("{what} must be a whole number from {lo} to {hi}").format(what=what, lo=limits[0], hi=limits[1])
        )
    return value


def retention_words(values: Retention) -> tuple[str, ...]:
    """``window=N max_age=N|off margin=N``, checked as zark checks them."""
    window = _int_in(values.window, WINDOW, _("The window"))
    max_age = _int_in(values.max_age, MAX_AGE, _("The maximum age"))
    margin = _int_in(values.margin, MARGIN, _("The margin"))
    if 0 < max_age <= window:
        raise CommandError(_("The maximum age must be longer than the window, or no limit"))
    return (f"window={window}", f"max_age={max_age if max_age else 'off'}", f"margin={margin}")


def _split(arg: str) -> tuple[str, str]:
    dataset, _sep, word = arg.partition("\t")
    return dataset, word


# One branch per operation: the table of the A2 plan's 2.2.
def build(  # pylint: disable=too-many-return-statements,too-many-branches
    op: str, arg: str, ctx: Context, retention: Retention | None = None
) -> Command:
    """The checked command for operation ``op`` with ``arg``. Raises
    :class:`CommandError` for anything the app must not send."""
    simple = {
        "refresh": ("status", "--refresh"),
        "explore": ("explore",),
        "alerts-install": ("alerts", "install"),
        "alerts-remove": ("alerts", "remove"),
        "clean": ("clean",),
        "exclude-list": ("exclude", "list"),
    }
    if op in simple:
        return Command(op, simple[op], _title(op))
    if op in ("mount", "umount", "prune", "fullcheck"):
        # zark asks the drive and the mode in the terminal; arg names the
        # drive the user clicked, for the title only.
        drive = check_name(arg) if arg else None
        return Command(op, (op,), _title(op), drive)
    if op == "backup":
        entry = _drive(ctx, arg)
        _device(ctx, str(entry.get("drive_id", "")))
        return Command(op, ("backup", "--drive", arg), _title(op, arg), arg)
    if op == "verify":
        check_name(arg)
        if arg not in ctx.pending:
            raise CommandError(_("{name} is not waiting for its registration").format(name=arg))
        return Command(op, ("registry", "verify", arg), _title(op), arg)
    if op in ("fix", "forget"):
        _drive(ctx, arg)
        return Command(op, ("registry", op, arg), _title(op), arg)
    if op == "retention":
        _drive(ctx, arg)
        if retention is None:
            raise CommandError(_("No retention values"))
        return Command(op, ("registry", "retention", arg, *retention_words(retention)), _title(op), arg)
    if op in ("health", "purge"):
        return Command(op, (op, _drive_device(ctx, arg)), _title(op), arg)
    if op == "prepare":
        known = {str(e.get("drive_id")) for e in ctx.drives.values()}
        if arg in known:
            raise CommandError(_("{name} is a registered backup drive").format(name=arg))
        if "-part" in arg or not arg.startswith(DISK_PREFIXES):
            raise CommandError(_("{name} is not a whole disk").format(name=arg))
        return Command(op, ("prepare", _device(ctx, arg)), _title(op))
    if op in ("exclude-add", "exclude-remove"):
        dataset, word = _split(arg)
        if not DATASET_RE.fullmatch(dataset) or word not in EXCLUDE_WORDS:
            raise CommandError(_("{arg!r} is not a dataset and a word").format(arg=arg))
        if op == "exclude-add" and dataset not in ctx.datasets:
            raise CommandError(_("{dataset} is not a dataset of this computer").format(dataset=dataset))
        if op == "exclude-remove" and dataset not in ctx.excluded:
            raise CommandError(_("{dataset} is not excluded").format(dataset=dataset))
        verb = "add" if op == "exclude-add" else "remove"
        return Command(op, ("exclude", verb, dataset, word), _title(op))
    raise CommandError(_("Unknown operation {op!r}").format(op=op))


def argv(command: Command, prefix: Sequence[str] = PKEXEC_PREFIX, zark: str = ZARK) -> list[str]:
    """The list VTE spawns. ``prefix`` and ``zark`` change in tests only."""
    if command.word not in POLICY_WORDS:
        raise CommandError(f"no polkit action for {command.word!r}")
    for word in command.words[1:]:
        if word.startswith("-") and word not in OPTIONS:
            raise CommandError(f"refused argument {word!r}")
    return [*prefix, zark, *command.words]


def disk_candidates(by_id: Path, drives: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Whole disks under ``by_id`` for Prepare: no partitions, no
    registered drive, the bus prefixes of :data:`DISK_PREFIXES`."""
    known = {str(e.get("drive_id")) for e in drives.values()}
    try:
        names = sorted(p.name for p in by_id.iterdir())
    except OSError:
        return []
    return [
        n
        for n in names
        if n.startswith(DISK_PREFIXES) and "-part" not in n and n not in known and DEVICE_RE.fullmatch(n)
    ]


def disk_label(by_id: Path, name: str, sys_block: Path = Path("/sys/class/block")) -> str:
    """``name - 1.82 TiB`` from sysfs; the name alone when sysfs says nothing."""
    try:
        kname = (by_id / name).resolve().name
        sectors = int((sys_block / kname / "size").read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return name
    return f"{name} - {fmt_bytes(sectors * 512)}"
