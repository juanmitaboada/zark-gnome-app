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
"""The main window (design 1.2): a sidebar of what the user manages and a
content page per item, a banner for the most urgent note, and the narrow
layout from a breakpoint.

It reads on file events, re-applies the clock rules every few seconds,
and refetches the live figures at start, on Ctrl+R and when ``status.json``
changes or a run ends. It writes nothing and takes no lock.
"""

# The window owns the app's state machine; splitting it would only move
# its fields around.
# pylint: disable=too-many-instance-attributes

from typing import Any

from gi.repository import Adw, Gio, GLib, Gtk, Pango

from zark_app import about, compat, model, shortcuts
from zark_app.i18n import _
from zark_app.live import Fetcher, Live
from zark_app.model import Action, DriveView, Snapshot
from zark_app.pages import drive as drive_page, exclusions, overview, pending, run, states
from zark_app.reader import Loaded
from zark_app.sources import Sources
from zark_app.units import fmt_since
from zark_app.widgets import copy_button, copy_tooltip

TICK_S = 5
NARROW = "max-width: 600sp"


class SidebarRow(Gtk.ListBoxRow):
    """A sidebar row with its key and section."""

    def __init__(self, key: str, section: str, title: str, subtitle: str, icon: Gtk.Widget) -> None:
        super().__init__()
        self.key = key
        self.section = section
        box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        box.append(icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        texts.append(Gtk.Label(label=title, xalign=0.0, ellipsize=Pango.EllipsizeMode.END))
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0.0, ellipsize=Pango.EllipsizeMode.END)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            texts.append(sub)
        box.append(texts)
        self.set_child(box)
        self.update_property([Gtk.AccessibleProperty.LABEL], [f"{title}, {subtitle}" if subtitle else title])


class ZarkWindow(Adw.ApplicationWindow):
    """The one window."""

    def __init__(self, app: Adw.Application, sources: Sources, loaded: Loaded, watch: bool = True) -> None:
        super().__init__(application=app, title="zark", default_width=1000, default_height=720)
        self.set_size_request(360, 360)
        self.sources = sources
        self.loaded = loaded
        self.live = Live()
        self.last_good: Any = None
        self.snapshot: Snapshot | None = None
        self.selected = "overview"
        self._fetcher = Fetcher(sources.runner, sources.now)
        self._status_key: Any = None
        self._was_running = False
        self._monitors: list[Gio.FileMonitor] = []
        self._rebuilding = False
        self._header_widgets: list[Gtk.Widget] = []
        self._build_ui()
        self._add_actions()
        self.refresh(live=True)
        if watch:
            self._watch()
            GLib.timeout_add_seconds(TICK_S, self._tick)

    # --- layout ---

    def _build_ui(self) -> None:
        self.toasts = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(min_sidebar_width=240, max_sidebar_width=300)
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        sidebar_view = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", primary=True)
        self.menu_button.set_tooltip_text(_("Main Menu"))
        self.menu_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Main Menu")])
        sidebar_header.pack_end(self.menu_button)
        sidebar_view.add_top_bar(sidebar_header)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.set_header_func(self._header)
        self.list.connect("row-selected", self._row_selected)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scrolled.set_child(self.list)
        sidebar_view.set_content(scrolled)
        self.split.set_sidebar(Adw.NavigationPage(title="zark", child=sidebar_view))

        self.content_view = Adw.ToolbarView()
        self.content_header = Adw.HeaderBar()
        self.title = Adw.WindowTitle(title=_("Overview"))
        self.content_header.set_title_widget(self.title)
        self.content_view.add_top_bar(self.content_header)
        self.banner = Adw.Banner(revealed=False)
        self.content_view.add_top_bar(self.banner)
        self.content_page = Adw.NavigationPage(title=_("Overview"), child=self.content_view)
        self.split.set_content(self.content_page)

        breakpoint_ = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(NARROW))
        breakpoint_.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint_)

    def _header(self, row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
        section = getattr(row, "section", "")
        previous = getattr(before, "section", None) if before is not None else None
        titles = {"drives": _("Backup Drives"), "settings": _("Settings")}
        if section in titles and section != previous:
            label = Gtk.Label(label=titles[section], xalign=0.0, margin_top=12, margin_start=12)
            label.add_css_class("heading")
            label.add_css_class("dim-label")
            row.set_header(label)
        else:
            row.set_header(None)

    def _add_actions(self) -> None:
        for name, callback in (
            ("reload", lambda *_a: self.reload()),
            ("back", lambda *_a: self.split.set_show_content(False)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        select = Gio.SimpleAction.new("select-index", GLib.VariantType.new("i"))
        select.connect("activate", lambda _a, v: self.select_index(v.get_int32()))
        self.add_action(select)
        files = Gio.SimpleAction.new("open-files", GLib.VariantType.new("s"))
        files.connect("activate", lambda _a, v: self._open_files(v.get_string()))
        self.add_action(files)

    # --- reading ---

    def _watch(self) -> None:
        if self.loaded.module is None:
            return
        for path in self.loaded.module.paths(self.sources.root):
            monitor = Gio.File.new_for_path(str(path)).monitor_file(Gio.FileMonitorFlags.NONE, None)
            monitor.connect("changed", lambda *_a: self.refresh())
            self._monitors.append(monitor)

    def _tick(self) -> bool:
        self.refresh()
        return True

    def reload(self) -> None:
        """Ctrl+R: read the files and the live figures again."""
        self.refresh(live=True)

    def refresh(self, live: bool = False) -> None:
        """Read both files and redraw what changed; ``live`` refetches the
        live figures first."""
        snap, self.last_good = model.build(self.loaded, self.sources, self.live, self.last_good)
        key = (snap.generated_at, snap.status_class)
        running = snap.run is not None
        changed = key != self._status_key or (self._was_running and not running)
        self._status_key, self._was_running = key, running
        self._show(snap)
        if live or (changed and self.snapshot is not None and self.loaded.module is not None):
            self._fetcher.fetch(model.source_pool_names(snap), self._got_live)

    def _got_live(self, live: Live) -> None:
        self.live = live
        snap, self.last_good = model.build(self.loaded, self.sources, self.live, self.last_good)
        self._show(snap)

    # --- drawing ---

    def _show(self, snap: Snapshot) -> None:
        if self.snapshot is not None and snap == self.snapshot:
            self.snapshot = snap
            return
        self.snapshot = snap
        self._menu(snap)
        self._sidebar(snap)
        self._banner(snap.banner)
        self._content()

    def _menu(self, snap: Snapshot) -> None:
        menu = Gio.Menu()
        for section in model.primary_actions(snap.timer_installed):
            part = Gio.Menu()
            for action in section:
                part.append_item(_copy_item(action))
            menu.append_section(None, part)
        last = Gio.Menu()
        last.append(_("Keyboard Shortcuts"), "app.shortcuts")
        last.append(_("About zark"), "app.about")
        menu.append_section(None, last)
        self.menu_button.set_menu_model(menu)

    def _sidebar(self, snap: Snapshot) -> None:
        self._rebuilding = True
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        rows: list[SidebarRow] = []
        if snap.run is not None:
            sub = _("Waiting for your answer") if snap.run.waiting else _step(snap)
            rows.append(SidebarRow("run", "run", snap.run.title, sub, _spinner()))
        rows.append(SidebarRow("overview", "top", _("Overview"), "", _icon("view-grid-symbolic")))
        if snap.page == "ok":
            for d in snap.drives:
                rows.append(SidebarRow(f"drive:{d.name}", "drives", d.name, d.short, overview.drive_icon(d)))
            for p in snap.pending:
                rows.append(
                    SidebarRow(
                        f"pending:{p.name}",
                        "drives",
                        p.name,
                        _("Not read back yet"),
                        _icon("document-open-recent-symbolic"),
                    )
                )
            rows.append(SidebarRow("exclusions", "settings", _("Exclusions"), "", _icon("folder-symbolic")))
        keys = [r.key for r in rows]
        if self.selected not in keys:
            self.selected = "overview"
        for r in rows:
            self.list.append(r)
            if r.key == self.selected:
                self.list.select_row(r)
        self._rebuilding = False

    def _banner(self, banner: model.BannerView | None) -> None:
        if banner is None:
            self.banner.set_revealed(False)
            return
        self.banner.set_title(banner.text)
        if banner.action is not None:
            self.banner.set_button_label(banner.action.label)
            self.banner.set_action_target_value(GLib.Variant("s", banner.action.command))
            self.banner.set_action_name("app.copy")
            self.banner.set_tooltip_text(copy_tooltip(banner.action))
        else:
            self.banner.set_action_name(None)
            self.banner.set_button_label(None)
            self.banner.set_tooltip_text(None)
        self.banner.set_revealed(True)

    def _row_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if self._rebuilding or row is None:
            return
        self.selected = getattr(row, "key", "overview")
        self._content()
        self.split.set_show_content(True)

    def select(self, key: str) -> None:
        """Show the page of ``key`` (``overview``, ``drive:<name>``, ...)."""
        index = 0
        while (row := self.list.get_row_at_index(index)) is not None:
            if getattr(row, "key", None) == key:
                self.list.select_row(row)
                return
            index += 1

    def select_index(self, n: int) -> None:
        """Ctrl+1 to Ctrl+9: Overview, then the drives in order."""
        snap = self.snapshot
        if n == 1:
            self.select("overview")
        elif snap is not None and 0 <= n - 2 < len(snap.drives):
            self.select(f"drive:{snap.drives[n - 2].name}")

    def _set_header(self, widgets: list[Gtk.Widget]) -> None:
        for w in self._header_widgets:
            self.content_header.remove(w)
        self._header_widgets = widgets
        for w in reversed(widgets):
            self.content_header.pack_end(w)

    def _content(self) -> None:
        snap = self.snapshot
        if snap is None:
            return
        title, subtitle, body, header = self._page(snap)
        self.title.set_title(title)
        self.title.set_subtitle(subtitle)
        self.content_page.set_title(title)
        self._set_header(header)
        self.content_view.set_content(body)

    # One return per page of the sidebar.
    def _page(  # pylint: disable=too-many-return-statements
        self, snap: Snapshot
    ) -> tuple[str, str, Gtk.Widget, list[Gtk.Widget]]:
        if snap.page == "no_zark":
            return "zark", "", states.no_zark(snap.detail), []
        if snap.page == "too_old":
            return "zark", "", states.too_old(snap), []
        updated = (
            _("Status updated {age}").format(age=fmt_since(snap.generated_at, snap.now))
            if snap.generated_at is not None
            else ""
        )
        key = self.selected
        if key == "run" and snap.run is not None:
            return snap.run.title, _step(snap), run.build(snap), []
        if key.startswith("drive:"):
            d = next((x for x in snap.drives if x.name == key[6:]), None)
            if d is not None:
                return d.name, d.line, drive_page.build(snap, d), self._drive_header(snap, d)
        if key.startswith("pending:"):
            p = next((x for x in snap.pending if x.name == key[8:]), None)
            if p is not None:
                return p.name, _("Not read back yet"), pending.build(p), []
        if key == "exclusions":
            return _("Exclusions"), updated, exclusions.build(snap), [copy_button(exclusions.header_action())]
        return _("Overview"), updated, overview.build(snap, self.select), []

    def _drive_header(self, snap: Snapshot, drive: DriveView) -> list[Gtk.Widget]:
        busy = snap.run is not None
        if drive.backup is not None and not busy:
            back = copy_button(drive.backup, suggested=True)
        else:
            back = Gtk.Button(label=_("Back Up"), sensitive=False)
            back.set_tooltip_text(
                _("zark is busy") if busy else _("Connect {drive} to back up").format(drive=drive.name)
            )
        menu = Gio.Menu()
        if drive.mounted:
            part = Gio.Menu()
            part.append(_("Open in Files"), f"win.open-files('{drive.name}')")
            menu.append_section(None, part)
        for section in model.drive_actions(drive.name, drive.doc, drive.mounted):
            part = Gio.Menu()
            for action in section:
                part.append_item(_copy_item(action))
            menu.append_section(None, part)
        more = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=menu)
        more.set_tooltip_text(_("Drive Menu"))
        more.update_property([Gtk.AccessibleProperty.LABEL], [_("Drive Menu")])
        return [back, more]

    def _open_files(self, pool: str) -> None:
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(str(model.mount_dir(pool))))
        launcher.launch(self, None, None)

    def toast(self, text: str) -> None:
        """A short message over the content."""
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def show_about(self) -> None:
        """About zark."""
        if self.snapshot is not None:
            about.show(self, self.snapshot)

    def show_shortcuts(self) -> None:
        """The shortcuts help."""
        shortcuts.show(self)


def _copy_item(action: Action) -> Gio.MenuItem:
    item = Gio.MenuItem.new(action.label, None)
    item.set_action_and_target_value("app.copy", GLib.Variant("s", action.command))
    return item


def _icon(name: str) -> Gtk.Image:
    return Gtk.Image.new_from_icon_name(name)


def _spinner() -> Gtk.Widget:
    return compat.spinner()


def _step(snap: Snapshot) -> str:
    r = snap.run
    if r is None:
        return ""
    if r.step_index is not None and r.step_total is not None:
        text = _("Step {i} of {n}").format(i=r.step_index, n=r.step_total)
        if r.fraction is not None:
            text += f", {int(r.fraction * 100)} %"
        return text
    return ""
