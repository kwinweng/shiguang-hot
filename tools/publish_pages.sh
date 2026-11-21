#!/bin/sh
# Publish only public site output; never stage files in the source checkout.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
dry_run=0
built=0
for option in "$@"; do
    case "$option" in
        --dry-run) dry_run=1 ;;
        --already-built) built=1 ;;
        *) echo "unknown option: $option" >&2; exit 2 ;;
    esac
done
cd "$root"
if [ "$built" = 0 ]; then
    SITE_MODE=public MAIL_DIGEST=0 TZ=Asia/Shanghai "${BOX_PYTHON:-python3}" pipeline.py
fi
# An already-built scrape supplies metadata refreshed after persistence.
if [ "$built" = 0 ]; then
    "${BOX_PYTHON:-python3}" tools/write_build_info.py
fi
for required in index.html build-info.json; do
    [ -f "site/$required" ] || { echo "publish refused: missing site/$required" >&2; exit 1; }
done
if [ -n "$(find site -name '.env*' -print)" ]; then
    echo 'publish refused: .env* found in site/' >&2
    exit 1
fi
temporary=$(mktemp -d)
worktree=$temporary/worktree
cleanup() {
    git -C "$root" worktree remove --force "$worktree" >/dev/null 2>&1 || true
    rm -rf "$temporary"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
git worktree add --detach "$worktree" HEAD >/dev/null
git -C "$worktree" rm -rf --ignore-unmatch . >/dev/null
cp -R site/. "$worktree/"
# 拾光资讯 v11（rebang）：已构建的 site-v11/ 一并发布到 gh-pages 的 rebang/ 子目录
# （服务器 nginx 把它挂到 https://news.kwinweng.com/ 根路径）。REBANG_PUBLISH=0 不带——线上根路径会 404，只在回退到旧阅读器时用。
rebang_site=${REBANG_SITE:-$root/site-v11}
if [ "${REBANG_PUBLISH:-1}" != 0 ] && [ -f "$rebang_site/index.html" ] && [ -f "$rebang_site/data/meta.json" ]; then
    if [ -e "$worktree/rebang" ]; then
        echo 'publish refused: old site already has rebang/' >&2
        exit 1
    fi
    if [ -n "$(find "$rebang_site" -name '.env*' -print)" ]; then
        echo 'publish refused: .env* found in rebang site' >&2
        exit 1
    fi
    mkdir "$worktree/rebang"
    cp -R "$rebang_site/." "$worktree/rebang/"
    printf 'Including rebang site from %s\n' "$rebang_site"
fi
rm -f "$worktree/CNAME"
touch "$worktree/.nojekyll"
if [ -n "${PAGES_CNAME:-}" ]; then
    printf '%s\n' "$PAGES_CNAME" > "$worktree/CNAME"
fi
# Check the exact packaged legacy file, not the v11 build time. The receiver
# (deploy/news-sync.sh) allows at most 2 hours old or 10 minutes into the future.
"${BOX_PYTHON:-python3}" -I - "$worktree/data/live.json" <<'PY'
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
prefix = 'publish refused: site/data/live.json: '
if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
    sys.exit(prefix + 'missing or non-regular file')
try:
    updated = datetime.fromisoformat(json.loads(path.read_text(encoding='utf-8'))['updated'].replace('Z', '+00:00'))
except (OSError, ValueError, KeyError, TypeError, AttributeError):
    sys.exit(prefix + 'invalid updated timestamp')
if updated.tzinfo is None:
    sys.exit(prefix + 'timestamp must include a timezone')
now = datetime.now(timezone.utc)
if now - updated > timedelta(hours=2):
    sys.exit(prefix + f'updated={updated.isoformat()} is older than 2 hours; rebuild the legacy site before publishing')
if updated > now + timedelta(minutes=10):
    sys.exit(prefix + f'updated={updated.isoformat()} is more than 10 minutes in the future')
PY

git -C "$worktree" add --all --force
tree=$(git -C "$worktree" write-tree)
commit=$(printf 'Publish public site\n' | git -C "$worktree" -c user.name='Pages publisher' -c user.email='pages@localhost' commit-tree "$tree")
count=$(git -C "$worktree" ls-tree -r --name-only "$commit" | wc -l | tr -d ' ')
printf 'Pages prepared: files=%s sha=%s dry-run=%s\n' "$count" "$commit" "$dry_run"
if [ "$dry_run" = 0 ]; then
    git push --force origin "$commit:refs/heads/gh-pages"
fi
