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
"""Sizes, ages and times as the app shows them. No GTK here."""

import re
from datetime import UTC, datetime

from zark_app.i18n import NC_, _, ngettext, pgettext

# A1TR-9: month names from the app's catalogue, not the C library's LC_TIME,
# so a date follows the app's language (as the extension's do).
_MONTHS = (
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "January"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "February"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "March"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "April"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "May"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "June"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "July"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "August"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "September"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "October"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "November"),
    # TRANSLATORS: a month's full name; it starts a row's title, as in "Noviembre de 2026": capitalize it.
    NC_("month", "December"),
)
_SHORT_MONTHS = (
    # TRANSLATORS: a month's short name, in a date such as "13 Nov 2026, 06:15".
    NC_("month, short", "Jan"),
    NC_("month, short", "Feb"),
    NC_("month, short", "Mar"),
    NC_("month, short", "Apr"),
    NC_("month, short", "May"),
    NC_("month, short", "Jun"),
    NC_("month, short", "Jul"),
    NC_("month, short", "Aug"),
    NC_("month, short", "Sep"),
    NC_("month, short", "Oct"),
    NC_("month, short", "Nov"),
    NC_("month, short", "Dec"),
)

_UNITS = ("KiB", "MiB", "GiB", "TiB", "PiB")


def fmt_bytes(n: int) -> str:
    """Binary units, as zark and ``zfs list`` show them, with three
    significant figures: ``412 GiB``, ``1.79 TiB``, ``9.20 GiB``."""
    if n < 1024:
        # TRANSLATORS: B is the unit symbol of bytes and stays as it is, as s, min and h do elsewhere.
        return _("{n} B").format(n=max(n, 0))
    value = float(n)
    index = 0
    value /= 1024
    while value >= 1024 and index < len(_UNITS) - 1:
        value /= 1024
        index += 1
    unit = _UNITS[index]
    if value < 10:
        text = f"{value:.2f}"
    elif value < 100:
        text = f"{value:.1f}"
    else:
        text = f"{value:.0f}"
    return f"{text} {unit}"


def fmt_pct(pct: int) -> str:
    """A percentage with a space before the sign, as the design writes it."""
    return f"{pct} %"


def fmt_rate(bytes_per_s: int) -> str:
    """A transfer rate."""
    # TRANSLATORS: {size} is a size such as "12.0 MiB": a rate per second; /s stays as it is.
    return _("{size}/s").format(size=fmt_bytes(bytes_per_s))


def fmt_ago(seconds: float) -> str:
    """``25 minutes ago``; never in the future (a clock behind the writer's
    reads as ``just now``)."""
    s = int(seconds)
    if s < 60:
        return _("just now")
    minutes = s // 60
    if minutes < 60:
        return ngettext("{n} minute ago", "{n} minutes ago", minutes).format(n=minutes)
    hours = minutes // 60
    if hours < 48:
        return ngettext("{n} hour ago", "{n} hours ago", hours).format(n=hours)
    days = hours // 24
    return ngettext("{n} day ago", "{n} days ago", days).format(n=days)


def fmt_since(when: datetime, now: datetime) -> str:
    """:func:`fmt_ago` from a timestamp."""
    return fmt_ago((now - when).total_seconds())


def fmt_duration(seconds: int) -> str:
    """A duration: ``45 s``, ``17 min``, ``2 h 05 min``."""
    if seconds < 60:
        # TRANSLATORS: s is the unit symbol of seconds and stays as it is.
        return _("{n} s").format(n=max(seconds, 0))
    minutes = seconds // 60
    if minutes < 60:
        # TRANSLATORS: min is the unit symbol of minutes and stays as it is.
        return _("{n} min").format(n=minutes)
    # TRANSLATORS: h and min are unit symbols and stay as they are; keep {m:02d}: minutes with two digits.
    return _("{h} h {m:02d} min").format(h=minutes // 60, m=minutes % 60)


def local(when: datetime) -> datetime:
    """``when`` in the local time zone."""
    return when.astimezone()


def _fmt_date(t: datetime, time: str) -> str:
    # BC22-50: the order of a date's parts is the catalogue's, not the code's.
    return _(
        # TRANSLATORS: a date and time, as "7 Nov 2026, 09:31": {day} is the day of the
        # month, {month} a month's short name, {year} the year, {time} "09:31" or
        # "06:15:10". Order them as your language writes a date, as German
        # "{day}. {month} {year}, {time}".
        "{day} {month} {year}, {time}"
    ).format(day=t.day, month=pgettext(*_SHORT_MONTHS[t.month - 1]), year=t.year, time=time)


def fmt_date_time(when: datetime) -> str:
    """``7 Nov 2026, 09:31`` in local time."""
    t = local(when)
    return _fmt_date(t, t.strftime("%H:%M"))


def fmt_date_time_s(when: datetime) -> str:
    """``13 Nov 2026, 06:15:10`` in local time: a backup point's time."""
    t = local(when)
    return _fmt_date(t, t.strftime("%H:%M:%S"))


# A point's name holds its time in UTC: zark_2026-11-13_05:15:10Z.
_POINT_NAME = re.compile(r"zark_(\d{4}-\d{2}-\d{2})_(\d{2}:\d{2}:\d{2})Z")


def parse_utc(text: object) -> datetime | None:
    """zark's ``2026-11-13T05:15:34Z``, or None."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def point_time(name: object) -> datetime | None:
    """The UTC time in a point's name, or None for a name not in zark's form."""
    match = _POINT_NAME.fullmatch(name) if isinstance(name, str) else None
    if match is None:
        return None
    return parse_utc(f"{match.group(1)}T{match.group(2)}Z")


def fmt_time(when: datetime) -> str:
    """``09:31`` in local time."""
    return local(when).strftime("%H:%M")


def fmt_month(key: str) -> str:
    """``November 2026`` from ``2026-11``."""
    when = datetime.strptime(key, "%Y-%m").replace(tzinfo=UTC)
    # TRANSLATORS: a month and its year, as "November 2026".
    return _("{month} {year}").format(month=pgettext(*_MONTHS[when.month - 1]), year=when.year)


def upstream_version(debian_version: str) -> str:
    """``2.3.0`` from ``2.3.0-1`` or ``1:2.3.0-1ubuntu1``."""
    version = debian_version.split(":", 1)[-1]
    return version.rsplit("-", 1)[0] if "-" in version else version


def zark_release(debian_version: str) -> str:
    """The installed version as zark spells its own: ``2.3.1-rc1`` from
    ``2.3.1~rc1-1``. Debian writes an upstream pre-release ``-`` as ``~`` so
    it sorts before the release (A112E-1)."""
    return upstream_version(debian_version).replace("~", "-")
