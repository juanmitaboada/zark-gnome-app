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
response; a destructive one has no default."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gi.repository import Adw, Gtk

from zark_app.commands import MARGIN, MAX_AGE, WINDOW, CommandError, Retention, retention_words
from zark_app.i18n import _

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
    dialog.add_response("stop", _("Stop and Close") if closing else _("Stop"))
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

    window = _spin(_("Window"), WINDOW, value("window_days", 30), _("Days with every backup point kept"))
    max_age = _spin(_("Maximum age"), MAX_AGE, value("max_age_days", 0), _("Days; 0 is no limit"))
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


def exclude(
    parent: Gtk.Widget, datasets: Sequence[str], on_apply: Callable[[str, str], None]
) -> Adw.AlertDialog:
    """Exclude a dataset of this computer from backups, local snapshots or
    both (design 2.4)."""
    dialog = _alert(_("Exclude a Dataset"), "", "exclude", _("Exclude"), False)
    names = Gtk.StringList.new(list(datasets))
    which = Adw.ComboRow(title=_("Dataset"), model=names)
    words = ("backups", "snapshots", "both")
    labels = Gtk.StringList.new([_("Backups"), _("Local snapshots"), _("Both")])
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


def prepare(
    parent: Gtk.Widget, disks: Sequence[tuple[str, str]], on_choose: Callable[[str], None]
) -> Adw.AlertDialog:
    """A2-1: the disk to prepare, from the whole disks under
    ``/dev/disk/by-id`` that are no registered drive. zark checks it and
    asks its own typed confirmation after."""
    body = (
        _("zark erases the disk you choose and makes it a backup drive.")
        + " "
        + _("It asks you to confirm in the terminal")
        if disks
        else _("No disk to prepare is connected: plug in an empty drive")
    )
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
        dialog.set_extra_child(rows)
    dialog.set_response_enabled("prepare", False)
    dialog.connect("response", lambda _d, r: on_choose(chosen[0]) if r == "prepare" and chosen else None)
    dialog.present(parent)
    return dialog
