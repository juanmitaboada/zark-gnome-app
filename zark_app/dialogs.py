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
"""The questions the app asks itself before a run (design 4, A2 plan 2.2):
Stop, Retention, Exclude and the Prepare disk picker. Every one is an
``AdwAlertDialog`` (libadwaita 1.5) with Cancel first and the close
response; a destructive one has no default. And one alert with OK only:
a backup's drive gone."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gi.repository import Adw, Gtk, Pango

from zark_app.commands import MARGIN, MAX_AGE, WINDOW, CommandError, Retention, retention_words
from zark_app.i18n import N_, _, pgettext
from zark_app.model import DriveGone
from zark_app.units import fmt_time

CANCEL = "cancel"


def _alert(heading: str, body: str, ok: str, ok_label: str, destructive: bool) -> Adw.AlertDialog:
    dialog = Adw.AlertDialog.new(heading, body)
    dialog.add_response(CANCEL, _("Cancel"))
    dialog.add_response(ok, ok_label)
    dialog.set_close_response(CANCEL)
    if destructive:
        dialog.set_response_appearance(ok, Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response(CANCEL)
    else:
        dialog.set_response_appearance(ok, Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response(ok)
    return dialog


def stop(parent: Gtk.Widget, backup: bool, closing: bool, on_stop: Callable[[], None]) -> Adw.AlertDialog:
    """ "Stop the Backup?" (design 4.1): Keep Running is the default and the
    close response."""
    heading = _("Stop the Backup?") if backup else _("Stop zark?")
    body = (
        _("Closing the window stops zark. It cleans up before it ends")
        if closing
        else _("zark stops the running command and cleans up before it ends")
    )
    dialog = Adw.AlertDialog.new(heading, body)
    dialog.add_response("keep", _("Keep Running"))
    # TRANSLATORS: Stop: the button that stops the running zark command.
    dialog.add_response("stop", _("Stop and Close") if closing else pgettext("button", "Stop"))
    dialog.set_response_appearance("stop", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("keep")
    dialog.set_close_response("keep")
    dialog.connect("response", lambda _d, r: on_stop() if r == "stop" else None)
    dialog.present(parent)
    return dialog


def _spin(title: str, limits: tuple[int, int], value: int, subtitle: str = "") -> Adw.SpinRow:
    row = Adw.SpinRow.new_with_range(limits[0], limits[1], 1)
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_value(value)
    return row


def retention(
    parent: Gtk.Widget, name: str, current: Mapping[str, Any], on_apply: Callable[[Retention], None]
) -> Adw.AlertDialog:
    """Retention for one drive: three spin rows in zark's limits; Apply is
    enabled only while zark would accept the values."""
    dialog = _alert(_("Retention for {name}").format(name=name), "", "apply", _("Apply"), False)

    def value(key: str, default: int) -> int:
        v = current.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else default

    window = _spin(
        # TRANSLATORS: Window: the retention window, the days with every backup
        # point kept; not a window on screen.
        pgettext("retention", "Window"),
        WINDOW,
        value("window_days", 30),
        _("Days with every backup point kept"),
    )
    max_age = _spin(_("Maximum age"), MAX_AGE, value("max_age_days", 0), _("Days; 0 is no limit"))
    # TRANSLATORS: Margin: the share of the drive a backup leaves free.
    margin = _spin(_("Margin"), MARGIN, value("margin_pct", 10), _("Percent of the drive left free"))
    rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    rows.add_css_class("boxed-list")
    for row in (window, max_age, margin):
        rows.append(row)
    problem = Gtk.Label(wrap=True, xalign=0.0, margin_top=6)
    problem.add_css_class("error")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(rows)
    box.append(problem)
    dialog.set_extra_child(box)

    def values() -> Retention:
        return Retention(int(window.get_value()), int(max_age.get_value()), int(margin.get_value()))

    def check(*_args: object) -> None:
        try:
            retention_words(values())
        except CommandError as e:
            problem.set_label(str(e))
            dialog.set_response_enabled("apply", False)
            return
        problem.set_label("")
        dialog.set_response_enabled("apply", True)

    for row in (window, max_age, margin):
        row.connect("notify::value", check)
    check()
    dialog.connect("response", lambda _d, r: on_apply(values()) if r == "apply" else None)
    dialog.present(parent)
    return dialog


def _label_factory(ellipsize: Pango.EllipsizeMode) -> Gtk.SignalListItemFactory:
    """A list item factory of labels for a ``Gtk.StringList``, cut as
    ``ellipsize`` says, the whole string as tooltip."""
    factory = Gtk.SignalListItemFactory()

    def setup(_f: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        item.set_child(Gtk.Label(xalign=0.0, ellipsize=ellipsize))

    def bind(_f: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        label = item.get_child()
        string = item.get_item()
        if isinstance(label, Gtk.Label) and isinstance(string, Gtk.StringObject):
            label.set_label(string.get_string())
            label.set_tooltip_text(string.get_string())

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    return factory


def exclude(
    parent: Gtk.Widget, datasets: Sequence[str], on_apply: Callable[[str, str], None]
) -> Adw.AlertDialog:
    """Exclude a dataset of this computer from backups, local snapshots or
    both (design 2.4)."""
    dialog = _alert(_("Exclude a Dataset"), "", "exclude", _("Exclude"), False)
    names = Gtk.StringList.new(list(datasets))
    which = Adw.ComboRow(title=_("Dataset"), model=names)
    # A2E-8: the names share a long start; cut it, keep the end, the whole in the list.
    which.set_factory(_label_factory(Pango.EllipsizeMode.START))
    which.set_list_factory(_label_factory(Pango.EllipsizeMode.NONE))
    words = ("backups", "snapshots", "both")
    labels = Gtk.StringList.new(
        [
            # TRANSLATORS: what a dataset is left out of: zark's backups, its
            # local snapshots, or both.
            pgettext("exclusion scope", "Backups"),
            _("Local snapshots"),
            pgettext("exclusion scope", "Both"),
        ]
    )
    what = Adw.ComboRow(title=_("Leave out of"), model=labels)
    rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    rows.add_css_class("boxed-list")
    rows.append(which)
    rows.append(what)
    dialog.set_extra_child(rows)
    dialog.set_response_enabled("exclude", bool(datasets))

    def apply(_d: Adw.AlertDialog, response: str) -> None:
        if response == "exclude" and datasets:
            on_apply(datasets[which.get_selected()], words[what.get_selected()])

    dialog.connect("response", apply)
    dialog.present(parent)
    return dialog


def risk_caption(checked: bool, hidden: int) -> str:
    """BC22-44: the translated caption under Prepare's English lines, one
    per branch of its body with disks listed; empty when the catalogue does
    not translate it, so an English reader does not read the risk twice."""
    if not checked:
        msgid = N_(
            # TRANSLATORS: risk caption, shown under English lines that stay
            # untranslated. It may only add caution: never say less than those lines.
            "Choose an empty disk: zark refuses one with partitions or data and writes nothing to it. "
            "Check the disk's name and size first. Could not check which disks this system uses: "
            "zark checks again before it writes."
        )
    elif hidden:
        msgid = N_(
            # TRANSLATORS: risk caption, shown under English lines that stay
            # untranslated. It may only add caution: never say less than those lines.
            "Choose an empty disk: zark refuses one with partitions or data and writes nothing to it. "
            "Check the disk's name and size first. Disks this system uses are not listed."
        )
    else:
        msgid = N_(
            # TRANSLATORS: risk caption, shown under English lines that stay
            # untranslated. It may only add caution: never say less than those lines.
            "Choose an empty disk: zark refuses one with partitions or data and writes nothing to it. "
            "Check the disk's name and size first."
        )
    text = _(msgid)
    return "" if text == msgid else text


def _caption_box(text: str) -> Gtk.Widget:
    """A warning icon and a wrapped label in libadwaita's warning style."""
    box = Gtk.Box(spacing=12)
    box.add_css_class("warning")
    icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
    icon.set_valign(Gtk.Align.START)
    label = Gtk.Label(label=text, wrap=True, xalign=0.0, hexpand=True)
    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    box.append(icon)
    box.append(label)
    return box


def _with_caption(rows: Gtk.Widget, caption: str) -> Gtk.Widget:
    """The disk list, under the risk caption when there is one."""
    extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    if caption:
        extra.append(_caption_box(caption))
    extra.append(rows)
    return extra


def prepare(
    parent: Gtk.Widget,
    disks: Sequence[tuple[str, str]],
    on_choose: Callable[[str], None],
    checked: bool = True,
    hidden: int = 0,
) -> Adw.AlertDialog:
    """A2-1: the disk to prepare, from the whole disks under
    ``/dev/disk/by-id`` that are no registered drive and that the system
    does not use (A2E-9; ``hidden`` of them left out, ``checked`` False when
    that could not be read). A disk that is not empty is listed too: zark
    refuses it before writing anything."""
    # The three lines on which disk zark takes and which disks are listed
    # stay English (risk score 2, glossary 6); the caption below carries them.
    body = (
        "The disk you choose must be empty: zark refuses one with partitions or data and leaves it untouched."
        + " "
        + _("It asks you to confirm in the terminal")
        if disks
        else _("No disk to prepare is connected: plug in an empty drive")
    )
    if not checked:
        body += "\n\n" + "Could not check which disks this system uses: zark checks again before it writes"
    elif hidden:
        body += "\n\n" + "Disks this system uses are not listed"
    dialog = _alert(_("Prepare a New Drive"), body, "prepare", _("Prepare..."), True)
    group: Gtk.CheckButton | None = None
    chosen: list[str] = []
    rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    rows.add_css_class("boxed-list")
    for name, label in disks:
        check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        if group is None:
            group = check
        else:
            check.set_group(group)
        row = Adw.ActionRow(title=label, activatable_widget=check)
        row.add_prefix(check)

        def picked(button: Gtk.CheckButton, disk: str = name) -> None:
            if button.get_active():
                chosen[:] = [disk]
                dialog.set_response_enabled("prepare", True)

        check.connect("toggled", picked)
        rows.append(row)
    if disks:
        dialog.set_extra_child(_with_caption(rows, risk_caption(checked, hidden)))
    dialog.set_response_enabled("prepare", False)
    dialog.connect("response", lambda _d, r: on_choose(chosen[0]) if r == "prepare" and chosen else None)
    dialog.present(parent)
    return dialog


def drive_gone(parent: Gtk.Widget, drive: str, gone: DriveGone) -> Adw.AlertDialog:
    """A backup's drive went away (zark 2.3.1's ``drive_gone``): its name,
    the local time it went, and zark's hint as written, selectable so its
    commands can be copied. OK only."""
    heading = _("{drive} went away during the backup").format(drive=drive)
    body = _("Since {time}.").format(time=fmt_time(gone.since)) if gone.since is not None else ""
    dialog = Adw.AlertDialog.new(heading, body)
    dialog.add_response("ok", _("OK"))
    dialog.set_default_response("ok")
    dialog.set_close_response("ok")
    if gone.hint:
        hint = Gtk.Label(label=gone.hint, wrap=True, selectable=True, xalign=0.0)
        hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        dialog.set_extra_child(hint)
    dialog.present(parent)
    return dialog
