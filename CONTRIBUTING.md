# Contributing to zark-gnome-app

Thank you for your interest. The project is small and the process informal.

## Reporting bugs

Open an issue at <https://github.com/juanmitaboada/zark-gnome-app/issues>
with the text of About > Troubleshooting > Debug Info, your Ubuntu version,
and what you expected against what the window showed. A copy of
`/var/lib/zark/status.json` helps; it holds nothing secret, but check it
holds nothing you would not publish.

## Changes

- Code, comments, commits and documentation in English.
- Every state the window shows comes from zark's reader and the status
  files' contract; the app never parses the strings that contract keeps
  for people (`step.label`, `waiting_for`, `last_run.message`, a notice's
  `text`).
- The app never writes zark's files, takes zark's lock or imports a pool.
- `make test` and `make lint` pass before a pull request; a new state gets
  a fixture in `tests/fixtures/app/`.
