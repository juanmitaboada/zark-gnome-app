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
"""A source pool's disk usage, from ``status.json``'s Space object and its
``datasets`` list: the parts of the space, the largest datasets and those
with the most in snapshots. The same figures and words as zark's GNOME Shell
extension (``lib/usage.js`` and ``lib/view.js``: ``poolUsage``,
``usageView``, ``datasetRow``). No GTK here."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType
from typing import Any

from zark_app.i18n import N_, NC_, _, ngettext, pgettext
from zark_app.units import fmt_bytes, fmt_when

# The parts of a pool's space, in drawing order.
SEGMENTS = (
    "user-data",
    "user-snapshots",
    "system-data",
    "system-snapshots",
    "other",
    "metadata",
    "free",
    "reserved",
)

# The legend: what each part of the space holds (the extension's words).
LABELS: dict[str, str | tuple[str, str]] = {
    "user-data": N_("User data"),
    "user-snapshots": N_("User snapshots"),
    # TRANSLATORS: the system's data (the root and boot datasets), a part of a pool's usage bar
    "system-data": N_("System"),
    "system-snapshots": N_("System snapshots"),
    "other": N_("Other datasets"),
    "metadata": N_("Pool metadata"),
    # TRANSLATORS: free space, a part of a usage bar
    "free": NC_("free space", "Free"),
    # TRANSLATORS: ZFS is a name; space the file system keeps for itself
    "reserved": N_("Reserved by ZFS"),
}

# How many datasets each list shows, as the extension.
LISTED = 12


@dataclass(frozen=True)
class Part:
    """A part of the space: its segment, its bytes, its words and size."""

    id: str
    bytes: int
    label: str
    size: str


@dataclass(frozen=True)
class DatasetRow:
    """A row of the datasets table: the shared part of the name (shown
    dimmed), the rest, its data and its snapshots ("-" for none)."""

    prefix: str
    name: str
    data: str
    snapshots: str


@dataclass(frozen=True)
class UsageView:
    """What a source pool's expanded row shows."""

    segments: tuple[Part, ...]
    legend: tuple[Part, ...]
    snapshots: str
    by_size: tuple[DatasetRow, ...]
    by_snapshots: tuple[DatasetRow, ...]
    dataset_count: int
    note: str


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def dataset_group(name: str) -> str:
    """``user``, ``system`` or ``other`` by the installer's layout:
    ``<pool>/USERDATA/...`` holds user data, ``<pool>/ROOT/...`` and
    ``<pool>/BOOT/...`` the system."""
    parts = name.split("/")
    top = parts[1] if len(parts) > 1 else None
    if top == "USERDATA":
        return "user"
    if top in ("ROOT", "BOOT"):
        return "system"
    return "other"


def _data(dataset: Mapping[str, Any]) -> int:
    return _int(dataset.get("usedbydataset_bytes")) + _int(dataset.get("usedbyrefreservation_bytes"))


def _size_or_dash(n: int) -> str:
    return fmt_bytes(n) if n > 0 else "-"


def dataset_row(dataset: Mapping[str, Any]) -> DatasetRow:
    """The name without its pool; its first two parts are the shared prefix
    when it has three or more (the top dataset and the boot environment or
    home), as the extension's ``datasetRow``."""
    full = str(dataset.get("name", "?"))
    parts = full.split("/")[1:] or [full]
    shared = 2 if len(parts) >= 3 else len(parts) - 1
    return DatasetRow(
        prefix="/".join(parts[:shared]) + "/" if shared > 0 else "",
        name="/".join(parts[shared:]),
        data=_size_or_dash(_data(dataset)),
        snapshots=_size_or_dash(_int(dataset.get("usedbysnapshots_bytes"))),
    )


def _label(segment: str) -> str:
    words = LABELS[segment]
    return pgettext(*words) if isinstance(words, tuple) else _(words)


# One local per figure of the extension's poolUsage.
def usage_view(  # pylint: disable=too-many-locals
    mod: ModuleType, pool: Mapping[str, Any], now: datetime
) -> UsageView | None:
    """A source pool entry's usage, or None without a Space object or a
    dataset list (zark could not read the pool or list its datasets)."""
    space = pool.get("space")
    datasets = pool.get("datasets")
    if not isinstance(space, dict) or not isinstance(datasets, list):
        return None
    entries = [d for d in datasets if isinstance(d, dict)]
    sums = {"user": [0, 0], "system": [0, 0], "other": [0, 0]}
    snapshots = 0
    shares = 0
    for d in entries:
        shares += int(mod.own_share(d))
        group = sums[dataset_group(str(d.get("name", "")))]
        group[0] += _data(d)
        group[1] += _int(d.get("usedbysnapshots_bytes"))
        snapshots += _int(d.get("usedbysnapshots_bytes"))
    used = _int(space.get("used_bytes"))
    figures = {
        "user-data": sums["user"][0],
        "user-snapshots": sums["user"][1],
        "system-data": sums["system"][0],
        "system-snapshots": sums["system"][1],
        "other": sum(sums["other"]),
        # The shares sum to a little less than used: the rest is what ZFS
        # keeps under the root that zfs list never shows (STATUS-FILES.md,
        # "Source pool entry").
        "metadata": max(0, used - shares),
        "free": _int(space.get("available_bytes")),
        "reserved": int(mod.reserved_bytes(space)),
    }
    parts = tuple(Part(s, figures[s], _label(s), fmt_bytes(figures[s])) for s in SEGMENTS)
    # Empty parts say nothing (bpool has no user data); Free stays, even at zero.
    legend = tuple(p for p in parts if p.bytes > 0 or p.id == "free")
    # Math.round(snapshots / used * 100), as the extension: divided first, so
    # an exact half rounds as it does there (A13R-5).
    percent = math.floor(snapshots / used * 100 + 0.5) if used > 0 else 0
    by_size = sorted(entries, key=lambda d: int(mod.own_share(d)), reverse=True)[:LISTED]
    by_snapshots = sorted(entries, key=lambda d: _int(d.get("usedbysnapshots_bytes")), reverse=True)[:LISTED]
    size_rows = tuple(dataset_row(d) for d in by_size if int(mod.own_share(d)) > 0)
    measured = mod.parse_timestamp(space.get("measured_at"))
    note = ngettext(
        "Snapshots: what removing all of a dataset's snapshots would free. "
        "{shown} of {n} dataset; measured {when} by zark.",
        "Snapshots: what removing all of a dataset's snapshots would free. "
        "{shown} of {n} datasets; measured {when} by zark.",
        len(entries),
    ).format(shown=len(size_rows), n=len(entries), when=fmt_when(measured, now) if measured else "?")
    return UsageView(
        segments=parts,
        legend=legend,
        snapshots=_(
            # "% o" is no printf directive: without this, xgettext flags the msgid
            # python-format and msgfmt -c wants a "%" in every translation (BC22-65).
            # xgettext: no-python-format
            "Snapshots hold {size}, {percent}% of the space in use"
        ).format(size=fmt_bytes(snapshots), percent=percent),
        by_size=size_rows,
        by_snapshots=tuple(dataset_row(d) for d in by_snapshots if int(mod.own_share(d)) > 0),
        dataset_count=len(entries),
        note=note,
    )
