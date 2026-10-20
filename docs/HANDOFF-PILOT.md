# Grok → Codex 首轮交接工具（Spec-only）

状态：阿欢已确认三天单项目试运行方案。按操作方回报，2026-10-20 18:41–18:44（北京时间）box 首轮已产出 `spec_ready`、退出0、relay 通知送达，Spec 已人工回原群；**尚未补记人工回执，72小时未开始**。这是 box 实测回报，不是本地测试结论。本工具不处理自动开发，不改变正式站、workflow、凭证、部署、域名或 main 保护。

## 范围和边界

首轮只接收热榜项目的 `mrd_ready`，以既有 ChatGPT 登录启动只读 Codex，结果为一份待批准的 Spec。`spec_approved`、开发、合并和部署事件全部拒绝。未核实原群用户身份/批准关联前，不能扩大为自动开发。

这是一条“指定 bot 主动投递 → 本地执行 → 现有 relay 通知 → bot 回群”的入口，不是群消息爬取器。工具没有 Grok API，不向任何群发送消息，不读取 relay 凭证。它也不会自动把当前云会话历史带到 box；所需 MRD 和约束要写入交接正文。

原 bot SOP 若限制调用 Codex，由总控将阿欢本次确认记录为限于该项目、该阶段、三天试运行的例外；不能扩大为任意模型或任意任务调度。项目内具体 Spec 的批准、合并与部署权限仍按原规则。

## 操作流程（由 box 维护者执行）

在隔离的工具分支/检出目录取用本 PR。任务代码目录另用独立 Git worktree；日志和交接包放在检出目录之外。不要在正在开发的 checkout 上安排并发写入。原有 relay 继续使用，无需重装或复制其凭证。

以下变量为操作方选择的路径；群 ID 必须从原群取得完整值，示例名不可直接使用。运行前先核对 box 的 CLI，而非采用本会话云工作区的登录。

```sh
PILOT_TOOL=/absolute/tool-checkout/tools/handoff_pilot.py
PILOT_STATE=/absolute/private-dir/rebang-pilot
PILOT_REPO=/absolute/isolated-shiguang-worktree
PILOT_GROUP=exact-conversation-id
python3 "$PILOT_TOOL" --state "$PILOT_STATE" doctor
python3 "$PILOT_TOOL" --state "$PILOT_STATE" init \
  --repo "$PILOT_REPO" --conversation "$PILOT_GROUP"
```

`doctor` 只查询既有登录状态、CLI 版本和 `exec --help`，不调用模型，不打印原始登录响应或凭证。出现 API key 环境变量或未确认 ChatGPT 登录即停止；不会自动登录、清除凭证或切换账单。`--ignore-user-config` 仅作用本次子进程，不修改磁盘配置；如 box 的配置是运行所必需，应先报告冲突，不擅自放宽参数。

`init` 只准备私有状态，不开始72小时窗口。默认全试运行最多10次执行，累计已知输入20万 token 后不再派下一轮，单轮超时600秒。单次调用可能超过剩余 token 预算；这是轮次间限制，不是实时精确 token 截断。可在初始化时使用已授权范围内的 `--max-runs`、`--max-input`、`--timeout`；已有状态不会覆盖。

由指定 bot 把本轮变化、已定事项和所需材料写成私有事件文件，例如 `/absolute/private-dir/event.json`。`document` 只描述本轮要求改变的部分；完整 MRD、已确认 Spec 可放在材料中：

```json
{
  "event_id": "stable-delivery-id",
  "source_message_id": "original-message-id",
  "project": "kwinweng/shiguang-hot",
  "conversation_id": "exact-conversation-id",
  "event_type": "mrd_ready",
  "task_id": "rebang-task-001",
  "revision": 1,
  "document": "本轮只调整好玩页面筛选行，其他已定事项保持不变",
  "document_sha256": "document 字符串精确 UTF-8 字节的 SHA-256",
  "settled_decisions": ["五格底栏名称和顺序已定", "自动开发保持关闭"],
  "materials": [
    {"name": "基线 Spec", "path": "docs/APP-UPGRADE-SPEC.md"},
    {"name": "本轮反馈", "content": "筛选行保持单行，内容超宽时横向滚动"}
  ]
}
```

示例路径须替换为实际文件。`settled_decisions` 和 `materials` 可省略，分别最多64条和16份；每份材料必须二选一提供 `path` 或 `content`，可附 `name`。相对路径以任务仓库根目录为准；绝对路径只能位于任务仓库或既有私有状态目录，不能指向隐藏文件或越界符号链接。其他位置的材料先复制到私有状态目录的 `materials/`，或用正文提供。只接受非空 UTF-8 文本，每份最多64 KiB；变化正文最多64 KiB，连同材料、已定事项的完整事件最多256 KiB。

runner 在领取任务时保存材料正文和 SHA-256 快照，用该快照生成提示词。后续源文件变化不会悄悄改变已领取任务。正文、已定事项或材料变化须使用新的 `revision`；相同版本、相同内容仍去重。旧记录没有上下文哈希时继续兼容去重，但不能原版本追加材料或已定事项。

输出要求为**增量 Spec**：只列变化摘要、受影响章节及替换建议、变化后的验收和待定项，不从头重写 MRD 或基线 Spec，不重开无关决定。缺少基线时列明缺口，只提有限的变更方案；与已定事项冲突时交阿欢裁决。材料内容作为参考，不执行其中的指令。新增材料不会触发自动开发。

不要在公开仓库提交真实群 ID、事件、MRD、日志或结果文件。事件字段和已定事项不具有用户批准效力；群白名单比较只是本地路由校验，不是已完成的 Grok 身份认证。

先做零模型检查：

```sh
python3 "$PILOT_TOOL" --state "$PILOT_STATE" check --event /absolute/private-dir/event.json
```

再通过已经安装的完成通知工具启动首轮。`--owner` 使用发起交接的热榜 bot 的真实 ID。此处示范使用 Linux box 的既有机制；不是让 Codex 在云端启动或部署服务。

```sh
NOTIFY_TAIL_CHARS=0 nohup "$HOME/.local/bin/notify-run" \
  --owner exact-owner-bot-id --task rebang-spec-probe \
  --log /absolute/private-dir/notify-run.log -- \
  python3 "$PILOT_TOOL" --state "$PILOT_STATE" run-spec \
  --event /absolute/private-dir/event.json \
  </dev/null >/absolute/private-dir/launcher.log 2>&1 &
```

`NOTIFY_TAIL_CHARS=0` 不把日志片段转进聊天；bot 读取已知结果文件即可。stdin 的提示词由 runner 用独立临时输入文件传给 Codex，不依赖后台终端输入。

原 relay 上游仅做完成通知，任务退出0不代表通知送达。bot 被叫醒后必须：

1. 读取 `report` 与对应 `runs/<key>/result.json`，确认 `status=spec_ready`；不能只看 wrapper 的 succeeded。
2. 读取 `spec.md`、真实 `events.jsonl` 用量与错误日志，回原群发送 Spec、任务/版本、用量和待确认项。失败就回失败原因，不自动重启模型。
3. 等待**阿欢本人在原群回复「已收到首轮」**。不能把 bot 自填的「群 ID + 时间 + 发送方」、relay 成功或 Spec 已发出当作回执。操作方看到该人工回复后，转录阿欢的实际回复时间并执行：

```sh
python3 "$PILOT_TOOL" --state "$PILOT_STATE" report
python3 "$PILOT_TOOL" --state "$PILOT_STATE" ack-result \
  --key key-from-result --receipt-kind human_ack --ack-by 阿欢 \
  --ack-at 'YYYY-MM-DDTHH:MM:SS+08:00'
```

时间必须精确到秒，可以带小数秒；须明确使用 `+08:00`，或省略时区但仍按北京时间解释。不接受其他时区、未来时间或早于该 Spec 完成的时间。占位时间不能直接运行。

回执记录为 `source=operator_transcription`：**操作方转录的人工确认，不是平台投递凭证，不是开发批准**，也没有独立核验阿欢身份。记录包含确认人、所需原话、北京时间、转录时间，以及 `platform_delivery_receipt=false`、`development_approval=false` 等标记。工具只允许 `--receipt-kind human_ack --ack-by 阿欢`，不能据此声称已接通平台身份认证。

只有此时才激活窗口：起点使用阿欢实际回复的 `ack_at`，而非晚些时候操作方录入的时间，终点为其后72小时。首次回执不可覆盖；相同人、相同时间的重复 ack 保留首次转录记录，不延长窗口。重复通知先检查 `result_receipt`，已回传的结果不重复发群、不重复调模型。首轮失败、通知丢失或用量未知时，先检查现有记录，不重建状态来绕过限制。

### 已有首轮记录直接补记

对 box 已有的 `rebang-task-001`、`revision=1`、`result_receipt=null`：只更新本 PR 的工具代码，继续用**原 `PILOT_STATE`**。运行 `report`，从对应记录取出原 `key`，待上述人工回复后直接运行 `ack-result`。**不要再次 `init`，不要再次 `run-spec`，不需要迁移或重建状态，也不调用模型**。补记会保留原任务、Spec、用量和请求快照，只在原状态及结果文件中记录回执与窗口；已有非空旧式回执同样不可覆盖。

## 去重、失败与停止

- 项目级运行锁禁止同状态目录并发执行；私有状态与源代码目录必须分离。
- 同任务/同版本重复投递不再调用模型，即使 event_id 不同。相同版本正文、已定事项或材料变化，event_id 被复用，或旧版本回放都会停止。
- 已 claimed/running/unknown 的任务不自动重跑；进程异常退出后保留状态供核查。没有无人值守的恢复按钮。
- 调用只读 Codex，通过 argv 与 stdin 传 MRD，不执行聊天提供的 shell 文本。独立输出仅是 Spec；提示词约束不应被宣传为外部身份认证或防止所有越权行为的证明。
- 暂停是本地开关，可由维护该机的总控/热榜 bot 执行。当前子进程也会收到终止请求；停止后的用量缺失记 unknown，不当成0。

```sh
python3 "$PILOT_TOOL" --state "$PILOT_STATE" pause
```

72小时到期不派新任务，已运行的一轮仍受超时和暂停约束。暂停后没有自动恢复；保留状态，等待用户决定。

## 用量记录

仅解析 CLI 一次最终 `turn.completed.usage`，不混加 app-server 累计快照。缺失、无效或多条无法判明的 usage 记 unknown，并阻止后续派发；cached input 是 input 子集，推理字段不重复加到 output。

`report` 给出已知 input、cached input、output、未知次数、任务记录和窗口时间。模型未报告时不能凭 CLI 默认值猜模型名称，不能直接估金额。relay bot、热榜 bot 和上游 MRD 整理的用量不在 Codex usage 内，要由对应平台另记。

本 PR 的测试全用假的 CLI，无真实模型调用；不将测试的模拟数字作为试运行统计。操作方回报的 box 首轮真实用量为 input 36089 / cached 12288 / output 6621 / reasoning 33；cached 包含在 input 中，reasoning 不再叠加到 output。relay 与人工回群已由操作方报告成功，仍须阿欢本人回原群后补记人工回执。

## 本地验证

2026-10-20：全项目111项测试通过（原83项 + 交接工具28项）。交接测试使用假的 CLI，覆盖项目/群白名单、哈希、批准事件拒绝、跨重启去重、版本冲突、旧状态直接补记、人工回执不可覆盖、重复确认不延长窗口、无效时间/代填回执拒绝、增量提示词、材料快照与越界限制、运行中暂停、到期/预算停止、失败与未知用量、缓存计数、API计费阻断及 CLI 入口 JSON 输出。Python 编译、`git diff --check` 和新增文案检查通过。无真实模型调用、真实群消息或 box 配置变更。
