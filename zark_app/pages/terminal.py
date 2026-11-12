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
"""The run page of a run the app started (design 2.3, 4.1;
``run-page-terminal.svg``): the progress card from ``progress.json``, the
result when it ends, and zark's terminal under the caption.

One page per run, kept while the run lasts: a redraw updates its top part
and never takes the terminal out of the page, since an unrealized terminal
stops passing what is written to it (a Stop's Ctrl+C among them).
"""

from gi.repository import Adw, Gtk

from zark_app.i18n import _
from zark_app.model import Snapshot
from zark_app.pages import run as run_page
from zark_app.runner import Run, outcome_text


class RunPage:
    """The page; :attr:`widget` goes into the window's content."""

    def __init__(self, run: Run) -> None:
        self.run = run
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.widget, f"set_margin_{side}")(12)
        self.top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.append(self.top)
        caption = Gtk.Label(label=_("zark's output - answer its questions here"), xalign=0.0)
        caption.add_css_class("heading")
        self.widget.append(caption)
        self.holder = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.holder.add_css_class("card")
        self.holder.set_child(run.terminal)
        self.widget.append(self.holder)

    def update(self, snapshot: Snapshot) -> None:
        """The card, the waiting line or the result, from the snapshot."""
        while (child := self.top.get_first_child()) is not None:
            self.top.remove(child)
        run = self.run
        mine = snapshot.run is not None and run.pid is not None and snapshot.run.pid == run.pid
        if run.outcome is not None:
            title, subtitle = outcome_text(run.outcome, run.command.title)
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            group = Adw.PreferencesGroup()
            group.add(row)
            self.top.append(group)
        elif mine and snapshot.run is not None:
            self.top.append(run_page.card(snapshot, snapshot.run))
        else:
            # pkexec gives no sign when the password is in, and not every
            # command writes progress.json: say what is true either way.
            row = Adw.ActionRow(
                title=_("Stopping, zark is cleaning up") if run.stopping else run.command.title,
                subtitle="" if run.stopping else _("GNOME asks for the administrator's password first"),
            )
            group = Adw.PreferencesGroup()
            group.add(row)
            self.top.append(group)
