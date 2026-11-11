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
"""Whole-page states (design section 5, ``states.svg``)."""

from gi.repository import Gtk

from zark_app.i18n import _
from zark_app.model import Action, Snapshot, cmd
from zark_app.widgets import status_page


def no_zark(detail: str) -> Gtk.Widget:
    """zark is not installed, or its reader is not where zark puts it."""
    page = status_page(
        _("zark Is Not Installed"),
        _("The zark package provides the commands this app runs: sudo apt install zark"),
        Action(_("Install zark"), "sudo apt install zark"),
    )
    page.set_tooltip_text(detail or None)
    return page


def too_old(snapshot: Snapshot) -> Gtk.Widget:
    """The installed zark's reader lacks what this app uses."""
    installed = snapshot.installed_zark or _("an unknown version")
    return status_page(
        _("zark Is Too Old"),
        _("This app needs zark 2.3.0 or later; the installed one is {installed}").format(installed=installed),
        Action(_("Update zark"), "sudo apt install --only-upgrade zark"),
    )


def no_status() -> Gtk.Widget:
    """No ``status.json``: indicator state ``none``."""
    return status_page(
        _("No Status Yet"),
        _("zark has not written its status file. Refresh it, or run a first backup"),
        Action(_("Refresh Status"), cmd("status", "--refresh")),
    )


def no_drives() -> Gtk.Widget:
    """No registered and no pending drive."""
    return status_page(
        _("No Backup Drives Yet"),
        _("Prepare an empty drive to hold the backups of this computer"),
        Action(_("Prepare a New Drive..."), cmd("prepare")),
    )
