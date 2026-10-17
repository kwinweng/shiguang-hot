# 聚合平台投递规范

本文供投递内容的 bot 使用。先在 `sources.json` 注册来源，再写入数据。原生数据不直接进入 git。

## 路径与原子写入

每期路径为 `/workspace/feeds-inbox/<source-id>/YYYY-MM-DD/feed.json`，图片放在同一期目录内。
`source-id` 必须与配置 id 一致；目录日期必须与 JSON 的 date 一致。

先将完整 JSON 写入同目录的 `feed.json.tmp`，关闭文件后用 `os.replace(tmp, destination)` 或 `mv` 替换 `feed.json`。
图片先完整写入，再替换 JSON。禁止直接覆盖正在被读取的 feed.json。日期采用北京时间。

```python
import json, os
from pathlib import Path
folder = Path('/workspace/feeds-inbox/example/2026-10-17')
folder.mkdir(parents=True, exist_ok=True)
tmp = folder / 'feed.json.tmp'
tmp.write_text(json.dumps(feed, ensure_ascii=False), encoding='utf-8')
os.replace(tmp, folder / 'feed.json')
```

## 字段

根节点为对象：`schema` 固定 `shiguang.feed/1`；`source` 为注册 id；`date` 为 YYYY-MM-DD。
`title` 为可选期刊标题。`blocks` 和 `sections` 为数组，可为空，至少提供一类内容。
section 包含 `title` 和 `items` 数组。
item 支持 `title`、`body` 字符串；可选 `link`（http/https）、`source`（来源名）、`sources`（来源名字符串数组）、`date`（显示日期）、`images`。
body 的换行保留，默认卡片收起显示两行，点击展开全文。内容按纯文本转义，不接受 HTML。
缺 title 回退为“未命名条目”；缺 body、link、source、date 或图片时可继续渲染。

images 为 `{ "file": "photo.jpg", "alt": "图片说明" }` 对象数组。
file 必须为期刊目录内的相对文件名；禁止绝对路径、越界 `..` 或指向目录外的符号链接。
允许 jpg/jpeg/png/webp；单张不超过 10 MiB（10 × 1024 × 1024 字节）。图片必须可由 Pillow 解码。
构建时自动转为 webp，长边不超过 1200px，缺图跳过；请填写准确的 alt。

## 可选 blocks

- `oneliner`：`{type:"oneliner", title?:"速览", items:["一句话", ...]}`，渲染要点列表。
- `markets`：`{type:"markets", items:[{name:"指数", value:"123", change:"+1%", note:"收盘"}]}`，紧凑数据卡；change 负号显示下降箭头，其余显示上升箭头，同时使用橙/蓝区分。
- `chart`：`{type:"chart", title:"一张图", image:"chart.png", caption:"说明"}`；image 也可为 `{file,alt}`。
- `tomorrow`：`{type:"tomorrow", items:["明日事项", ...]}`，渲染清单。

列表项也兼容 `{title,body}`。未知 block 忽略并给出警告。

## 校验与可见范围

运行 `python3 validate_feed.py /workspace/feeds-inbox/example/2026-10-17/feed.json`。
运行 `python3 validate_feed.py mail` 会按配置适配并检查真实原始邮件数据。
退出码 0 表示无错误（可能有警告），1 表示错误或无数据。错误包括 schema、source、日期、数组或字段类型不符。
缺字段、缺图、非法图片路径、非 HTTP 链接、未知 block 给出警告；不合法期刊在构建时跳过。

visibility 以 `sources.json` 为唯一依据，投递文件无法自行修改可见范围。
`private` 只供内网，不得进入 git、public-feeds 或公开站点。
`public` 由本机 publish_public.py 规范化、压图后进入 public-feeds，仅保留最近 14 天。
公开构建只读取 public-feeds；内网优先原始目录，其次原生投递目录，最后 public-feeds，同日期优先本机。
无数据来源不生成页面、不显示入口；请勿向生产目录投递演示内容。

## 完整示例

```json
{
  "schema": "shiguang.feed/1",
  "source": "example",
  "date": "2026-10-17",
  "title": "今日精选",
  "blocks": [
    {"type":"oneliner","items":["重要事件一句话"]},
    {"type":"markets","items":[{"name":"示例指数","value":"100","change":"-0.5%","note":"样例"}]},
    {"type":"chart","title":"趋势","image":"chart.png","caption":"图表说明"},
    {"type":"tomorrow","items":["关注明日发布会"]}
  ],
  "sections": [
    {"title":"科技","items":[{"title":"示例标题","body":"第一段。\n\n第二段。","link":"https://example.com/news","sources":["示例来源"],"date":"2026-10-17","images":[{"file":"photo.jpg","alt":"图片说明"}]}]}
  ]
}
```

## 兼容适配器

`mail` 读取 `/workspace/mail-digest/YYYY-MM-DD/digest.json` 的 date、sections，映射为统一 schema，固定来源 mail，private。
`world` 读取 `/workspace/world-brief/YYYY-MM-DD/brief.json`，将 oneliner、markets、chart、tomorrow 映射到 blocks，保留 sections，固定来源 world，public。
`native` 直接读取 feed.json；配置 directory、filename、adapter，默认目录 `/workspace/feeds-inbox/<id>`。
`MAIL_FEED_DIR`、`WORLD_FEED_DIR` 可覆盖兼容目录；其他来源可在配置 env 指定变量。
`SOURCES_OVERRIDE` 可指定完整替代配置文件，仅用于隔离验证；不要改变 private 的真实可见范围。
