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
"""The keyboard shortcuts help (design 3.3), through :mod:`zark_app.compat`."""

from typing import Any

from gi.repository import Adw, Gtk

from zark_app import compat
from zark_app.i18n import N_, _

SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        N_("General"),
        [
            ("<Control>question", N_("Keyboard Shortcuts")),
            ("F10", N_("Open the Main Menu")),
            ("<Control>r", N_("Reload")),
            ("<Control>w", N_("Close the Window")),
            ("<Control>q", N_("Quit")),
        ],
    ),
    (
        N_("Navigation"),
        [
            ("<Control>1", N_("Overview")),
            ("<Control>2 <Control>9", N_("Backup Drives, in Order")),
            ("<Alt>Left", N_("Back, in the Narrow Layout")),
        ],
    ),
]


def _new_dialog(parent: Gtk.Window) -> Any:
    dialog = Adw.ShortcutsDialog()
    for title, items in SECTIONS:
        section = Adw.ShortcutsSection(title=_(title))
        for keys, label in items:
            section.add(Adw.ShortcutsItem(title=_(label), accelerator=keys))
        dialog.add(section)
    dialog.present(parent)
    return dialog


def _old_window(parent: Gtk.Window) -> Gtk.ShortcutsWindow:
    window = Gtk.ShortcutsWindow(transient_for=parent, modal=True)
    section = Gtk.ShortcutsSection()
    for title, items in SECTIONS:
        group = Gtk.ShortcutsGroup(title=_(title))
        for keys, label in items:
            group.add_shortcut(Gtk.ShortcutsShortcut(title=_(label), accelerator=keys))
        section.add_group(group)
    window.add_section(section)
    window.present()
    return window


def show(parent: Gtk.Window, minor: int | None = None) -> Any:
    """Show the help: ``AdwShortcutsDialog`` from 1.8, else
    ``Gtk.ShortcutsWindow`` (GTK 4.14's ``add_section``)."""
    return _new_dialog(parent) if compat.uses_shortcuts_dialog(minor) else _old_window(parent)
