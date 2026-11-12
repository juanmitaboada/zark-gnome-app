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
"""The privileged argv: its shape, the policy's argv1, and every check."""

# pylint: disable=redefined-outer-name

import ast
from pathlib import Path

import pytest

from zark_app import commands
from zark_app.commands import CommandError, Context, Retention, build

ROOT = Path(__file__).resolve().parent.parent
BLACK_ID = "usb-WD_Elements_25A3_575834314131-0:0"


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    """black connected, blue not; spare pending; two datasets, one excluded."""
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    disk = tmp_path / "sdz"
    disk.touch()
    (by_id / BLACK_ID).symlink_to(disk)
    (by_id / "usb-New_Disk_0001-0:0").symlink_to(disk)
    (by_id / "usb-New_Disk_0001-0:0-part1").symlink_to(disk)
    (by_id / "wwn-0x5000000000000001").symlink_to(disk)
    return Context(
        drives={"black": {"drive_id": BLACK_ID}, "blue": {"drive_id": "usb-Blue_0002-0:0"}},
        pending=frozenset({"spare"}),
        by_id=by_id,
        datasets=frozenset({"rpool/home", "rpool/scratch"}),
        excluded={"rpool/scratch": frozenset({"backups"})},
    )


GOOD = [
    ("backup", "black", ("backup", "--drive", "black")),
    ("refresh", "", ("status", "--refresh")),
    ("explore", "", ("explore",)),
    ("prepare", "usb-New_Disk_0001-0:0", ("prepare", "/dev/disk/by-id/usb-New_Disk_0001-0:0")),
    ("verify", "spare", ("registry", "verify", "spare")),
    ("alerts-install", "", ("alerts", "install")),
    ("alerts-remove", "", ("alerts", "remove")),
    ("clean", "", ("clean",)),
    ("mount", "black", ("mount",)),
    ("umount", "black", ("umount",)),
    ("prune", "black", ("prune",)),
    ("health", "black", ("health", f"/dev/disk/by-id/{BLACK_ID}")),
    ("fullcheck", "black", ("fullcheck",)),
    ("fix", "black", ("registry", "fix", "black")),
    ("forget", "black", ("registry", "forget", "black")),
    ("purge", "black", ("purge", f"/dev/disk/by-id/{BLACK_ID}")),
    ("exclude-add", "rpool/home\tboth", ("exclude", "add", "rpool/home", "both")),
    ("exclude-remove", "rpool/scratch\tbackups", ("exclude", "remove", "rpool/scratch", "backups")),
    ("exclude-list", "", ("exclude", "list")),
]


@pytest.mark.parametrize(("op", "arg", "words"), GOOD)
def test_argv(ctx: Context, op: str, arg: str, words: tuple[str, ...]) -> None:
    """The argv's shape (Fable's A2 review, section 3)."""
    argv = commands.argv(build(op, arg, ctx))
    assert argv[:3] == ["/usr/bin/pkexec", "--disable-internal-agent", "/usr/share/zark/zark"]
    assert tuple(argv[3:]) == words
    assert argv[3] in commands.POLICY_WORDS
    assert all(not w.startswith("-") or w in commands.OPTIONS for w in argv[4:])


def test_every_op_tested() -> None:
    """Every operation of the builder is in the table above."""
    assert {op for op, _a, _w in GOOD} | {"retention"} == set(commands.OPS)


def test_retention(ctx: Context) -> None:
    """zark's words and limits."""
    cmd = build("retention", "black", ctx, Retention(30, 0, 10))
    assert cmd.words == ("registry", "retention", "black", "window=30", "max_age=off", "margin=10")
    assert build("retention", "black", ctx, Retention(30, 400, 0)).words[-2] == "max_age=400"
    for bad in (Retention(0, 0, 10), Retention(30, 30, 10), Retention(30, 0, 51), Retention(3651, 0, 1)):
        with pytest.raises(CommandError):
            build("retention", "black", ctx, bad)


@pytest.mark.parametrize(
    ("op", "arg"),
    [
        ("backup", "-x"),
        ("backup", "a b"),
        ("backup", "../x"),
        ("backup", "green"),
        ("backup", "blue"),
        ("verify", "black"),
        ("fix", "--all"),
        ("health", "blue"),
        ("purge", "green"),
        ("prepare", BLACK_ID),
        ("prepare", "usb-New_Disk_0001-0:0-part1"),
        ("prepare", "wwn-0x5000000000000001"),
        ("prepare", "usb-Gone_0003-0:0"),
        ("prepare", "../../sda"),
        ("exclude-add", "rpool/other\tboth"),
        ("exclude-add", "rpool/home\teverything"),
        ("exclude-add", "-rpool\tboth"),
        ("exclude-remove", "rpool/home\tbackups"),
        ("mount", "-o"),
        ("nothing", ""),
    ],
)
def test_refused(ctx: Context, op: str, arg: str) -> None:
    """A value the app must not send never becomes an argv."""
    with pytest.raises(CommandError):
        build(op, arg, ctx)


def test_disk_candidates(ctx: Context) -> None:
    """Whole disks, not registered, with a bus prefix."""
    assert commands.disk_candidates(ctx.by_id, ctx.drives) == ["usb-New_Disk_0001-0:0"]


def test_only_commands_builds_pkexec() -> None:
    """No module but commands.py holds pkexec's path, its flag or zark's
    path as a string in code."""
    banned = ("/usr/bin/pkexec", "--disable-internal-agent", "/usr/share/zark/zark")
    for path in (ROOT / "zark_app").rglob("*.py"):
        if path.name == "commands.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not any(b in node.value for b in banned), (path.name, node.value)


def test_policy_words_match_file() -> None:
    """POLICY_WORDS is the policy file's argv1 set."""
    import xml.etree.ElementTree as ET  # pylint: disable=import-outside-toplevel

    root = ET.parse(ROOT / "data" / "com.juanmitaboada.Zark.policy").getroot()
    argv1 = {a.text for a in root.iter("annotate") if a.get("key") == "org.freedesktop.policykit.exec.argv1"}
    assert argv1 == set(commands.POLICY_WORDS)
