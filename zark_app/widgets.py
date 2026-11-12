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
"""Small widgets the pages share."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, Gtk

from zark_app.i18n import _
from zark_app.model import Action

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ICON_FOR_LEVEL = {
    "info": "dialog-information-symbolic",
    "warning": "dialog-warning-symbolic",
    "critical": "dialog-error-symbolic",
}


RUN_ACTION = "win.run"


def run_target(action: Action) -> GLib.Variant:
    """The ``win.run`` target of an action: its operation and argument."""
    return GLib.Variant("(ss)", (action.op, action.arg))


def action_button(action: Action, suggested: bool = False) -> Gtk.Button:
    """A button that runs its operation (A2-5: no copy items). While zark is
    busy the window disables ``win.run``, and every such button with it."""
    button = Gtk.Button(label=action.label, valign=Gtk.Align.CENTER)
    # The target first: an action name without its target warns.
    button.set_action_target_value(run_target(action))
    button.set_action_name(RUN_ACTION)
    if suggested:
        button.add_css_class("suggested-action")
    return button


def mounted_buttons(drive: str) -> list[Gtk.Button]:
    """A drive mounted for browsing (A1E-6): Open in Files and Unmount, as
    icon buttons with their names as tooltip and accessible label."""
    open_ = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
    open_.set_action_target_value(GLib.Variant("s", drive))
    open_.set_action_name("win.open-files")
    unmount = Gtk.Button(icon_name="media-eject-symbolic", valign=Gtk.Align.CENTER)
    unmount.set_action_target_value(run_target(Action(_("Unmount"), "umount", drive)))
    unmount.set_action_name(RUN_ACTION)
    for button, label in ((open_, _("Open in Files")), (unmount, _("Unmount"))):
        button.add_css_class("flat")
        button.set_tooltip_text(label)
        button.update_property([Gtk.AccessibleProperty.LABEL], [label])
    return [open_, unmount]


def property_row(title: str, value: str, subtitle_selectable: bool = False) -> Adw.ActionRow:
    """A read-only fact: the title dimmed, the value emphasised (``.property``,
    libadwaita 1.4)."""
    row = Adw.ActionRow(title=title, subtitle=value, subtitle_selectable=subtitle_selectable)
    row.add_css_class("property")
    return row


def level_bar(fraction: float, level: str = "ok") -> Gtk.LevelBar:
    """A fill meter; libadwaita colours its ``high`` and ``full`` offsets."""
    meter = Gtk.LevelBar(min_value=0.0, max_value=1.0, value=min(max(fraction, 0.0), 1.0))
    meter.set_size_request(96, -1)
    meter.set_valign(Gtk.Align.CENTER)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_LOW)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_HIGH)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_FULL)
    if level == "critical":
        meter.add_css_class("error")
    elif level == "warning":
        meter.add_css_class("warning")
    return meter


def level_icon(level: str) -> Gtk.Image:
    """A notice's icon, with its level as the accessible name: no state is
    told by colour alone."""
    image = Gtk.Image.new_from_icon_name(ICON_FOR_LEVEL.get(level, "dialog-information-symbolic"))
    if level == "critical":
        image.add_css_class("error")
    elif level == "warning":
        image.add_css_class("warning")
    return image


def mark_paintable(dark: bool) -> Gdk.Paintable | None:
    """zark's mark for status pages, its white-sector variant in dark style."""
    path = DATA_DIR / "images" / ("zark-mark-dark.svg" if dark else "zark-mark.svg")
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        return None


def status_page(title: str, description: str, action: Action | None = None) -> Adw.StatusPage:
    """A whole-page state with zark's mark (design section 5)."""
    dark = Adw.StyleManager.get_default().get_dark()
    page = Adw.StatusPage(title=title, description=description, vexpand=True)
    paintable = mark_paintable(dark)
    if paintable is not None:
        page.set_paintable(paintable)
    else:
        page.set_icon_name("com.juanmitaboada.Zark-symbolic")
    if action is not None:
        button = action_button(action, suggested=True)
        button.set_halign(Gtk.Align.CENTER)
        button.add_css_class("pill")
        page.set_child(button)
    return page


@dataclass(frozen=True)
class ViewState:
    """Where a page was scrolled to and which of its expander rows were
    open, to carry over to the page that replaces it."""

    scroll: float
    expanded: frozenset[str]


def _descendants(widget: Gtk.Widget) -> Iterator[Gtk.Widget]:
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from _descendants(child)
        child = child.get_next_sibling()


def _scrolled(widget: Gtk.Widget) -> Gtk.ScrolledWindow | None:
    if isinstance(widget, Gtk.ScrolledWindow):
        return widget
    return next((w for w in _descendants(widget) if isinstance(w, Gtk.ScrolledWindow)), None)


def view_state(widget: Gtk.Widget) -> ViewState:
    """The scroll position of ``widget``'s first scrolled window and the
    titles of its expanded expander rows."""
    scrolled = _scrolled(widget)
    scroll = scrolled.get_vadjustment().get_value() if scrolled is not None else 0.0
    expanded = frozenset(
        w.get_title() for w in _descendants(widget) if isinstance(w, Adw.ExpanderRow) and w.get_expanded()
    )
    return ViewState(scroll, expanded)


# How long a restored position waits for the new page's rows to be laid
# out; past it the user's own scrolling wins.
RESTORE_S = 2


def restore_view_state(widget: Gtk.Widget, state: ViewState) -> None:
    """Open the same expander rows in ``widget`` and scroll it to the same
    place once its content is tall enough to get there."""
    for row in _descendants(widget):
        if isinstance(row, Adw.ExpanderRow) and row.get_title() in state.expanded:
            row.set_expanded(True)
    scrolled = _scrolled(widget)
    if scrolled is None or state.scroll <= 0:
        return
    adjustment = scrolled.get_vadjustment()

    def apply(adj: Gtk.Adjustment) -> None:
        adj.set_value(state.scroll)
        # Reached once the page is laid out tall enough: stop following it.
        if adj.get_upper() - adj.get_page_size() >= state.scroll and handler[0]:
            adj.disconnect(handler[0])
            handler[0] = 0

    def give_up() -> bool:
        if handler[0]:
            adjustment.disconnect(handler[0])
            handler[0] = 0
        return False

    handler = [adjustment.connect("changed", apply)]
    apply(adjustment)
    if handler[0]:
        GLib.timeout_add_seconds(RESTORE_S, give_up)
