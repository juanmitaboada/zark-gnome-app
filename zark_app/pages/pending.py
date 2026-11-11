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
"""A pending drive: ``prepare`` wrote it, apt kept zark from reading it back
(``drive_pending``, M20)."""

from gi.repository import Adw, Gtk

from zark_app.i18n import _
from zark_app.model import PendingView
from zark_app.widgets import command_label, copy_button, property_row


def build(pending: PendingView) -> Gtk.Widget:
    """The pending drive's page."""
    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup(
        title=_("Not Read Back Yet"),
        description=_("zark prepared this drive while apt was running, so it could not read it back"),
    )
    group.add(property_row(_("zark says"), pending.text, subtitle_selectable=True))
    row = Adw.ActionRow(title=_("Finish the registration in a terminal"))
    row.add_suffix(copy_button(pending.action, suggested=True))
    group.add(row)
    command = Adw.PreferencesRow(activatable=False)
    label = command_label(pending.action.command)
    label.set_margin_top(12)
    label.set_margin_bottom(12)
    label.set_margin_start(12)
    command.set_child(label)
    group.add(command)
    page.add(group)
    return page
