# Vendored static assets

No npm, no build step — these are committed static files (the jkub lesson).
To upgrade: download the new pinned release, update the version + SHA256 here, commit.

| File            | Package    | Version | Source                                                         | SHA256                                                             |
| --------------- | ---------- | ------- | -------------------------------------------------------------- | ------------------------------------------------------------------ |
| `alpine.min.js` | `alpinejs` | 3.14.9  | `https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js` | `3ed1eed252488921df65e363d6715deb04d7f92aaedb9e52199fdf73cb1e0ad3` |

Styling is hand-authored CSS inside `index.html` — no CSS framework.
(Pico CSS was vendored initially, then dropped in the dashboard redesign: a fully
custom design overrode all of it anyway.)

Verify: `Get-FileHash console/static/*.js -Algorithm SHA256`
