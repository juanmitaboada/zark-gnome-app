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
"""About (design 2.6, ``about.svg``): ``AdwAboutDialog``, libadwaita 1.5."""

from gi.repository import Adw, Gtk

from zark_app import APP_ID, ISSUES, VERSION, WEBSITE
from zark_app.i18n import _
from zark_app.model import Snapshot
from zark_app.units import upstream_version


def debug_info(snapshot: Snapshot) -> str:
    """The versions a report needs."""
    gtk = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
    adw = f"{Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}"
    lines = [
        f"zark-gnome-app {VERSION}",
        f"zark (installed): {snapshot.installed_zark or 'unknown'}",
        f"zark (status file writer): {snapshot.writer_version or 'none'}",
        f"status: {snapshot.status_class}, progress: {snapshot.progress_class}",
        f"indicator: {snapshot.indicator}",
        f"GTK {gtk}",
        f"libadwaita {adw}",
    ]
    return "\n".join(lines) + "\n"


def show(parent: Gtk.Widget, snapshot: Snapshot) -> Adw.AboutDialog:
    """Present the dialog."""
    installed = upstream_version(snapshot.installed_zark) if snapshot.installed_zark else None
    comments = (
        _("Reads the status files of the installed zark {version}").format(version=installed)
        if installed
        else _("Reads zark's status files")
    )
    dialog = Adw.AboutDialog(
        application_icon=APP_ID,
        application_name="zark",
        developer_name="Juanmi Taboada",
        version=VERSION,
        comments=comments,
        website=WEBSITE,
        issue_url=ISSUES,
        license_type=Gtk.License.APACHE_2_0,
        copyright="Copyright 2026 Juanmi Taboada",
        debug_info=debug_info(snapshot),
        debug_info_filename="zark-gnome-app-debug.txt",
    )
    dialog.set_developers(["Juanmi Taboada https://www.juanmitaboada.com"])
    dialog.add_link(_("zark"), "https://github.com/juanmitaboada/zark")
    dialog.present(parent)
    return dialog
