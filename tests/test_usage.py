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
"""A source pool's usage (A13), as the extension's lib/usage.js and
lib/view.js compute it. The figures of app:connected were worked out by
hand from its status.json (rpool's 26 datasets, bpool's 3)."""

import copy
from datetime import UTC, datetime
from typing import Any

from tests.harness import app_case, zark_case
from tests.test_model import snap
from zark_app import units, usage
from zark_app.usage import DatasetRow

NOW = datetime(2026, 10, 24, 9, 25, tzinfo=UTC)


def _status() -> tuple[Any, dict[str, Any]]:
    case = app_case("connected")
    mod = case.loaded.module
    assert mod is not None
    doc = mod.read_status(case.sources.root / "var/lib/zark/status.json").doc
    return mod, copy.deepcopy(doc)


def test_rpool() -> None:
    """Parts, legend, snapshots line, both lists and the note."""
    mod, doc = _status()
    view = usage.usage_view(mod, doc["source_pools"][0], NOW)
    assert view is not None
    assert [(p.id, p.size) for p in view.legend] == [
        ("user-data", "600 GiB"),
        ("user-snapshots", "133 GiB"),
        ("system-data", "112 GiB"),
        ("system-snapshots", "8.96 GiB"),
        ("other", "512 MiB"),
        ("metadata", "438 MiB"),
        ("free", "66.6 GiB"),
        ("reserved", "29.0 GiB"),
    ]
    assert [p.label for p in view.legend][:3] == ["User data", "User snapshots", "System"]
    assert [p.id for p in view.segments] == list(usage.SEGMENTS)
    space = doc["source_pools"][0]["space"]
    # The parts add up to the chart's total (STATUS-FILES.md, Space object).
    assert sum(p.bytes for p in view.segments) == mod.chart_total(space)
    assert view.snapshots == "Snapshots hold 142 GiB, 17% of the space in use"
    assert view.by_size[:3] == (
        DatasetRow("USERDATA/", "home_bf193q", "600 GiB", "133 GiB"),
        DatasetRow("ROOT/", "ubuntu_7k2m4p", "44.8 GiB", "4.10 GiB"),
        DatasetRow("ROOT/ubuntu_7k2m4p/", "var/lib/libvirt", "41.5 GiB", "-"),
    )
    assert [r.name for r in view.by_snapshots[:5]] == [
        "home_bf193q",
        "ubuntu_7k2m4p",
        "var/lib",
        "var/cache",
        "var/log",
    ]
    assert len(view.by_size) == 12 and view.dataset_count == 26
    # measured_at 08:58Z, TZ=Europe/Madrid in the suite.
    assert view.note == (
        "Snapshots: what removing all of a dataset's snapshots would free. "
        "12 of 26 datasets; measured today 10:58 by zark."
    )


def test_bpool_empty_parts_and_root() -> None:
    """No user data: those parts leave the legend; Free stays. The pool's
    root dataset is a row of its own name."""
    mod, doc = _status()
    view = usage.usage_view(mod, doc["source_pools"][1], NOW)
    assert view is not None
    assert [p.id for p in view.legend] == [
        "system-data",
        "system-snapshots",
        "other",
        "metadata",
        "free",
        "reserved",
    ]
    assert view.snapshots == "Snapshots hold 61.0 MiB, 22% of the space in use"
    assert view.by_size == (
        DatasetRow("BOOT/", "ubuntu_7k2m4p", "213 MiB", "61.0 MiB"),
        DatasetRow("", "bpool", "96.0 KiB", "-"),
        DatasetRow("", "BOOT", "96.0 KiB", "-"),
    )
    assert view.note.endswith("3 of 3 datasets; measured today 10:58 by zark.")


def test_free_stays_at_zero_and_no_share_is_no_row() -> None:
    """A full pool still lists Free; a dataset that holds nothing of its own
    (a parent of others) is not a row."""
    mod, doc = _status()
    pool = doc["source_pools"][1]
    pool["space"]["available_bytes"] = 0
    for d in pool["datasets"]:
        if d["name"] == "bpool/BOOT":
            d["usedbydataset_bytes"] = 0
    view = usage.usage_view(mod, pool, NOW)
    assert view is not None
    assert ("free", "0 B") in [(p.id, p.size) for p in view.legend]
    assert "BOOT" not in [r.name for r in view.by_size]
    assert view.note.startswith("Snapshots: what removing all") and "2 of 3 datasets" in view.note


def test_not_listed() -> None:
    """No Space object, or no dataset list: no usage (the row says why)."""
    mod, doc = _status()
    pool = doc["source_pools"][0]
    assert usage.usage_view(mod, {**pool, "space": None}, NOW) is None
    assert usage.usage_view(mod, {k: v for k, v in pool.items() if k != "datasets"}, NOW) is None


def test_groups() -> None:
    """The installer's layout decides the group."""
    assert usage.dataset_group("rpool/USERDATA/home_x") == "user"
    assert usage.dataset_group("rpool/ROOT/ubuntu_x/var") == "system"
    assert usage.dataset_group("bpool/BOOT") == "system"
    assert usage.dataset_group("rpool") == "other"
    assert usage.dataset_group("rpool/scratch") == "other"


def test_fmt_when() -> None:
    """Local time (TZ=Europe/Madrid), relative to the local day, as the
    extension's formatWhen."""
    now = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    assert units.fmt_when(datetime(2026, 11, 19, 8, 5, tzinfo=UTC), now) == "today 09:05"
    # 23:30Z on the 18th is 00:30 on the 19th in Madrid: today.
    assert units.fmt_when(datetime(2026, 11, 18, 23, 30, tzinfo=UTC), now) == "today 00:30"
    assert units.fmt_when(datetime(2026, 11, 18, 22, 50, tzinfo=UTC), now) == "yesterday 23:50"
    assert units.fmt_when(datetime(2026, 10, 24, 7, 18, tzinfo=UTC), now) == "24 Oct 09:18"


def test_snapshot_carries_usage() -> None:
    """Source pools expand with their usage, live figures or not; /boot does not."""
    s = snap(app_case("connected"))
    assert [(p.name, p.source, p.usage is not None) for p in s.pools] == [
        ("rpool", True, True),
        ("bpool", True, True),
    ]
    boot = snap(zark_case("boot-ext4"), live=False)
    assert boot.boot is not None and not boot.boot.source and boot.boot.usage is None
