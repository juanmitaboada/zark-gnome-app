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
"""Stands in for pkexec in the tests: no privilege, no polkit. Called as
``python3 -I fake_pkexec.py <mode> [<file>] <zark path> <command> ...``.

Modes: ``exit:<n>`` exits n; ``env:<file>`` writes its environment and argv
to <file> as JSON and exits 0; ``ask`` asks a question and exits 0 on
"yes", 1 otherwise; ``trap`` waits for SIGINT and exits 130, as zark's
cleanup does; ``sleep`` waits until killed.
"""

import json
import os
import signal
import sys
import time


def main() -> int:
    """Act as the mode says."""
    mode = sys.argv[1]
    if mode.startswith("exit:"):
        print("fake zark:", " ".join(sys.argv[2:]))
        return int(mode[5:])
    if mode.startswith("env:"):
        with open(mode[4:], "w", encoding="utf-8") as f:
            json.dump({"env": dict(os.environ), "argv": sys.argv[2:], "tty": os.isatty(0)}, f)
        return 0
    if mode == "ask":
        answer = input("Continue? [y/N] ")
        return 0 if answer.strip() == "yes" else 1
    if mode == "trap":

        def stop(_signum: int, _frame: object) -> None:
            print("Interrupted by SIGINT, cleaning up")
            sys.exit(130)

        signal.signal(signal.SIGINT, stop)
        print("running")
        while True:
            time.sleep(0.05)
    if mode == "sleep":
        while True:
            time.sleep(0.05)
    return 2


if __name__ == "__main__":
    sys.exit(main())
