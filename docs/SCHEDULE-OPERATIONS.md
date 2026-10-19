# 公开更新与外部定时接入

2026-10-19。用户已确认同时推进 feed 推送发布与外部定时触发。代码基于 main 的 `e86567413295a61872c2b3971cadff4467dc8f61`，在独立 `codex/schedule-reliability` 分支实现，与设计原型、时间流排序分开。推送、合并与正式部署仍按此前约定另获批准。

## 发布行为

| 触发 | 行为 |
| --- | --- |
| main 的 public-feeds/** 推送 | 从当前 main、现有 tg.db 与公开 feeds 全量建站；NO_FETCH=1，不联网采集、不提交数据库 |
| GitHub schedule（每小时 :07/:37） | 完整采集、构建、提交 tg.db、上传并发布 Pages |
| workflow_dispatch | 同上；可附 dispatch_id 供外部程序准确跟踪 |
| tg.db 单文件推送 | 不匹配 feed 路径；工作流内部的 GITHUB_TOKEN 普通推送也不会递归触发 |

所有运行共用 `shiguang-public` 并发组，`cancel-in-progress: false`，不中断正在采集或部署的运行。默认只保留一个 pending，较新等待项会替换旧等待项；不是每个提交都单独部署。运行开始 checkout 当前 main，避免仅依据旧事件 SHA 构建。总超时 30 分钟是防卡死上限，不是发布时限承诺；最近一次已知成功约一分钟，极端回填可能需要后续运行继续。

数据无变化时不提交或推送。有变化时只提交 tg.db；提交或推送失败会让工作流失败并停止后续部署，不强推、不自动 rebase 旧产物。Actions 并发组不锁 box 的提交：box 在采集期间更新 main 时，本次数据 push 可能被拒绝，后续 feed 运行会接着发布，下一次采集补回未持久化的数据。

公开构建成功后写入 `build-info.json`：实际源码提交、public-feeds Git 树、实际数据库 SHA-256、构建时间、触发类型与 run_id。元数据在数据库提交前生成；不能用随后提交 tg.db 的 HEAD 替换构建输入，也不能仅比较 Actions 事件 head_sha 判断 feed 是否追平。此文件不含来源原文、账户信息、token 或内网地址。

## 先保存 bot PAT 权限

在电脑浏览器打开 <https://github.com/settings/personal-access-tokens>，使用 kwinweng 登录，编辑 bot 当前使用的 fine-grained token：

1. Repository access 覆盖 kwinweng/shiguang-hot。
2. Repository permissions 的 Actions 设为 Read and write，保存。原有 feed 推送所需的 Contents 权限保留，不额外申请其他权限。
3. 不把 token 复制进对话、源码、终端命令参数或日志。当前工具使用 gh 已有登录，不要求读取 hosts.yml 或替换凭证。

如果直接编辑原 token，云端授权变更仍须在 bot 的实际 gh 会话中验证。若重新生成 token，旧 token 的配置不会自动更新；由阿欢在 bot 机器安全替换，不在本文件中传递秘密。

## 上线后在 bot 机器验证

必须先合并并部署新工作流，再使用带 dispatch_id 的触发工具；旧工作流没有该输入，工具会失败，不会静默回退。

在 bot 检出新版本的项目目录运行只读检查：

```sh
python3 tools/dispatch_hourly.py --check
```

该检查只证明当前 gh 身份能读取工作流且工作流启用；**不能证明 Actions 写权限**。不要用 Codex 当前环境的 gh 会话或用户网页上的手动运行代替 bot PAT 验证。

用户批准真实发布验证后，在同一 bot 会话执行一次：

```sh
python3 tools/dispatch_hourly.py --wait --timeout 3900
```

- 每次生成唯一 dispatch_id，并显示准确运行链接，不把别人的手动运行当成本次运行。
- `dispatch_accepted` 只表示触发请求被接受；`run_found` 表示找到本次运行；只有最后 `workflow_succeeded` 且退出码 0 才表示工作流成功。
- 403、采集或部署失败、取消、等待超时均返回非零；不会换 token、自动扩大权限或重复提交 POST。超时不会取消远端运行，先看已有运行再决定是否重试。
- 3900 秒用于一次性完整验收，可容纳前一轮占用并发组及本轮运行；不是外部任务的建议等待时间。真实端到端验收尚未在当前环境执行。

## 接入既有每小时 :11 例程

保留现有定时任务，不另建一套重复 cron。将其中的 gh workflow run 调用替换为在项目目录执行：

```sh
python3 tools/dispatch_hourly.py --timeout 120
```

此模式等到能定位运行后退出，明确输出 `not_waited`，不把它当成 Pages 已成功。后面的 `/workspace/tg-local/sync.sh` 按原流程执行，不因 dispatch 403 或索引超时而漏掉内网同步。接入时应分别记录两步退出状态：

```sh
# 在已检出修复的项目目录；示例仅供修改现有例程，不会自行安装 cron。
dispatch_status=0
python3 tools/dispatch_hourly.py --timeout 120 || dispatch_status=$?
sync_status=0
/workspace/tg-local/sync.sh || sync_status=$?
if [ "$dispatch_status" -ne 0 ] || [ "$sync_status" -ne 0 ]; then
    exit 1
fi
```

原有同步在触发后立即运行，可能还看不到本轮采集的数据库提交；本方案不把它改成等待远端完成的同步，也不据此声称两站同一秒更新。若需强同步，单独评估该语义与任务时长。

本仓库不含 bot 的 cron 配置或 sync.sh，当前环境也不能访问那台机器，因此没有修改或安装外部任务。由阿欢或获授权的 bot 在原例程中接入；当前仅准备了可审阅命令与工具，没有发消息给总控。

## 验收与回滚

本地验证：新增测试使用临时本地 bare Git 仓库，覆盖无变化、成功推送、其他文件已暂存、远端先更新后的非快进拒绝、commit hook 失败和构建输入元数据；触发客户端用模拟 gh 验证，不向 GitHub 发出真实 POST。还执行全套测试、actionlint、公开 NO_FETCH 构建与数据库只读核验。

上线后的验收分别检查：合法 feed 推送确实触发并部署、bot PAT 完整采集运行成功、相邻触发没有并行采集或中断部署、没有递归、线上 build-info 与公开 feed 树追平。工作流成功不替代公开站内容核验。

若需回滚，回退这次独立修复提交，外部例程恢复原 gh workflow run 调用；保留新增的 feed 和数据库数据。不自动撤销或更换 PAT，权限恢复由阿欢在 GitHub 管理。不得为了恢复旧版本强推 main。
