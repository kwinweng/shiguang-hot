# X 转储私有收件箱

这是收件端的格式和操作约定，不是上线授权。收件仓库、凭证、Grok 例程和 Mini 配置不由本工具创建或修改。

## 发件格式

在独立私有仓库的 `main` 上，**同一个提交**更新根目录 `manifest.json` 和它指向的 `dumps/<dump_id>.tar.gz`。清单只指向最新的完整包；Mini 不按 Git 历史或文件修改时间找包，也不在坏包时尝试用远端较旧的包。

```json
{
  "dump_id": "20261126T0106",
  "generated_at": "2026-11-26T01:08:22+08:00",
  "files": ["posts.json", "quotes.json", "_dump.json"],
  "post_count": 66,
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

- `dump_id` 是导出开始时的北京时间，格式 `YYYYMMDDTHHMM`，不能晚于 `generated_at`，也不能比它早超过 36 小时。不同导出不要复用同一个 `dump_id`；Mini 不覆盖同名目录。
- 先写完各份原始 X JSON，再写 `_dump.json`。后者的 `generated_at` 必须和清单是同一个时刻。两个时间都用带时区的 ISO 8601。收件时允许过去 36 小时到未来 5 分钟，以 `generated_at` 为准。
- 包是 gzip 压缩的 **USTAR**。直接把 UTF-8 `.json` 文件放在包顶层，不要包一层目录，不要放 `./` 前缀。文件名以 ASCII 字母、数字或 `_` 开头，其余只允许 ASCII 字母、数字、`_`、`-`、`.`，总长不超过 100 字符；不允许大小写折叠后同名。只收普通文件，不收链接、设备、目录或 PAX/GNU 扩展头。
- `files` 是包内完整文件列表，包含 `_dump.json`；`post_count` 是现有 `read_export` 读出的不重复主帖数，必须大于零。`quotes*`、`replies*`、`refs*` 不单独算主帖。可选文件没有数据就省略，不放空数组或非 JSON 日志。`sha256` 是**整个 gzip 包**的 SHA-256 小写十六进制（上面只是格式示例）。
- 每份最多 128 个成员，单文件最多 8 MiB，压缩包最多 16 MiB，解压后的 tar（含头与填充）最多 32 MiB，清单最多 64 KiB。不要把其他文件或凭据放进收件仓库。

## Mini 收件

- 不设置 `REBANG_X_INBOX_REPO`（或设置为空）时，本轮完全跳过。获批接入后，在 Mini 发布器的本机环境配置该变量为不含凭证的 Git 地址；Git 认证由 Mini 本机配置处理。收件与发布应使用各自的仓库和身份，Mini 的收件身份只需读权限。
- 发布器在 `rebang_refresh.sh` 前读取收件仓库，不向它推送，不签出它的文件。只浅取 `main` 到发布状态目录 `.git/mac-publish/x-inbox.git` 的本地裸缓存。只读支持 SSH、HTTPS，或离线演练的 `file://`。
- 坏包、断网、认证失败或收件超时只记日志，不写 HALT，原发布流程继续使用已有的 X 转储，原有过期策略不变。坏包不会改动目标根下的内容。不改变发布器原有的 main/gh-pages 校验和停机条件。
- 全部检查通过后才用同一文件系统上的临时目录原子改名，将新包放入 `var/rebang/x-dump/<dump_id>/`。保留时间戳最新的六份本工具写入的目录；保留制作者不明或手工导入的目录。`.x-inbox-owned` 是本机写入的保留标记，不放进发件包，不复制进手工导入目录。不要在发布器运行时手工写入同一个目标根。

离线演练入口（用本机临时的裸仓库，不指向生产）：

```sh
python3 -I tools/x_inbox_pull.py --repo "$FILE_INBOX_URL" \
  --cache "$TEST_STATE/x-inbox.git" --target-root "$TEST_CHECKOUT/var/rebang/x-dump"
```
