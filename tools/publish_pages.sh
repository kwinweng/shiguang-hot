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
# 拾光热榜 v11（rebang）：已构建的 site-v11/ 一并发布到 gh-pages 的 rebang/ 子目录
# （news.kwinweng.com/rebang/）。REBANG_PUBLISH=0 不带；回退：删掉/改名 site-v11 后再发布一次即可下线。
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
git -C "$worktree" add --all --force
tree=$(git -C "$worktree" write-tree)
commit=$(printf 'Publish public site\n' | git -C "$worktree" -c user.name='Pages publisher' -c user.email='pages@localhost' commit-tree "$tree")
count=$(git -C "$worktree" ls-tree -r --name-only "$commit" | wc -l | tr -d ' ')
printf 'Pages prepared: files=%s sha=%s dry-run=%s\n' "$count" "$commit" "$dry_run"
if [ "$dry_run" = 0 ]; then
    git push --force origin "$commit:refs/heads/gh-pages"
fi
