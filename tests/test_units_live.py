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
"""Units and the live commands' argv and parsers."""

from datetime import UTC, datetime

from tests.harness import FixtureRunner
from zark_app import live, units
from zark_app.live import Fetcher, Live


def test_bytes() -> None:
    """Three significant figures in binary units."""
    assert units.fmt_bytes(0) == "0 B"
    assert units.fmt_bytes(1023) == "1023 B"
    assert units.fmt_bytes(1024) == "1.00 KiB"
    assert units.fmt_bytes(412 * 1024**3) == "412 GiB"
    assert units.fmt_bytes(int(1.79 * 1024**4)) == "1.79 TiB"
    assert units.fmt_bytes(int(21.4 * 1024**3)) == "21.4 GiB"


def test_ages() -> None:
    """Ages in words, singular and plural."""
    assert units.fmt_ago(5) == "just now"
    assert units.fmt_ago(60) == "1 minute ago"
    assert units.fmt_ago(25 * 60) == "25 minutes ago"
    assert units.fmt_ago(3 * 3600) == "3 hours ago"
    assert units.fmt_ago(2 * 86400 + 10) == "2 days ago"
    assert units.fmt_ago(-30) == "just now"


def test_durations() -> None:
    """Durations."""
    assert units.fmt_duration(45) == "45 s"
    assert units.fmt_duration(17 * 60) == "17 min"
    assert units.fmt_duration(2 * 3600 + 5 * 60) == "2 h 05 min"


def test_upstream_version() -> None:
    """dpkg's version without epoch and revision."""
    assert units.upstream_version("2.3.0-1") == "2.3.0"
    assert units.upstream_version("1:2.3.0-1ubuntu1") == "2.3.0"
    assert units.upstream_version("2.3.0") == "2.3.0"


def test_argv_reads_only() -> None:
    """Every command is a read: list, get or dpkg-query, never a change."""
    argvs = [live.zpool_argv(), live.zfs_list_argv(["rpool"]), live.zfs_get_argv(["rpool"]), live.dpkg_argv()]
    for argv in argvs:
        assert argv[0] in ("zpool", "zfs", "dpkg-query")
        if argv[0] in ("zpool", "zfs"):
            assert argv[1] in ("list", "get")
    assert "-s" in argvs[2] and "local" in argvs[2]


def test_parse_zpool() -> None:
    """Lines that do not parse are left out."""
    pools = live.parse_zpool("rpool\t100\t40\t60\t40\nbusy\t-\t-\t-\t-\nbad line\n")
    assert list(pools) == ["rpool"] and pools["rpool"].capacity == 40


def test_parse_exclusions() -> None:
    """Only a local "no" excludes."""
    text = (
        "rpool/a\torg.zark:replicate\tno\tlocal\n"
        "rpool/b\torg.zark:snapshot\tno\tlocal\n"
        "rpool/c\torg.zark:replicate\tyes\tlocal\n"
        "rpool/d\torg.zark:replicate\tno\tinherited from rpool\n"
    )
    got = live.parse_exclusions(text, {"rpool/a": 10})
    assert [(e.dataset, e.backups, e.snapshots, e.used) for e in got] == [
        ("rpool/a", True, False, 10),
        ("rpool/b", False, True, None),
    ]


def test_fetcher_without_pools() -> None:
    """No status file: only zpool list and dpkg run."""
    runner = FixtureRunner({"zpool": {"status": 0, "stdout": ""}, "dpkg": {"status": 0, "stdout": "2.3.0-1"}})
    got: list[Live] = []
    Fetcher(runner, lambda: datetime(2026, 1, 1, tzinfo=UTC)).fetch([], got.append)
    assert len(got) == 1 and got[0].zark_version == "2.3.0-1" and got[0].exclusions is None
    assert [c[0] for c in runner.calls] == ["zpool", "dpkg-query"]


def test_fetcher_failures() -> None:
    """A failing command leaves its part None."""
    runner = FixtureRunner({})
    got: list[Live] = []
    Fetcher(runner, lambda: datetime(2026, 1, 1, tzinfo=UTC)).fetch(["rpool"], got.append)
    assert got[0].pools is None and got[0].used is None and got[0].zark_version is None


def test_point_time() -> None:
    """A1E-5: a point's name holds UTC; shown in local time (TZ=Europe/Madrid
    in the suite); a name not in zark's form has no time."""
    when = units.point_time("zark_2026-11-13_05:15:10Z")
    assert when == datetime(2026, 11, 13, 5, 15, 10, tzinfo=UTC)
    assert units.fmt_date_time_s(when) == "13 Nov 2026, 06:15:10"
    assert units.point_time("zark_2026-11-13_05:15:10") is None
    assert units.point_time("manual-snapshot") is None
    assert units.point_time(None) is None
    assert units.parse_utc("2026-10-22T21:32:42Z") == datetime(2026, 10, 22, 21, 32, 42, tzinfo=UTC)
    assert units.parse_utc("yesterday") is None
