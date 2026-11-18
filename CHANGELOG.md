# Changelog

## [Unreleased]

- This Computer shows what fills each pool, as zark's GNOME Shell
  extension does: open a pool's row for a bar of its space (user data and
  snapshots, the system and its snapshots, other datasets, pool metadata,
  free, reserved by ZFS) with its legend, how much the snapshots hold, the
  twelve largest datasets or the twelve with the most in snapshots, and
  when zark measured it. Reclaim Space... there runs `zark prune`, whose
  first question offers to clean this computer's snapshots. A pool whose
  datasets zark could not list says so and still offers Reclaim Space....
- Prepare a New Drive lists a disk once: a disk behind a USB bridge has
  two names (its own and its enclosure's) and showed twice. The name shown
  and passed to `zark prepare` is the one zark registers it under, the
  disk's own (`ata-`, `nvme-`) before its enclosure's (`usb-`). A
  registered drive is left out under every name it has, not only the
  registered one.
- A date's order comes from the translation, so a language can write it
  as it does (German "7. Nov. 2026, 09:31"); English is unchanged.
- A connected drive's icon is never the missing-icon placeholder: with
  plain Adwaita (no `emblem-ok-symbolic` since its version 50) it is
  GTK's own check mark.
- The drive-gone dialog opens with zark's hint unselected; it can still be
  selected and copied.
- Prepare a New Drive: "It asks you to confirm in the terminal." ends with
  a full stop.
- Tests: CI and the README's Development steps use zark `v2.3.3` (its
  status fixtures are 2.3.2's, unchanged).

## [1.2.0] - 2026-11-18

- The app in Spanish and in the eight languages closest to it and to
  English: Brazilian and European Portuguese, French, Italian, Catalan,
  Galician, German and Dutch. The window, the desktop entry (its
  description and search words), the AppStream metadata and the
  administrator's password dialogs (polkit) follow the session's
  language; month names too. Commands, options and zark's own output stay
  English in every language, and so do the three lines of Prepare a New
  Drive on which disk zark takes, with a translated caption under them in
  the warning style. About credits the translators. Corrections from
  native speakers are welcome (README, Translations).
- Prepare a New Drive says what zark does: the disk must be empty, and
  zark refuses one with partitions or a format it recognizes, leaving it
  untouched; the caption adds that zark cannot see every kind of data and
  asks to check the disk's name and size. The polkit texts of prepare and
  health say that the disk must be empty.
- A catalogue that cannot be loaded leaves the app in English.
- For translators and maintainers: the template `po/zark-gnome-app.pot`
  holds the app's, the desktop file's, the metainfo's and the policy's
  texts (`make pot`), with notes and contexts where a word is ambiguous;
  `make i18n` builds the catalogues and merges them, each file's language
  tags in its reader's form; `make po-risk` lists the msgids that match
  `po/RISK-WORDS` with their review in `po/RISK-REVIEWED`; the tests check
  every catalogue against the template, its placeholders, white space and
  plural forms, and open every state of the app in a pseudo-translation.
- Tests: zark 2.3.2's reader and status fixtures (`tests/fixtures/zark-2.3.2/`);
  CI and the README's Development steps use zark `v2.3.2`.

## [1.1.3] - 2026-11-16

- When a backup's drive goes away during the run (zark 2.3.1's
  `drive_gone`), a dialog shows the drive, the local time it went away and
  zark's hint as written, selectable so its reboot command can be copied;
  once per run and drive, besides zark's own notification. It stays quiet
  while zark's GNOME Shell extension 1.3 or later is active (GNOME Shell's
  `org.gnome.Shell.Extensions`), which shows its own; with no answer from
  GNOME Shell the app shows it.
- Packaging: `make deb-ppa` no longer prints lintian's
  `binary-nmu-debian-revision-in-source` for the PPA's per-series revision.

## [1.1.2] - 2026-11-16

Fixes from the three eli checklists (1.1.1 was not released on its own).

From the third:

- The run's percentage and time left are zark's, as before the peak hold
  from the second checklist, which is gone. zark 2.3.1 counts what follows
  a resume in the round of the resume, so its totals hold from start to
  end. With zark 2.3.0, whose estimate grows with a further round after a
  resume, the run shows the bytes sent and the rate from that growth on,
  with a pulsing bar and no percentage or time left: a percentage would
  read near the end long before it.
- With a release candidate of zark installed (Debian's `2.3.1~rc1-1`), the
  window no longer says the status file was written by another zark: the
  installed version is compared in zark's own spelling (`2.3.1-rc1`).

From the second:

- While the app's own command runs, a Suspend chosen from GNOME's menu
  asks for the administrator's password first: the app holds logind's
  sleep inhibitor in block mode beside GTK's, which gnome-session takes in
  block-weak mode and logind skips for the user's own request. Closing a
  laptop's lid still suspends (logind's `LidSwitchIgnoreInhibited=yes`).
- A mount that ends well offers Open in Files and Unmount on its result,
  for the drive it left mounted.
- Prepare a New Drive... leaves out the disks this system uses (a vdev of
  an imported pool, a mounted filesystem, active swap, through partitions
  and dm or md devices), as zark's own check does; if that cannot be read
  it says so and zark checks again.
- A drive whose last run was interrupted or not read back shows the error
  icon in red; an incomplete one keeps the warning icon.
- Every run ends with a line under zark's output saying what ran and how
  it ended, in green, yellow or red.
- The Exclude dialog's dataset names keep their end.

From the first:

- The launcher runs Python in isolated mode (`-I`) as installed too:
  dh-python 7 (resolute, stonking) no longer rewrites its shebang, and
  `make deb` checks it in each built package.
- A page keeps its scroll position and its open months when the window
  redraws it (at least once a minute), instead of jumping to its top.
- The run's percentage comes from the bytes sent only. Before data moves
  the bar pulses and the step shows as "Step N of 8"; once the data is
  sent the bar is full ("data sent"), as in the extension.
- Backup points show their local time, with their name (which holds UTC)
  beside it, on the drive page and in "Last run".
- A drive mounted for browsing has Open in Files and Unmount on its row
  and page, no Back Up, and only those two in its menu. A run's title
  names its drive ("Mounting backup2").

## [1.1] - not released

Operations, for zark 2.3.0 and later.

- Every action of the design runs one zark command,
  `pkexec /usr/share/zark/zark <command> ...`, under its own polkit action
  (`com.juanmitaboada.Zark.<command>`, in `/usr/share/polkit-1/actions/`):
  the administrator's password, kept five minutes per command, asked every
  time for prepare, purge and health.
- zark runs in a terminal inside the window and asks its questions there;
  the run page shows its progress, and a notification says when zark waits
  while the window is not in front.
- Stop, Ctrl+C in the terminal, Close and Quit during a run ask first,
  then stop zark with Ctrl+C; zark cleans up. Logout and suspend are
  inhibited while the app's run lasts.
- Prepare a New Drive picks a whole disk from `/dev/disk/by-id`; Retention
  and Exclude have their dialogs; every value is checked before zark runs.
- Ctrl+B backs up the selected drive, Ctrl+M browses or unmounts it.
- The copy buttons of 1.0 are gone.

## [1.0] - not released

The first version, read-only, for zark 2.3.0 and later.

- One window: a sidebar with the Overview, each backup drive (registered
  and pending) and Exclusions; a page for each.
- The Overview: the system pools with live figures, `/boot` on 26.10, the
  backup drives with their state, zark's notices.
- A drive's page: last backup and run, space with the margin and what the
  next retention frees, backup points by month with what removing older
  ones frees, largest datasets, other snapshots, retention, the last full
  check.
- A run started in a terminal: its step, bytes, datasets and time left.
- Every state of zark's status files: no status yet, stale, newer, written
  by another zark, an orphan run, a drive mounted for browsing or unplugged
  during a run, no drives, zark not installed or too old.
- Where an action belongs, its button copies the zark command.
- libadwaita 1.5 and later, with `AdwSpinner` from 1.6 and
  `AdwShortcutsDialog` from 1.8; a narrow layout under 600 sp.
