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
"""The two run-time switches of design D6: ``AdwSpinner`` from libadwaita 1.6
and ``AdwShortcutsDialog`` from 1.8; GTK's own widgets before that (noble
ships 1.5)."""

from gi.repository import Adw, Gtk

SPINNER_SINCE = 6
SHORTCUTS_SINCE = 8


def adw_minor() -> int:
    """libadwaita's minor version (major is 1 throughout)."""
    return int(Adw.get_minor_version())


def spinner(minor: int | None = None) -> Gtk.Widget:
    """A running spinner."""
    if (adw_minor() if minor is None else minor) >= SPINNER_SINCE and hasattr(Adw, "Spinner"):
        return Adw.Spinner()
    widget = Gtk.Spinner()
    widget.start()
    return widget


def uses_shortcuts_dialog(minor: int | None = None) -> bool:
    """Whether the shortcuts help is ``AdwShortcutsDialog``."""
    return (adw_minor() if minor is None else minor) >= SHORTCUTS_SINCE and hasattr(Adw, "ShortcutsDialog")
