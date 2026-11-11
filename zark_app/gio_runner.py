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
"""Runs the live commands through ``Gio.Subprocess``: argv only, no shell,
asynchronous, with a time limit."""

from collections.abc import Callable, Sequence

from gi.repository import Gio, GLib

from zark_app.sources import CommandResult

TIME_LIMIT_S = 10


class GioRunner:  # pylint: disable=too-few-public-methods
    """The real :class:`zark_app.sources.Runner`."""

    def run(self, argv: Sequence[str], done: Callable[[CommandResult], None]) -> None:
        """Run ``argv``; ``done`` gets status None when it cannot start or
        runs past :data:`TIME_LIMIT_S`."""
        args = tuple(argv)
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        )
        # Untranslated, parseable output whatever the session's locale.
        launcher.setenv("LC_ALL", "C", True)
        try:
            proc = launcher.spawnv(list(args))
        except GLib.Error:

            def failed() -> bool:
                done(CommandResult(args, None))
                return False

            GLib.idle_add(failed)
            return
        timed_out = [False]

        def kill() -> bool:
            timed_out[0] = True
            proc.force_exit()
            return False

        timer = GLib.timeout_add_seconds(TIME_LIMIT_S, kill)

        def finished(p: Gio.Subprocess, res: Gio.AsyncResult) -> None:
            if not timed_out[0]:
                GLib.source_remove(timer)
            try:
                _ok, stdout, _err = p.communicate_utf8_finish(res)
            except GLib.Error:
                done(CommandResult(args, None))
                return
            status = p.get_exit_status() if p.get_if_exited() and not timed_out[0] else None
            done(CommandResult(args, status, stdout or ""))

        proc.communicate_utf8_async(None, None, finished)
