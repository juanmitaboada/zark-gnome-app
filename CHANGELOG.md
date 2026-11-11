# Changelog

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
