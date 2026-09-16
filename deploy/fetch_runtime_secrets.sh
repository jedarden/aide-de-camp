#!/run/current-system/sw/bin/bash
# ExecStartPre: deliver the Telegram bot token to the server at start.
#
# The consuming process fetches its own secret — the running server never
# depends on an agent (or a human) holding read access to OpenBao. That
# dependency is exactly the shape that stalled the credential-provisioning
# beads ("OpenBao permission denied" on the token path), because the fix was
# assumed to need a broader grant. It does not: it needs this script.
#
# The token travels by pipe from `bao kv get -field=token` straight into a
# mode-600 file under the unit's runtime directory. It never appears in argv,
# an environment variable, a log line, or a manifest. Failure to fetch is not
# fatal: Telegram is an optional integration, so a failed fetch degrades to
# "Telegram disabled" (missing file) while the server starts normally. A
# previous good delivery is kept — a transient OpenBao outage during a
# restart must not disable a working integration.
#
# Env:
#   TELEGRAM_BOT_TOKEN_FILE  target file (default under $XDG_RUNTIME_DIR,
#                            matching RuntimeDirectory= in the unit)
#   TELEGRAM_BOT_TOKEN_PATH  OpenBao KV v2 path to fetch (default: the
#                            documented aide-de-camp token path)

set -euo pipefail
umask 077

# NixOS: /usr/bin and /bin hold almost nothing, so mktemp/mv/chmod live only
# on the current system profile. Prepend it — whatever PATH the unit supplies
# keeps its earlier entries (bao-as resolves from ~/.local/bin first).
PATH="/run/current-system/sw/bin:${PATH:-/usr/bin:/bin}"

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
OUT="${TELEGRAM_BOT_TOKEN_FILE:-$RUNTIME_DIR/aide-de-camp/telegram_bot_token}"
SECRET_PATH="${TELEGRAM_BOT_TOKEN_PATH:-secret/ardenone-cluster/aide-de-camp/telegram_bot_token}"

# Resolve bao-as the way the healthcheck resolves bead: the systemd user
# manager runs this unit with a minimal PATH, so fall back to the documented
# install location before giving up.
if command -v bao-as >/dev/null 2>&1; then
    BAO_AS="$(command -v bao-as)"
elif [ -x "${HOME:-/home/coding}/.local/bin/bao-as" ]; then
    BAO_AS="${HOME:-/home/coding}/.local/bin/bao-as"
else
    echo "fetch_runtime_secrets: bao-as not found - Telegram stays disabled" >&2
    exit 0
fi

mkdir -p "$(dirname "$OUT")"
chmod 700 "$(dirname "$OUT")"

# Write to a same-directory temp file and rename into place: a reader can
# never observe a half-written token file, and a failed fetch leaves any
# previous delivery untouched. umask 077 makes the file mode 600.
TMP="$(mktemp "${OUT}.tmp.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

# stdout (the value) goes only into $TMP. stderr (error text naming the path,
# never the value) flows to the journal so a degradation is diagnosable.
if ! "$BAO_AS" openbao-v2 bao kv get -field=token "$SECRET_PATH" > "$TMP"; then
    if [ -s "$OUT" ]; then
        echo "fetch_runtime_secrets: OpenBao fetch failed - keeping previous delivery at $OUT" >&2
        exit 0
    fi
    echo "fetch_runtime_secrets: OpenBao fetch failed and no previous delivery exists - Telegram stays disabled" >&2
    exit 0
fi

if [ ! -s "$TMP" ]; then
    echo "fetch_runtime_secrets: OpenBao returned an empty token - Telegram stays disabled" >&2
    exit 0
fi

mv -f "$TMP" "$OUT"
echo "fetch_runtime_secrets: delivered $SECRET_PATH to $OUT (mode 600; value never logged)"
