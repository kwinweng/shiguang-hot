阿欢 2026-11-26 批准的拾光资讯新版 Logo 原图（Light / Dark / Tinted 三套 1024×1024）：
- `shiguang-logo-light-1024.png`：默认 / 浅色（主屏图标、PWA 图标、分享图、浅色标签页与浅色启动图）
- `shiguang-logo-dark-1024.png`：深色（深色标签页与深色启动图；原生 iOS App 深色图标）
- `shiguang-logo-tinted-1024.png`：着色灰阶版（原生 iOS App Tinted 图标留底）

运行 `uv run --python 3.11 --with pillow python tools/build_rebang_icons.py` 重新生成站点图标、启动图和分享图。顶栏不使用这张图（PR #47，日期居左）；脚本仍会写出 `web-v11/logo.png`，页面不用。
