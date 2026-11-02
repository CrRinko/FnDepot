Hermes Agent for fnOS
=====================

Web UI: http://<NAS-IP>:49375
Username: hermes
Password: no fixed default. It is generated on the first start.

Read the password on the NAS as root:

    sudo cat /var/apps/hermes-agent/etc/password

The dashboard uses a password login page and a signed cookie session.
Do not expose port 49375 directly to the internet.

Upgrades are delivered by FnDepot / fnOS App Center. The built-in
`hermes update` command is disabled by install-stamp.json.
