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
"""A zark command run by the app, hosted in a ``Vte.Terminal`` (design 4.1,
A2 plan section 3).

VTE forks pkexec from the app's main thread, makes the pty its controlling
terminal, and pkexec ``execv``s zark in that process: zark owns the
terminal, its questions work as on any terminal, and the app writes to it
only what the user types and Ctrl+C for Stop.

The ``Vte.Terminal`` lives as long as the child: disposing it closes the
pty's master, which hangs the terminal up and stops zark (SIGHUP). The page
that shows it only borrows it.
"""

import os
import signal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from gi.repository import Gdk, GLib, Gtk, Vte

from zark_app.commands import Command
from zark_app.i18n import _

# VTE's VTE_SPAWN_NO_PARENT_ENVV (vtepty.h): the child gets only the list
# below, not the app's environment (A2R-1: a SHELL outside /etc/shells makes
# pkexec exit 127).
NO_PARENT_ENVV = 1 << 25
SCROLLBACK = 10000

Kind = Literal[
    "cancelled", "not_authorized", "done", "failed", "usage", "busy", "updates", "stopped", "killed"
]


@dataclass(frozen=True)
class Outcome:
    """How a run ended, for the result row (A2 plan 3.3)."""

    kind: Kind
    code: int | None
    signal: int | None = None


def child_env(environ: Mapping[str, str]) -> list[str]:
    """The child's whole environment: the session's locale and nothing else
    (VTE adds TERM, COLORTERM and VTE_VERSION; pkexec sets PATH)."""
    keys = sorted(k for k in environ if k == "LANG" or k.startswith("LC_"))
    return [f"{k}={environ[k]}" for k in keys]


def classify(wait_status: int, saw_progress: bool, other_run: bool) -> Outcome:
    """The exit table of the A2 plan, 3.3. ``saw_progress``: this run wrote
    ``progress.json`` (zark started); ``other_run``: another run's
    ``progress.json`` exists (for exit 75)."""
    code = os.waitstatus_to_exitcode(wait_status)
    if code < 0:
        # A2R-2: a signal before zark started (Stop during the password
        # dialog) is a cancel, not an orphan.
        return Outcome("killed" if saw_progress else "cancelled", None, -code)
    table: dict[int, Kind] = {0: "done", 1: "failed", 2: "usage", 126: "cancelled", 127: "not_authorized"}
    if code in table:
        return Outcome(table[code], code)
    if code == 75:
        return Outcome("busy" if other_run else "updates", code)
    if code in (129, 130, 141, 143):
        return Outcome("stopped", code)
    return Outcome("failed", code)


def outcome_text(outcome: Outcome, title: str) -> tuple[str, str]:
    """The result row's title and subtitle."""
    texts: dict[Kind, tuple[str, str]] = {
        "done": (_("Done"), title),
        "failed": (_("{title} failed").format(title=title), _("zark's output below says why")),
        "usage": (_("zark refused the command"), _("This is a defect of the app: please report it")),
        "stopped": (_("Stopped"), _("zark cleaned up")),
        "cancelled": (_("Cancelled"), title),
        "not_authorized": (_("Not Authorized"), _("An administrator's password is needed to run zark")),
        "busy": (_("zark Is Busy"), _("Another zark command is running. Try again when it ends")),
        "updates": (
            _("Updates Are Being Installed"),
            _("apt is running, so zark did not import the drive. Try again when it ends"),
        ),
        "killed": (
            _("zark ended unexpectedly"),
            _("It was stopped by signal {n}").format(n=signal.Signals(outcome.signal).name)
            if outcome.signal
            else "",
        ),
    }
    return texts[outcome.kind]


class Run:  # pylint: disable=too-many-instance-attributes
    """One command in its terminal, from spawn to ``child-exited``."""

    def __init__(
        self,
        command: Command,
        argv: list[str],
        on_exit: Callable[["Run"], None],
        on_ctrl_c: Callable[["Run"], None],
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.command = command
        self.argv = argv
        self.pid: int | None = None
        self.alive = False
        self.stopping = False
        self.saw_progress = False
        self.status: int | None = None
        self.outcome: Outcome | None = None
        self.started = False
        self._on_exit = on_exit
        self._on_ctrl_c = on_ctrl_c
        self._env = child_env(os.environ if environ is None else environ)
        # Any: the GObject stubs describe VTE's GTK 3 build.
        self.terminal: Any = cast(Any, Vte.Terminal(vexpand=True, hexpand=True))
        self.terminal.set_scrollback_lines(SCROLLBACK)
        self.terminal.connect("child-exited", self._child_exited)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.terminal.add_controller(keys)
        self.terminal.update_property([Gtk.AccessibleProperty.LABEL], [_("zark's output")])

    def start(self) -> None:
        """Spawn the argv in the terminal."""
        flags = GLib.SpawnFlags.DEFAULT | GLib.SpawnFlags(NO_PARENT_ENVV)
        self.alive = True
        self.started = True
        # pty flags, working directory, argv, envv, spawn flags, child
        # setup and its data, timeout, cancellable, callback, user data.
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT, None, self.argv, self._env, flags, None, None, -1, None, self._spawned, None
        )

    def _spawned(self, _terminal: Vte.Terminal, pid: int, error: GLib.Error | None, *_args: object) -> None:
        if error is not None or pid < 0:
            # Nothing ran: pkexec missing or not executable; report as 127.
            self.alive = False
            self.outcome = Outcome("not_authorized", 127)
            self._on_exit(self)
            return
        self.pid = pid

    def _child_exited(self, _terminal: Vte.Terminal, status: int) -> None:
        # The raw wait status (VTE's reaper passes waitpid's); the window
        # classifies it, knowing whether another run holds zark's lock.
        self.alive = False
        self.status = status
        self._on_exit(self)

    def stop(self) -> bool:
        """Ctrl+C to the terminal: SIGINT to zark's foreground group; once
        only, since zark ignores further signals while it cleans up."""
        if not self.alive or self.stopping:
            return False
        self.stopping = True
        self.terminal.feed_child(list(b"\x03"))
        return True

    def _key(self, _ctl: Gtk.EventControllerKey, keyval: int, _code: int, state: Gdk.ModifierType) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)
        if ctrl and shift and key == Gdk.KEY_c:
            self.terminal.copy_clipboard_format(Vte.Format.TEXT)
            return True
        if ctrl and shift and key == Gdk.KEY_v:
            self.terminal.paste_clipboard()
            return True
        if ctrl and not shift and key == Gdk.KEY_c and self.alive:
            # A2-2: a Ctrl+C asks as Stop does instead of stopping at once.
            self._on_ctrl_c(self)
            return True
        return False

    def set_colors(self, foreground: Gdk.RGBA, background: Gdk.RGBA) -> None:
        """The style's colours, again on a light or dark change."""
        self.terminal.set_colors(foreground, background, None)
