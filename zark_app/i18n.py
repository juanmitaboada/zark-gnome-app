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

No catalogue ships yet (A1T adds them); without one every string is
English, its source.
"""

import gettext

DOMAIN = "zark-gnome-app"
LOCALEDIR = "/usr/share/locale"

_translation = gettext.translation(DOMAIN, LOCALEDIR, fallback=True)


def _(message: str) -> str:
    """The translation of ``message``."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """The translation of ``singular`` or ``plural`` for ``n``."""
    return _translation.ngettext(singular, plural, n)


def N_(message: str) -> str:  # pylint: disable=invalid-name
    """Marks ``message`` for extraction; translated where it is shown."""
    return message
