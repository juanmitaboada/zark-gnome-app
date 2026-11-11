# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

This app runs as the user and, in this version, runs no zark command: it
reads zark's status files and the output of `zpool list`, `zfs list`,
`zfs get` and `dpkg-query`. A vulnerability in it could still mislead you
about your backups, so please report responsibly.

Open a private advisory at
<https://github.com/juanmitaboada/zark-gnome-app/security/advisories/new>,
or write to the maintainer at the address in `debian/control`. Please do
not open a public issue for a security problem.
