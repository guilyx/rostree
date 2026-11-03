# Security policy

## Supported versions

Security fixes go into the latest release. rostree follows semantic versioning,
so upgrading within the same major version is meant to be safe.

| Version | Supported |
|---|---|
| 1.x (latest) | yes |
| < 1.0 | no |

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately through GitHub:
the repository's **Security** tab → **Report a vulnerability**. Only the
maintainers see the report, and the fix and advisory can be prepared there
before anything is public.

Please include the rostree version, what an attacker controls (a `package.xml`,
a workspace path, a snapshot file…) and what they get. A proof of concept helps
but is not required.

You should get a first answer within a week. If it is confirmed, we will agree a
disclosure date with you, and credit you in the advisory unless you would rather
not be.

## What rostree trusts, and what it does not

rostree is a local developer tool: it reads files on your disk and writes
reports. It has no server, opens no network connection, and runs no code from the
packages it reads. The places where untrusted input meets it are:

- **`package.xml` manifests** — parsed with `defusedxml`, which refuses entity
  expansion and external entities. REP 149 `condition` attributes are evaluated
  by a small parser of their own, never with `eval`.
- **The HTML graph** (`rostree graph -f html`) — embeds package names,
  descriptions and paths from those manifests into a page that may be shared.
  Every value is escaped before it reaches the page, and the page loads nothing
  from the network.
- **Snapshot files** (`rostree diff --against`) — read as JSON, never executed.
- **External programs** — `dot` (Graphviz) to render images, and `open` /
  `xdg-open` / `os.startfile` to open a result. Each is called with a fixed
  argument list and a path resolved with `shutil.which`, never through a shell.

A way around any of these is a vulnerability, and we want to hear about it.
