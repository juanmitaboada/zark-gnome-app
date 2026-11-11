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
"""Live figures from unprivileged commands, as ``docs/STATUS-FILES.md``
("Drives and live figures") allows: ``zpool list``, ``zfs list``, ``zfs
get`` of zark's user properties, and dpkg's version of zark. No GTK here.

Never an import, an export or a change of a pool.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from zark_app.sources import CommandResult, Runner

REPLICATE = "org.zark:replicate"
SNAPSHOT = "org.zark:snapshot"


def zpool_argv() -> list[str]:
    """Every imported pool, so a backup drive mounted for browsing shows."""
    return ["zpool", "list", "-Hp", "-o", "name,size,allocated,free,capacity"]


def zfs_list_argv(pools: Sequence[str]) -> list[str]:
    """Each dataset's ``used`` (its subtree) in the source pools."""
    return ["zfs", "list", "-Hp", "-o", "name,used", "-t", "filesystem,volume", "-r", *pools]


def zfs_get_argv(pools: Sequence[str]) -> list[str]:
    """zark's exclusion properties where they are set locally."""
    return [
        "zfs",
        "get",
        "-Hp",
        "-o",
        "name,property,value,source",
        "-s",
        "local",
        "-t",
        "filesystem,volume",
        "-r",
        f"{REPLICATE},{SNAPSHOT}",
        *pools,
    ]


def dpkg_argv() -> list[str]:
    """The installed zark package's version."""
    return ["dpkg-query", "-W", "-f", "${Version}", "zark"]


@dataclass(frozen=True)
class PoolLive:
    """One line of ``zpool list -Hp``."""

    name: str
    size: int
    allocated: int
    free: int
    capacity: int


@dataclass(frozen=True)
class Exclusion:
    """A dataset with ``org.zark:replicate=no`` or ``org.zark:snapshot=no``
    set locally."""

    dataset: str
    backups: bool
    snapshots: bool
    used: int | None


@dataclass(frozen=True)
class Live:
    """What the commands gave; None where a command failed or did not run."""

    measured_at: datetime | None = None
    pools: dict[str, PoolLive] | None = None
    used: dict[str, int] | None = None
    exclusions: tuple[Exclusion, ...] | None = None
    zark_version: str | None = None


def _int(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def parse_zpool(stdout: str) -> dict[str, PoolLive]:
    """``zpool list -Hp -o name,size,allocated,free,capacity``; lines that do
    not parse are left out (a pool being imported shows ``-``)."""
    pools: dict[str, PoolLive] = {}
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 5:
            continue
        numbers = [_int(f.rstrip("%")) for f in fields[1:]]
        if any(n is None for n in numbers):
            continue
        size, alloc, free, cap = (n or 0 for n in numbers)
        pools[fields[0]] = PoolLive(fields[0], size, alloc, free, cap)
    return pools


def parse_used(stdout: str) -> dict[str, int]:
    """``zfs list -Hp -o name,used``."""
    used: dict[str, int] = {}
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 2 and (n := _int(fields[1])) is not None:
            used[fields[0]] = n
    return used


def parse_exclusions(stdout: str, used: dict[str, int] | None) -> tuple[Exclusion, ...]:
    """``zfs get -Hp -o name,property,value,source -s local``: only ``no``
    excludes, as zark reads it (``commands/exclude.py``)."""
    flags: dict[str, set[str]] = {}
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 4 or fields[3] != "local" or fields[2] != "no":
            continue
        if fields[1] in (REPLICATE, SNAPSHOT):
            flags.setdefault(fields[0], set()).add(fields[1])
    return tuple(
        Exclusion(
            dataset=name,
            backups=REPLICATE in props,
            snapshots=SNAPSHOT in props,
            used=used.get(name) if used is not None else None,
        )
        for name, props in sorted(flags.items())
    )


class Fetcher:  # pylint: disable=too-few-public-methods
    """Runs the four commands and calls ``done`` once with a :class:`Live`.
    With no source pools (no status file) only ``zpool list`` and dpkg run."""

    def __init__(self, runner: Runner, now: Callable[[], datetime]) -> None:
        self._runner = runner
        self._now = now

    def fetch(self, pools: Sequence[str], done: Callable[[Live], None]) -> None:
        """Start the commands for ``pools``."""
        results: dict[str, CommandResult] = {}
        wanted = ["zpool", "dpkg"] + (["used", "get"] if pools else [])
        argvs = {
            "zpool": zpool_argv(),
            "dpkg": dpkg_argv(),
            "used": zfs_list_argv(pools),
            "get": zfs_get_argv(pools),
        }

        def one(key: str) -> Callable[[CommandResult], None]:
            def finished(result: CommandResult) -> None:
                results[key] = result
                if len(results) == len(wanted):
                    done(self._assemble(results))

            return finished

        for key in wanted:
            self._runner.run(argvs[key], one(key))

    def _assemble(self, results: dict[str, CommandResult]) -> Live:
        def ok(key: str) -> str | None:
            r = results.get(key)
            return r.stdout if r is not None and r.status == 0 else None

        zpool, used_text, get_text, dpkg = ok("zpool"), ok("used"), ok("get"), ok("dpkg")
        used = parse_used(used_text) if used_text is not None else None
        return Live(
            measured_at=self._now(),
            pools=parse_zpool(zpool) if zpool is not None else None,
            used=used,
            exclusions=parse_exclusions(get_text, used) if get_text is not None else None,
            zark_version=(dpkg.strip() or None) if dpkg is not None else None,
        )
