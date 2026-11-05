#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

APP="$TMP/target"
CMD="$TMP/cmd"
VAR="$TMP/var"
STORE="$TMP/certs.json"
CRT="$TMP/gitlab.example.com.crt"
KEY="$TMP/gitlab.example.com.key"

cp -a "$ROOT/package/app" "$APP"
cp -a "$ROOT/package/cmd" "$CMD"
mkdir -p "$VAR"

openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 2 \
    -keyout "$KEY" -out "$CRT" \
    -subj "/CN=gitlab.example.com" \
    -addext "subjectAltName=DNS:gitlab.example.com" >/dev/null 2>&1

python3 - "$STORE" "$CRT" "$KEY" <<'PY'
import json
import sys
import time

store, crt, key = sys.argv[1:4]
entry = {
    "domain": "gitlab.example.com",
    "san": ["gitlab.example.com"],
    "certificate": crt,
    "fullchain": "",
    "privateKey": key,
    "validFrom": 0,
    "validTo": int(time.time() * 1000) + 86400 * 1000,
    "used": True,
    "sum": "test",
    "appFlag": 0,
}
with open(store, "w", encoding="utf-8") as stream:
    json.dump([entry], stream)
PY

export TRIM_APPDEST="$APP"
export TRIM_PKGVAR="$VAR"
export GITLAB_CERT_STORE="$STORE"
export GITLAB_DOMAIN="gitlab.example.com"
export HTTPS_PORT="18443"
export HTTP_PORT="18080"
export SSH_PORT="12224"
export TIME_ZONE="Asia/Shanghai"
export TRIM_TEMP_LOGFILE="$TMP/message.txt"

bash -n "$CMD"/*
"$CMD/install_callback"
test -f "$VAR/settings.env"
test -f "$VAR/config/gitlab.rb"
test -f "$VAR/config/ssl/gitlab.crt"
test -f "$VAR/config/ssl/gitlab.key"
grep -q "external_url 'https://gitlab.example.com:18443'" "$VAR/config/gitlab.rb"
grep -q 'GITLAB_DOMAIN=gitlab.example.com' "$VAR/settings.env"

chmod 555 "$VAR/config"
if ! HTTPS_PORT=18444 "$CMD/install_callback"; then
    echo "install_callback should tolerate a read-only config directory" >&2
    exit 1
fi
chmod 755 "$VAR/config"
test -f "$VAR/settings.env"

before="$(sha256sum "$VAR/settings.env" | awk '{print $1}')"
if HTTPS_PORT=443 "$CMD/config_callback"; then
    echo "config_callback unexpectedly accepted port 443" >&2
    exit 1
fi
after="$(sha256sum "$VAR/settings.env" | awk '{print $1}')"
test "$before" = "$after"

touch "$VAR/keep-data"
wizard_data_action=keep "$CMD/uninstall_callback"
test -f "$VAR/keep-data"
touch "$VAR/delete-data"
wizard_data_action=delete "$CMD/uninstall_callback"
test ! -f "$VAR/delete-data"

mkdir -p "$VAR/locked/sub"
touch "$VAR/locked/sub/file"
chmod 555 "$VAR/locked/sub"
if wizard_data_action=delete "$CMD/uninstall_callback"; then
    echo "uninstall_callback should fail when root-owned data cannot be removed" >&2
    exit 1
fi
test -f "$VAR/locked/sub/file"
chmod 755 "$VAR/locked/sub"
rm -rf "$VAR/locked"

echo "lifecycle tests ok"
