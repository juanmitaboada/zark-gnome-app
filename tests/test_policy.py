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
"""The polkit policy (A2 plan, section 1): structure as polkit's
``policyconfig-1.dtd`` orders it, one action per argv1, the defaults of the
study's 6.1 and M24-2 2a."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "data" / "com.juanmitaboada.Zark.policy"
PATH_KEY = "org.freedesktop.policykit.exec.path"
ARGV1_KEY = "org.freedesktop.policykit.exec.argv1"
EVERY_TIME = {"prepare", "purge", "health"}
KEPT = {
    "backup",
    "prune",
    "registry",
    "exclude",
    "mount",
    "umount",
    "explore",
    "clean",
    "status",
    "alerts",
    "fullcheck",
}


def actions() -> list[ET.Element]:
    """The policy's actions."""
    return list(ET.parse(POLICY).getroot().iter("action"))


def test_top_level_order() -> None:
    """policyconfig (vendor?, vendor_url?, icon_name?, action+)."""
    root = ET.parse(POLICY).getroot()
    tags = [c.tag for c in root]
    assert root.tag == "policyconfig"
    assert tags[:3] == ["vendor", "vendor_url", "icon_name"]
    assert set(tags[3:]) == {"action"}


@pytest.mark.parametrize("action", actions(), ids=lambda a: a.get("id"))
def test_action(action: ET.Element) -> None:
    """action (description+, message+, defaults, annotate*), both
    annotations, the defaults by command, no allow_gui."""
    tags = [c.tag for c in action]
    assert tags == ["description", "message", "defaults", "annotate", "annotate"]
    notes = {a.get("key"): a.text for a in action.iter("annotate")}
    assert notes[PATH_KEY] == "/usr/share/zark/zark"
    word = notes[ARGV1_KEY]
    assert action.get("id") == f"com.juanmitaboada.Zark.{word}"
    found = action.find("defaults")
    assert found is not None
    defaults = {d.tag: d.text for d in found}
    assert defaults["allow_any"] == "no" and defaults["allow_inactive"] == "no"
    assert defaults["allow_active"] == ("auth_admin" if word in EVERY_TIME else "auth_admin_keep")
    message = action.findtext("message") or ""
    assert "$(cmdline_short)" in message
    assert "allow_gui" not in ET.tostring(action, encoding="unicode")


def test_one_action_per_command() -> None:
    """Fourteen actions, one per argv1, every one with argv1."""
    words = [{a.get("key"): a.text for a in act.iter("annotate")}.get(ARGV1_KEY) for act in actions()]
    assert None not in words
    assert sorted(w for w in words if w) == sorted(EVERY_TIME | KEPT)
    assert len(words) == len(set(words)) == 14
