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
"""Reading the catalogues for the checks: a small parser of the PO format
as xgettext and msgmerge write it, the risk-word check and a
pseudo-translation for the tests.

    python3 -I tests/potools.py risk    # make po-risk
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PO = ROOT / "po"
POT = PO / "zark-gnome-app.pot"
RISK_WORDS = PO / "RISK-WORDS"
RISK_REVIEWED = PO / "RISK-REVIEWED"

# Python's str.format fields and polkit's $(name): both must reach every
# translation unchanged.
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}|\$\([A-Za-z_]+\)")

_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass
class Entry:
    """One message of a catalogue."""

    msgid: str = ""
    msgid_plural: str | None = None
    msgstr: dict[int, str] = field(default_factory=dict)
    locations: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _unquote(text: str) -> str:
    body = text.strip()
    if not (body.startswith('"') and body.endswith('"')):
        raise ValueError(f"not a PO string: {text!r}")
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body[1:-1])


def quote(text: str) -> str:
    """``text`` as one PO string."""
    return (
        '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'
    )


def parse(path: Path) -> list[Entry]:
    """The entries of a PO or POT file, the header (empty msgid) first."""
    entries: list[Entry] = []
    current = Entry()
    key: tuple[str, int] | None = None
    started = False

    def close() -> None:
        nonlocal current, started, key
        if started:
            entries.append(current)
        current, started, key = Entry(), False, None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            close()
        elif line.startswith("#:"):
            current.locations += line[2:].split()
        elif line.startswith("#."):
            current.comments.append(line[2:].strip())
        elif line.startswith("#,"):
            current.flags += [f.strip() for f in line[2:].split(",")]
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            if key is None:
                raise ValueError(f"{path}: a string continues nothing: {raw!r}")
            _append(current, key, _unquote(line))
        else:
            word, _sep, rest = line.partition(" ")
            key = _keyword(word)
            if key is None:
                raise ValueError(f"{path}: unknown line {raw!r}")
            started = True
            _append(current, key, _unquote(rest))
    close()
    return entries


def _keyword(word: str) -> tuple[str, int] | None:
    if word in ("msgid", "msgid_plural", "msgstr"):
        return (word, 0)
    match = re.fullmatch(r"msgstr\[(\d+)\]", word)
    return ("msgstr", int(match.group(1))) if match else None


def _append(entry: Entry, key: tuple[str, int], text: str) -> None:
    name, index = key
    if name == "msgid":
        entry.msgid += text
    elif name == "msgid_plural":
        entry.msgid_plural = (entry.msgid_plural or "") + text
    else:
        entry.msgstr[index] = entry.msgstr.get(index, "") + text


def placeholders(text: str) -> list[str]:
    """The placeholders of ``text``, sorted, repeats kept."""
    return sorted(PLACEHOLDER.findall(text))


def risk_stems(path: Path = RISK_WORDS) -> list[str]:
    """The stems of po/RISK-WORDS, one per line, # starting a comment."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stem = line.split("#", 1)[0].strip()
        if stem:
            out.append(stem.lower())
    return out


def risk_hits(entries: list[Entry], stems: list[str]) -> list[tuple[Entry, list[str]]]:
    """The entries whose msgid (or plural) has a word starting with a stem."""
    out = []
    for entry in entries:
        if not entry.msgid:
            continue
        text = entry.msgid + "\n" + (entry.msgid_plural or "")
        hit = [s for s in stems if re.search(r"(?<![A-Za-z])" + re.escape(s), text, re.IGNORECASE)]
        if hit:
            out.append((entry, hit))
    return out


def reviewed(path: Path = RISK_REVIEWED) -> dict[str, str]:
    """po/RISK-REVIEWED: the score of each reviewed msgid (``<score> "<msgid>"``)."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        score, _sep, text = line.partition(" ")
        out[_unquote(text)] = score
    return out


def pseudo(entries: list[Entry], lang: str = "es") -> str:
    """A pseudo-translation: each text prefixed with ``XX ``, placeholders
    kept, two plural forms."""
    lines = [
        'msgid ""',
        'msgstr ""',
        quote(f"Language: {lang}\n"),
        quote("MIME-Version: 1.0\n"),
        quote("Content-Type: text/plain; charset=UTF-8\n"),
        quote("Content-Transfer-Encoding: 8bit\n"),
        quote("Plural-Forms: nplurals=2; plural=(n != 1);\n"),
        "",
    ]
    for entry in entries:
        if not entry.msgid:
            continue
        lines.append(f"msgid {quote(entry.msgid)}")
        if entry.msgid_plural is not None:
            lines.append(f"msgid_plural {quote(entry.msgid_plural)}")
            lines.append(f"msgstr[0] {quote('XX ' + entry.msgid)}")
            lines.append(f"msgstr[1] {quote('XX ' + entry.msgid_plural)}")
        elif entry.msgid == "translator-credits":
            lines.append(f"msgstr {quote('XX Translator')}")
        else:
            lines.append(f"msgstr {quote('XX ' + entry.msgid)}")
        lines.append("")
    return "\n".join(lines)


def _risk() -> int:
    stems = risk_stems()
    done = reviewed()
    hits = risk_hits(parse(POT), stems)
    for entry, hit in hits:
        score = done.get(entry.msgid, "UNREVIEWED")
        print(f"{score:10} {quote(entry.msgid)}")
        print(f"{'':10} {', '.join(hit)} - {' '.join(entry.locations)}")
    print(f"{len(hits)} msgids match po/RISK-WORDS")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["risk"]:
        print("usage: python3 -I tests/potools.py risk", file=sys.stderr)
        sys.exit(2)
    sys.exit(_risk())
