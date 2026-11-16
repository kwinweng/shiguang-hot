# iOS 主屏幕 web app 底栏贴底（第二轮，接 PR #71）

真机现象（阿欢 iPhone 17 Pro，iOS 27.2，Chrome「添加到主屏幕」）：底栏下面空一大截（约 62pt），深浅色都有。

根因：iOS 26/27 standalone 下 WebKit 报的视口（innerHeight / 100dvh / `position:fixed;inset:0`）只有「屏幕高 − 状态栏高」
（874 − 62 = 812，WebKit bug 313800），但网页其实铺满整屏，812 以下那 62pt 照样画 html 背景。
外壳 `.app` 用 `inset:0` 按视口排版 → 底栏停在 812；PR #71 又把底栏底部内边距算成 max(0, 34 − 62) = 0 → 图标贴着 812，下面一整条空白。
PR #71 把那条带子当成「系统占用、画不进去」，这个判断错了。

修复：仅 iOS standalone、整屏宽、视口比屏幕矮且顶部安全区 > 0（视口从屏幕顶开始）时，外壳高度 = 整屏高度（`--app-h`，class `app-fullscreen`），
底栏照常垫 `env(safe-area-inset-bottom)`（34），env() 错报 0 时兜底 20。浏览器标签页、安卓、桌面、iPad 分屏不变。

诊断：长按左上角日期 1 秒开/关诊断浮层（记在本机 localStorage `rebang-v11-diag`），`?diag=1` 仍可用。

复现：`python3 capture.py <站点根 URL> <before-|after->`（Playwright WebKit 模拟 402x874@3x、安全区 62/34）。
before-* = main 构建：底栏下沿 812，空白 62，padding 0（8/8，只记录不断言）。
after-* = 本分支：外壳与底栏下沿 874，padding 34；长按诊断开/关/持久化；浏览器标签页 683、安卓、桌面不变（22/22）。
`*-device.png` = 812 视口截图贴到 874 画布、底部用 html 背景补齐（真机看到的样子）；`after-ios-standalone-paint-*` = 画布 874、innerHeight 报 812。
模拟器复现不了真机「报矮画满」本身，最终以真机为准。
