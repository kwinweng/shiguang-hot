# 拾光资讯命名统一实施方案

> 2026-11-25。后续由 T3 按 `executing-plans` 逐段执行，串行计划以 [AGENTS.md](../../AGENTS.md) 和 [HANDOFF.md](../../HANDOFF.md) 为准。每段的红灯操作须取得阿欢对具体提交、操作范围和回退方式的批准。

**目标**：产品统一叫「拾光资讯」，英文展示用 `Shiguang News`，项目技术身份统一为 `shiguang-news`，清除生产链路中用于旧产品的 `rebang`、`hot`、`热榜` 命名。

**做法**：先兼容旧入口和已有数据，再让发布包同时提供新旧目录，随后分开切接收、网站路由和仓库身份，最后清理旧入口。公网首页及文章深链始终使用 `https://news.kwinweng.com/`，每段核实线上再进入下一段。

**涉及**：Python、静态前端、Git/GitHub、Mac mini 发布器和 launchd、服务器 `news-sync` 和 nginx、T3、Air。

## 已定范围与实施前置

- 以 [DECISIONS.md](../../DECISIONS.md) 11/25 01:36 原话为准：「我希望到时全部都叫拾光资讯，全部用 News。那些跟 Hot 还有热榜相关的东西，都要被清除掉，这就是我的诉求。你按照这一个来设计方案，并且交给相应的智能体去执行实施。」这条取代同日暂留 `rebang` 的决定。第 6 步须等第 5 步上线核实，以及第 0.5 步发布器跟进 `main`、专用 checkout 迁往 `~/projects/shiguang-news-publish` 后第一轮自然发布成功。0.5 步可先完成自己的批准和验收。
- 基线是方案分支 `0a1471bb`。盘点时 `origin/main` 为 `a42349d0`，仍有旧 `codeload` 地址，而方案分支已含新地址。第 6 步开始时按实际 `main`、第 0.5 步线上版本及服务器现装文件重新盘点。已有改名引用优先复用，实际生产消费者迁移以本方案顺序为准。
- GitHub Pages 服务于 11/25 00:40 停用，`gh-pages` 仍是生产同步源。`gh-pages`、DNS、域名、noindex、`tg.db` 数据口径及发布频率按现状运行。流水线只保留一个数据写入和发布入口。盒子、iOS App、外部供稿器或旧例程有消费者时列在切换清单，由对应项目负责，按需要取得批准。
- `DECISIONS.md`、`docs/HANDOFF-history.md`、历史取证文件、原始快照、Git 历史保留原文。维护中手册里的现行命令和链接要更新。取证目录迁址时保留文件名和内容，更新现行入口中的链接。文章、原始回包、外部 API 路径按其原始含义处理。

## 引用盘点

本页末尾按文件和行号索引 `0a1471bb` 的命中。原始搜索命中 725 行，补扫 `site-v11`、`web-v11`、`hotsearch` 等命中 1,226 行，并入驼峰标识和「热点」后共 1,311 行，文件名检索命中 497 个路径（含 `screenshot` 误报、历史证据和原始快照）。当前隔离工作区有 190 个 skip-worktree 路径，因此以 Git 对象树补扫，避免漏掉稀疏检出的内容。

```sh
# 在实施基线和最后清理时各跑一次。显式给提交，覆盖稀疏检出路径。
git grep -n -I -i -E 'rebang|shiguang[-_]hot|热榜|\bhot\b' HEAD --
git grep -n -I -i -E 'rebang|shiguang[-_]hot|热榜|\bhot\b|hotsearch|hotdaily|HotWebSession|site[-_]v11|web[-_]v11|hot[_-]' HEAD --
git grep -n -I -E '(^|[^[:alnum:]])[Hh]ot[A-Z][[:alnum:]_]*|热点' HEAD --
git ls-files | grep -i -E 'rebang|hot'
git ls-tree -r --name-only HEAD -- rebang/ web-v11/ docs/rebang-v1/ tests/fixtures/rebang/
```

### 有效代码、数据和文件路径

- **Python**。`rebang/` 的 `archive`、`bloggers`、`contract`、`extract`、`hotsearch`、`ingest`、`push`、`site`、`tgmeta`、`translate`，以及绝对、相对和字符串形式的动态导入（例如 `rebang/hotsearch/collect.py` 导入 provider）。同时查 CLI `python -m`、路径用法和函数/变量命名。`contract/{channels,bloggers,hotsearch}.json`、`contract/schema.py`、`site/builder.py`、`archive/build.py`、`tgmeta`、`translate`、`extract` 共同读写 `rebang.*` 格式，涵盖 `items`、`channels`、`bloggers`、`page`、`site-meta`、`site-bloggers`、`hotsearch(-config/-index)`、`archive/history` 的日档和索引、`search-index`、`tgmeta`、`translate-cache/pending`、`extract-cache`。这些是持久格式，需加双读测试。
- **源码和构建目录**。`web-v11/`、`site-v11/`、`site-v11.prev/`、`site-v11.tmp-*`，及 `.gitignore`、CLI 默认值、构建和缓存检查。`web-v11/index.html`、`manifest.webmanifest` 现已显示「拾光资讯」，检查标题、分享元信息、图标、规范链接、`start_url` 和英文文案。`app.js`、`lib.js`、`app.css`、`features/{favorites,search}.js` 有 `Rebang*` 全局、CSS、测试探针、热搜标签和 JSON 路径。`rebang.favorites.v1`、`rebang-v11-{diag,mode,note-closed,read,font}` 以及 `web/modules.js` 的 `rebang.lastSeen`、`rebang-cache:`、`rebang-theme` 也是已有数据。站点更新和回退须验同一浏览器内已存收藏、取消收藏、已读和设置，含 iOS WKWebView。
- **运行状态**。`var/rebang/` 下 `in/`、`cache/`（含 TG 元数据及 ingest/extract）、`translate/{cache,pending}.json`、按日 `archive/`、`hotsearch-archive/`、`x-dump/`、`x-replies/`、`media/`、`weibo-crawler/`、`digests/`、`logs/`、`local-ops/`、`venv/` 和各目录锁。另核对仓库根 `media/`、`tg.db`、`.git/mac-publish/{lock,refs.json,HALT}`。历史素材可能有 `/workspace/shiguang-prod/var/rebang/media/...` 绝对路径，也有来自根 `media/` 的引用。识别两者，验证图片、动图和视频实际加载。`.config/rebang` 的凭据默认路径和环境注入点是运行依赖，只查路径、权限或由配置持有人验收。
- **脚本和变量**。`tools/{rebang_refresh.sh,rebang_mac_refresh.sh,build_rebang_icons.py,translate_deepseek.py,mac_publish.py,mac_publish.sh,mac_publish.launchd.plist.example,publish_pages.sh,dispatch_hourly.py}`，还有 `deploy/news-sync.{sh,service,timer}`、`pipeline.py`、`.github/workflows/hourly.yml`、发布器 0.5 步的固定启动入口以及所有定时器指向的脚本。仓内现行代码与运维入口命中的变量为 `REBANG_{DIGEST_ROOT,JIKE_RSSHUB,PUBLIC_BASE,PUBLISH,REPO,SITE,TRANSLATE_API_KEY,TRANSLATE_CACHE,TRANSLATE_EFFORT,TRANSLATE_ENGINE,TRANSLATE_KEY_ENV,TRANSLATE_MODEL,TRANSLATE_URL,WEIBO_COOKIE,WEIBO_OUTPUT,WEREAD_SESSION,X_DUMP}` 和 `HOT-DAILY_FEED_DIR`。迁移时也检查 `TRANSLATE_KEY_ENV` 指定的变量名。`--no-publish` 在复核和试跑时用，发布 dry-run 要同时带 `--already-built`，否则 `publish_pages.sh` 会先跑 `pipeline.py`。
- **测试**。`tests/test_rebang_*.py`、`tests/rebang_*.test.js`、`tests/rebang_site_testdata.py`、`tests/fixtures/rebang/` 和 `tests/fixtures/rebang-tiny.webm`，以及复用产物的 `test_deepseek_runner.py`、`test_mac_publish.py`、`test_publish_pages.py`、`test_news_server_sync.py`、`test_schedule_tools.py`、`test_news_modules_browser.py`、`news_modules.test.js`。实施时与第 5 步结束后的新测试一并扫描。
- **现行文档**。`README.md`、`AGENTS.md`、`HANDOFF.md`、`进度.md`、`deploy/README.md`、`docs/{BOX-SCRAPER-CUTOVER,SOURCE-FETCH-OPERATIONS}.md`、`docs/rebang-v1/` 下的契约、模块、设计系统、运维、Mac 发布、采集恢复、来源候选和本方案。`docs/legacy/` 和部分运维页混有在用依赖和历史描述，按段处理。例如 `docs/SOURCE-FETCH-OPERATIONS.md` 的 PR #17 固定提交和原流程名是出处，当前可点击的 issue 链接可随 GitHub 身份更新。Pages 已停用，修正 README 与旧站手册仍写「等待停用」的现行说明。`docs/rebang-v1/evidence/`、`handoff-20261117/`、`public-feeds/` 中停更的原始公版投递按历史材料保全。若某 fallback 仍引用旧投递，迁移活跃查找逻辑并验证原快照仍能回读。

### 发布、服务器和外部引用

- **实际包结构**。只读盘点的 `gh-pages` `779d524a` 有根目录 `index.html`、`build-info.json`、`data/live.json`、`archive/manifest.json` 等旧格式校验输入，也有 `rebang/{index.html,app.css,app.js,manifest.webmanifest,data/,media/}`。旧根还生成 `hot.html` 和 `hot-daily/` 等。总 2,363 个文件，子目录 1,069 个，约 57.3 MB 未压缩，双目录阶段至少多这份逻辑文件体量，压缩包和服务器盘峰值需实测。此包的 `build-info.json` 给出的 `source_commit` 是 `06d08d7c`；这只证明分支上包的内容，公网须另行验收。
- **接收与挂载**。仓内 `deploy/news-sync.sh` 负责下载、检查整棵包的公开边界，按包根的旧格式做 archive schema 3、fallback、`data/live.json` 新鲜度和规模校验，再原子交换整个静态根。仓内脚本没有专门从 `rebang/` 抽取的逻辑；`deploy/README.md` 和运维手册记录的是 nginx 用 `try_files /rebang$uri …` 挂到公网根，旧 `/rebang/…` 301 到 `/<…>`。服务器现装 `/usr/local/libexec/news-sync.sh` 据交接与仓内不同；仓内无 nginx 配置，**需服务器只读核对**真实 `ExecStart`、installed SHA、输入选择和各项校验、nginx 展开的 `root`/`alias`/`try_files`/redirect、请求头、`location` 优先级、计时器最近回执和是否还活跃。服务器若单独抽取子目录，D 段明确改该选择器；若整树安装，D 段只增加并启用 `news/` 校验，E 段再切实际对外读取。现装实现是生产补丁基线。
- **Mini**。`tools/mac_publish.py` 现查 `META_PATH = 'rebang/data/meta.json'`、`site-v11/data/meta.json` 和 `tools/rebang_refresh.sh`，核对上次 gh-pages 父包与公网 meta，分别对父包和候选做接收 dry-run，再普通原子推送。`source_commit` 位于包根 `build-info.json`，指的是构建代码 SHA。检查 0.5 步启动器、绝对 Python/PATH、实际 publish lock、`refs.json` / `HALT`、launchd plist 和输出日志。0.5 步已将 checkout 放在 `~/projects/shiguang-news-publish/checkout`，第 6 步仅需更新其 remote；若只读盘点发现 plist 仍含旧引用，列入获批改动范围。
- **外部依赖**。`shiguang-hot-ios` 的 `HotWebSession` 使用现网网页，依据历史交接，实际 URL、允许导航的路径及原生桥接符号由 iOS 负责人复核。只列依赖，独立仓库变更和原生发布另办。还须盘点资讯 bot 的 `feeds-inbox/hot-daily`、X 转储生产者、旧翻译脚本和例程（含旧 `/workspace/shiguang-prod`、`/workspace/rebang-v1-briefs`）、`lingji-news-source` 只读旧阅读器库、Air 和 T3 工作树。`docs/HANDOFF-history.md` 保存了 iOS 依赖和媒体原始路径证据。

### 含 Hot 的不同功能

- **热搜**是 11/15 定下的现行功能，依据 `HANDOFF.md` 和 `rebang/contract/hotsearch.json`。保留百度、知乎、B 站、独立失败状态、北京日期和 60 天档期。`hotsearch`、`HOTSEARCH_SCHEMA`、`--hot-archive`、`view-hot`、`hotHost`、相关 `hot*` JS/CSS/测试、`data/hotsearch.json`、`data/hotsearch/{index,YYYY-MM-DD}.json` 统一建议为 `search-trends` 系列。公网兼容期双出数据文件，测试缓存中的旧前端配新包也能打开当日与历史热搜。知乎 `topstory/hot-lists/total` 等第三方接口、原始回包的字段依供应方协议保留。
- **`hot-daily` 是「今日重点」**。现行入口是 `sources.json` 的源 ID、`hot.source`、投递目录和 `HOT-DAILY_FEED_DIR`，经 `rebang/contract/channels.json` 和 `rebang/ingest/core.py` 给已存在资讯条目打标，与热搜无关。建议对生产者和消费者协调切到 `daily-highlights`、`DAILY_HIGHLIGHTS_FEED_DIR`，只接收一份同日内容。对旧源 ID、归档、健康记录和深链保留可回读映射，维持第 5 步规则与条目 ID，原包保留。
- **旧站「热点」**。`pipeline.py`、`shiguang/enrich/hot.py`、`shiguang/site/{pages,news,history,icons,render}.py`、`web/modules.js` 和历史用例仍参与旧包或供稿。建议改为 `focus`、`focus.html`，`sources.json` 的旧推荐键改 `focus`，旧站逻辑口径按原样；由 A 段确认活跃依赖，H 段验收最终输出。GitHub `Trending` 来源是独立公开资讯来源，依原语义保留。`screenshot.png` 和 `tools/screenshot.py` 是子串误报。

## 推荐命名

| 对象 | 目标名 |
|---|---|
| 产品、英文、项目 | `拾光资讯`、`Shiguang News`、`shiguang-news` |
| 仓库、主仓、SSD | `kwinweng/shiguang-news`、`~/projects/shiguang-news`、`/Volumes/kwin_SSD/Development/shiguang-news` |
| 发布 checkout、T3 | `~/projects/shiguang-news-publish/checkout`、原「拾光资讯」项目迁新 SSD 路径，显示「拾光资讯 / Shiguang News」 |
| Python 包与格式 | `shiguang_news/`、`python -m shiguang_news.site` 等、`shiguang-news.items/1` 等，兼容期读旧 schema |
| 浏览器身份 | `window.ShiguangNews*`、`shiguang-news-*` CSS、`shiguang-news.favorites.v1` 等本地键 |
| 前端、构建、运行、配置 | `web-news/`、`site-news/`、`site-news.prev/`、`site-news.tmp-*`、`var/shiguang-news/`、`~/.config/shiguang-news/` |
| 刷新、图标、变量 | `tools/news_refresh.sh`、`tools/news_mac_refresh.sh`、`tools/build_news_icons.py`、`SHIGUANG_NEWS_*` |
| 文档、测试 | `docs/shiguang-news/`、本方案移为 `docs/shiguang-news/RENAME-PLAN.md`、`tests/test_shiguang_news_*.py`、`tests/shiguang_news_*.test.js`、`tests/fixtures/shiguang-news/` |
| 包、浏览器路径 | `gh-pages:news/`、`news/data/meta.json`；公网根 `/` 为规范首页，迁移期 `/news/…` 和 `/rebang/…` 直接跳到对应根路径，文章深链 `/#/item/<id>` |
| 热搜和今日重点 | `search_trends` Python、`search-trends` JSON/DOM、`data/search-trends.json`、`data/search-trends/<日期>.json`、`--search-trends-archive`、`daily-highlights` 源 ID |

## 实施共用验收和回退约定

- 每段由最新获准 `main` 开独立分支，写针对性的回归用例，先聚焦验收后按规则走合并。生产配置独有的段也用对应分支保存可脱敏的补丁或操作清单及测试；核实合并后的代码自然发布成功，再执行该段批准的切换。GitHub 改名或本地迁址和当天分支合并的先后按 G 段。每段独立记录 `main`/`gh-pages` SHA、源 SHA、日志和核验时间于 `进度.md`。无新包或缺服务器回执时，该段只记待验。
- Python 聚焦命令沿用 `uv run --python 3.11 --with pytest --with pillow --with beautifulsoup4 --with playwright --with lxml --with segno python -m pytest -q -rs`，在结尾加对应测试文件；全量时去掉文件参数。JS 为 `node --test tests/*.test.js`。额外运行 `git diff --check`、改动的 shell 用 `sh -n` 或 `bash -n`。测试在隔离工作区或合成临时 bare 仓/静态目录，无真实账号、采集、通知或部署。服务器原子交换须在 Linux 测，macOS 跳过的用例单列；取证截图变动不随代码提交。
- 上线统一验收。以 Mini 自然 `:05` 回执中的 gh-pages SHA 为准，以 `git fetch --no-tags origin gh-pages` 获取对象，避免跟滚动 HEAD 混淆。把 `PAGES_SHA` 设置为回执的 SHA，`MERGE_SHA` 设置为本段合并提交，`META_PATH` 按阶段设为 `rebang/data/meta.json` 或 `news/data/meta.json`。下载公网 meta 原始字节，与对应包内文件逐字节比对。`source_commit` 可以是在本段合并之后构建的提交，须包含本段合并且与 Mini 本轮记录一致。

```sh
check_dir=$(mktemp -d)
(
  set -eu
  git show "$PAGES_SHA:$META_PATH" > "$check_dir/expected.json"
  curl -fsS --proto '=https' -H 'Cache-Control: no-cache' \
    https://news.kwinweng.com/data/meta.json -o "$check_dir/public.json"
  cmp "$check_dir/expected.json" "$check_dir/public.json"
  shasum -a 256 "$check_dir/expected.json" "$check_dir/public.json"
  git show "$PAGES_SHA:build-info.json" > "$check_dir/build-info.json"
  source_sha=$(jq -er '.source_commit' "$check_dir/build-info.json")
  git merge-base --is-ancestor "$MERGE_SHA" "$source_sha"
  jq -e '.fixture == false and .public_base == "https://news.kwinweng.com/" and .counts.news > 0' "$check_dir/public.json"
)
```

- 公网 GET 首页、JS/CSS、图片/视频、深链、热搜当日和归档、manifest、`robots.txt`，核对页面 meta、HTTP `X-Robots-Tag` 和不公开的 `/mail/`、`/archive/`、`/__login/`、`/api/`。记录 `data_at`、`built_at`、数据数量和 `published=true` 的对应自然接收（每 20 分钟另有最多 90 秒抖动，按现装计时器实值）。旧网页能加载和源版本推进都要通过。
- 回退保留独立已验证静态树、相应 gh-pages SHA、已合入配置与所有运行数据增量。`news-sync-previous` 会随下一轮成功被替换。代码用 revert 合并，按原发布链自然验证；旧包回退通过正常快进生成兼容内容，不强推。新旧 nginx 指向必须与服务器活跃静态树、下一包同时相容。需要紧急切静态树时，在原子交换能力、已确认无在途接收和专门批准下执行，保留失败树供排查。发现 `.git/mac-publish/HALT` 按 0.5 步手册核对 ref、数据库和公网后再恢复。
- 复核材料只给必要 diff、去敏验收点与回退。涉及发布、数据库或用户数据、密钥、权限时按全局规则做异家族只读复核，指定具体可用模型并核实实际执行信息，通常最多两轮。使用 Codex 复核时采用 `runtimeMode:"approval-required"`，在工作区前后运行 `/Volumes/kwin_SSD/Development/t3_personal_bot/scripts/review-guard snapshot|verify <工作区>`。缺这些证据时复核记为未完成。纯文档本页只供排期。

## 八段串行实施

### A · 代码和浏览器先兼容 · 0.75–1.5 人日

- [ ] **前置**。第 0.5 步和第 5 步已在线验收。冻结旧依赖、所有工作树和远端、GitHub 仓库 ID/默认分支、Pages 停用状态、公开路由/响应头、接收 SHA 和现行调度，记录旧 `gh-pages` 基线。向 iOS、Air、盒子和供稿方收集当前调用路径、版本和是否仍运行。检查第 5 步新增的热搜/今日重点消费者。
- [ ] **变更**。迁移包、源码、生成目录和脚本，生产 checkout 默认仍使用同一份既有运行状态，发布目录仍只有 `rebang/`。仓内旧入口能一起改的原子改名；兼容期只为查到的外部 `python -m rebang.<模块>` 或脚本调用提供显式转发，脚本用 `exec` 传递参数和退出码。Python 不建整包软链接，避免同一模块被两个名字重复加载。增加受控的旧 schema 输入映射，持久状态的写格式切换放到 B。公开 JSON 的格式要和 A 仍在使用的旧客户端相容，发现依赖旧 schema 时先留旧路径的旧格式输出，明确下游切换点。前端成组更新 `Rebang*`/CSS/读存储，测试旧缓存 JS/CSS 混入场景，必要时给变更资产做版本化。旧页面会写旧键，因此可回退期须保证旧键也含最新收藏。若回退时旧页面有新增或删除，再升级应反映这份变动。按实际浏览器能力测试双写失败和恢复，避免复活已取消的收藏。实现旧浏览器键首次读与完整迁移，支持旧 ID 数组和对象格式、新值优先、写入成功再确认，隐私或额度限制时保留旧值。热搜与今日重点的命名按阿欢选择，等待期间各功能照常。
- [ ] **验收**。`test_rebang_contract.py`、`test_rebang_site.py`、`test_rebang_site_browser.py`、`test_rebang_hotsearch.py`、`test_mac_publish.py` 和更名后的同类测试，加 JS 全量。用预置旧值的浏览器验证重启/回退、收藏、搜索、热搜、分享与文章 ID。线上应继续匹配 `rebang/data/meta.json`，Mini 构建使用新代码。
- [ ] **回退与批准**。B 之前可 revert 本段，保留已有路径与浏览器数据。B 之后先按 B 的回退流程证明旧代码能读含新增内容的状态。改名代码准备属绿灯；发布与收藏数据触发跨家族复核，涉及旧凭据文件的操作留给 B 的获批切换。

### B · 切换运行目录及供稿 · 0.5–1 人日

- [ ] **前置**。A 已自然上线，清楚列出锁、写入者、账号、源/目标卷、所有显式路径以及最后一次正常发布的快照。用合成树演练同卷移动和失败回退，检查树大小、空目录、文件校验、权限和旧指向。核实 0.5 步如果把数据和代码置于不同目录，迁移当时生效的运行根。供应方若未切 `daily-highlights`，消费者先支持旧投递作为回读，等外部确认生产切换再清。
- [ ] **变更**。先做可恢复快照，随后在批准窗口内等所有写进程退出，持实际 Mini 发布锁及适用的刷新/翻译等排他锁，将 `var/rebang` 同卷改名为 `var/shiguang-news`，确保旧工具经暂时兼容路径仍命中同一棵树及同一锁文件 inode；或由单一显式运行根统一指向新目录。旧、新物理目录同时含数据时停止并按来源、时间、ID、哈希人工核对，禁止自动覆盖或合并。需要跨卷则先复制到新卷空目录，停写后做最终增量和校验，再交换指向。备份文件只留本机受控位置，绝不进入 Git 或公开包。`venv` 有绝对路径脚本，按新位置重建并验解释器，或继续使用 0.5 步独立环境。数据库与根媒体照现有独立位置工作。
- [ ] **数据兼容**。在读取时识别旧格式并规范化路径，或用可重复的离线迁移把现用缓存转换成新 schema，记录键、条目及日期数量和变更前后摘要。保留翻译 cache/pending 键、TG 补充索引、X 原始转储和回复、每日期最后成功热搜、资讯归档、媒体及条目 ID。旧绝对媒体路径只针对已识别的受控根映射并检查实际文件。对需要回退的文件在演练中证明旧代码能读迁后新写数据，若不兼容，准备反向转换并以含增量的新树为输入。环境新旧名称都配置时，新名优先，路径冲突在写前停止；通过受批准的配置入口更新注入绑定。凭据目录由持有人只移动路径/重绑，保持权限和所有权，仅核对文件元数据。
- [ ] **验收**。`test_rebang_translate.py`、`test_deepseek_runner.py`、`test_rebang_ingest.py`、`test_rebang_bloggers.py`、`test_rebang_archive.py`、`test_rebang_hotsearch.py`、`test_mac_publish.py`。合成目录先测一份逻辑状态、重试不丢写、移动中断、正反格式转换；线上记录前后文件数、归档日期/条数、缓存命中、媒体核验及 Mini 自然发布。
- [ ] **回退与批准**。持同样的锁，先保全并验证切换后的最新树；若需反向转换，先在旁路验证，再恢复原路径、注入名和入口。使用新旧阶段均能读的兼容提交持续构建。生产运行目录、密钥路径、例程变更属红灯；跨家族复核迁移、用户数据与发布边界。

### C · gh-pages 双目录 · 0.5–1 人日

- [ ] **前置**。B 通过，实际 `news-sync`、nginx 路由和包根校验查明。用 `git ls-tree` 和实际压缩包量测候选文件数、解包时间、磁盘、下载时限与每轮发布容量；对照当前 receiver 规模阈值推演 F。基线 `2363 / 1069` 仅供估算，按实测包计算签核。
- [ ] **变更**。`tools/publish_pages.sh` 从同一次 `site-news/` 构建拷贝两份普通文件树 `news/` 与 `rebang/`，两份内容逐文件哈希相同，保留包根 `site/` 产物、`build-info.json` 和元数据，遇缺子树或目录冲突拒绝打包。禁止归档软/硬链接。Mini 的父包校验按当前上线规则识别旧单树或双树，候选要求双树一致，继续核对公网旧路径的 meta 原始字节。新单树父包的识别和读指纹在 F 落地并保留至回退完成。两份都存在但内容不一致时停止，避免用另一份掩盖线上回退或损坏。
- [ ] **验收**。`test_publish_pages.py`、`test_mac_publish.py`、`test_news_server_sync.py` 加缺目录、坏文件、双树内容不一致、旧单树父包的合成用例。`sh tools/publish_pages.sh --dry-run --already-built` 只在合成 checkout 测。线上运行 `git diff --exit-code "$PAGES_SHA:rebang" "$PAGES_SHA:news"`，然后核对 Mini 回执和接收 `published=true` 对应同一包，公网仍匹配旧子树。
- [ ] **回退与批准**。D 开始前可 revert 为旧单树并自然发布。以后恢复旧树按 D/E 顺序先回到兼容接收。仓内兼容实现绿灯；发布链路跨家族复核，包含包容量和父包兼容。

### D · 服务器接收切新路径 · 0.25–0.5 人日

- [ ] **前置**。C 的双树已实际接收。对 `/usr/local/libexec/news-sync.sh` 做受控独立备份和 SHA 记录，确认 `ExecStart`、真实静态根、timer、部署锁、当前/previous 树及 nginx 拟切路径。先用现装脚本和合成包复现当前行为。
- [ ] **变更**。以现装版本做最小补丁。服务器若选子树，改为选择 `news/` 并保留 E 阶段仍需服务的 `rebang/` 树；若落整树，强制 `news/index.html` 和 `news/data/meta.json` 可解析、`fixture=false`、HTTPS 根的 `public_base` 正确，并验证应有的静态资源。两份共存时核对 meta 指纹相等。接收回执带所选路径和 meta 摘要，便于关联实际收到的包。过渡期仍接收旧树用于 E 前服务和回退。坚持整包公开边界、路径校验、旧根 schema/新鲜度/完整性、锁和原子交换。生产 URL 这段继续使用当时的旧仓库入口。仓内 `deploy/news-sync.sh` 和其测试更新同一契约，安装补丁与仓内差异保留可审查记录。
- [ ] **验收**。`bash -n deploy/news-sync.sh`、`python3 -I tests/test_news_server_sync.py`，Linux 合成树增加双目录通过、`news/` 缺失或损坏时目标 inode 和内容不变、旧根约束仍拦截的用例。获批安装前以 `--source <合成包> --target <临时目标> --dry-run --work-dir <临时目录>` 核对新旧以及 F 的新单树候选。安装后等 `journalctl -u news-sync.service --since '<窗口 UTC 时间>' --no-pager` 当轮显示 `published=true`，记录服务器选中新路径或已校验 `news/` 的证据，与包 SHA 和公网指纹对应。D 阶段公网仍服务旧树。
- [ ] **回退与批准**。异常时由获批操作者恢复原脚本，保留下一轮继续接收双目录，按共用回退确认当前树完整。服务器安装属红灯，跨家族复核现装基线 diff 与接收测试。

### E · nginx 根路径切新树及旧链接跳转 · 0.25–0.5 人日

- [ ] **前置**。D 已过自然同步，新树完整。按真实展开配置制作补丁和备份，确认根 `try_files`、`location` 优先级、查询串和安全路由。以本地 nginx 合成站验证原配置、补丁和回退。
- [ ] **变更**。公网 `/` 和根资产改为从静态根的 `news/` 服务。兼容期 `/rebang`、`/rebang/…` 与 `/news`、`/news/…` 跳转到规范根的同一路径，保留查询串，让浏览器保留原片段 `#/item/<id>`。禁止暴露 gh-pages 包根或 previous。保留 robots 和禁止路径，补测 `/news/mail/`、`/rebang/api/` 跳转后也不可读。批准后 `nginx -t` 通过才 reload。
- [ ] **验收**。用 GET `curl -sS -D - -o /dev/null 'https://news.kwinweng.com/rebang/data/meta.json?check=1'` 验 301 和 `Location`，对 `/news/…`、带斜杠和无斜杠入口重复。浏览器跟随旧文章深链，确认哈希保留、同源收藏和文章可打开。公网指纹改按 `news/data/meta.json` 对照；观察 E 后首个新 gh-pages 包自然接收并验证 `published=true`、资产、移动端及 iOS 路径；没有真机回执就列为待验。
- [ ] **回退与批准**。F 前包仍有两份，恢复 E 前 nginx 配置，`nginx -t` 后 reload 并验证旧树指纹；F 后必须先恢复兼容双树并验在服，再把 nginx 指回旧树。服务器/nginx 属红灯，跨家族复核路由与回退。

### F · 发布包移除旧子树 · 0.25–0.5 人日

- [ ] **前置**。E 后成功自然同步至少一轮，建议再观察 24 小时，确认消费者都使用根/新树，旧 URL 由 nginx 提供跳转。用最新双树当基线实测新单树能过原有 `max(100, ceil(当前静态树公开文件数 × 0.5))` 检查；若失败，保留双树并另做经过复核的分树完整性设计。切换后的第一轮仍会以双树为父包。
- [ ] **变更**。候选包只放 `news/`，`tools/mac_publish.py` 父包校验接受双树或新单树，候选只认新单树，公网只对 `news/data/meta.json`。包根兼容旧站校验的 `site/` 产物仍照发。`news-sync` 保留接收曾验证的双树以便回退。
- [ ] **验收**。`test_publish_pages.py`、`test_mac_publish.py`、`test_news_server_sync.py` 对「双父包→新候选」「新父包→新候选」都过。`git cat-file -e "$PAGES_SHA:news/data/meta.json"` 成功，`git cat-file -e "$PAGES_SHA:rebang"` 按预期找不到，`build-info.json` 和旧根校验文件存在。等自然接收，公网指纹、最新条目及旧 URL 301 都通过。
- [ ] **回退与批准**。若已发布新单树，提交向前修复，只恢复候选双目录输出，保留识别新单树父包和使用 `news/` 指纹的逻辑。先以新单树父包和双树候选演练，再正常快进发布，nginx 继续读新树。批准记录绑定将旧子树从发布包和静态快照轮转清出的实际范围；发布链路跨家族复核。保留独立双树备份。

### G · 改 GitHub 与本地身份 · 0.75–1.5 人日

- [ ] **前置及证据**。F 通过。记录源和目标仓库 ID/默认分支、`main` 和 `gh-pages`、Pages 停用、两个仓库名的占用情况。分别核对接收、Mini、旧盒子、Air 的真实 URL、现有工作树的路径、HEAD、分支、未提交文件、当前线程和各 remote 的 fetch URL、独立 push URL、refspec、过滤器、upstream。以 `gh repo view kwinweng/shiguang-hot --json id,nameWithOwner,defaultBranchRef,viewerPermission` 和 `gh api repos/kwinweng/shiguang-hot/pages` 取证。Pages 响应须结合可确认的仓库访问权限解读。只摘录无凭据的地址和设置。
- [ ] **确保接收不断**。不得假定 GitHub 网页和 Git URL 的重定向也适用于直连 `codeload`。提前用已获准的非生产演练验证实际 `curl -q --fail --location --silent --show-error --proto '=https' --proto-redir '=https'` 下载方式、内容校验与失败路径。正式窗口前在现装基线上预备一行 URL 补丁和回退件。推荐在同一获准窗口先为现装 receiver 准备只针对已核对仓库身份的旧/新地址兼容入口，以已知可用 URL 为主，仅在明确旧地址失效时尝试新地址，失败仍保留最后一棵正常静态树。若准备只改一行，则须核对旧 `codeload` 的连续性，且建立服务器切换窗口、在途检查和失败回退安排。验证不了之前停在此处。保持 HTTPS 与校验边界，旧 URL 只在窗口使用，切完去掉回退分支。演练要确认两套端点决策在至少一处失效时可快速回到已知可用入口，避免把最后一版静态树能访问误记为持续更新。
- [ ] **GitHub 与生产 remote**。选两个 `:05` 之间的充足窗口，先核实无在途发布与接收、取得实际发布锁并备好两端切换件；再按阿欢批准执行 `gh repo rename shiguang-news -R kwinweng/shiguang-hot`。立即核对新 ID 相同、分支未被改写、Pages 仍关闭以及新/旧 URL 的 GET tarball。新入口校验后用现装脚本最小补丁切到 `https://codeload.github.com/kwinweng/shiguang-news/tar.gz/refs/heads/gh-pages`。持同一把 0.5 步发布锁且无在途推送，改 `~/projects/shiguang-news-publish/checkout` 的 `origin`，保持相同 fetch/push 规则、认证、不动 checkout 路径；对照 `refs.json`、当前两条远端回执、代码和数据，无 HALT 后等下一轮自然运行。接收与 Mini 两处都通过才开始收尾本地迁址。
- [ ] **主仓和 SSD**。先让旧路径的线程、终端、编辑器和任务退出。在新路径均无目录及悬空链接、状态和演练均通过后，获批操作者从两目录以外执行以下命令。先后顺序沿用 11/22 旧方案第 4 段，另修复所有保留的 T3 worktree。每项后检查真实状态，部分成功时只撤回已执行项。

```sh
old_main="$HOME/projects/shiguang-hot"
new_main="$HOME/projects/shiguang-news"
old_ssd=/Volumes/kwin_SSD/Development/shiguang-hot
new_ssd=/Volumes/kwin_SSD/Development/shiguang-news
(
  set -eu
  test -d "$old_main/.git" && test -f "$old_ssd/.git" || exit 1
  for dest in "$new_main" "$new_ssd"; do
    test ! -e "$dest" && test ! -L "$dest" || exit 1
  done
  git -C "$old_main" worktree move "$old_ssd" "$new_ssd"
  mv -n "$old_main" "$new_main"
  test -d "$new_main/.git" && test ! -e "$old_main" || exit 1
  git -C "$new_main" worktree repair "$new_ssd"
  git -C "$new_main" worktree list --porcelain
  git -C "$new_ssd" rev-parse --path-format=absolute --git-common-dir
  git -C "$new_ssd" remote set-url origin git@github.com:kwinweng/shiguang-news.git
  git -C "$new_ssd" remote set-url mini-handoff https://github.com/kwinweng/shiguang-news.git
  git -C "$new_ssd" ls-remote origin refs/heads/main refs/heads/gh-pages
)
```

- [ ] **T3、其他 remotes、Air**。对每个保留 worktree 用新主仓 `git worktree repair <实测路径>` 修复并比对迁前 HEAD、分支和未提交状态。现有 `~/.t3/worktrees/shiguang-hot/*` 前缀只有在 T3 支持迁移存量绑定时才同步迁走。否则保留老线程可用，清单交 H 段处理。更新原 T3 项目的 `workspaceRoot` 和显示名，用新 checkout 验证身份、配置和旧线程可读。`origin`、`mini-handoff` 及额外 remote 各保留现有协议、fetch refspec、`blob:none`、upstream，有独立 push URL 的单独换；逐个 `git ls-remote`。Air 已链接但未核实本机，用同样清单检查和更新独立 checkout、自动化引用；Air 操作无法验收时列待办。Mini 的恢复副本保留原文和未提交文件。仓内 `README`、`AGENTS`、`docs/SOURCE-FETCH-OPERATIONS` 的活动地址、`deploy/news-sync.sh`、`tools/dispatch_hourly.py` 和对应测试同段核对；仓内新 URL 的最终调整待新身份可读再合，上线仍走自然轮次。
- [ ] **验收**。GitHub ID、默认分支和 Pages 停用状态核对。Mini 自然 `:05` 产新包，记录 `source_commit`、远端 refs 及原子推送回执。服务器用新 URL 自然接收 `published=true`，公网 meta 匹配新包。各工作树 HEAD/状态及新的 common-dir 路径正确，T3 项目实际新建 checkout 可用，Air 有独立核验回执。`python3 -I tests/test_schedule_tools.py` 和 `python3 -I tests/test_news_server_sync.py` 验 GitHub 地址和服务器脚本，期间不真实 dispatch。
- [ ] **回退与批准**。只回迁失败的身份或目录步骤。需要反向改 GitHub 时获阿欢批准、先核对同一 ID 且旧名未占用，再用 `gh repo rename shiguang-hot -R kwinweng/shiguang-news`；接收与 Mini 恢复对应 remote，核对自然运行。主仓和 SSD 先由新主仓 `git worktree move` 移回 SSD 旧名，再 `mv -n` 主仓回旧名，用旧主仓 `git worktree repair` 恢复 SSD 和 T3 登记，按实际 GitHub 身份恢复远端及 T3 项目路径。GitHub、生产脚本/remote、工作区迁移依本阶段红灯办理；跨家族复核生产连续性、路径和权限边界。

### H · 清除旧入口、文档迁址与最终验收 · 0.5–1 人日

- [ ] **前置**。G 自然发布和接收通过。逐一核对旧 Python、脚本、环境、web JSON、数据路径、T3、Air 与外部生产者的兼容调用；按阿欢确定的旧入口期限，证据显示可撤。过渡期有真实设备只带旧收藏时，保留范围明确的只读迁移器，使其能迁移后首次访问。浏览器回滚期间双写兼容结束后，新键单写、旧键仅导入，导入成功的空集合也持久记录，避免重现已取消收藏。
- [ ] **变更**。删除获批的旧 wrapper、运行目录软链接、旧环境别名、旧热搜网络路径和活跃旧命名。历史格式解码器可搬入统一迁移入口，旧 schema 和持久 ID 仅作为可导入的数据格式，仍在用的旧实例列成限时兼容及负责人。旧站包根的 `hot.html` / `hot-daily` 以 A 的名字收尾，仍提供包根校验必需文件。迁 `docs/rebang-v1/` 至 `docs/shiguang-news/`，方案改为 `RENAME-PLAN.md`；把附录盘点引用标为历史基线，更新现行文档、测试及忽略规则。获批后退役 nginx `/rebang/` 入口；若选择延长 301，清理段保留明确截止点。最后再考虑清理批准清单内的退役 T3 worktree、旧发布目录备份；包含未提交文件的一律先保全。历史数据、已保存收藏和备份不因命名清理被删除。
- [ ] **验收**。跑全量 Python、JS、`git diff --check` 和本页三类扫描。每个余项给出处，如历史证据、上游协议、旧数据迁移读取或外部项目待办。未支持的 T3 前缀和延长的 301 标为剩余例外。重复自然发布和自然接收指纹，检查旧路由按批准策略返回、新闻及博主条数正常、热搜当日和历史均可读、收藏/设置/搜索不丢。检查发布包 `news/` 子树、包根 `build-info.json` 和校验输入齐备。
- [ ] **回退与批准**。逐项 revert 兼容入口，恢复 nginx redirect 只需已验证的路由补丁，恢复删除的工作区文件要用清理前独立归档。需恢复旧数据路径时按 B 的锁和增量规则执行。删旧目录/文件和服务器退役路由属红灯。用户数据、发布链路和路径清理跨家族复核。

## 请阿欢拍板的三件事

1. **两个功能的技术名称。** 建议选 1「热搜用 `search-trends`，今日重点用 `daily-highlights`，中文和功能照旧」；选 2「沿用现行功能，另定技术规范名」。不回复时先保留两项功能及兼容，暂缓清理这两类旧命名。
2. **旧链接兼容期限。** 建议选 1「`/rebang/` 先 301，待新包稳定 14 天且核对 iOS 与已知消费者，再批准撤掉」；选 2「继续保留 301，列为过渡遗留」；选 3「指定另一个期限」。不回复时现有 301 继续，暂不执行撤除。收藏兼容以保住旧数据为验收，旧客户端未迁移或没有可行导入方式时单列，不能以日期为由静默丢收藏。
3. **T3 如不支持原地改历史前缀。** 建议选 1「原项目迁新路径，保留老线程和旧路径的只读登记，支持迁移后逐步收尾」；选 2「先保全旧线程和未提交文件，批准清单后迁移可替换的工作区，再清理原路径」。不回复时保留历史工作区和数据，不删除或重建原项目。

八段合计约 **3.75–7.5 人日**，另计审批、外部配合、取证与自然发布/接收等待。最大风险是接收脚本、nginx、Mini 的指纹路径与 GitHub 归档入口在不同机器上生效，任一环节先清旧就可能让站点停更或根路径 404。双包期按同一次构建对字节，等到自然接收确实更新公网再前进，保留能即时恢复的静态树和绝对路径清单。

## 附录 · 基线命中索引

以下索引均以 `0a1471bb` 行号为准。数字记录文本命中的行，文件名列还包含只有路径命中的条目。提取文本可用 `git show 0a1471bb:<路径>`，按指定行号查看。重复的目录路径以目录行归并。

### 工具、发布、接收和忽略规则

```text
.gitignore  29–33
deploy/README.md  14–15, 78
tools/build_rebang_icons.py  10–11
tools/login_gate.py  109, 122
tools/mac_publish.py  19, 27–28, 103, 105
tools/publish_pages.sh  40–45, 48–49, 52–54
tools/rebang_mac_refresh.sh  2, 6–7, 13, 20, 27
tools/rebang_refresh.sh  3–7, 12, 23–24, 26, 29–30, 38–39, 43, 45–46, 52, 56, 58–59, 61, 63–65, 87–88, 97
tools/translate_deepseek.py  2, 4, 7, 24, 26, 143, 147, 151–153, 164
```

### 现行或混合文档

```text
AGENTS.md  16, 24, 27
HANDOFF.md  2, 5, 9, 20, 22–23, 26, 30, 33, 35–36
README.md  7, 9–11, 18, 25–31, 40–42
docs/BOX-SCRAPER-CUTOVER.md  8–9, 26–27
docs/SOURCE-FETCH-OPERATIONS.md  3, 28
docs/legacy/ARCHITECTURE.md  3, 5, 11, 18, 34, 39–40, 48, 73, 77, 107, 124
docs/legacy/DESIGN.md  3, 5, 10
docs/legacy/INGEST.md  3, 94
docs/legacy/README.md  5–7, 13, 42
docs/rebang-v1/COLLECTION-RECOVERY.md  9–11, 17, 21–23, 31, 37
docs/rebang-v1/CONTRACT.md  3, 9–12, 16, 18, 35, 37, 40, 42, 44, 46, 48, 50, 52–53, 59–66, 72–81, 84, 86, 91–92, 98–99
docs/rebang-v1/DESIGN-SYSTEM.md  1, 3, 17, 69
docs/rebang-v1/MAC-PUBLISH.md  9–10, 27
docs/rebang-v1/MODULES.md  4, 12, 14–17, 21, 26–31, 34–36, 38, 41, 44–46, 48–49, 51–52, 54, 56–57, 60–63, 67–69, 72, 75–76, 82
docs/rebang-v1/OPERATIONS.md  3, 7–11, 13, 26, 28, 30, 32, 34, 38–39, 41–42, 44, 48, 51
docs/rebang-v1/youtube-candidates.md  6
进度.md  6, 10
```

### 历史原文与被本方案替换的草案

```text
DECISIONS.md  11, 19, 37–39
docs/HANDOFF-history.md  5, 7–8, 12, 16–18, 25–26, 32–39, 41–42, 47, 49, 55, 57–62, 65, 69, 71, 73, 97, 105
docs/rebang-v1/NEWS-RENAME-PLAN.md  10, 20–24, 31
docs/rebang-v1/evidence/bloggers/live-run-summary.json  3
docs/rebang-v1/evidence/frontend-v11/README.md  8, 10
docs/rebang-v1/evidence/frontend-v11/capture-log.json  9, 13
docs/rebang-v1/evidence/frontend-v11/capture.py  2, 14, 54–55, 65, 67, 124, 143, 151–152
docs/rebang-v1/evidence/hotsearch/live-hotsearch.json  2, 14, 23, 32, 41, 50, 59, 68, 77, 86, 95, 104, 113, 122, 131, 140, 149, 158, 167, 176, 185, 194, 203, 212, 221, 230, 239, 248, 257, 266, 275, 284, 292, 301, 310, 319, 328, 337, 346, 355, 364, 373, 382, 391, 400, 408, 417, 426, 435, 444, 453, 463, 470, 478, 487, 496, 505, 514, 523, 531, 539, 548, 557, 565, 574, 582, 591, 600, 609, 618, 627, 636, 645, 654, 663, 672, 681, 688, 697, 704, 713, 721, 737, 744, 751, 758, 765, 772, 779, 786, 793, 800, 807, 814, 821, 828, 835, 842, 849, 856, 863, 870, 877, 884, 891, 898, 905, 912, 919, 926, 933, 940, 947, 954, 961, 968, 975, 982, 989, 996, 1003, 1010, 1017, 1024, 1031, 1038, 1045, 1052, 1059, 1066, 1073, 1080
docs/rebang-v1/evidence/hotsearch/live-smoke.md  4, 6–7, 12, 26
docs/rebang-v1/evidence/infinite-feed/README.md  8
docs/rebang-v1/evidence/infinite-feed/capture.py  13, 69, 105, 109, 115, 172–173, 175, 179, 181, 184
docs/rebang-v1/evidence/infinite-feed/perf.py  47
docs/rebang-v1/evidence/integration-v13/capture.py  4, 88, 107, 486, 499, 534–535, 539–540, 542–543, 546, 549–550, 552, 570
docs/rebang-v1/evidence/integration-v13/live-result.json  2, 195, 245, 473, 686
docs/rebang-v1/evidence/integration-v13/local-result.json  473, 686
docs/rebang-v1/evidence/integration-v13/p2live-result.json  508, 794–795
docs/rebang-v1/evidence/integration-v13/p2local-result.json  508, 794–795
docs/rebang-v1/evidence/integration-v13/wechat_verify.py  7, 18–19, 60
docs/rebang-v1/evidence/integration/capture.py  3, 56–57, 61–62, 64–65, 68, 71–72, 74, 92
docs/rebang-v1/evidence/integration/live-result.json  2, 35, 228
docs/rebang-v1/evidence/integration/local-result.json  35, 228
docs/rebang-v1/evidence/ios-standalone-fullheight/README.md  13
docs/rebang-v1/evidence/ios-standalone-fullheight/capture.py  14, 31, 53, 88, 97
docs/rebang-v1/evidence/ios-tabbar/capture.py  3, 11, 27, 45
docs/rebang-v1/evidence/perf-0116/check_video_real_data.py  1, 5
docs/rebang-v1/evidence/perf-0116/perf.py  1, 65
docs/rebang-v1/evidence/sources-ingest/live-smoke.txt  3, 40
docs/rebang-v1/evidence/sources-ingest/no-fetch-repo-tgdb.txt  1, 38
docs/rebang-v1/evidence/v16-visual/capture.py  13, 134–136, 138–142, 145, 149, 163, 201, 205, 211, 269–270, 272, 276, 278, 281
docs/rebang-v1/evidence/v16-visual/perf.py  47
docs/rebang-v1/evidence/weibo/capture.py  3
public-feeds/github/2026-10-18/feed.json  48
public-feeds/github/2026-10-20/feed.json  10
public-feeds/hot-daily/2026-10-17/feed.json  3, 5
public-feeds/hot-daily/2026-10-18/feed.json  3, 5
public-feeds/hot-daily/2026-10-19/feed.json  3, 5
public-feeds/hot-daily/2026-10-20/feed.json  3, 5
public-feeds/hot-daily/2026-10-21/feed.json  3, 5
public-feeds/hot-daily/2026-10-22/feed.json  3, 5
```

### Python、来源和旧站根校验依赖

```text
pipeline.py  16, 87
rebang/__init__.py  1
rebang/archive/__init__.py  文件名或目录名
rebang/archive/build.py  4, 16–20, 25, 182, 184
rebang/bloggers/__init__.py  1
rebang/bloggers/__main__.py  1, 13–14, 24–25, 27, 29–33, 35, 38–39
rebang/bloggers/common.py  文件名或目录名
rebang/bloggers/feed.py  文件名或目录名
rebang/bloggers/jike.py  112
rebang/bloggers/media.py  5, 9, 18
rebang/bloggers/preview.py  1
rebang/bloggers/run.py  9, 21, 27
rebang/bloggers/weibo.py  3, 10, 22–23
rebang/bloggers/weread.py  4, 8, 31–32, 337
rebang/bloggers/x.py  文件名或目录名
rebang/bloggers/youtube.py  文件名或目录名
rebang/contract/__init__.py  1–3, 6–7
rebang/contract/bloggers.json  2, 35, 43, 51
rebang/contract/channels.json  2–3, 45
rebang/contract/hotsearch.json  2–3, 5, 10
rebang/contract/schema.py  9–10, 31–32, 291–293, 296–298, 302
rebang/extract/__init__.py  18, 186
rebang/hotsearch/__init__.py  1
rebang/hotsearch/__main__.py  1, 3, 17, 21
rebang/hotsearch/archive.py  3, 11, 14, 28, 34, 42, 75
rebang/hotsearch/collect.py  1, 6, 22, 31, 41
rebang/hotsearch/http.py  8, 74
rebang/hotsearch/providers/__init__.py  文件名或目录名
rebang/hotsearch/providers/baidu.py  4, 6, 27, 40, 45, 49, 64, 66
rebang/hotsearch/providers/bilibili.py  4, 6, 44, 64, 66
rebang/hotsearch/providers/zhihu.py  1, 5, 7, 41, 57
rebang/ingest/__init__.py  1, 5–6
rebang/ingest/__main__.py  7–8, 12, 15, 22–23
rebang/ingest/core.py  1, 14, 18, 173, 193, 356, 407, 410, 412, 499–500, 615, 625
rebang/push/__init__.py  文件名或目录名
rebang/push/__main__.py  1
rebang/push/cli.py  21, 25
rebang/push/load.py  1, 61, 63, 102
rebang/push/render.py  4, 32
rebang/push/select.py  3
rebang/push/timeutil.py  文件名或目录名
rebang/site/__init__.py  1, 3–4
rebang/site/__main__.py  文件名或目录名
rebang/site/builder.py  3–8, 10, 21, 24–26, 32, 104, 111, 125–127, 167–168, 171–174, 184, 220, 224–228, 231–232, 236, 239, 371, 383, 385, 389, 396, 401–402, 430, 438–441, 450, 457, 460, 483–484, 490, 494
rebang/tgmeta/__init__.py  8, 19, 21
rebang/tgmeta/__main__.py  1, 10, 25
rebang/translate/__init__.py  5, 7, 9, 11–12, 23, 33, 93–94, 122, 153, 169–171
rebang/translate/__main__.py  2–3, 15
shiguang/enrich/hot.py  1, 24
shiguang/model.py  47
shiguang/site/history.py  14, 169
shiguang/site/news.py  87
shiguang/site/pages.py  4, 31, 101, 149, 160, 179, 187, 210, 229, 249, 277–278, 280, 286, 289, 293, 297, 309
shiguang/site/render.py  17, 186, 456
sources.json  13, 37
```

### 测试和测试夹具

```text
tests/fixtures/rebang-tiny.webm  文件名或目录名
tests/fixtures/rebang/archive/harness.html  57–60, 106, 151–152
tests/fixtures/rebang/archive/published-items.json  2
tests/fixtures/rebang/bloggers/atom_simonw.xml  文件名或目录名
tests/fixtures/rebang/bloggers/rss_imtx.xml  文件名或目录名
tests/fixtures/rebang/bloggers/rss_jike_rsshub.xml  文件名或目录名
tests/fixtures/rebang/bloggers/rss_karpathy_atom.xml  文件名或目录名
tests/fixtures/rebang/bloggers/rss_oneusefulthing.xml  文件名或目录名
tests/fixtures/rebang/bloggers/rss_wechat2rss.xml  文件名或目录名
tests/fixtures/rebang/bloggers/wechat-article.html  文件名或目录名
tests/fixtures/rebang/bloggers/weread_mp_articles.json  文件名或目录名
tests/fixtures/rebang/bloggers/x_dump/_dump.json  文件名或目录名
tests/fixtures/rebang/bloggers/x_dump/posts.json  文件名或目录名
tests/fixtures/rebang/bloggers/x_dump/quotes.json  文件名或目录名
tests/fixtures/rebang/bloggers/x_dump/replies.json  文件名或目录名
tests/fixtures/rebang/bloggers/youtube_channel_videos.html  文件名或目录名
tests/fixtures/rebang/bloggers/youtube_feed.xml  文件名或目录名
tests/fixtures/rebang/bloggers/youtube_watch.html  文件名或目录名
tests/fixtures/rebang/contract/hotsearch-valid.json  2, 7, 9
tests/fixtures/rebang/contract/items-valid.json  2, 49, 52
tests/fixtures/rebang/hotsearch/baidu-empty.json  1
tests/fixtures/rebang/hotsearch/baidu-success-false.json  文件名或目录名
tests/fixtures/rebang/hotsearch/baidu.json  1
tests/fixtures/rebang/hotsearch/bili-code-error.json  文件名或目录名
tests/fixtures/rebang/hotsearch/bilibili.json  文件名或目录名
tests/fixtures/rebang/hotsearch/not-json.txt  文件名或目录名
tests/fixtures/rebang/hotsearch/zhihu-empty.json  文件名或目录名
tests/fixtures/rebang/hotsearch/zhihu.json  1
tests/fixtures/rebang/ingest/feed-atom.xml  文件名或目录名
tests/fixtures/rebang/ingest/feed-rss.xml  文件名或目录名
tests/fixtures/rebang/ingest/inbox.json  11
tests/fixtures/rebang/ingest/tg-messages.json  文件名或目录名
tests/fixtures/rebang/ingest/trending.html  文件名或目录名
tests/fixtures/rebang/push/bloggers-expired.json  文件名或目录名
tests/fixtures/rebang/push/golden-seven.txt  文件名或目录名
tests/fixtures/rebang/push/items-boundary.json  2
tests/fixtures/rebang/push/items-exclusions.json  2
tests/fixtures/rebang/push/items-seven.json  2
tests/fixtures/rebang/push/items-two.json  2
tests/fixtures/rebang/push/items-zero.json  2
tests/fixtures/rebang/push/meta.json  文件名或目录名
tests/fixtures/rebang/tgmeta/discussion-off.html  文件名或目录名
tests/fixtures/rebang/tgmeta/discussion.html  文件名或目录名
tests/fixtures/rebang/tgmeta/page.html  文件名或目录名
tests/fixtures/rebang/weibo/longtext-RrFnBaNaI.json  文件名或目录名
tests/fixtures/rebang/weibo/mymblog-1560906700.json  文件名或目录名
tests/news_modules.test.js  66–67
tests/rebang_features.test.js  8–9, 21, 95
tests/rebang_site.test.js  1, 4, 72–73, 77, 88–89, 94–95, 99, 257
tests/rebang_site_testdata.py  4, 25, 63–64, 67, 69
tests/test_deepseek_runner.py  8, 16–20, 27, 36, 43, 74, 108, 159–161, 165, 169–170, 213, 246, 249, 252–254, 259, 265–266
tests/test_feeds.py  11, 13, 17, 137, 146, 153, 197, 211
tests/test_ingest_web.py  7, 69, 76, 83
tests/test_mac_publish.py  39, 94, 100–101, 181
tests/test_news_modules.py  142, 148, 150
tests/test_news_modules_browser.py  57, 113, 143, 212, 214, 362
tests/test_publish_pages.py  60, 64–67, 148–150, 152, 157–158, 164
tests/test_rebang_archive.py  9–10, 13–14, 46
tests/test_rebang_archive_browser.py  11, 14–16, 40
tests/test_rebang_blocks.py  10–13, 15
tests/test_rebang_bloggers.py  1, 9–14, 16, 98, 139, 155, 309, 323, 335, 338, 361, 441, 506–508, 527, 534, 555, 574, 600, 623, 638, 657, 668, 707, 729, 737, 755, 767, 802, 827, 857, 887, 898, 929–930
tests/test_rebang_contract.py  1, 7–8, 11, 42, 44–46, 48–49, 65, 67, 71, 74, 76, 79, 81, 172
tests/test_rebang_extract.py  1, 6, 84
tests/test_rebang_hotsearch.py  9–12, 15, 17, 40, 56, 69, 98, 118, 130, 140, 162, 168, 172, 176, 184, 189, 194, 207, 210–211
tests/test_rebang_ingest.py  1, 16–19, 22, 128, 202–203, 207, 237
tests/test_rebang_push.py  8–13, 16, 26, 43, 46, 153, 160, 183, 200, 226, 236, 242
tests/test_rebang_site.py  10–12, 34, 102, 104, 120, 131, 140, 142, 144, 146–147, 180, 209, 211, 214, 218, 223, 228, 262, 264, 284, 286, 288–290, 292–293, 295–296, 299–300
tests/test_rebang_site_browser.py  15–16, 23, 26–27, 43, 46, 72, 83, 134, 160, 168–170, 172, 288, 296, 306, 312, 324, 330, 533
tests/test_rebang_tgmeta.py  9–11, 13, 106, 116, 140, 148
tests/test_rebang_translate.py  8–9
tests/test_render.py  139
```

### 前端与存储

```text
web-v11/app.css  1, 3, 313–330, 339, 344–349, 362, 377–378, 413, 470, 519, 557, 655, 657–683, 686–690, 697, 701–703
web-v11/app.js  3, 11, 26, 35, 43, 73, 84–85, 88, 100–101, 108, 113–116, 148, 152, 161, 198, 229, 642–644, 646, 648, 650, 653–654, 657, 659–665, 667–668, 673, 677, 679–681, 856, 892, 900, 905, 933, 992, 1068–1069, 1073, 1075, 1077, 1080, 1084, 1100, 1112, 1407, 1415–1417, 1441, 1488–1489
web-v11/brand/README.md  1
web-v11/features/favorites.js  6, 8, 118–120, 123–124, 166, 194, 201, 249
web-v11/features/search.js  6, 67–69, 72–73, 90, 167–168, 188
web-v11/index.html  77–78, 81
web-v11/lib.js  10, 172, 174–175, 179, 182, 188, 192, 195–196, 198–199, 201, 378–379, 381
web/app.js  554
web/modules.js  25, 118, 121, 129, 138, 194, 234, 242, 257, 263, 266, 340, 417
web/news.js  7
web/style.css  524
```

文件名额外归并为 `docs/rebang-v1/evidence/**`（368 条）、`public-feeds/hot-daily/**`（6 条）和 `screenshot.png`、`tools/screenshot.py`（2 条误报）。证据目录的可执行捕获脚本按取证原件保留，后续需要复跑时从新入口另建验收命令。
