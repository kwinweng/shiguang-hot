# 拾光热榜 · 项目规矩（Claude 和 Codex 共用）

流程按 SOP v0.3（短链路版）：阿欢在 Mac 上的 Claude Code 会话里提需求；Claude 写 PRD、规格和样稿，
调度 Codex 写代码，并做质检；Codex 写代码、交叉审查。阿欢只过两道闸门：G1 看样稿定方案，G2 用手机点过预览后批准合并。

## 仓库
- 公开仓库 `kwinweng/shiguang-hot`，公开站 https://kwinweng.github.io/shiguang-hot/
- 架构、页面规则、`sources.json` 字段见 `ARCHITECTURE.md`；投递格式见 `INGEST.md`；内网登录见 `PRIVATE_LOGIN.md`。
- 代码：`shiguang/`（收内容 → 统一 → 加工 → 出页）、`web/`（样式和脚本）、`tools/`、`tests/`。
- 需求和进度：`docs/PRD.md`（末尾附「决定记录」）、`docs/SPEC.md`（验收标准和任务清单）、`HANDOFF.md`（≤40 行）。

## 命令
```bash
scripts/check.sh                              # 每个任务完成前必须通过
python3 -m unittest discover tests            # 只跑测试
NO_FETCH=1 python3 pipeline.py                # 用现有 tg.db 建公开版到 site/，不抓取
SITE_MODE=private NO_FETCH=1 python3 pipeline.py   # 内网版
python3 tools/screenshot.py index.html        # 手机截图到 shots/（--desktop / --dark / --build）
```
- Mac 自带 Python 3.9，CI 和 box 是 Linux：`site/build.py` 的原子替换用到 Linux 的 `renameat2`，
  在 Mac 上会报错；登录门测试要能绑定本机端口。这两类失败在 Mac 沙箱里属于环境问题，不算回归。

## 模型
| 用途 | 模型 |
|---|---|
| Codex 写代码 | `gpt-6.1-sol`，medium |
| Codex 唱反调、疑难问题 | `gpt-6.1-sol`，加 `-c model_reasoning_effort=high` |
| Codex 轻量检查 | `gpt-6-luna` |
| 极难问题（要阿欢同意） | `gpt-6-astra` |
| Claude | 当前最新的 Opus |

**禁止**使用上一代模型 `gpt-6-sol`、`gpt-5.6-*`。不降级换弱模型：两家都没额度就等。

## 调用 Codex
每次都显式写模型和沙箱，不依赖 Mac 上的默认配置（默认模型是 `gpt-6-astra`）：
```bash
codex exec --ephemeral -m gpt-6.1-sol -s workspace-write -C /Users/kwin/projects/shiguang-hot \
  -o .codex-out/<任务>.md "<任务说明：只给文件路径、验收标准和验收命令>"
```
- 唱反调和审查用只读：`-s read-only`。`.codex-out/` 不提交。
- 同一个问题失败 2 次，Claude 先诊断再决定重试还是自己写；第 3 次还失败就问阿欢。
- Codex 报限额错误或本周额度低于 20%：改由 Claude 写，Codex 审（有额度时）。

## Git
- **禁止直接推 main**。main 开了保护，另有两条合法的自动推送：Actions 的 `hourly.yml` 推 `tg.db`，box 上的 `publish_public.py` 推 `public-feeds/`。
- 一个任务一个分支、一个 PR；分支名 `feat/…`、`fix/…`、`chore/…`、`docs/…`。合并到 main 要阿欢在 G2 批准。
- 不强推、不删分支、不改 git 历史；不碰 `tg.db` 和 `public-feeds/` 的提交。

## 隐私和安全（公开仓库）
- **口味数据、个人信息不进这个仓库**：口味排除项、常住城市、喜好清单、样品、PRD 原文都放在私有仓库
  `kwinweng/shiguang-haowan-haomai`（本机 `~/projects/shiguang-haowan-haomai`）。代码在运行时从私有位置读取，
  路径用环境变量传入；找不到就跳过个性化，不能报错退出。
- 测试和样例只用虚构数据。提交前确认 diff 里没有私有仓库的原文。
- 不读 `.env`、`*.pem`、`hosts.yml`；密钥只放 GitHub Secrets；编码引擎拿不到生产密钥。
- 公开构建产物不得出现 private 来源和「邮件」二字（建站时有检查，别绕过）。
- Claude 和 Codex 不接入 box；部署、定时任务、线上日志由 grok 负责。
- 不抓小红书，不接需要登录或反爬的平台，不带 cookie 抓取。

## 设计
- 遵循「光」视觉规范（见 `ARCHITECTURE.md`「视觉规范」）；`tests/test_render.py` 守着金色、字重、玻璃卡等规则。
- 做设计前先截线上真实页面，以线上为基线。底栏是 今日 / 热点 / 栏目 / 收藏。
