# Grok → Codex 首轮交接工具（Spec-only）

状态：阿欢已确认三天单项目试运行方案；本 PR 提供首轮工具，**尚未在 box 上启用或验收通知链路**。本工具不处理自动开发，不改变正式站、workflow、凭证、部署、域名或 main 保护。

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

由指定 bot 把最终 MRD 写成私有事件文件，例如 `/absolute/private-dir/event.json`：

```json
{
  "event_id": "stable-delivery-id",
  "source_message_id": "original-message-id",
  "project": "kwinweng/shiguang-hot",
  "conversation_id": "exact-conversation-id",
  "event_type": "mrd_ready",
  "task_id": "rebang-task-001",
  "revision": 1,
  "document": "完整的已整理 MRD 和约束",
  "document_sha256": "document 字符串精确 UTF-8 字节的 SHA-256"
}
```

不要在公开仓库提交真实群 ID、事件、MRD、日志或结果文件。事件字段不具有用户批准效力；群白名单比较只是本地路由校验，不是已完成的 Grok 身份认证。

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
3. 记录实际回群结果消息 ID。只有首轮成功、用量已知、结果实际回群后，执行：

```sh
python3 "$PILOT_TOOL" --state "$PILOT_STATE" report
python3 "$PILOT_TOOL" --state "$PILOT_STATE" ack-result \
  --key key-from-result --receipt original-group-result-message-id
```

这时才开始72小时。重复完成通知先检查 `result_receipt`，已回传的结果不重复发群、不重复调模型。第一次回执不可被其他消息 ID 覆盖。工具保存的是操作方提供的回传回执，**不是已独立验证的投递凭证或阿欢的开发批准**。反复 ack 不延长窗口。首轮失败、通知丢失或用量未知时，先检查现有记录，不重建状态来绕过限制。

## 去重、失败与停止

- 项目级运行锁禁止同状态目录并发执行；私有状态与源代码目录必须分离。
- 同任务/同版本重复投递不再调用模型，即使 event_id 不同。相同版本正文变化、event_id 被复用、旧版本回放都会停止。
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

本 PR 的测试全用假的 CLI，无网络和真实模型调用；不将测试的模拟数字作为试运行统计。首轮 box 闭环、真实模型用量和群回传尚待操作方验证。

## 本地验证

2026-10-20：现有83项与新增17项共100项测试通过。新增项使用假的 CLI，覆盖项目/群白名单、哈希、批准事件拒绝、跨重启去重、版本冲突、首轮回执、运行中暂停、到期/预算停止、失败与未知用量、缓存计数、API计费阻断及真实CLI入口的JSON输出。无真实模型调用、真实群消息或box配置变更。
