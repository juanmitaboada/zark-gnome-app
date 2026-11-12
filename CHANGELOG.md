# Changelog

## [1.1] - unreleased

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

## [1.0] - unreleased

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
