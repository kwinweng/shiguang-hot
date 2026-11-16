# YouTube 频道（2026-11-16 15:49 阿欢确认：「YouTube 13 个频道全部启用」）

2026-11-16 按阿欢的兴趣挑（科技/AI、Apple 与数码、3D 打印、科幻、美食、风景旅行、观星、喜剧；兴趣面见 `/workspace/shiguang-haowan-haomai-clean/taste/round1.md`）。
每个频道都在 14:40 左右（北京时间）打开过频道页核对：频道 id、名字、订阅数、视频数、最近一次更新都来自 YouTube 公开页面。

**已全部启用**：下表 13 个已写进 `rebang/contract/bloggers.json` 的 `youtube.accounts`（`handle` 用 UC 开头的频道 id），格式：
`{"handle": "UCbfYPyITQ-7l4upoX8nvctg", "name": "Two Minute Papers", "home": "https://www.youtube.com/@TwoMinutePapers"}`

| # | 频道 | 链接 | 频道 id | 订阅 / 视频数 | 最近更新 | 为什么 |
|---|---|---|---|---|---|---|
| 1 | Two Minute Papers | https://www.youtube.com/@TwoMinutePapers | UCbfYPyITQ-7l4upoX8nvctg | 184 万 / 1111 | 1 天前 | AI 和图形学新论文的几分钟速读，跟进 AI 进展最省时间 |
| 2 | Andrej Karpathy | https://www.youtube.com/@AndrejKarpathy | UCXUPKJO5MZQN11PqgIvyuvQ | 177 万 / 17 | 1 年前 | 已在 X 和博客关注；长篇 LLM 原理课，更新很少但每条都重 |
| 3 | Marques Brownlee（MKBHD） | https://www.youtube.com/@mkbhd | UCBJycsmduvYEL83R_U4JriQ | 2140 万 / 1866 | 4 天前 | Apple 新品和数码评测的标杆 |
| 4 | Mrwhosetheboss | https://www.youtube.com/@Mrwhosetheboss | UCMiJRAwDNSNzuYeN2uWa0pA | 2310 万 / 1945 | 6 天前 | 手机、配件和怪奇数码，偏好玩 |
| 5 | CNC Kitchen | https://www.youtube.com/@CNCKitchen | UCiczXOhGpvoQGhOL16EZiTg | 77 万 / 258 | 14 小时前 | 3D 打印材料与强度实测，硬核但好懂 |
| 6 | Kurzgesagt – In a Nutshell | https://www.youtube.com/@kurzgesagt | UCsXVk37bltHxD1rDPwtNM8Q | 2580 万 / 400 | 5 天前 | 宇宙、科学的动画科普，画面好 |
| 7 | Isaac Arthur | https://www.youtube.com/@isaacarthurSFIA | UCZFipeZtQM5CKUjx6grh54g | 117 万 / 1029 | 1 天前 | 硬科幻与未来学：太空殖民、巨构、文明尺度 |
| 8 | 美食作家王刚 | https://www.youtube.com/@chefwang | UCg0m_Ah8P_MQbnn77-vYnYw | 215 万 / 1138 | 1 天前 | 中文家常菜，做法讲得最实在 |
| 9 | Chinese Cooking Demystified | https://www.youtube.com/@ChineseCookingDemystified | UC54SLBnD5k5U3Q6N__UjbAw | 102 万 / 362 | 2 周前 | 地方菜考据，「寻觅美食」那一类 |
| 10 | Kraig Adams | https://www.youtube.com/@KraigAdams | UCpnuadQ_w3r6f4Q_NRlqd-w | 83.8 万 / 374 | 2 周前 | 无旁白徒步风景（多洛米蒂、喜马拉雅、巴塔哥尼亚），短视频多 |
| 11 | Dr. Becky | https://www.youtube.com/@DrBecky | UCYNbYGl89UUowy8oXkipC-Q | 89.2 万 / 617 | 3 天前 | 天体物理学家讲天文新闻，观星向 |
| 12 | AstroBackyard | https://www.youtube.com/@AstroBackyard | UCn3npsPixgoi_xLdCg9J-LQ | 53.8 万 / 399 | 5 天前 | 后院天文摄影教程和器材，对应「天文望远镜与赤道仪」 |
| 13 | Ryan George | https://www.youtube.com/@RyanGeorge | UCh9IfI45mmk59eDvSWtuuhQ | 185 万 / 445 | 6 天前 | 自导自演的短喜剧（Pitch Meeting 原作者），常拿科幻片开涮 |

核对过但没放进来：Teaching Tech（3D 打印，9 个月没更新）；SnazzyLabs / 影视飓风 / 极客湾（按名字查到的频道不是本人官方号，没核实到正确地址就不列）。

抓取方式：官方频道订阅 `feeds/videos.xml?channel_id=…`（不用 API 密钥）；这个接口 2026 年常对存在的频道回 404，所以失败会重试一次，再退到公开频道页 + 视频页补发布时间。站内点封面用 YouTube 嵌入播放器播放，在国内需要能访问 YouTube 的网络；播不了时有「在 YouTube 打开」。
