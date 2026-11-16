# iOS 主屏幕 web app 底栏置底（P3）

根因：iOS 26 standalone 模式下视口（innerHeight/100dvh）比 screen.height 短，底部一条由系统占用并用 html 背景色绘制；
但 `env(safe-area-inset-bottom)` 仍报 34px，底栏又垫一次安全区 → 图标离底很远，看起来“没置底”。

修复：仅 iOS standalone 时，`--safe-bot = max(0, inset − gap)`；env() 错报 0 且全屏时兜底 20px。Safari/Chrome 标签页、桌面、安卓不变。

复现：`python3 capture.py <base URL> <prefix>`（WebKit iPhone 模拟 + 桌面 Chromium，深/浅色），断言底栏下沿 = 视口高度、ios26 场景底栏高 ≤ 61。
before-* = 修复前 main 构建（8/10，ios26 两项 FAIL，高 92）；after-* = 本分支构建（10/10，高 60）。
真机诊断：打开 `/?diag=1` 显示视口/安全区/底栏位置。
