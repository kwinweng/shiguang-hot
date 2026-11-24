#!/bin/sh
set -eu
case ${BOX_PYTHON:-} in
    /*) [ -x "$BOX_PYTHON" ] || { echo 'BOX_PYTHON is not executable' >&2; exit 2; } ;;
    *) echo 'BOX_PYTHON must be an absolute Python path' >&2; exit 2 ;;
esac
if [ "${1:-}" = --worker-v1 ]; then
    exec "$BOX_PYTHON" -I "$(dirname "$0")/mac_publish.py" "$@"
fi
# Transitional entry for installations still pointing launchd at the checkout.
command -v flock >/dev/null || { echo 'flock is required on PATH' >&2; exit 2; }
root=$(cd "$(dirname "$0")/.." && pwd -P)
cd "$root"
exec "$BOX_PYTHON" -I "$root/tools/mac_publish_launcher.py" --legacy-entry "$@"
