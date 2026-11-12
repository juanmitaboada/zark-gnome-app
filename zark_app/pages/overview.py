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
"""The Overview (design 2.1, ``main-window.svg``)."""

from collections.abc import Callable

from gi.repository import Adw, Gtk

from zark_app import compat
from zark_app.i18n import _
from zark_app.model import DriveView, PendingView, PoolView, Snapshot, size_line
from zark_app.pages import states
from zark_app.units import fmt_since
from zark_app.widgets import action_button, level_bar, level_icon, mounted_buttons

Select = Callable[[str], None]


def drive_icon(drive: DriveView) -> Gtk.Widget:
    """The drive's status icon; each state also has words beside it."""
    if drive.state in ("running", "waiting"):
        return compat.spinner()
    names = {
        "attention": "dialog-warning-symbolic",
        "connected": "emblem-ok-symbolic",
        "disconnected": "drive-harddisk-symbolic",
    }
    image = Gtk.Image.new_from_icon_name(names[drive.state])
    if drive.state == "attention":
        image.add_css_class("warning")
    elif drive.state == "connected":
        image.add_css_class("success")
    else:
        image.add_css_class("dim-label")
    return image


def _pool_row(pool: PoolView, now_label: Callable[[PoolView], str]) -> Adw.ActionRow:
    row = Adw.ActionRow(title=pool.name, subtitle=size_line(pool.used, pool.size, pool.pct))
    row.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk-system-symbolic"))
    extra = now_label(pool)
    if extra:
        row.set_subtitle(f"{row.get_subtitle()} - {extra}")
    if pool.level in ("warning", "critical"):
        # The level in words too, in the subtitle so the narrow layout keeps it.
        word = _("critical") if pool.level == "critical" else _("warning")
        row.set_subtitle(f"{row.get_subtitle()}, {word}")
        row.add_suffix(level_icon(pool.level))
    if pool.pct is not None:
        row.add_suffix(level_bar(pool.pct / 100, pool.level))
    return row


def _computer(snapshot: Snapshot) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=_("This Computer"))
    group.set_description(
        _("Live figures from zpool list") if snapshot.pools_live else _("Figures from zark's status file")
    )

    def label(pool: PoolView) -> str:
        if pool.live or pool.measured_at is None:
            return ""
        return _("measured {age}").format(age=fmt_since(pool.measured_at, snapshot.now))

    for pool in snapshot.pools:
        group.add(_pool_row(pool, label))
    if snapshot.boot is not None:
        group.add(_pool_row(snapshot.boot, label))
    return group


def drive_row(drive: DriveView, select: Select, busy: bool) -> Adw.ActionRow:
    """A drive's row: icon, name, state line, Back Up or a chevron."""
    row = Adw.ActionRow(title=drive.name, subtitle=drive.line, activatable=True)
    row.add_prefix(drive_icon(drive))
    if drive.mounted:
        for button in mounted_buttons(drive.name):
            row.add_suffix(button)
    elif drive.backup is not None and not busy:
        row.add_suffix(action_button(drive.backup, suggested=True))
    row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
    row.connect("activated", lambda _r: select(f"drive:{drive.name}"))
    return row


def pending_row(pending: PendingView, select: Select) -> Adw.ActionRow:
    """A pending drive's row, with the command that finishes it."""
    row = Adw.ActionRow(
        title=pending.name, subtitle=_("Prepared, not read back yet (apt was running)"), activatable=True
    )
    row.add_prefix(Gtk.Image.new_from_icon_name("document-open-recent-symbolic"))
    row.add_suffix(action_button(pending.action))
    row.connect("activated", lambda _r: select(f"pending:{pending.name}"))
    return row


def _drives(snapshot: Snapshot, select: Select) -> Gtk.Widget:
    if not snapshot.drives and not snapshot.pending:
        return states.no_drives()
    group = Adw.PreferencesGroup(title=_("Backup Drives"))
    busy = snapshot.run is not None
    for drive in snapshot.drives:
        group.add(drive_row(drive, select, busy))
    for pending in snapshot.pending:
        group.add(pending_row(pending, select))
    return group


def _notices(snapshot: Snapshot) -> Adw.PreferencesGroup | None:
    if not snapshot.notices:
        return None
    group = Adw.PreferencesGroup(title=_("Notices"))
    for notice in snapshot.notices:
        row = Adw.ActionRow(title=notice.title, subtitle=notice.text, subtitle_selectable=True)
        row.add_prefix(level_icon(notice.level))
        if notice.action is not None:
            row.add_suffix(action_button(notice.action))
        group.add(row)
    return group


def build(snapshot: Snapshot, select: Select) -> Gtk.Widget:
    """The Overview, or the "No Status Yet" page."""
    if snapshot.page == "no_status":
        return states.no_status()
    page = Adw.PreferencesPage()
    page.add(_computer(snapshot))
    drives = _drives(snapshot, select)
    if isinstance(drives, Adw.PreferencesGroup):
        page.add(drives)
    else:
        holder = Adw.PreferencesGroup()
        holder.add(drives)
        page.add(holder)
    notices = _notices(snapshot)
    if notices is not None:
        page.add(notices)
    return page
