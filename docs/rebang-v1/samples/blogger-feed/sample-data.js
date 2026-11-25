/* 博主信息流样页的示例数据（2026-11-25）。
   全部是虚构的「示例」博主和占位内容，不对应任何真实账号；图片用 CSS 渐变占位。
   字段形状对齐 bloggers.json 里的 blogger 条目（platform / handle / display_name / metrics / media / quote），
   另加样页才用的 repost（微博式转发）和 mt（机器翻译）。 */
window.SAMPLE = {
  platforms: [
    {id: 'x', name: 'X'}, {id: 'weibo', name: '微博'}, {id: 'jike', name: '即刻'},
    {id: 'wechat', name: '公众号'}, {id: 'blog', name: '博客'}, {id: 'youtube', name: 'YouTube'}
  ],
  accounts: {
    a1: {name: '示例·模型观察', handle: 'sample_models', plat: 'x', hue: 8, posts: 128, last: '12 分钟前',
      bio: '【示例账号】这里会显示博主在原平台的简介。样页用占位文字，正式版从采集数据里读。'},
    a2: {name: '示例·产品手记', handle: '示例产品手记', plat: 'weibo', hue: 28, posts: 64, last: '1 小时前',
      bio: '【示例账号】微博博主的简介占位。'},
    a3: {name: '示例·开源周报', handle: 'sample_oss', plat: 'jike', hue: 205, posts: 41, last: '3 小时前',
      bio: '【示例账号】即刻博主的简介占位。'},
    a4: {name: '示例·长文作者', handle: 'sample-longform', plat: 'wechat', hue: 150, posts: 22, last: '昨天',
      bio: '【示例账号】公众号简介占位。'},
    a5: {name: 'Sample Researcher', handle: 'sample_research', plat: 'x', hue: 265, posts: 87, last: '2 小时前',
      bio: '[Sample account] Placeholder bio. 英文博主正文先显示译文。'},
    a6: {name: '示例·视频频道', handle: 'sample_video', plat: 'youtube', hue: 340, posts: 15, last: '昨天',
      bio: '【示例账号】视频频道简介占位。'}
  },
  posts: [
    {id: 'p1', acc: 'a1', time: '12 分钟前',
      text: '【示例正文】这是一条带四张图的短帖。正式版这里显示博主原文；图片按九宫格排，点图进大图浏览。',
      imgs: 4, metrics: {reply: 18, repost: 42, like: 356}},
    {id: 'p2', acc: 'a5', time: '2 小时前', mt: true,
      text: '【示例译文】英文博主的帖子先显示机器翻译，右下角「看原文」可以展开英文原文。这条还引用了另一条帖子，引用卡片显示在正文下面。',
      orig: '[Sample original] The original English text is shown here when “看原文” is tapped. Placeholder only.',
      quote: {acc: 'a1', time: '5 小时前', text: '【示例被引用帖】被引用的原帖缩成一张小卡片，点卡片进原帖。', imgs: 1},
      metrics: {reply: 9, repost: 31, like: 210}},
    {id: 'p3', acc: 'a2', time: '1 小时前',
      text: '【示例转发语】微博式转发：上面是转发人说的话，下面灰底框里是被转发的原微博。',
      repost: {acc: 'a3', text: '【示例原微博】被转发的原文和它的配图放在灰底框里，点灰框进原帖。这里放一段稍长的文字，看看两三行时的排版效果。', imgs: 3},
      metrics: {reply: 5, repost: 12, like: 88}},
    {id: 'p4', acc: 'a4', time: '昨天 21:40', title: '【示例长文标题】公众号 / 博客的长文在流里显示标题 + 摘要',
      text: '【示例长文摘要】长文超过六行就折叠，末尾显示「全文」，点开在原地展开，再点「收起」。\n\n第二段占位文字：正式版这里是文章开头几段。样页用重复的占位句子把篇幅撑长，方便看折叠效果。\n\n第三段占位文字：一段一段往下排，行高和现有正文页保持一致。\n\n第四段占位文字：展开后可以继续往下滑，不会跳到别的页面。\n\n第五段占位文字：到这里应该已经超过折叠高度了。',
      cover: true, metrics: {reply: 0, repost: 0, like: 0}},
    {id: 'p5', acc: 'a3', time: '3 小时前',
      text: '【示例正文】九张图的帖子，排成三乘三的九宫格。',
      imgs: 9, metrics: {reply: 3, repost: 7, like: 64}},
    {id: 'p6', acc: 'a6', time: '昨天 18:05',
      text: '【示例视频】视频帖显示封面、播放键和时长，能站内播的直接播，不能的点开去原站。',
      video: '12:48', metrics: {reply: 21, repost: 0, like: 530}},
    {id: 'p7', acc: 'a1', time: '昨天 09:12',
      text: '【示例正文】只有一张图的帖子：单图按原比例放大显示，不裁成正方形。',
      imgs: 1, metrics: {reply: 2, repost: 6, like: 77}},
    {id: 'p8', acc: 'a2', time: '11-23',
      text: '【示例正文】纯文字短帖，没有图片和引用。',
      metrics: {reply: 1, repost: 0, like: 12}},
    {id: 'p9', acc: 'a5', time: '11-22', mt: true,
      text: '【示例译文】两张图的帖子，左右并排。',
      orig: '[Sample original] Two images side by side.', imgs: 2,
      metrics: {reply: 4, repost: 15, like: 98}}
  ]
};
