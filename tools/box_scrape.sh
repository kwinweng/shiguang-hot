#!/bin/sh
# Bot routine entry point. Python handles validation, locking, persistence and
# publish_pages.sh after persistence; publish failure preserves scrape status.
set -eu
exec "${BOX_PYTHON:-python3}" "$(dirname "$0")/box_scrape.py" "$@"
