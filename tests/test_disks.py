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
"""The disks the system uses, for the Prepare picker (A2E-9)."""

from typing import Any

import pytest

from tests.harness import FixtureRunner
from zark_app import disks

# eli-like: rpool on sda4, /boot and the ESP on sda2 and sda1, swap on a
# dm-crypt over sda3, a stick on sdb, and sdc with a bind mount on a partition.
BY_ID = {
    "/dev/disk/by-id/ata-SYSTEM_DISK-part4": "/dev/sda4",
    "/by-id/ata-SYSTEM_DISK": "/dev/sda",
    "/by-id/usb-Stick_0001-0:0": "/dev/sdb",
    "/by-id/usb-Other_0002-0:0": "/dev/sdc",
}
ZPOOL = (
    "rpool\t476G\t9G\t467G\t-\t-\t1%\t1%\t1.00x\tONLINE\t-\n"
    "\t/dev/disk/by-id/ata-SYSTEM_DISK-part4\t476G\t9G\t467G\t-\t-\t1%\t1%\t-\tONLINE\n"
)
FINDMNT = "/dev/sda2 /boot\n/dev/sda1 /boot/efi\n/dev/sdc1[/sub] /mnt/x\ntmpfs /run\n"
SWAPON = "/dev/dm-0\n"
LSBLK = (
    "/dev/sda disk \n/dev/sda1 part /dev/sda\n/dev/sda2 part /dev/sda\n/dev/sda3 part /dev/sda\n"
    "/dev/sda4 part /dev/sda\n/dev/dm-0 crypt /dev/sda3\n/dev/sdb disk \n/dev/sdc disk \n"
    "/dev/sdc1 part /dev/sdc\n"
)


def resolve(path: str) -> str:
    """The fixture's symlinks."""
    return BY_ID.get(path, path)


def test_parsers() -> None:
    """Each read's ``/dev`` sources, as zark reads them."""
    assert disks.pool_devices(ZPOOL) == {"/dev/disk/by-id/ata-SYSTEM_DISK-part4"}
    assert disks.mount_devices(FINDMNT) == {"/dev/sda2", "/dev/sda1", "/dev/sdc1"}
    assert disks.swap_devices(SWAPON) == {"/dev/dm-0"}
    assert disks.whole_disks({"/dev/dm-0"}, LSBLK, resolve) == {"/dev/sda"}


def test_in_use_and_free() -> None:
    """The system disk (pool, mounts, swap over dm-crypt) and the disk with a
    mounted partition are in use; the stick is free."""
    used = disks.in_use({"zpool": ZPOOL, "findmnt": FINDMNT, "swapon": SWAPON, "lsblk": LSBLK}, resolve)
    assert used == {"/dev/sda", "/dev/sdc"}
    names = ["ata-SYSTEM_DISK", "usb-Stick_0001-0:0", "usb-Other_0002-0:0"]
    assert disks.free("/by-id", names, used, resolve) == ["usb-Stick_0001-0:0"]


def _answers(**over: Any) -> dict[str, Any]:
    base = {
        "zpool-vdevs": {"status": 0, "stdout": ZPOOL},
        "findmnt": {"status": 0, "stdout": FINDMNT},
        "swapon": {"status": 0, "stdout": SWAPON},
        "lsblk": {"status": 0, "stdout": LSBLK},
    }
    base.update(over)
    return base


def test_check_runs_the_four_reads() -> None:
    """The four commands, unprivileged, and their answer."""
    runner = FixtureRunner(_answers())
    got: list[set[str] | None] = []
    disks.check(runner, got.append, resolve)
    assert got == [{"/dev/sda", "/dev/sdc"}]
    assert sorted(c[0] for c in runner.calls) == ["findmnt", "lsblk", "swapon", "zpool"]


@pytest.mark.parametrize("failing", ["zpool-vdevs", "findmnt", "swapon", "lsblk"])
def test_a_failed_read_says_unknown(failing: str) -> None:
    """Any read that fails: None, so the picker removes nothing and says so."""
    runner = FixtureRunner(_answers(**{failing: {"status": 1, "stdout": ""}}))
    got: list[set[str] | None] = []
    disks.check(runner, got.append, resolve)
    assert got == [None]
