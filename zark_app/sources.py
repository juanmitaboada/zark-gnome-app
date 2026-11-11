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
"""Where the app reads from: real paths, or a fixture's. No GTK here."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from zark_app.reader import ZARK_DIR

TIMER_PATH = Path("/etc/systemd/system/zark-status.timer")
REGISTRY_PATH = "/etc/zark/known_drives.json"
MOUNT_ROOT = Path("/mnt/zark")


@dataclass(frozen=True)
class CommandResult:
    """One command's outcome: ``status`` None when it could not start or ran
    past its time limit."""

    argv: tuple[str, ...]
    status: int | None
    stdout: str = ""


class Runner(Protocol):  # pylint: disable=too-few-public-methods
    """Runs a command without a shell and calls ``done`` on the main loop."""

    def run(self, argv: Sequence[str], done: Callable[[CommandResult], None]) -> None:
        """Run ``argv``."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Sources:  # pylint: disable=too-many-instance-attributes
    """Every input of the app. ``alive`` overrides the reader's liveness
    check (fixtures name processes that do not exist)."""

    runner: Runner
    root: Path = Path("/")
    by_id: Path = Path("/dev/disk/by-id")
    proc: Path = Path("/proc")
    boot_id_path: Path = Path("/proc/sys/kernel/random/boot_id")
    timer_path: Path = TIMER_PATH
    zark_dir: Path = ZARK_DIR
    now: Callable[[], datetime] = _now
    alive: Callable[[Mapping[str, Any]], bool] | None = field(default=None)
