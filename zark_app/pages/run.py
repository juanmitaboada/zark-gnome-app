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
"""A run the app did not start (design 2.3, last line): read from
``progress.json`` only, no Stop and no answers."""

from gi.repository import Adw, Gtk

from zark_app import compat
from zark_app.i18n import _, ngettext
from zark_app.model import RunView, Snapshot
from zark_app.units import fmt_bytes, fmt_duration, fmt_rate, fmt_time
from zark_app.widgets import property_row


def _transfer_rows(run: RunView, group: Adw.PreferencesGroup) -> None:
    t = run.transfer
    if t is None:
        group.add(property_row(_("Data"), _("No data is moving yet")))
        return
    done, total, rate = t.get("bytes_done"), t.get("bytes_total"), t.get("rate_bytes_per_s")
    if isinstance(done, int) and isinstance(total, int):
        at_least = _("at least ") if t.get("bytes_total_partial") is not False else ""
        text = _("{done} of {at_least}{total}").format(
            done=fmt_bytes(done), at_least=at_least, total=fmt_bytes(total)
        )
        if isinstance(rate, int) and rate > 0:
            text += f" - {fmt_rate(rate)}"
        group.add(property_row(_("Data"), text))
    ds_total, ds_done = t.get("datasets_total"), t.get("datasets_done")
    if isinstance(ds_total, int) and isinstance(ds_done, int):
        text = ngettext("{done} of {n} dataset", "{done} of {n} datasets", ds_total).format(
            done=ds_done, n=ds_total
        )
        failed = t.get("datasets_failed")
        if isinstance(failed, int) and failed:
            text += ", " + ngettext("{n} failed", "{n} failed", failed).format(n=failed)
        group.add(property_row(_("Datasets"), text))
    if isinstance(t.get("dataset"), str):
        state = t.get("dataset_state")
        value = f"{t['dataset']} ({state})" if isinstance(state, str) else t["dataset"]
        group.add(property_row(_("Now"), value))
    if run.eta_s is not None:
        group.add(property_row(_("Time left"), fmt_duration(run.eta_s)))


def card(snapshot: Snapshot, run: RunView) -> Adw.PreferencesGroup:
    """The progress card: step, bar, bytes, datasets, time left, waiting."""
    group = Adw.PreferencesGroup(title=run.title)
    if run.started_at is not None:
        elapsed = int((snapshot.now - run.started_at).total_seconds())
        group.set_description(
            _("Started {time}, running for {duration}").format(
                time=fmt_time(run.started_at), duration=fmt_duration(elapsed)
            )
        )
    if run.step_index is not None and run.step_total is not None:
        group.add(
            property_row(_("Step {i} of {n}").format(i=run.step_index, n=run.step_total), run.label or "-")
        )
    fraction = run.fraction
    if fraction is None and run.step_index is not None and run.step_total:
        fraction = run.step_index / run.step_total
    if fraction is not None:
        progress = Gtk.ProgressBar(fraction=fraction, show_text=True, text=f"{int(fraction * 100)} %")
        progress.set_margin_top(12)
        progress.set_margin_bottom(12)
        progress.set_margin_start(12)
        progress.set_margin_end(12)
        if run.stalled_s is not None:
            progress.add_css_class("dim-label")
        holder = Adw.PreferencesRow(activatable=False)
        holder.set_child(progress)
        group.add(holder)
    _transfer_rows(run, group)
    if run.waiting:
        group.add(property_row(_("zark is waiting for you"), run.waiting_for or _("Answer in the terminal")))
    if run.stalled_s is not None:
        group.add(property_row(_("Heartbeat"), _("No update for {n} s").format(n=run.stalled_s)))
    return group


def build(snapshot: Snapshot) -> Gtk.Widget:
    """The run page."""
    run = snapshot.run
    page = Adw.PreferencesPage()
    if run is None:
        return page
    head = Adw.PreferencesGroup()
    status = Adw.StatusPage(
        title=_("Running in a Terminal"),
        description=_("Answer its questions there") if run.waiting else _("zark runs in another window"),
    )
    status.set_child(compat.spinner())
    status.add_css_class("compact")
    head.add(status)
    page.add(head)
    group = card(snapshot, run)
    page.add(group)
    return page
