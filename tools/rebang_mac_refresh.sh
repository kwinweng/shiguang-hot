#!/bin/sh
# Mac manual entry point. REBANG_DIGEST_ROOT can later point at the synced raw inbox.
# Until then this uses the delivered snapshot; it does not fetch new daily digests.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
digests=${REBANG_DIGEST_ROOT:-$root/var/rebang/digests/20261117T2324}
for directory in feeds-inbox/hot-daily feeds-inbox/github world-brief x-digest; do
    if [ ! -d "$digests/$directory" ]; then
        printf 'missing digest directory: %s\n' "$digests/$directory" >&2
        exit 2
    fi
done
cd "$root"
exec env \
    "HOT-DAILY_FEED_DIR=$digests/feeds-inbox/hot-daily" \
    "GITHUB_FEED_DIR=$digests/feeds-inbox/github" \
    "WORLD_FEED_DIR=$digests/world-brief" \
    "X_FEED_DIR=$digests/x-digest" \
    "BOX_PYTHON=$root/var/rebang/venv/bin/python" \
    "PATH=/opt/homebrew/bin:$PATH" \
    TZ=Asia/Shanghai \
    sh tools/rebang_refresh.sh "$@"
