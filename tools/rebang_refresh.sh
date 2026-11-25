#!/bin/sh
# 拾光资讯 v11 定时刷新（不需要任何 token / 模型）：
#   t.me 附加信息 → TG/RSS/官方源入库 → 热搜 + 按日归档 → 博主（博客、公众号、即刻、YouTube；微博未配置时只记录状态；X 只读 var/rebang/x-dump 里已有的转储）
#   → 翻译缓存回填（入库时自动查 var/rebang/translate/cache.json）→ 建站 site-v11/ → 发布 gh-pages（rebang/ 子目录）
# 幂等、加锁，可每 30 分钟跑一次。任何一步失败：保留上一份数据继续往下走；建站失败则不替换 site-v11、不发布。
# 用法：sh tools/rebang_refresh.sh [--no-publish] [--no-fetch]
#   环境：BOX_PYTHON（默认 python3）、REBANG_PUBLIC_BASE（默认 https://news.kwinweng.com/，站点由 nginx 从 rebang/ 子目录挂在根路径）
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
PY=${BOX_PYTHON:-python3}
BASE=${REBANG_PUBLIC_BASE:-https://news.kwinweng.com/}
publish=1
fetch=1
for option in "$@"; do
    case "$option" in
        --no-publish) publish=0 ;;
        --no-fetch) fetch=0 ;;
        *) echo "unknown option: $option" >&2; exit 2 ;;
    esac
done
export TZ=Asia/Shanghai
mkdir -p var/rebang/in var/rebang/cache var/rebang/logs
exec 9>>var/rebang/.refresh.lock
if ! flock -n 9; then
    echo "rebang refresh busy; skipped"
    exit 0
fi
log=var/rebang/logs/refresh-$(date +%Y%m%dT%H%M%S).log
status=var/rebang/logs/last-refresh.json
failed=''
step() {  # step <名字> <命令…>：失败只记下，不中断
    name=$1; shift
    printf '== %s %s\n' "$(date '+%F %T')" "$name" >> "$log"
    if "$@" >> "$log" 2>&1; then printf 'ok   %s\n' "$name"; else printf 'FAIL %s (see %s)\n' "$name" "$log"; failed="$failed $name"; fi
}
ingest() {
    out=var/rebang/in/ingest.json
    if [ "$fetch" = 1 ]; then "$PY" -m rebang.ingest --db tg.db --media-root . --out "$out.tmp"; else "$PY" -m rebang.ingest --db tg.db --media-root . --no-fetch --out "$out.tmp"; fi
    mv -f "$out.tmp" "$out"
}
bloggers() {
    # X 只读现有转储。始终运行适配器，让 CLI 处理 REBANG_X_DUMP 并报告缺少原稿，而不是跳过整个平台。
    platforms=blog,wechat,jike,youtube,x,weibo
    weibo_cookie=${REBANG_WEIBO_COOKIE:-$HOME/.config/rebang/weibo-cookie.txt}
    weibo_out=${REBANG_WEIBO_OUTPUT:-var/rebang/weibo-crawler}
    # 只检查文件是否存在，缺配置也由适配器记录状态。
    if [ -f "$weibo_cookie" ]; then
        mkdir -p "$weibo_out"
    fi
    "$PY" -m rebang.bloggers --out var/rebang/in/bloggers.json --platform "$platforms" \
        --weibo-cookie-file "$weibo_cookie" --weibo-output "$weibo_out" --translate-engine cache
}
build() {
    tmp=site-v11.tmp-$$
    rm -rf "$tmp"
    # step 在 if 里调用本函数，set -e 不生效：每步失败都要显式返回，不能轮换 site-v11
    "$PY" -m rebang.site --in var/rebang/in --out "$tmp" --hot-archive var/rebang/hotsearch-archive --public-base "$BASE" || { rm -rf "$tmp"; return 1; }
    [ -f "$tmp/index.html" ] && [ -f "$tmp/data/meta.json" ] || { rm -rf "$tmp"; return 1; }
    rm -rf site-v11.prev
    # .prev 删不掉时 mv 会把旧站挪进它里面，必须先停
    [ ! -e site-v11.prev ] || { rm -rf "$tmp"; return 1; }
    if [ -d site-v11 ]; then mv site-v11 site-v11.prev || { rm -rf "$tmp"; return 1; }; fi
    mv "$tmp" site-v11 || { [ -d site-v11.prev ] && [ ! -e site-v11 ] && mv site-v11.prev site-v11; rm -rf "$tmp"; return 1; }
}
pub() {
    if [ ! -f site/index.html ] || [ ! -f site/build-info.json ]; then
        echo 'old public site/ not built yet (tools/box_scrape.sh builds it); skip publish'; return 1
    fi
    # 与 box_scrape（旧站抓取发布）共用同一把锁，避免两边同时动 git worktree / gh-pages
    "$PY" - <<'PYEOF'
import fcntl, subprocess, sys, time
with open('.box-scrape.lock', 'a') as lock:
    for _ in range(90):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
        except BlockingIOError:
            time.sleep(10)
    else:
        print('box scrape still running after 15 min; skip publish'); sys.exit(1)
    sys.exit(subprocess.run(['sh', 'tools/publish_pages.sh', '--already-built']).returncode)
PYEOF
}
start=$(date '+%F %T %z')
if [ "$fetch" = 1 ]; then
    step tgmeta "$PY" -m rebang.tgmeta
    step hotsearch "$PY" -m rebang.hotsearch --out var/rebang/in/hotsearch.json --live --archive var/rebang/hotsearch-archive
    step bloggers bloggers
fi
step ingest ingest
built=0
step build build && built=1
case " $failed " in *" build "*) built=0 ;; esac
if [ "$publish" = 1 ] && [ "$built" = 1 ]; then step publish pub; fi
printf '{"start": "%s", "end": "%s", "failed": "%s", "log": "%s"}\n' "$start" "$(date '+%F %T %z')" "${failed# }" "$log" > "$status"
find var/rebang/logs -name 'refresh-*.log' -mtime +7 -delete 2>/dev/null || true
[ -z "$failed" ]
