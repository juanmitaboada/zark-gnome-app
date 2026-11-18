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

import functools
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango

from zark_app import compat
from zark_app.i18n import _
from zark_app.model import Action, DriveView, PendingView, PoolView, Snapshot, size_line
from zark_app.pages import states
from zark_app.units import fmt_since
from zark_app.usage import DatasetRow, Part, UsageView
from zark_app.widgets import action_button, level_bar, level_icon, mounted_buttons

Select = Callable[[str], None]
# A pool's table is sorted by "size" or "snapshots"; the window keeps the choice.
Sort = Callable[[str, str], None]

# The parts' colours, the extension's (its stylesheets, light and dark alike).
COLOURS = {
    "user-data": "#3584e4",
    "user-snapshots": "#99c1f1",
    "system-data": "#9141ac",
    "system-snapshots": "#dc8add",
    "other": "#b5835a",
    "metadata": "#9a9996",
    "free": "rgba(127,127,127,0.25)",
    "reserved": "rgba(127,127,127,0.6)",
}
# A connected drive: the theme's emblem, else GTK's own check mark.
CONNECTED_ICONS = ["emblem-ok-symbolic", "object-select-symbolic"]
BAR_HEIGHT = 12
SWATCH = 10


def drive_icon(drive: DriveView) -> Gtk.Widget:
    """The drive's status icon; each state also has words beside it."""
    if drive.state in ("running", "waiting"):
        return compat.spinner()
    names = {
        "attention": "dialog-error-symbolic" if drive.level == "error" else "dialog-warning-symbolic",
        "disconnected": "drive-harddisk-symbolic",
    }
    if drive.state == "connected":
        # Adwaita 50 has no emblem-ok-symbolic (G2); GTK ships object-select-symbolic itself.
        image = Gtk.Image.new_from_gicon(Gio.ThemedIcon.new_from_names(CONNECTED_ICONS))
    else:
        image = Gtk.Image.new_from_icon_name(names[drive.state])
    if drive.state == "attention":
        # A2E-4: red for a run cut short or not read back, amber otherwise.
        image.add_css_class("error" if drive.level == "error" else "warning")
    elif drive.state == "connected":
        image.add_css_class("success")
    else:
        image.add_css_class("dim-label")
    return image


def _pool_row(pool: PoolView, now_label: Callable[[PoolView], str], row: Any) -> None:
    """A pool's row (an action or expander row): its figures, age, level and bar."""
    row.set_title(pool.name)
    row.set_subtitle(size_line(pool.used, pool.size, pool.pct))
    row.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk-system-symbolic"))
    extra = now_label(pool)
    if extra:
        row.set_subtitle(f"{row.get_subtitle()} - {extra}")
    if pool.level in ("warning", "critical"):
        # The level in words too, in the subtitle so the narrow layout keeps it.
        word = (
            # TRANSLATORS: how full a pool is, lower case after a comma in its line.
            _("critical")
            if pool.level == "critical"
            # TRANSLATORS: how full a pool is, lower case after a comma in its line.
            else _("warning")
        )
        row.set_subtitle(f"{row.get_subtitle()}, {word}")
        row.add_suffix(level_icon(pool.level))
    if pool.pct is not None:
        row.add_suffix(level_bar(pool.pct / 100, pool.level))


def _rgba(spec: str) -> Gdk.RGBA:
    colour = Gdk.RGBA()
    colour.parse(spec)
    return colour


class ColourBar(Gtk.Widget):
    """Parts side by side in their colours, a rounded track around them;
    drawn with GTK's own snapshot (no cairo bindings). The legend says the
    figures in words, so the bar is not read out."""

    def __init__(self, parts: Sequence[tuple[str, int]], width: int = -1, height: int = BAR_HEIGHT) -> None:
        super().__init__(accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.parts = [(_rgba(COLOURS[part]), size) for part, size in parts]
        self.set_size_request(width, height)
        self.round = width < 0

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:  # pylint: disable=arguments-differ
        """Draw the parts left to right, each as wide as its share."""
        width, height = self.get_width(), self.get_height()
        total = sum(size for _c, size in self.parts)
        if width <= 0 or height <= 0 or total <= 0:
            return
        radius = height / 2 if self.round else 0.0
        bounds = Graphene.Rect().init(0, 0, width, height)
        clip = Gsk.RoundedRect()
        clip.init_from_rect(bounds, radius)
        snapshot.push_rounded_clip(clip)
        x = 0.0
        for colour, size in self.parts:
            span = width * size / total
            if span > 0:
                snapshot.append_color(colour, Graphene.Rect().init(x, 0, span, height))
                x += span
        snapshot.pop()


def _legend(parts: Sequence[Part]) -> Gtk.FlowBox:
    """Swatch, part and size; two columns where there is room."""
    box = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        homogeneous=True,
        min_children_per_line=1,
        max_children_per_line=2,
        column_spacing=24,
        row_spacing=4,
    )
    for part in parts:
        line = Gtk.Box(spacing=8)
        swatch = ColourBar([(part.id, 1)], SWATCH, SWATCH)
        swatch.set_valign(Gtk.Align.CENTER)
        line.append(swatch)
        line.append(Gtk.Label(label=part.label, xalign=0.0, hexpand=True))
        size = Gtk.Label(label=part.size, xalign=1.0)
        size.add_css_class("numeric")
        line.append(size)
        box.append(Gtk.FlowBoxChild(child=line, focusable=False))
    return box


def _plain_row(child: Gtk.Widget) -> Adw.PreferencesRow:
    child.set_margin_top(12)
    child.set_margin_bottom(12)
    child.set_margin_start(12)
    child.set_margin_end(12)
    row = Adw.PreferencesRow(activatable=False, focusable=False)
    row.set_child(child)
    return row


def _sort_button(title: str, on: bool, pick: Callable[[], None]) -> Gtk.ToggleButton:
    """A column title that sorts the table: a toggle button, pressed for the
    active order, so a screen reader says which one is (A13R-3)."""
    box = Gtk.Box(spacing=2, halign=Gtk.Align.END)
    box.append(Gtk.Label(label=title))
    if on:
        box.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
    button = Gtk.ToggleButton(child=box, halign=Gtk.Align.END, active=on)
    button.add_css_class("flat")
    if not on:
        button.add_css_class("dim-label")
    button.connect("toggled", lambda b: pick() if b.get_active() else None)
    return button


def _descendants(widget: Gtk.Widget) -> list[Gtk.Widget]:
    out: list[Gtk.Widget] = []
    child = widget.get_first_child()
    while child is not None:
        out.append(child)
        out.extend(_descendants(child))
        child = child.get_next_sibling()
    return out


def sort_button(widget: Gtk.Widget, pool: str) -> Gtk.ToggleButton | None:
    """The pressed sort button of ``pool``'s table under ``widget``."""
    for row in _descendants(widget):
        if isinstance(row, Adw.ExpanderRow) and row.get_title() == pool:
            return next(
                (b for b in _descendants(row) if isinstance(b, Gtk.ToggleButton) and b.get_active()), None
            )
    return None


def _name_label(row: DatasetRow) -> Gtk.Label:
    label = Gtk.Label(xalign=0.0, hexpand=True, ellipsize=Pango.EllipsizeMode.START)
    if row.prefix:
        # The shared part dimmed, as the extension, so the rest stands out.
        prefix = GLib.markup_escape_text(row.prefix)
        label.set_markup(f'<span alpha="55%">{prefix}</span>{GLib.markup_escape_text(row.name)}')
    else:
        label.set_label(row.name)
    label.set_tooltip_text(row.prefix + row.name)
    return label


def _table(usage: UsageView, sort: str, pick: Callable[[str], None]) -> Gtk.Grid:
    grid = Gtk.Grid(column_spacing=18, row_spacing=4)
    head = Gtk.Label(label=_("Dataset"), xalign=0.0, hexpand=True)
    head.add_css_class("dim-label")
    grid.attach(head, 0, 0, 1, 1)
    columns = (
        # TRANSLATORS: a column title: the space a dataset's own data takes
        ("size", _("Data")),
        # TRANSLATORS: a column title: the space a dataset's snapshots take
        ("snapshots", _("Snapshots")),
    )
    buttons = [_sort_button(title, key == sort, functools.partial(pick, key)) for key, title in columns]
    # One group: one order always pressed; pressing the other sorts by it.
    buttons[1].set_group(buttons[0])
    for index, button in enumerate(buttons, start=1):
        grid.attach(button, index, 0, 1, 1)
    rows = usage.by_snapshots if sort == "snapshots" else usage.by_size
    for index, row in enumerate(rows, start=1):
        grid.attach(_name_label(row), 0, index, 1, 1)
        for column, text in ((1, row.data), (2, row.snapshots)):
            cell = Gtk.Label(label=text, xalign=1.0, margin_end=12)
            cell.add_css_class("numeric")
            grid.attach(cell, column, index, 1, 1)
    return grid


def _reclaim() -> Gtk.Button:
    # zark prune's first question offers origin (the closing map's row).
    return action_button(Action(_("Reclaim Space..."), "prune"))


def pool_details(pool: PoolView, sort: str, on_sort: Sort) -> list[Gtk.Widget]:
    """A source pool's expanded rows (A13): the parts of its space, what its
    snapshots hold with Reclaim Space, its datasets and the note."""
    usage = pool.usage
    if usage is None:
        line = Adw.ActionRow(title=_("zark could not list this pool's datasets: the notices below say why"))
        line.add_suffix(_reclaim())
        return [line]
    parts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    parts.append(ColourBar([(p.id, p.bytes) for p in usage.segments]))
    parts.append(_legend(usage.legend))
    snapshots = Adw.ActionRow(title=usage.snapshots)
    snapshots.add_suffix(_reclaim())
    table = _table(usage, sort, lambda key: on_sort(pool.name, key))
    note = Gtk.Label(label=usage.note, xalign=0.0, wrap=True)
    note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    note.add_css_class("dim-label")
    note.add_css_class("caption")
    return [_plain_row(parts), snapshots, _plain_row(table), _plain_row(note)]


def _computer(snapshot: Snapshot, sorts: Mapping[str, str], on_sort: Sort) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=_("This Computer"))
    group.set_description(
        _("Live figures from {command}").format(command="zpool list")
        if snapshot.pools_live
        else _("Figures from zark's status file")
    )

    def label(pool: PoolView) -> str:
        if pool.live or pool.measured_at is None:
            return ""
        return _("measured {age}").format(age=fmt_since(pool.measured_at, snapshot.now))

    for pool in (*snapshot.pools, *([snapshot.boot] if snapshot.boot is not None else [])):
        if not pool.source:
            # /boot's ext4 partition: its figures only.
            row = Adw.ActionRow()
            _pool_row(pool, label, row)
            group.add(row)
            continue
        expander = Adw.ExpanderRow()
        _pool_row(pool, label, expander)
        for child in pool_details(pool, sorts.get(pool.name, "size"), on_sort):
            expander.add_row(child)
        group.add(expander)
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


def build(
    snapshot: Snapshot,
    select: Select,
    sorts: Mapping[str, str] | None = None,
    on_sort: Sort | None = None,
) -> Gtk.Widget:
    """The Overview, or the "No Status Yet" page. ``sorts`` holds each
    pool's table order, which ``on_sort`` changes."""
    if snapshot.page == "no_status":
        return states.no_status()
    page = Adw.PreferencesPage()
    page.add(_computer(snapshot, sorts or {}, on_sort or (lambda _p, _k: None)))
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
