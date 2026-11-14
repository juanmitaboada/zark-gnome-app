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
"""Which disks the system is using, for the Prepare picker (A2E-9).

The same rule as zark's ``lib/identity.py`` ``protected_disks``, which
``prepare`` applies before it writes: a disk is in use when it holds a vdev
of an imported pool, a mounted filesystem or active swap, each device taken
down to its whole disks (a partition, a LUKS or other dm device, an md
array). Every read is unprivileged; zark checks again anyway. No GTK here.
"""

import os
import re
from collections.abc import Callable, Iterable, Sequence

from zark_app.sources import CommandResult, Runner

Resolve = Callable[[str], str]


def zpool_vdevs_argv() -> list[str]:
    """Every imported pool with its vdevs, as full paths."""
    return ["zpool", "list", "-vHP"]


def findmnt_argv() -> list[str]:
    """Every mounted filesystem's source."""
    return ["findmnt", "-rn", "-o", "SOURCE,TARGET"]


def swapon_argv() -> list[str]:
    """Active swap."""
    return ["swapon", "--show=NAME", "--noheadings", "--raw"]


def lsblk_argv() -> list[str]:
    """Every block device with its type and parent, by kernel name."""
    return ["lsblk", "-nrpo", "KNAME,TYPE,PKNAME"]


def pool_devices(stdout: str) -> set[str]:
    """The vdev paths of ``zpool list -vHP`` (zark reads the same lines)."""
    found = set()
    for line in stdout.splitlines():
        fields = line.strip().split()
        if fields and fields[0].startswith("/dev/"):
            found.add(fields[0])
    return found


def mount_devices(stdout: str) -> set[str]:
    """The ``/dev`` sources of ``findmnt -rn -o SOURCE,TARGET``, without a
    bind mount's ``[/path]``."""
    found = set()
    for line in stdout.splitlines():
        fields = line.split()
        if fields and fields[0].startswith("/dev/"):
            found.add(re.sub(r"\[.*\]$", "", fields[0]))
    return found


def swap_devices(stdout: str) -> set[str]:
    """The ``/dev`` lines of ``swapon --show``."""
    return {line.strip() for line in stdout.splitlines() if line.strip().startswith("/dev/")}


def whole_disks(devices: Iterable[str], lsblk: str, resolve: Resolve = os.path.realpath) -> set[str]:
    """The whole disks beneath ``devices``, from ``lsblk -nrpo
    KNAME,TYPE,PKNAME`` (a device under several parents is listed once per
    parent)."""
    kind: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    for line in lsblk.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        kind[fields[0]] = fields[1]
        if len(fields) >= 3:
            parents.setdefault(fields[0], set()).add(fields[2])
    disks: set[str] = set()
    for device in devices:
        todo, seen = [resolve(device)], set()
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            if kind.get(name) == "disk":
                disks.add(name)
            todo.extend(parents.get(name, ()))
    return disks


def in_use(answers: dict[str, str], resolve: Resolve = os.path.realpath) -> set[str]:
    """The disks in use, from the four commands' outputs."""
    devices = (
        pool_devices(answers["zpool"]) | mount_devices(answers["findmnt"]) | swap_devices(answers["swapon"])
    )
    return whole_disks(devices, answers["lsblk"], resolve)


def check(
    runner: Runner, done: Callable[[set[str] | None], None], resolve: Resolve = os.path.realpath
) -> None:
    """Run the four reads and call ``done`` with the disks in use, or None
    when any read failed."""
    argvs = {
        "zpool": zpool_vdevs_argv(),
        "findmnt": findmnt_argv(),
        "swapon": swapon_argv(),
        "lsblk": lsblk_argv(),
    }
    results: dict[str, CommandResult] = {}

    def one(key: str) -> Callable[[CommandResult], None]:
        def finished(result: CommandResult) -> None:
            results[key] = result
            if len(results) < len(argvs):
                return
            if any(r.status != 0 for r in results.values()):
                done(None)
                return
            done(in_use({k: r.stdout for k, r in results.items()}, resolve))

        return finished

    for key, argv in argvs.items():
        runner.run(argv, one(key))


def free(
    by_id: os.PathLike[str] | str, names: Sequence[str], used: set[str], resolve: Resolve = os.path.realpath
) -> list[str]:
    """The by-id ``names`` whose disk is not in ``used``."""
    return [n for n in names if resolve(os.path.join(by_id, n)) not in used]
