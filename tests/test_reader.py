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
"""zark's reader, imported as the app imports it, against zark's fixtures
and their ``expected.json`` (zark's README: the tests of every reader)."""

from pathlib import Path

import pytest

from tests.harness import zark_case, zark_case_names, zark_src
from zark_app import reader


@pytest.mark.parametrize("name", zark_case_names())
def test_case_classes(name: str) -> None:
    """Each case's progress class, status class and indicator."""
    case = zark_case(name)
    mod = case.loaded.module
    assert case.loaded.problem == "ok", case.loaded.detail
    assert mod is not None and case.expected is not None
    now = case.sources.now()
    progress_path, status_path = mod.paths(case.sources.root)
    progress, status = mod.read_progress(progress_path), mod.read_status(status_path)

    def alive(doc: object) -> bool:
        if case.sources.alive is not None:
            return case.sources.alive(doc)  # type: ignore[arg-type]
        return bool(mod.process_alive(doc, proc=case.sources.proc, boot_id_path=case.sources.boot_id_path))

    pc = mod.classify_progress(progress, now, alive)
    sc = mod.classify_status(status, now)
    assert pc == case.expected["progress"]
    assert sc == case.expected["status"]
    assert mod.indicator(pc, progress.doc, sc, status.doc) == case.expected["indicator"]


@pytest.mark.parametrize("name", [n for n in zark_case_names() if "drive-contents" in n])
def test_drive_contents(name: str) -> None:
    """The drive contents cases: what a drive's tab shows."""
    case = zark_case(name)
    mod = case.loaded.module
    assert mod is not None and case.expected is not None
    status = mod.read_status(mod.paths(case.sources.root)[1])
    for drive in status.doc["drives"]:
        exp = case.expected["drives"][drive["name"]]
        assert mod.drive_margin_bytes(drive) == exp["margin_bytes"]
        got = mod.drive_contents(drive)
        if exp["contents"] is None:
            assert got is None
            continue
        for key, value in exp["contents"].items():
            assert getattr(got, key) == value, (drive["name"], key)


def test_load_ok() -> None:
    """The reader of the zark checkout loads and carries every needed name."""
    loaded = reader.load(zark_src())
    assert loaded.problem == "ok", loaded.detail
    assert loaded.module is not None
    assert Path(str(loaded.module.__file__)).resolve() == reader.reader_path(zark_src()).resolve()


def test_load_absent(tmp_path: Path) -> None:
    """No zark tree: absent, nothing imported."""
    loaded = reader.load(tmp_path / "nothing")
    assert loaded.problem == "absent" and loaded.module is None


def test_load_too_old(tmp_path: Path) -> None:
    """A reader without the names the app uses."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "lib" / "status_reader.py").write_text(
        '__all__ = ["SCHEMA_VERSION"]\nSCHEMA_VERSION = 1\n', encoding="utf-8"
    )
    loaded = reader.load(tmp_path)
    assert loaded.problem == "too_old"
    assert "read_status" in loaded.detail
    assert reader.load(zark_src()).problem == "ok"


def test_load_broken(tmp_path: Path) -> None:
    """A reader that does not import is too old, not a crash."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "lib" / "status_reader.py").write_text("raise RuntimeError('no')\n", encoding="utf-8")
    assert reader.load(tmp_path).problem == "too_old"
    assert reader.load(zark_src()).problem == "ok"
