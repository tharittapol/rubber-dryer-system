#!/bin/sh
set -eu

TEMPLATE="/mosquitto/config/conf.d/bridge-emqxcloud.conf.tmpl"
OUTDIR="/tmp/mosquitto.d"
OUTPUT="$OUTDIR/bridge-emqxcloud.conf"

: "${EMQX_HOST:?Missing EMQX_HOST}"
: "${EMQX_PORT:?Missing EMQX_PORT}"
: "${EMQX_CLIENTID:?Missing EMQX_CLIENTID}"
: "${EMQX_USERNAME:?Missing EMQX_USERNAME}"
: "${EMQX_PASSWORD:?Missing EMQX_PASSWORD}"
: "${MOSQ_CAFILE:?Missing MOSQ_CAFILE}"

[ -f "$TEMPLATE" ] || { echo "Template not found: $TEMPLATE" >&2; exit 1; }
[ -f "$MOSQ_CAFILE" ] || { echo "CA file not found: $MOSQ_CAFILE" >&2; exit 1; }

# install envsubst if missing (alpine)
if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst not found, installing gettext..."
  apk add --no-cache gettext >/dev/null
fi

mkdir -p "$OUTDIR"
envsubst < "$TEMPLATE" > "$OUTPUT"
chmod 600 "$OUTPUT" || true

echo "Generated: $OUTPUT"
exec mosquitto -c /mosquitto/config/mosquitto.conf
