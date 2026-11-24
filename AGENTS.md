# AGENTS

本仓库的协作规则。入口与代码位置见 [`README.md`](README.md)，当前进度见 [`HANDOFF.md`](HANDOFF.md)，阿欢定过的事见 [`DECISIONS.md`](DECISIONS.md) 和 [`NOT-DOING.md`](NOT-DOING.md)。

## 谁来做（2026-11-24 起）

- 开发在 T3 Code 里进行，按全局「T3 Code 通用开发流程」走：默认一个线程做完，自己跑验收，命中风险才加复核。取代 11/15 的「全程只用 Grok」规则，T3 里可用的模型都可以开发。
- 跨模型复核：改动涉及花钱、权限和登录、对外发消息（含 8:30 私聊稿、推送）、密钥配置、数据库（含 `tg.db`、收藏等用户数据），或阿欢要求时，交另一家模型只读复核，只给必要 diff 和验收点。命中风险或风险拿不准最多两轮；纯展示等明确低风险、且已需要复核的改动，第二轮仍有挡路项时可自动修、自测并做最后一轮，不用另问。
- 不读 `.env`、密钥、Cookie 文件内容；不存密码；不编造账号、链接或内容。微博 Cookie 只放本机仅自己可读的文件，不进仓库。

## 审批红绿灯（2026-11-08 本人确认；与下文冲突时以本节为准）

- **绿灯，AI 直接做、事后汇报**：技术实现、本地验证、在功能分支提交。推送功能分支、开合并请求也可以直接做。
- **纯文档合并**：只改 `*.md`、`docs/` 的合并不影响线上。自动检查和独立审阅都通过后可以直接合并，事后汇报。
- **红灯，须本人批准**：
  - 会进站点或发布脚本的合并。生产克隆 `/workspace/shiguang-prod` 每轮采集前会 fast-forward 到 `origin/main` 并重新建站发布，这类合并约 30 分钟内就会上线，所以等同于上线。
  - 正式上线或部署、真实数据、删数据或未提交的文件、花钱、对外发消息、密钥、权限、改算账口径或产品方向、建或停例程、改域名与访问权限。
  - 拿不准的一律按红灯处理。只有阿欢本人的原话算批准。
- 需要问阿欢时，先查 `DECISIONS.md` 和 `NOT-DOING.md`。提问用一句话写清：什么事、我的建议、不回复时怎么办（红灯默认「先不做」）。
- 部署后要做线上核实，确认线上版本包含这次提交；没核实就不算完成。
- `main` 有盒子全局 pre-push 钩子挡直推：走分支加合并请求，不用 `--no-verify`。只有 `tools/persist_action_data.sh` 的数据提交带 `ALLOW_MAIN_PUSH=publish`。

## 开发验收

- 先跑和改动相关的聚焦用例。全量验收在含本次改动的隔离工作区（T3 worktree）里跑，不在 `/Volumes/kwin_SSD/Development/shiguang-hot` 原目录跑：
  - Python 用 3.11+，本机默认 `python3` 缺 pytest。用 `uv run --python 3.11 --with pytest --with pillow --with beautifulsoup4 --with playwright --with lxml python -m pytest -q -rs`（2026-11-24 试跑：464 过、2 跳过）。离线浏览器用例需要本机已装 Playwright 的 Chromium。
  - 前端跑 `node --test tests/*.test.js`。
- 浏览器测试会改写 `docs/rebang-v1/evidence/history-favorites-search/` 的三张截图，不要提交这些截图改动。
- 失败先在改动前的同一提交上复现，复现了才算旧问题；不要沿用文档里的旧基线。
- 测试不跑采集、推送、发布，不连真实账号。

## 回报与交接

- 回报：改了什么、跑了哪些检查及结果、有没有触发复核及结论、还要阿欢验收什么。没上线就写「未上线」，上线了写实际线上版本和关键页面检查结果。
- `HANDOFF.md` 只在决定、可验证结果、阻塞或下一步变化时更新；旧记录移到 `docs/HANDOFF-history.md`。
- 做动效、过渡、加载或空状态前，先看盒子上的 `/workspace/dev-sop/motion-cards.md`。本机读不到就照现有页面风格做，并在回报里写明。
- 不删例程和 bot：需要停先暂停，删除要阿欢批准。
