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
"""The translations (A1T plan sections 2 to 5, review A1TR-1 to A1TR-9):
the template is current, every risky msgid was reviewed, the texts kept
English stay out, every catalogue compiles, loads and matches the
template with its placeholders, white space and plural forms, the merged
desktop file, metainfo and policy are valid, no text is translated at
import time, and every state of the app shows its texts translated. The
catalogue in the tests is a pseudo-translation of the template (each text
prefixed with ``XX``), built here and never shipped; the catalogues of
po/LINGUAS are checked the same way."""

# pylint: disable=redefined-outer-name

import ast
import gettext
import locale
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import potools
from zark_app import i18n

ROOT = potools.ROOT
PO = potools.PO
DATA = ROOT / "data"
APP_ID = "com.juanmitaboada.Zark"
DOMAIN = "zark-gnome-app"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
PSEUDO_LANGS = ("es", "pt_BR")


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} is not installed")
    return path


def linguas() -> list[str]:
    """The languages of po/LINGUAS."""
    text = (PO / "LINGUAS").read_text(encoding="utf-8")
    return [w for line in text.splitlines() for w in line.split("#", 1)[0].split()]


@pytest.fixture(scope="module")
def pseudo_po(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A po directory holding the pseudo-translation as ``es`` and, for a
    language with a region, as ``pt_BR``."""
    out = tmp_path_factory.mktemp("po")
    entries = potools.parse(potools.POT)
    for lang in PSEUDO_LANGS:
        (out / f"{lang}.po").write_text(potools.pseudo(entries, lang), encoding="utf-8")
    (out / "LINGUAS").write_text("\n".join(PSEUDO_LANGS) + "\n", encoding="utf-8")
    return out


def catalogues(pseudo_po: Path) -> list[Path]:
    """Every catalogue to check: po/LINGUAS's and the pseudo-translation."""
    return [PO / f"{lang}.po" for lang in linguas()] + [pseudo_po / f"{lang}.po" for lang in PSEUDO_LANGS]


def _key(entry: potools.Entry) -> tuple[str | None, str]:
    return (entry.msgctxt, entry.msgid)


# -- the template ----------------------------------------------------------


def _messages(path: Path) -> list[tuple[str | None, str, str | None, list[str]]]:
    return [(e.msgctxt, e.msgid, e.msgid_plural, e.comments) for e in potools.parse(path)[1:]]


def test_pot_current(tmp_path: Path) -> None:
    """po/zark-gnome-app.pot holds what make pot writes from the sources:
    the same messages, contexts and translator comments. Source lines and
    wrapping are left out, since gettext's versions differ on them (0.21 on
    noble, 1.0 on stonking)."""
    _tool("xgettext")
    fresh = tmp_path / "fresh.pot"
    subprocess.run(["make", "-s", "-C", str(ROOT), "pot", f"POT={fresh}"], check=True, capture_output=True)
    assert _messages(fresh) == _messages(potools.POT)


def test_no_white_space_at_the_ends() -> None:
    """No msgid starts or ends with white space: a fragment glued into a
    sentence cannot be translated (A1TR-5)."""
    bad = [e.msgid for e in potools.parse(potools.POT)[1:] if e.msgid != e.msgid.strip()]
    assert not bad


def test_contexts() -> None:
    """The words with more than one meaning carry a context (A1TR-3)."""
    contexts = {(e.msgctxt, e.msgid) for e in potools.parse(potools.POT) if e.msgctxt}
    for want in (
        ("retention", "Window"),
        ("exclusion scope", "Backups"),
        ("notice title", "Backups"),
        ("drive check", "Clean"),
        ("button", "Stop"),
        ("space", "Free"),
        ("month", "May"),
        ("month, short", "May"),
    ):
        assert want in contexts


def test_risk_words_reviewed() -> None:
    """Every msgid that matches po/RISK-WORDS has a score in
    po/RISK-REVIEWED, and that file names nothing else."""
    hits = {e.msgid for e, _stems in potools.risk_hits(potools.parse(potools.POT), potools.risk_stems())}
    done = potools.reviewed()
    assert sorted(hits - set(done)) == [], "not reviewed: add them to po/RISK-REVIEWED"
    assert sorted(set(done) - hits) == [], "reviewed but no longer in the template"
    assert set(done.values()) <= {"label", "caption", "1"}


def test_risk_words_match_stems() -> None:
    """A stem matches the start of a word, in any case."""
    entries = [potools.Entry(msgid=m) for m in ("Erasing a Drive", "Keyboard", "A cleared pool", "Unstop")]
    got = [e.msgid for e, _s in potools.risk_hits(entries, ["eras", "key", "clear", "stop"])]
    assert got == ["Erasing a Drive", "Keyboard", "A cleared pool"]


def test_risk_captions_always_reviewed() -> None:
    """A risk caption is a match whatever its words (BC22-44)."""
    caption = potools.Entry(msgid="Choose an empty disk", comments=["TRANSLATORS: risk caption, shown under"])
    assert [e.msgid for e, _s in potools.risk_hits([caption, potools.Entry(msgid="Choose")], ["eras"])] == [
        "Choose an empty disk"
    ]


def test_kept_out_of_the_template() -> None:
    """The score-2 lines, the commands inside texts and the product's name
    never reach a translator (glossary 1 and 6; plan T-2; A1TR-6)."""
    msgids = [e.msgid for e in potools.parse(potools.POT)]
    for line in (
        "The disk you choose must be empty: zark refuses one with partitions or a format it recognizes, "
        "and leaves it untouched.",
        "Could not check which disks this system uses: zark checks again before it writes",
        "Disks this system uses are not listed",
        "zark",
    ):
        assert line not in msgids
    for command in ("sudo apt install", "zfs get", "zpool list"):
        assert not [m for m in msgids if command in m]


def test_repr_fields_are_plain() -> None:
    """No msgid holds a conversion such as {name!r}: xgettext does not flag
    it and no check compares it (A1TR-4)."""
    assert not [e.msgid for e in potools.parse(potools.POT) if re.search(r"\{[^}]*[!:]r", e.msgid)]


def test_release_notes_not_translated() -> None:
    """Every release's notes carry translate="no" (plan T-6)."""
    root = ET.parse(DATA / f"{APP_ID}.metainfo.xml.in").getroot()
    notes = root.findall("./releases/release/description")
    assert notes and all(n.get("translate") == "no" for n in notes)


def test_policy_template_has_no_domain() -> None:
    """The policy carries no gettext-domain: polkit would look its texts
    up at run time and ignore the merged translations (A1TR-1)."""
    text = (DATA / f"{APP_ID}.policy.in").read_text(encoding="utf-8")
    assert "gettext-domain" not in text


def _import_time_calls(node: ast.AST, in_function: bool = False) -> list[int]:
    """The lines of _(), ngettext() and pgettext() calls outside any function."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
        in_function = True
    found = []
    if (
        not in_function
        and isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("_", "ngettext", "pgettext")
    ):
        found.append(node.lineno)
    for child in ast.iter_child_nodes(node):
        found += _import_time_calls(child, in_function)
    return found


def test_no_translation_at_import() -> None:
    """No _(), ngettext() or pgettext() runs when a module is imported:
    the domain is bound later, in main (A1TR-8)."""
    found = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in sorted((ROOT / "zark_app").rglob("*.py"))
        for line in _import_time_calls(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not found


def test_import_check_bites() -> None:
    """A module-level call is seen; one in a function is not."""
    assert _import_time_calls(ast.parse('X = _("a")\ndef f():\n    return _("b")\n')) == [1]


# -- the catalogues --------------------------------------------------------


def test_linguas_match_po_files() -> None:
    """po/LINGUAS names exactly the catalogues in po/ (A1TR-7)."""
    assert sorted(linguas()) == sorted(p.stem for p in PO.glob("*.po"))


@pytest.mark.parametrize("lang", linguas())
def test_catalogue_matches_template(lang: str) -> None:
    """A catalogue holds the template's messages, no more and no fewer:
    run msgmerge after make pot (A1TR-7)."""
    template = {_key(e) for e in potools.parse(potools.POT)[1:]}
    catalogue = {_key(e) for e in potools.parse(PO / f"{lang}.po")[1:]}
    assert sorted(template - catalogue, key=str) == [], "missing: msgmerge the catalogue"
    assert sorted(catalogue - template, key=str) == [], "not in the template"


def test_catalogues_compile_and_load(pseudo_po: Path, tmp_path: Path) -> None:
    """msgfmt -c accepts every catalogue, Python's gettext loads it, and its
    header says UTF-8 and its own language (A1TR-2)."""
    msgfmt = _tool("msgfmt")
    for po in catalogues(pseudo_po):
        mo = tmp_path / f"{po.stem}.mo"
        subprocess.run([msgfmt, "-c", "-o", str(mo), str(po)], check=True)
        with mo.open("rb") as handle:
            info = gettext.GNUTranslations(handle).info()
        assert info.get("content-type") == "text/plain; charset=UTF-8", po.name
        assert info.get("language") == po.stem, po.name


def test_bad_catalogue_keeps_english(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A catalogue that cannot be read leaves the app in English, with a
    line on stderr, instead of stopping it (A1TR-2)."""
    target = tmp_path / "locale" / "es" / "LC_MESSAGES"
    target.mkdir(parents=True)
    (target / f"{DOMAIN}.mo").write_bytes(b"\xde\x12\x04\x95 not a catalogue")
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.setattr(i18n, "_translation", gettext.NullTranslations())
    saved = locale.setlocale(locale.LC_ALL)
    try:
        i18n.setup(tmp_path / "locale")
    finally:
        locale.setlocale(locale.LC_ALL, saved)
    assert i18n._("This Computer") == "This Computer"


def test_placeholders_kept(pseudo_po: Path) -> None:
    """Each translation has exactly its source's placeholders: {name} for
    Python, $(name) for polkit."""
    for po in catalogues(pseudo_po):
        for entry in potools.parse(po)[1:]:
            for index, text in entry.msgstr.items():
                if not text:
                    continue
                source = entry.msgid if index == 0 or entry.msgid_plural is None else entry.msgid_plural
                assert potools.placeholders(text) == potools.placeholders(source), (po.name, entry.msgid)


def test_white_space_kept(pseudo_po: Path) -> None:
    """A translation starts and ends with the white space its source does."""
    for po in catalogues(pseudo_po):
        for entry in potools.parse(po)[1:]:
            for text in entry.msgstr.values():
                if text:
                    lead = len(entry.msgid) - len(entry.msgid.lstrip())
                    trail = len(entry.msgid) - len(entry.msgid.rstrip())
                    assert len(text) - len(text.lstrip()) == lead, (po.name, entry.msgid)
                    assert len(text) - len(text.rstrip()) == trail, (po.name, entry.msgid)


def test_placeholder_check_bites() -> None:
    """A dropped or renamed placeholder is seen."""
    assert potools.placeholders("{drive} went away") != potools.placeholders("{disco} se fue")
    assert potools.placeholders("x: $(cmdline_short)") != potools.placeholders("x")


def test_plural_forms(pseudo_po: Path) -> None:
    """Each catalogue states its plural forms, and every plural entry has
    that many translations."""
    for po in catalogues(pseudo_po):
        entries = potools.parse(po)
        header = entries[0].msgstr[0]
        match = re.search(r"^Plural-Forms: nplurals=(\d+); plural=[^;]+;", header, re.MULTILINE)
        assert match, po.name
        n = int(match.group(1))
        for entry in entries[1:]:
            if entry.msgid_plural is not None:
                assert sorted(entry.msgstr) == list(range(n)), (po.name, entry.msgid)


# -- merged at build -------------------------------------------------------


def merge(po_dir: Path, out: Path) -> Path:
    """The desktop file, the metainfo and the policy merged with the
    catalogues of ``po_dir`` by make i18n itself, as the package build does."""
    _tool("msgfmt")
    subprocess.run(
        ["make", "-s", "-C", str(ROOT), "i18n", f"PODIR={po_dir}", f"I18N={out}"],
        check=True,
        capture_output=True,
    )
    return out


def xml_langs(path: Path) -> set[str]:
    """The xml:lang values of a merged XML file."""
    return {e.get(XML_LANG) or "" for e in ET.parse(path).getroot().iter() if e.get(XML_LANG)}


def desktop_langs(path: Path) -> set[str]:
    """The languages of a merged desktop file's keys (``Comment[pt_BR]``)."""
    return set(re.findall(r"^[A-Za-z]+\[([^\]]+)\]=", path.read_text(encoding="utf-8"), re.MULTILINE))


def bcp47(lang: str) -> str:
    """``pt-BR`` from the locale name ``pt_BR``."""
    return lang.replace("_", "-")


def test_language_names() -> None:
    """po/LINGUAS's names are a language and maybe a region (``pt_BR``):
    the forms make i18n turns between a locale name and BCP 47."""
    assert all(re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2})?", lang) for lang in linguas())


@pytest.fixture(scope="module")
def merged(pseudo_po: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Merged with the pseudo catalogue."""
    return merge(pseudo_po, tmp_path_factory.mktemp("merged"))


@pytest.fixture(scope="module")
def merged_real(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Merged with po/LINGUAS's catalogues, as the package build does."""
    return merge(PO, tmp_path_factory.mktemp("merged-real"))


def test_desktop_merged(merged: Path) -> None:
    """The merged desktop file is valid and carries the translations; Name
    stays the product's."""
    desktop = merged / f"{APP_ID}.desktop"
    subprocess.run([_tool("desktop-file-validate"), str(desktop)], check=True)
    text = desktop.read_text(encoding="utf-8")
    assert "Comment[es]=XX See the state" in text and "GenericName[es]=XX Backups" in text
    assert not re.search(r"^Name\[", text, re.MULTILINE)


def test_metainfo_merged(merged: Path) -> None:
    """The merged metainfo is valid and translates its summary, not its
    name or release notes."""
    metainfo = merged / f"{APP_ID}.metainfo.xml"
    subprocess.run([_tool("appstreamcli"), "validate", "--no-net", str(metainfo)], check=True)
    root = ET.parse(metainfo).getroot()
    assert [s.text for s in root.findall("summary") if s.get(XML_LANG) == "es"] == [
        "XX See the state of your zark backups and backup drives"
    ]
    assert not [n for n in root.findall("name") if n.get(XML_LANG)]
    assert not [p for p in root.iterfind("./releases/release/description/p") if p.get(XML_LANG)]


def test_merged_language_forms(merged: Path) -> None:
    """Each merged file carries its languages in the form its reader wants,
    whatever gettext built it (0.21 writes pt_BR, 0.22 and later pt-BR):
    the policy the locale name (polkitd matches $LANG's variants), the
    metainfo BCP 47 (AppStream), the desktop file the locale name."""
    assert xml_langs(merged / f"{APP_ID}.policy") == set(PSEUDO_LANGS)
    assert xml_langs(merged / f"{APP_ID}.metainfo.xml") == {bcp47(lang) for lang in PSEUDO_LANGS}
    assert desktop_langs(merged / f"{APP_ID}.desktop") == set(PSEUDO_LANGS)


def test_policy_merged(merged: Path) -> None:
    """The merged policy carries an xml:lang copy of every action's
    description and message, the command placeholder intact, and no
    gettext-domain (A1TR-1)."""
    text = (merged / f"{APP_ID}.policy").read_text(encoding="utf-8")
    assert "gettext-domain" not in text
    root = ET.fromstring(text)
    actions = root.findall("action")
    assert actions
    for action in actions:
        for tag in ("description", "message"):
            es = [e.text or "" for e in action.findall(tag) if e.get(XML_LANG) == "es"]
            assert len(es) == 1 and es[0].startswith("XX "), (action.get("id"), tag)
            if tag == "message":
                assert es[0].endswith("$(cmdline_short)")


def test_policy_merged_same_without_catalogue(tmp_path: Path) -> None:
    """With no language the installed policy is the template's actions as
    they are."""
    (tmp_path / "po").mkdir()
    (tmp_path / "po" / "LINGUAS").write_text("", encoding="utf-8")
    out = merge(tmp_path / "po", tmp_path / "out")
    assert not [e for e in ET.parse(out / f"{APP_ID}.policy").getroot().iter() if e.get(XML_LANG)]


def test_merged_real_catalogues(merged_real: Path) -> None:
    """The catalogues of po/LINGUAS merged: valid files, every policy
    message keeps its command placeholder, every language in each file in
    its reader's form (A1TR-7)."""
    subprocess.run([_tool("desktop-file-validate"), str(merged_real / f"{APP_ID}.desktop")], check=True)
    subprocess.run(
        [_tool("appstreamcli"), "validate", "--no-net", str(merged_real / f"{APP_ID}.metainfo.xml")],
        check=True,
    )
    root = ET.parse(merged_real / f"{APP_ID}.policy").getroot()
    for message in root.iter("message"):
        assert (message.text or "").endswith("$(cmdline_short)"), message.get(XML_LANG)
    assert xml_langs(merged_real / f"{APP_ID}.policy") == set(linguas())
    assert xml_langs(merged_real / f"{APP_ID}.metainfo.xml") == {bcp47(lang) for lang in linguas()}
    assert desktop_langs(merged_real / f"{APP_ID}.desktop") == set(linguas())


# -- the app in Spanish ------------------------------------------------------


@pytest.fixture
def spanish(pseudo_po: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The pseudo catalogue installed as es under a locale directory, the
    environment of a Spanish session, and the domain bound as main binds it;
    everything put back after."""
    msgfmt = _tool("msgfmt")
    target = tmp_path / "locale" / "es" / "LC_MESSAGES"
    target.mkdir(parents=True)
    subprocess.run([msgfmt, "-o", str(target / f"{DOMAIN}.mo"), str(pseudo_po / "es.po")], check=True)
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    monkeypatch.setattr(i18n, "_translation", gettext.NullTranslations())
    saved = locale.setlocale(locale.LC_ALL)
    i18n.setup(tmp_path / "locale")
    yield
    locale.setlocale(locale.LC_ALL, saved)


@pytest.mark.usefixtures("spanish")
def test_texts_in_spanish() -> None:
    """The catalogue's texts, placeholders filled, months from it too."""
    # pylint: disable=import-outside-toplevel
    from zark_app import units

    assert i18n._("This Computer") == "XX This Computer"
    assert i18n.ngettext("{n} day", "{n} days", 3).format(n=3) == "XX 3 days"
    assert i18n.pgettext("retention", "Window") == "XX Window"
    assert units.fmt_month("2026-11") == "XX XX November 2026"


def test_english_without_setup() -> None:
    """Until main binds the domain, the source text."""
    assert i18n._("This Computer") == "This Computer"


def _untranslated_patterns() -> list[re.Pattern[str]]:
    """The template's msgids as patterns of a shown text, placeholders as
    any text; only those with enough words of their own to tell an
    untranslated text from zark's data."""
    out = []
    for entry in potools.parse(potools.POT)[1:]:
        for msgid in (entry.msgid, entry.msgid_plural):
            if not msgid:
                continue
            own = potools.PLACEHOLDER.sub("", re.sub(r"\{[^}]*\}", "", msgid))
            if len(re.findall(r"[A-Za-z]", own)) < 4:
                continue
            parts = re.split(r"\{[^}]*\}", msgid)
            out.append(re.compile("^" + ".+".join(re.escape(p) for p in parts) + "$"))
    return out


@pytest.mark.usefixtures("spanish")
def test_every_state_translated() -> None:
    """Every state of tests/screenshots.py's SHOTS, opened under the pseudo
    catalogue: no shown text is one of the template's messages left in
    English, and the window does show translated texts (A1TR-8)."""
    # pylint: disable=import-outside-toplevel
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gtk  # noqa: F401  # pylint: disable=unused-import

    # Gtk's import above opens the display.
    if Gdk.Display.get_default() is None:
        pytest.skip("no display: run under xvfb-run")
    from tests.screenshots import SHOTS
    from tests.test_window import open_window, texts
    from zark_app.main import ZarkApp

    patterns = _untranslated_patterns()
    app = ZarkApp(watch=False)
    app.register(None)
    english: list[tuple[str, str]] = []
    translated = 0
    for name, page in SHOTS:
        window = open_window(app, name, page)
        try:
            for text in texts(window):
                if text.startswith("XX "):
                    translated += 1
                elif any(p.match(text) for p in patterns):
                    english.append((f"{name} {page}", text))
        finally:
            window.destroy()
    assert not english
    assert translated > len(SHOTS)
    window = open_window(app, "app:connected")
    try:
        assert "XX Live figures from zpool list" in texts(window)
    finally:
        window.destroy()
