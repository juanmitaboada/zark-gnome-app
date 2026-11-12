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
"""Exclusions (design 2.4, ``exclusions.svg``): read with ``zfs get`` of
zark's user properties, unprivileged."""

from gi.repository import Adw, Gtk

from zark_app.i18n import N_, _
from zark_app.live import Exclusion
from zark_app.model import Action, Snapshot
from zark_app.units import fmt_bytes
from zark_app.widgets import action_button

# zark's rule (commands/exclude.py, D10).
NEVER = (
    N_("The boot environments"),
    N_("The boot pool"),
    N_("The keystore"),
    N_("The structural containers"),
)


def _row(item: Exclusion, what: str) -> Adw.ActionRow:
    row = Adw.ActionRow(
        title=item.dataset,
        subtitle=fmt_bytes(item.used) if item.used is not None else _("Size not read"),
    )
    row.add_suffix(action_button(Action(_("Include Again"), "exclude-remove", f"{item.dataset}\t{what}")))
    return row


def build(snapshot: Snapshot) -> Gtk.Widget:
    """The Exclusions page."""
    page = Adw.PreferencesPage()
    if snapshot.exclusions is None:
        status = Adw.StatusPage(
            title=_("Exclusions Not Read"),
            description=_("zfs get could not read zark's properties. Reload with Ctrl+R"),
            icon_name="dialog-warning-symbolic",
        )
        holder = Adw.PreferencesGroup()
        holder.add(status)
        page.add(holder)
        return page
    groups = (
        (_("Left Out of Backups"), "backups", [e for e in snapshot.exclusions if e.backups]),
        (_("Left Out of Local Snapshots"), "snapshots", [e for e in snapshot.exclusions if e.snapshots]),
    )
    for title, what, items in groups:
        group = Adw.PreferencesGroup(title=title)
        if not items:
            group.set_description(_("None"))
        for item in items:
            group.add(_row(item, what))
        page.add(group)
    never = Adw.PreferencesGroup(
        title=_("Never Excluded"),
        description=_("zark always keeps these, whatever their properties say"),
    )
    for text in NEVER:
        never.add(Adw.ActionRow(title=_(text)))
    full = Adw.ActionRow(title=_("zark's full list, with inherited values and the ones it ignores"))
    full.add_suffix(action_button(Action(_("Show zark's Full List..."), "exclude-list")))
    never.add(full)
    page.add(never)
    return page


def header_action() -> Action:
    """The header's "Exclude..." button: a dialog asks the dataset."""
    return Action(_("Exclude..."), "exclude-add")
