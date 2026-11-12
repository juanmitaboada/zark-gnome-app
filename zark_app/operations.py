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
"""Operations: from a button to a zark run and back (A2 plan sections 2
and 3).

A button names an operation and its argument (:class:`zark_app.model.Action`);
this module asks what the operation still needs (a dialog), builds the
checked command (:mod:`zark_app.commands`), runs it in a terminal
(:mod:`zark_app.runner`), and turns its end into the result row. One run at
a time: zark's lock admits one.
"""

# The controller keeps the run's whole lifecycle in one place.
# pylint: disable=too-many-instance-attributes

from typing import TYPE_CHECKING, Any

from gi.repository import Adw, Gio, Gtk

from zark_app import commands, dialogs
from zark_app.commands import Command, CommandError, Context, Retention
from zark_app.i18n import _
from zark_app.model import Snapshot
from zark_app.runner import Run, classify, outcome_text

if TYPE_CHECKING:
    from zark_app.window import ZarkWindow

NOTIFICATION = "zark-waiting"
# Ops that need a dialog before the command exists.
DIALOG_OPS = ("retention", "exclude-add", "prepare")


def context(snapshot: Snapshot | None, by_id: Any) -> Context:
    """What :func:`zark_app.commands.build` checks against, from the snapshot."""
    if snapshot is None or snapshot.status is None:
        return Context(drives={}, by_id=by_id)
    drives = {str(d.name): d.doc for d in snapshot.drives}
    excluded: dict[str, frozenset[str]] = {}
    for e in snapshot.exclusions or ():
        words = {w for w, on in (("backups", e.backups), ("snapshots", e.snapshots)) if on}
        excluded[e.dataset] = frozenset(words)
    return Context(
        drives=drives,
        pending=frozenset(p.name for p in snapshot.pending),
        by_id=by_id,
        datasets=frozenset(snapshot.datasets),
        excluded=excluded,
    )


class Operations:
    """The window's runs."""

    def __init__(self, window: "ZarkWindow") -> None:
        self.window = window
        self.run: Run | None = None
        self.close_after = False
        self._inhibit = 0
        self._notified = False
        self._was_waiting = False

    # --- state ---

    def busy(self) -> bool:
        """A run of the app's, or any zark run in ``progress.json``."""
        snap = self.window.snapshot
        return (self.run is not None and self.run.alive) or (snap is not None and snap.run is not None)

    def alive(self) -> bool:
        """The app's own run still has its child."""
        return self.run is not None and self.run.alive

    # --- from a button ---

    def dispatch(self, op: str, arg: str) -> None:
        """Run ``op`` with ``arg``, after its dialog when it has one."""
        if self.busy():
            self.window.toast(_("zark is busy"))
            return
        snap = self.window.snapshot
        if op == "retention":
            doc = next((d.doc for d in snap.drives if d.name == arg), None) if snap else None
            current = doc.get("retention") if isinstance(doc, dict) else None
            dialogs.retention(
                self.window,
                arg,
                current if isinstance(current, dict) else {},
                lambda values: self._start(op, arg, values),
            )
            return
        if op == "exclude-add":
            excluded = {e.dataset for e in (snap.exclusions or ())} if snap else set()
            datasets = [d for d in (snap.datasets if snap else ()) if d not in excluded]
            dialogs.exclude(self.window, datasets, lambda ds, word: self._start(op, f"{ds}\t{word}"))
            return
        if op == "prepare":
            ctx = context(snap, self.window.sources.by_id)
            names = commands.disk_candidates(ctx.by_id, ctx.drives)
            disks = [(n, commands.disk_label(ctx.by_id, n)) for n in names]
            dialogs.prepare(self.window, disks, lambda name: self._start(op, name))
            return
        self._start(op, arg)

    def _start(self, op: str, arg: str, values: Retention | None = None) -> None:
        try:
            command = commands.build(
                op, arg, context(self.window.snapshot, self.window.sources.by_id), values
            )
            argv = commands.argv(command, self.window.sources.pkexec_prefix, self.window.sources.zark_path)
        except CommandError as e:
            self.window.toast(str(e))
            return
        self.start(command, argv)

    def start(self, command: Command, argv: list[str]) -> None:
        """Spawn ``argv`` for ``command`` and show its run page."""
        if self.busy():
            self.window.toast(_("zark is busy"))
            return
        self.run = Run(command, argv, self._exited, self._ask_stop)
        self.close_after = False
        app = self.window.get_application()
        if app is not None:
            app.hold()
            reason = command.title
            self._inhibit = app.inhibit(
                self.window,
                Gtk.ApplicationInhibitFlags.LOGOUT | Gtk.ApplicationInhibitFlags.SUSPEND,
                reason,
            )
        self.window.style_terminal()
        self.run.start()
        self.window.select_run()

    # --- while it runs ---

    def observe(self, snapshot: Snapshot) -> None:
        """Called with every snapshot: this run's ``progress.json`` and its
        questions."""
        run = self.run
        if run is None or not run.alive:
            return
        mine = snapshot.run is not None and run.pid is not None and snapshot.run.pid == run.pid
        if mine:
            run.saw_progress = True
        waiting = bool(mine and snapshot.run is not None and snapshot.run.waiting)
        if waiting and not self._was_waiting:
            run.terminal.grab_focus()
            self.window.say(_("zark is waiting for your answer"))
            if not self.window.is_active():
                self._notify(snapshot.run.waiting_for if snapshot.run else "")
        if not waiting and self._notified:
            self._withdraw()
        self._was_waiting = waiting

    def _notify(self, text: str) -> None:
        app = self.window.get_application()
        if app is None:
            return
        note = Gio.Notification.new(_("zark is waiting for your answer"))
        if text:
            note.set_body(text)
        note.set_default_action("app.present")
        app.send_notification(NOTIFICATION, note)
        self._notified = True

    def _withdraw(self) -> None:
        app = self.window.get_application()
        if app is not None:
            app.withdraw_notification(NOTIFICATION)
        self._notified = False

    # --- stopping ---

    def _ask_stop(self, _run: Run) -> None:
        self.ask_stop(closing=False)

    def ask_stop(self, closing: bool) -> None:
        """Stop..., Ctrl+C in the terminal, Close and Quit: one question."""
        run = self.run
        if run is None or not run.alive:
            return
        if run.stopping:
            # zark ignores further signals while it cleans up.
            if closing:
                self.close_after = True
            return

        def stop() -> None:
            self.close_after = closing
            self.stop()

        dialogs.stop(self.window, run.command.word == "backup", closing, stop)

    def stop(self) -> None:
        """Ctrl+C to zark; the page says it is cleaning up."""
        if self.run is not None and self.run.stop():
            self.window.redraw()

    # --- the end ---

    def _exited(self, run: Run) -> None:
        snap = self.window.snapshot
        other = snap is not None and snap.run is not None and snap.run.pid != run.pid
        if run.outcome is None and run.status is not None:
            run.outcome = classify(run.status, run.saw_progress, other)
        if self._notified:
            self._withdraw()
        app = self.window.get_application()
        if app is not None:
            if self._inhibit:
                app.uninhibit(self._inhibit)
                self._inhibit = 0
            app.release()
        if self.close_after or self.window.gone:
            if not self.window.gone:
                self.window.close_now()
            return
        kind = run.outcome.kind if run.outcome is not None else None
        if kind == "cancelled":
            # 126 (the dialog dismissed) or a Stop before zark started: nothing happened.
            self.done()
            return
        if kind in ("not_authorized", "busy", "updates") and run.outcome is not None:
            # Design 5: an alert, and back to where the user was.
            title, body = outcome_text(run.outcome, run.command.title)
            self.done()
            alert = Adw.AlertDialog.new(title, body)
            alert.add_response("close", _("Close"))
            alert.present(self.window)
            return
        self.window.refresh(live=True)
        self.window.redraw()
        self.window.say(run.command.title + ": " + run.outcome.kind if run.outcome else "")

    def done(self) -> None:
        """Done: the terminal goes; back to the page before the run."""
        if self.run is not None and self.run.alive:
            return
        self.run = None
        self.window.leave_run()
