# v11 设计系统（web-v11/）

2026-11-16 起。适用于新站 `web-v11/`（https://news.kwinweng.com/）；旧站 `web/` 仍按根目录 `DESIGN.md`。
视觉方向不变：v10/v13 设计稿的深色杂志风、金色强调（`HANDOFF.md`「已定的决定」）。本文件规定**令牌、图标、动效**三件事，让全站只有一套写法。

## 和默认技术栈的对应

阿欢的默认栈是 shadcn/ui（Nova 风格）+ Lucide 图标 + Motion 动效。v11 是无构建、无依赖的原生 JS 静态站，所以按「最小改动」落地：

| 默认栈 | v11 的做法 | 为什么 |
| --- | --- | --- |
| shadcn/ui 令牌 | `app.css` 的 `:root` 用 shadcn 的语义令牌名（`--background`、`--foreground`、`--card`、`--muted`、`--muted-foreground`、`--primary`、`--border`、`--ring`、`--destructive`、`--radius`），取值沿用设计稿 | 以后迁到 React + shadcn 时令牌可以原样搬；旧变量名（`--bg`、`--ink`、`--gold`…）保留为别名，组件样式不用逐行改 |
| Nova 风格 | 紧凑间距（4 的倍数）、圆角以 12px 为基准按 shadcn 公式派生 | Nova = 收紧内边距/外边距；圆角由主题定，设计稿卡片就是 12–16px |
| Lucide | 全站图标换成 Lucide 原样路径（v1.73.0，ISC，`LICENSES/lucide.txt`），内联 SVG，不引 npm 包 | 一套图标；平台 logo（X、微博等 `icons/*.svg`）是品牌标识，不算图标集 |
| Motion | 不引 Motion 运行时。状态变化用 CSS 过渡、手势跟手用 rAF/transform，时长和缓动统一取令牌 | 无构建站点加 Motion 要多一个依赖；只保留一种动效写法 |

## 令牌（`web-v11/app.css` `:root`）

### 颜色

| 令牌 | 暗色（默认） | 亮色 | 用途 |
| --- | --- | --- | --- |
| `--background` | `#101114` | `#f6f3ec` | 页面底色 |
| `--foreground` | `#f4f1ea` | `#1c1b18` | 正文 |
| `--foreground-soft` | `#d6d1c6` | `#3f3c37` | 次级正文 |
| `--card` | `#191b20` | `#fffcf6` | 卡片、面板 |
| `--muted` | `#16181c` | `#f3efe6` | 内嵌底（译文块等） |
| `--muted-strong` | `#0c0d10` | `#efeae0` | 图片占位、更深的内嵌 |
| `--muted-foreground` | `#a39e93` | `#6f6a62` | 辅助文字 |
| `--muted-foreground-2` | `#6e6a62` | `#8a857c` | 最弱文字（时间、计数） |
| `--primary` | `#d6b36a` | `#8f6a1e` | 金色强调、选中 |
| `--primary-foreground` | `#161409` | `#fff8e8` | 金底上的字 |
| `--accent` / `--accent-border` / `--accent-foreground` | 金色 8%/20% 透明 | 13%/33% | 提示条 |
| `--border` / `--border-strong` | `#2a2c31` / `#3a3c42` | `#e4dfd4` / `#cfc8ba` | 分隔线 |
| `--ring` | 金色 40% | 金色 40% | 焦点环、金色描边 |
| `--destructive` | `#e15d5d` | `#d14545` | 收藏红心、未读数 |
| `--warning` | `#e1a05d` | `#b56a1a` | 「暂时取不到」提示 |

亮暗只跟随系统（`prefers-color-scheme`），没有站内开关。全屏图片/视频查看器固定黑底，两种主题一样。

### 字号（px）

`--text-2xs` 10 · `--text-xs` 11 · `--text-sm` 12 · `--text-sm2` 13 · `--text-base` 14 · `--text-md` 15 · `--text-lg` 16 · `--text-xl` 17 · `--text-2xl` 18 · `--text-3xl` 20 · `--text-4xl` 22 · `--text-display` 28（频道大标题）。
`app.css` 里不再写裸字号；原来的 9 / 10.5 / 11.5 / 12.5 / 14.5px 已并到相邻一档（9→10、10.5→11、11.5→12、12.5→13、推文正文 14.5→14）。

### 间距

`--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16（页边距 `--page-pad`）· `--space-5` 20 · `--space-6` 24 · `--space-8` 32。新写的样式只用这些值。

### 圆角

`--radius` 12px 为基准：`--radius-xs` 4 · `--radius-sm` 8 · `--radius-md` 10 · `--radius-lg` 12 · `--radius-xl` 16 · `--radius-full` 999（胶囊/圆钮）。头像、圆点用 `50%`。原来的 14px 并到 16，6px 并到 4。

### 动效

| 令牌 | 值 | 用在 |
| --- | --- | --- |
| `--duration-fast` | 150ms | 侧滑返回松手后的收尾 |
| `--duration-base` | 200ms | 淡入淡出、提示条、卡片回弹 |
| `--duration-slow` | 300ms | 频道回弹、下拉刷新回位、刷新按钮转一圈 |
| `--ease-out` | `cubic-bezier(.2,.8,.2,1)` | 默认缓动 |
| `--ease-in-out` | `cubic-bezier(.4,0,.2,1)` | 需要对称时 |

JS 里的过渡用 `app.js` 的 `MOTION`（同样的数值）。系统开「减少动态效果」时 CSS 和 JS 的时长都归零，回顶不再平滑滚动。

规则：
- 跟手的过程（拖动频道、侧滑返回、拖卡片、看图拖动）不加过渡；只有松手后的回弹/收尾用令牌时长。
- 不做滚动驱动的动画，不在滚动时改布局。
- 隐藏的底栏页用 `visibility` + `content-visibility:hidden`，不用 `display:none`：切回频道页不必整页重排（实测见 `docs/rebang-v1/evidence/perf-0116/`）。

## 图标（Lucide）

- 内联 SVG：`class="lucide lucide-<名字>"`、`viewBox="0 0 24 24"`、`stroke="currentColor"`、圆角端点；线宽统一由 CSS `--icon-stroke`（1.75）控制。
- JS 生成的图标走 `lib.js` 的 `icon(name, attrs)`（路径表 `LUCIDE`）；`index.html` 里的静态图标用同一份路径。
- 现在用到：`columns-2` `rows-2`（翻法）、`rotate-cw`（刷新）、`search`、`layout-grid` `user` `flame` `star`（底栏）、`chevron-left` `chevron-right`（返回、上一条/下一条、查看器）、`x`（关闭）、`eye` `message-circle` `repeat-2` `heart`（互动数）、`play`（视频）、`check`（认证）。
- 新增图标：从 lucide-static 同版本拷路径进 `LUCIDE`，不要手画、不要混用别的图标库。
