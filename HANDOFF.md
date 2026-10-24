# 交接记录

## 2026-10-24 PR #31 有图探索条目修补

- 探索分类标签必须放在 `.tx` 内并独占一行；有图行使用正文、图片两列，不能沿用分类占左列的三列网格。无图及坏图仍保持全文宽度。
- `explore_messages()` 输出标题时执行 `strip()`，列表渲染再执行 `trim()`，兼容已有缓存数据；保留标题内部空格。
- 浏览器回归使用正常加载的图片，覆盖 320、393、1280 像素宽度、分类筛选、标签与正文位置、图片右对齐及标题首尾空白。截图位于 `/tmp/rebang-explore-image-desktop.png` 和 `/tmp/rebang-explore-image-mobile.png`。
- 验证：`python3 -m pytest -q`（196 passed、58 subtests）、`node --test tests/*.test.js`（9 passed）、`NO_FETCH=1 python3 pipeline.py` 均通过。
- Python 首轮在 `test_dirty_checkout_refused_at_sync_and_persist` 的 Git 索引字节快照比较中偶发失败；未改代码完整重跑通过。未扩大本次修补范围。
- 未读取密钥文件，未 push、合并、部署或操作 gh-pages。

## 2026-10-24 PR #31 第二轮修复

- 无图列表标题跨满整行，不保留图片占位；图片加载失败移除后同样恢复整行宽度。
- 回顾页移除顶部摘要卡片，保留日期导航和事件列表。
- 浏览器回归覆盖无图、坏图及 320、393、1280 像素宽度，并断言回顾页无摘要卡片。
- 验证：`python3 -m pytest -q`（195 passed、58 subtests）、`node --test tests/*.test.js`（9 passed）、`NO_FETCH=1 python3 pipeline.py` 均通过。
- 未读取密钥文件，未 push、合并、部署或操作 gh-pages。

## 2026-10-24 PR #31 第一轮修复

- 开始时没有 HANDOFF.md；`web/modules.js` 有中断遗留改动，已在其基础上继续。
- 探索真实内容保存在 `tg.db` 的 `trial_item`，不在收件箱 issues 中。构建只读现有表；缺库或缺表返回空，不创建表。分类名称与来源名称取公开 `trial-sources.json`，好看保持空，不新增来源。
- 不存在条目不能逐个请求所有历史日期。历史索引新增 ID 到日期映射，直接查对应归档；未知 ID 显示缺失状态。
- CSS 存在旧原型规则和末尾正式布局覆盖。实时行、筛选文字、品牌栏、字重需检查最终计算样式，不能只修改前面的规则。
- 未读取密钥文件；未合并 main、部署、操作 gh-pages 或 push。
- 验证：`python3 -m pytest -q`（194 passed、58 subtests）、Node 测试（13 passed）、`NO_FETCH=1 python3 pipeline.py` 通过。真实 iOS 安全区仍待实机确认。
