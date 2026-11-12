# zark

[![CI](https://github.com/juanmitaboada/zark-gnome-app/actions/workflows/ci.yml/badge.svg)](https://github.com/juanmitaboada/zark-gnome-app/actions/workflows/ci.yml) [![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

A GNOME app for [zark](https://github.com/juanmitaboada/zark): the state of
your backups and backup drives in one window.

zark backs up an Ubuntu system installed on encrypted ZFS to an external
drive, and rebuilds it, bootable, from a live USB when the disk dies. It
runs in a terminal; this app shows how your backups stand: how full the
system pools are, each backup drive with its last backup, its space and its
backup points by month, the datasets left out of backups, and a backup
running in a terminal, with its progress.

It reads the two status files the installed
zark writes (`/run/zark/progress.json` and `/var/lib/zark/status.json`,
described in zark's
[`docs/STATUS-FILES.md`](https://github.com/juanmitaboada/zark/blob/main/docs/STATUS-FILES.md))
through zark's own reader, and the live figures of `zpool list`, `zfs list`
and `zfs get`, all without privileges. It never writes zark's files, never
takes its lock and never imports a pool itself.

Each operation (back up, reclaim space, prepare, check, erase or register a
drive, exclusions, retention) runs one zark command,
`pkexec /usr/share/zark/zark <command> ...`, under its own polkit action
(`com.juanmitaboada.Zark.<command>`), with the administrator's password:
kept five minutes per command, asked every time for prepare, purge and
health. zark runs in a terminal inside the window and asks its questions
there as it always does. On Ubuntu 24.04 the terminal is not read by screen
readers (VTE 0.76 has no GTK 4 accessibility); the app's own announcements
still are.

What changed in each version is in [CHANGELOG.md](CHANGELOG.md).

## Requirements

- Ubuntu 24.04 LTS, 26.04 LTS or 26.10, with GNOME.
- zark 2.3.0 or later, installed as a package (the app imports its reader
  from `/usr/share/zark`).

## Install

From the PPA zark uses:

```bash
sudo add-apt-repository ppa:juanmitaboada/zark
sudo apt install zark-gnome-app
```

## Translations

The texts are marked for gettext (domain `zark-gnome-app`; `make pot`
writes the template). No catalogue ships yet. Corrections to translations
are welcome as pull requests.

## Development

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-vte-3.91 \
    xvfb xauth librsvg2-common python3-pytest
git clone https://github.com/juanmitaboada/zark ../zark
make test               # the suite under Xvfb, from the fixtures
make screenshots        # one PNG per state, in build/screenshots
make venv lint          # ruff, mypy, pylint at the pinned versions
make run CASE=app:connected
make deb                # the .deb on this machine's series
sudo make deb-all       # the .deb in a clean chroot of each series
```

The tests read zark's status file fixtures (`tests/fixtures/zark-2.3.0/`,
copied unchanged from zark's tag with a sha256 manifest) and the app's own
(`tests/fixtures/app/`); no test runs `zfs`, `zpool`, pkexec or a command of
zark's: `tests/fake_pkexec.py` stands in for pkexec in the terminal tests.

## License

Apache-2.0, as zark. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
