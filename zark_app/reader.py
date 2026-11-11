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
"""zark's reference reader of the status files, imported from the installed
zark (``docs/STATUS-FILES.md``, "Reference reader"), never copied.

zark's package is named ``lib``, a generic name: after the import the module
must be the file under the zark directory, and it must carry every name this
app uses.
"""

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

ZARK_DIR = Path("/usr/share/zark")
MODULE = "lib.status_reader"

# The reader's names this app calls; all in zark 2.3.0's __all__.
NEEDED = (
    "ATTENTION_RESULTS",
    "SCHEMA_VERSION",
    "age_days",
    "capacity_level",
    "classify_progress",
    "classify_status",
    "drive_connected",
    "drive_contents",
    "drive_margin_bytes",
    "eta_seconds",
    "byte_fraction",
    "indicator",
    "own_share",
    "parse_timestamp",
    "paths",
    "process_alive",
    "read_progress",
    "read_status",
    "reserved_bytes",
    "retention_next_is_floor",
)

Problem = Literal["ok", "absent", "too_old", "shadowed"]


@dataclass(frozen=True)
class Loaded:
    """The outcome of loading the reader: ``module`` only when ``problem``
    is ``ok``."""

    problem: Problem
    module: ModuleType | None = None
    detail: str = ""


def reader_path(zark_dir: Path = ZARK_DIR) -> Path:
    """Where the reader lives in a zark tree."""
    return zark_dir / "lib" / "status_reader.py"


def _forget_other(zark_dir: Path) -> None:
    # A test may load several zark trees in one process; a module from another
    # tree must not answer this one's import.
    root = zark_dir.resolve()
    for name in (MODULE, "lib"):
        module = sys.modules.get(name)
        origin = getattr(module, "__file__", None) if module is not None else None
        if module is not None and (origin is None or root not in Path(origin).resolve().parents):
            del sys.modules[name]


def load(zark_dir: Path = ZARK_DIR) -> Loaded:
    """Import ``lib.status_reader`` from ``zark_dir`` and check it."""
    path = reader_path(zark_dir)
    if not path.is_file():
        return Loaded("absent", detail=str(path))
    entry = str(zark_dir)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    _forget_other(zark_dir)
    try:
        module = importlib.import_module(MODULE)
    # Any failure of a foreign module's import is the same outcome for the app.
    except Exception as e:  # pylint: disable=broad-exception-caught
        return Loaded("too_old", detail=f"cannot import {MODULE}: {e}")
    origin = getattr(module, "__file__", None)
    if origin is None or Path(origin).resolve() != path.resolve():
        return Loaded("shadowed", detail=f"{MODULE} came from {origin}")
    names = set(getattr(module, "__all__", ()))
    missing = [n for n in NEEDED if n not in names]
    if missing:
        return Loaded("too_old", detail="missing: " + ", ".join(missing))
    if getattr(module, "SCHEMA_VERSION", None) != 1:
        return Loaded("too_old", detail=f"schema {getattr(module, 'SCHEMA_VERSION', None)}")
    return Loaded("ok", module=module)
