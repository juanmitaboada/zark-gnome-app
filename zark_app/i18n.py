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
"""Translations: gettext with the domain ``zark-gnome-app``.

``setup`` binds the domain at start (``main``); until then, and without a
catalogue for the user's language, every string is English, its source.
The catalogues live in ``/usr/share/locale/<lang>/LC_MESSAGES``.
"""

import gettext
import locale
import sys
from pathlib import Path

DOMAIN = "zark-gnome-app"
LOCALEDIR = Path("/usr/share/locale")

_translation: gettext.NullTranslations = gettext.NullTranslations()


def setup(localedir: Path = LOCALEDIR) -> None:
    """Bind the domain for the user's locale (``LANGUAGE``, ``LC_ALL``,
    ``LC_MESSAGES``, ``LANG``), from the catalogues under ``localedir``."""
    global _translation  # pylint: disable=global-statement
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        # A locale that is not generated: C for the C library, the
        # catalogue still chosen from the environment below.
        pass
    try:
        _translation = gettext.translation(DOMAIN, str(localedir), fallback=True)
    except (OSError, LookupError, ValueError, UnicodeDecodeError) as error:
        # A catalogue that cannot be read (A1TR-2): English beats no app.
        print(f"zark-gnome-app: translations not loaded, English used: {error}", file=sys.stderr)
        _translation = gettext.NullTranslations()


def _(message: str) -> str:
    """The translation of ``message``."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """The translation of ``singular`` or ``plural`` for ``n``."""
    return _translation.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    """The translation of ``message`` in ``context``, for a word with more
    than one meaning."""
    return _translation.pgettext(context, message)


def N_(message: str) -> str:  # pylint: disable=invalid-name
    """Marks ``message`` for extraction; translated where it is shown."""
    return message


def NC_(context: str, message: str) -> tuple[str, str]:  # pylint: disable=invalid-name
    """Marks ``message`` in ``context`` for extraction; translated where it
    is shown, with :func:`pgettext`."""
    return (context, message)
