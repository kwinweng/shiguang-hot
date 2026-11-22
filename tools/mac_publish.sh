#!/bin/sh
set -eu
case ${BOX_PYTHON:-} in
    /*) [ -x "$BOX_PYTHON" ] || { echo 'BOX_PYTHON is not executable' >&2; exit 2; } ;;
    *) echo 'BOX_PYTHON must be an absolute Python path' >&2; exit 2 ;;
esac
command -v flock >/dev/null || { echo 'flock is required on PATH' >&2; exit 2; }
exec "$BOX_PYTHON" -I "$(dirname "$0")/mac_publish.py" "$@"
