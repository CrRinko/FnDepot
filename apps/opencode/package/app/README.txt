OpenCode V2 for fnOS
====================

Version: __VERSION__ (linux-amd64, glibc)
Upstream: https://github.com/anomalyco/opencode

Web UI
------
URL:      http://<NAS-IP>:49374
Username: opencode
Password: cat /var/apps/opencode/etc/password

The password is generated randomly during installation. Only administrators
can see the app entry by default.

Projects
--------
The web server starts in the "opencode/projects" shared folder:
  /var/apps/opencode/share/projects

Put repositories there. Additional folders can be authorized from the fnOS
app settings; OpenCode's tools can use them when fnOS permissions allow.

Command line
------------
  /var/apps/opencode/target/bin/opencode --help

To use the CLI against the running web service:
  OPENCODE_PASSWORD="$(cat /var/apps/opencode/etc/password)" \
    /var/apps/opencode/target/bin/opencode --server http://127.0.0.1:49374

Logs and data
-------------
  /var/apps/opencode/var/opencode.log   service log
  /var/apps/opencode/home               OpenCode config, auth and session data

Security
--------
The server listens on all interfaces. It is protected by HTTP Basic
authentication with the generated password. Do not expose port 49374 directly
to the internet; use the fnOS reverse proxy or VPN if remote access is needed.

Upgrading
---------
Upgrade through FnDepot and the fnOS App Center only. Do not use the TUI
/update command or `opencode upgrade` inside this app: the FPK is managed by
fnOS, and the packaged binary does not use a self-update installation method.
Background update checks are disabled in this package.

