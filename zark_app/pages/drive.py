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
"""A drive's page (design 2.2, ``drive-page.svg``)."""

# One function per group of the design's table; the figures are many.
# pylint: disable=too-many-locals

from typing import Any

from gi.repository import Adw, Gtk

from zark_app.i18n import _, ngettext
from zark_app.model import (
    CHECK_WORDS,
    DriveDetails,
    DriveView,
    MonthView,
    Snapshot,
    drive_details,
    eject_words,
    obj,
    result_words,
)
from zark_app.units import fmt_bytes, fmt_date_time, fmt_month, fmt_since
from zark_app.widgets import property_row


def _status(snapshot: Snapshot, drive: DriveView) -> Adw.PreferencesGroup:
    mod = snapshot.module
    doc = drive.doc
    group = Adw.PreferencesGroup(title=_("Status"))
    last = mod.parse_timestamp(doc.get("last_backup_at")) if mod is not None else None
    if last is not None:
        value = f"{fmt_date_time(last)} ({fmt_since(last, snapshot.now)})"
    else:
        value = _("No backup yet")
    group.add(property_row(_("Last backup"), value))
    run = doc.get("last_run")
    if isinstance(run, dict):
        parts = [result_words(run.get("result"))]
        if isinstance(run.get("point"), str):
            parts.append(run["point"])
        missing = run.get("datasets_missing")
        if isinstance(missing, int) and missing > 0:
            parts.append(ngettext("{n} dataset missing", "{n} datasets missing", missing).format(n=missing))
        if run.get("message"):
            parts.append(str(run["message"]))
        group.add(property_row(_("Last run"), " - ".join(parts), subtitle_selectable=True))
    else:
        group.add(property_row(_("Last run"), _("No run recorded")))
    group.add(property_row(_("Eject after a backup"), eject_words(doc.get("autoeject"))))
    check = doc.get("last_check")
    if isinstance(check, dict):
        result = check.get("result")
        words = _(CHECK_WORDS[result]) if isinstance(result, str) and result in CHECK_WORDS else str(result)
        ended = mod.parse_timestamp(check.get("ended_at")) if mod is not None else None
        when = f" ({fmt_since(ended, snapshot.now)})" if ended is not None else ""
        message = f" - {check['message']}" if check.get("message") else ""
        group.add(property_row(_("Last full check"), f"{words}{when}{message}", subtitle_selectable=True))
    record = doc.get("last_point_record")
    if isinstance(record, dict):
        group.add(property_row(_("Last point's record"), ", ".join(f"{k} {v}" for k, v in record.items())))
    return group


def _space(snapshot: Snapshot, drive: DriveView, details: DriveDetails) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=_("Space"))
    space = details.space
    if space is None:
        group.set_description(_("Not measured yet: back up to this drive"))
        return group
    if space.live:
        group.set_description(_("Live, while zark has the drive imported"))
    elif space.measured_at is not None:
        group.set_description(
            _("Measured at the last backup, {age}").format(age=fmt_since(space.measured_at, snapshot.now))
        )
    total = max(space.total, 1)
    meter = Gtk.LevelBar(min_value=0.0, max_value=1.0, value=space.used / total, hexpand=True)
    meter.set_margin_top(12)
    meter.set_margin_bottom(6)
    meter.set_margin_start(12)
    meter.set_margin_end(12)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_LOW)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_HIGH)
    meter.remove_offset_value(Gtk.LEVEL_BAR_OFFSET_FULL)
    meter.update_property([Gtk.AccessibleProperty.LABEL], [_("Used space")])
    holder = Adw.PreferencesRow(activatable=False)
    holder.set_child(meter)
    group.add(holder)
    group.add(property_row(_("Used"), fmt_bytes(space.used)))
    group.add(property_row(_("Free"), fmt_bytes(space.available)))
    group.add(property_row(_("Reserved by ZFS"), fmt_bytes(space.reserved)))
    if space.margin is not None:
        margin_pct = obj(drive.doc.get("retention")).get("margin_pct")
        group.add(
            property_row(
                _("Margin a backup leaves free"),
                f"{fmt_bytes(space.margin)} ({margin_pct} %)"
                if margin_pct is not None
                else fmt_bytes(space.margin),
            )
        )
    if details.after_free is not None and details.after_reclaim is not None:
        floor = _("at least ") if details.after_floor else ""
        what = []
        if details.after_points is not None:
            what.append(
                ngettext("{n} point", "{n} points", details.after_points).format(n=details.after_points)
            )
        if details.after_snapshots is not None:
            what.append(
                ngettext("{n} snapshot", "{n} snapshots", details.after_snapshots).format(
                    n=details.after_snapshots
                )
            )
        row = Adw.ActionRow(
            title=_("After the next retention: {floor}{free} free").format(
                floor=floor, free=fmt_bytes(details.after_free)
            ),
            subtitle=_("Frees {size}: {what}").format(
                size=fmt_bytes(details.after_reclaim), what=", ".join(what)
            )
            if what
            else _("Frees {size}").format(size=fmt_bytes(details.after_reclaim)),
        )
        group.add(row)
    elif "retention_next" in drive.doc:
        group.add(property_row(_("After the next retention"), _("Not measured")))
    return group


def _month_row(month: MonthView) -> Adw.ExpanderRow:
    count = len(month.points)
    parts = [ngettext("{n} point", "{n} points", count).format(n=count)]
    if month.incomplete:
        parts.append(
            ngettext("{n} incomplete", "{n} incomplete", month.incomplete).format(n=month.incomplete)
        )
    elif month.all_whole:
        parts.append(_("all whole"))
    subtitle = _("{what} - held alone {size}").format(what=", ".join(parts), size=fmt_bytes(month.held_alone))
    row = Adw.ExpanderRow(title=fmt_month(month.key), subtitle=subtitle)
    if month.has_entry:
        text = (
            _("Removing older points frees {size}").format(size=fmt_bytes(month.frees))
            if month.frees is not None
            else _("Removing older points: not measured")
        )
        row.add_suffix(Gtk.Label(label=text, css_classes=["dim-label"], wrap=True))
    elif month.inside_window:
        row.add_suffix(Gtk.Label(label=_("inside the window"), css_classes=["dim-label"]))
    for point in month.points:
        marks = []
        if point.get("complete") is False:
            marks.append(_("incomplete"))
        if point.get("whole") is True:
            marks.append(_("whole"))
        used = point.get("used_bytes")
        if isinstance(used, int):
            marks.append(_("holds {size} alone").format(size=fmt_bytes(used)))
        child = Adw.ActionRow(title=str(point.get("name", "?")), subtitle=", ".join(marks))
        child.add_css_class("property")
        row.add_row(child)
    return row


def _points(details: DriveDetails) -> Adw.PreferencesGroup | None:
    if details.months is None:
        return None
    total = sum(len(m.points) for m in details.months)
    group = Adw.PreferencesGroup(
        title=_("Backup Points"), description=ngettext("{n} point", "{n} points", total).format(n=total)
    )
    if not details.months_add_up:
        group.set_description(
            (group.get_description() or "")
            + ". "
            + _("Each month shows what it holds alone; removing several months frees more than their sum")
        )
    for month in details.months:
        group.add(_month_row(month))
    return group


def _largest(details: DriveDetails) -> Adw.PreferencesGroup | None:
    if details.largest is None:
        return None
    group = Adw.PreferencesGroup(title=_("Largest Datasets"))
    for name, share in details.largest:
        group.add(property_row(name, fmt_bytes(share)))
    return group


def _other(details: DriveDetails) -> Adw.PreferencesGroup | None:
    if details.other is None:
        return None
    group = Adw.PreferencesGroup(title=_("Other Snapshots"))
    labels = {"intermediate": _("Intermediate"), "other": _("Other")}
    for key, title in labels.items():
        entry: Any = details.other.get(key)
        if isinstance(entry, dict):
            count = entry.get("count", 0)
            size = entry.get("used_bytes")
            value = ngettext("{n} snapshot", "{n} snapshots", count).format(n=count)
            if isinstance(size, int):
                value += f", {fmt_bytes(size)}"
            group.add(property_row(title, value))
    return group


def _retention(drive: DriveView) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title=_("Retention"))
    retention = obj(drive.doc.get("retention"))
    window = retention.get("window_days")
    max_age = retention.get("max_age_days")
    margin = retention.get("margin_pct")
    group.add(
        property_row(
            _("Window"),
            ngettext("{n} day", "{n} days", window).format(n=window) if isinstance(window, int) else "-",
        )
    )
    group.add(
        property_row(
            _("Maximum age"),
            ngettext("{n} day", "{n} days", max_age).format(n=max_age)
            if isinstance(max_age, int) and max_age > 0
            else _("No limit"),
        )
    )
    group.add(property_row(_("Margin"), f"{margin} %" if isinstance(margin, int) else "-"))
    return group


def build(snapshot: Snapshot, drive: DriveView) -> Gtk.Widget:
    """The drive's page."""
    page = Adw.PreferencesPage()
    progress = None
    run = snapshot.run
    if run is not None and run.drive == drive.name and run.drive_space is not None:
        progress = {"drive": {"name": drive.name, "space": run.drive_space}}
    if snapshot.module is None:
        return page
    details = drive_details(snapshot.module, drive.doc, progress, snapshot.now)
    page.add(_status(snapshot, drive))
    page.add(_space(snapshot, drive, details))
    for group in (_points(details), _largest(details), _other(details)):
        if group is not None:
            page.add(group)
    page.add(_retention(drive))
    return page
