#!/bin/sh
# Linux cron entry point. Python handles validation, locking and isolated output.
set -eu
exec "${BOX_PYTHON:-python3}" "$(dirname "$0")/box_scrape.py" "$@"
