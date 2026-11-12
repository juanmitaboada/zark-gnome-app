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
"""Builds :class:`zark_app.sources.Sources` from a fixture case, for the tests,
the screenshots and ``dev/run``.

Two kinds of case:

- zark's own, in ``fixtures/zark-2.3.0/<case>/`` with its ``expected.json``:
  the clock and the liveness come from it, as zark's fixtures README says;
  no live command answers (the file's figures show, dated).
- the app's, in ``fixtures/app/<case>/`` with a ``case.json``: the clock,
  the liveness, the ``/dev/disk/by-id`` names that exist, whether the hourly
  timer is installed, which zark the app finds (``ok``, ``absent``, ``old``)
  and each live command's answer.

zark's reader comes from a zark checkout named by ``ZARK_SRC`` (CI checks
out zark's tag; ``make`` defaults to ``../zark``).
"""

import json
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zark_app.reader import Loaded, load
from zark_app.sources import CommandResult, Sources

HERE = Path(__file__).resolve().parent
ZARK_CASES = HERE / "fixtures" / "zark-2.3.0"
APP_CASES = HERE / "fixtures" / "app"
OLD_READER = (
    '"""A reader from before the names this app uses."""\n__all__ = ["SCHEMA_VERSION"]\nSCHEMA_VERSION = 1\n'
)


def zark_src() -> Path:
    """The zark checkout whose ``lib/status_reader.py`` the tests import."""
    return Path(os.environ.get("ZARK_SRC", str(HERE.parent.parent / "zark"))).resolve()


def _key(argv: Sequence[str]) -> str:
    if argv[0] == "zpool":
        return "zpool"
    if argv[0] == "dpkg-query":
        return "dpkg"
    return "used" if argv[1] == "list" else "get"


class FixtureRunner:  # pylint: disable=too-few-public-methods
    """Answers the live commands from a case, at once; no command runs."""

    def __init__(self, answers: dict[str, Any] | None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: Sequence[str], done: Callable[[CommandResult], None]) -> None:
        """Answer ``argv`` from the case; a command without an answer fails."""
        args = tuple(argv)
        self.calls.append(args)
        answer = self.answers.get(_key(argv))
        if answer is None:
            done(CommandResult(args, 1, ""))
        else:
            done(CommandResult(args, int(answer["status"]), str(answer["stdout"])))


@dataclass
class Case:
    """A case ready to read."""

    name: str
    sources: Sources
    loaded: Loaded
    runner: FixtureRunner
    expected: dict[str, Any] | None
    keep: Any = None


def _at(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _by_id(tmp: Path, names: Sequence[str]) -> Path:
    by_id = tmp / "by-id"
    by_id.mkdir()
    disk = tmp / "disk"
    disk.touch()
    for name in names:
        # Links, as udev makes them; the commands' checks want a link.
        (by_id / name).symlink_to(disk)
    return by_id


def zark_case(name: str, connected: Sequence[str] = ()) -> Case:
    """One of zark's fixtures."""
    root = ZARK_CASES / name
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    now = _at(expected["now"])
    tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
    extra: dict[str, Any] = {}
    process = expected["progress_process"]
    if process == "alive":
        extra["alive"] = lambda _doc: True
    elif process == "proc":
        extra["proc"] = root / "proc"
        extra["boot_id_path"] = root / "proc" / "sys" / "kernel" / "random" / "boot_id"
    runner = FixtureRunner(None)
    sources = Sources(
        runner=runner,
        root=root,
        by_id=_by_id(Path(tmp.name), connected),
        timer_path=Path(tmp.name) / "zark-status.timer",
        zark_dir=zark_src(),
        now=lambda: now,
        **extra,
    )
    return Case(name, sources, load(sources.zark_dir), runner, expected, keep=tmp)


def app_case(name: str) -> Case:
    """One of the app's fixtures."""
    root = APP_CASES / name
    spec = json.loads((root / "case.json").read_text(encoding="utf-8"))
    now = _at(spec["now"])
    tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
    base = Path(tmp.name)
    timer = base / "zark-status.timer"
    if spec["timer"]:
        timer.touch()
    zark_dir = zark_src()
    if spec["zark"] == "absent":
        zark_dir = base / "no-zark"
    elif spec["zark"] == "old":
        zark_dir = base / "old-zark"
        (zark_dir / "lib").mkdir(parents=True)
        (zark_dir / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (zark_dir / "lib" / "status_reader.py").write_text(OLD_READER, encoding="utf-8")
    runner = FixtureRunner(spec["live"])
    alive: Any = (lambda _doc: True) if spec["alive"] else None
    sources = Sources(
        runner=runner,
        root=root,
        by_id=_by_id(base, spec["by_id"]),
        timer_path=timer,
        zark_dir=zark_dir,
        now=lambda: now,
        alive=alive,
    )
    return Case(name, sources, load(zark_dir), runner, None, keep=tmp)


def zark_case_names() -> list[str]:
    """zark's cases, sorted."""
    return sorted(p.name for p in ZARK_CASES.iterdir() if p.is_dir())


def app_case_names() -> list[str]:
    """The app's cases, sorted."""
    return sorted(p.name for p in APP_CASES.iterdir() if p.is_dir())


def any_case(name: str) -> Case:
    """``app:<name>`` or ``zark:<name>``."""
    kind, _sep, case = name.partition(":")
    return app_case(case) if kind == "app" else zark_case(case)
