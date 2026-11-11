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
"""Rules the code must keep: the reader contract (no write, no lock, no
pool change), the fixtures copied unchanged, the repository's text rules."""

import hashlib
import re
from pathlib import Path

import pytest

from tests.harness import ZARK_CASES, zark_src

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "zark_app"

FORBIDDEN = [
    (r"\bimport\b.*\bfcntl\b|\bflock\b|\blockf\b", "takes a lock"),
    (r"zark\.lock|status\.lock", "names zark's locks"),
    (r"[\"'](import|export|destroy|set|create|rollback|offline|online|clear)[\"']", "a zfs/zpool change"),
    (r"pkexec|polkit", "privilege (A2's)"),
    (r"open\([^)]*[\"'][wax]\+?b?[\"']", "writes a file"),
    (r"write_text|write_bytes|os\.replace|os\.rename|shutil\.", "writes a file"),
]


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*.py")), ids=lambda p: p.name)
def test_reader_contract(path: Path) -> None:
    """``docs/STATUS-FILES.md``, "What a reader must not do"."""
    text = path.read_text(encoding="utf-8")
    for pattern, what in FORBIDDEN:
        assert not re.search(pattern, text), f"{path.name}: {what}"


def _manifest(root: Path) -> dict[str, str]:
    out = {}
    for line in (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        out[name.removeprefix("./")] = digest
    return out


def test_fixture_manifest() -> None:
    """The copy of zark's fixtures matches its manifest, file for file."""
    manifest = _manifest(ZARK_CASES)
    files = {
        str(p.relative_to(ZARK_CASES)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ZARK_CASES.rglob("*")
        if p.is_file() and p.name != "MANIFEST.sha256"
    }
    assert files == manifest


def test_fixtures_equal_zark() -> None:
    """The copy equals zark's own fixtures in the checkout the tests use."""
    theirs = zark_src() / "tests" / "fixtures" / "status"
    if not theirs.is_dir():
        pytest.skip(f"no zark fixtures at {theirs}")
    for name, digest in _manifest(ZARK_CASES).items():
        assert hashlib.sha256((theirs / name).read_bytes()).hexdigest() == digest, name
    extra = {str(p.relative_to(theirs)) for p in theirs.rglob("*") if p.is_file()} - set(
        _manifest(ZARK_CASES)
    )
    assert not extra, f"zark has fixtures the copy lacks: {sorted(extra)}"


TEXT_SUFFIXES = {".py", ".md", ".json", ".xml", ".desktop", ".svg", ".yml", ".toml", ".ini", ".in", ""}
BAD_CHARS = re.compile(
    "["
    + "".join(
        chr(c)
        for c in (
            0x2013,
            0x2014,
            0x2026,
            0x2018,
            0x2019,
            0x201C,
            0x201D,
            0x00A0,
            0x202F,
            0x00AD,
            0x200B,
            0x200C,
            0x200D,
            0xFEFF,
        )
    )
    + "]"
)


def _tracked_text() -> list[Path]:
    skip = {".git", "build", ".tox", ".mypy_cache", ".ruff_cache", "__pycache__", ".pytest_cache"}
    out = []
    for p in ROOT.rglob("*"):
        if any(part in skip for part in p.relative_to(ROOT).parts) or not p.is_file():
            continue
        if "fixtures" in p.parts:
            continue
        if p.suffix in TEXT_SUFFIXES or p.parent.name == "debian":
            out.append(p)
    return out


def test_text_rules() -> None:
    """ASCII punctuation only: no dashes but '-', no ellipsis character, no
    curly quotes, no invisible or hard spaces."""
    bad = [
        str(p.relative_to(ROOT)) for p in _tracked_text() if BAD_CHARS.search(p.read_text(encoding="utf-8"))
    ]
    assert not bad


def test_potfiles_list_every_translated_module() -> None:
    """Every module that imports the translation functions is in
    po/POTFILES.in, so make pot extracts its strings."""
    listed = {
        line.strip()
        for line in (ROOT / "po" / "POTFILES.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    users = {
        str(p.relative_to(ROOT))
        for p in PACKAGE.rglob("*.py")
        if "from zark_app.i18n import" in p.read_text(encoding="utf-8")
    }
    assert users == listed
