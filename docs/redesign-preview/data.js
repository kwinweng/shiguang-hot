'use strict';

// Public channel taxonomy follows categories.md. No private or excluded feeds.
const CATEGORIES = ['全部', '新闻', '财经', '消费', '科技'];

// Display names for the channels present in real-data.js.
const CHANNEL_NAMES = {
  xhqcankao: '风向旗参考快讯',
  tnews365: '竹新社',
  freechinese: 'FREE 中文',
  FinanceNewsDaily: '华尔街见闻·财经时讯',
  HuaErJie1: '华尔街日报',
  TimeHorizonX: 'Time经济观察',
  pelosi3: '敏感经济信息分享',
  CE_Observe: '每日消费电子观察',
  zaihuapd: '在花科技圈',
  NewlearnerChannel: 'Newlearnerの自留地',
};

// Channel -> primary category, derived from the local snapshot's real items.
const CHANNELS = [...new Set(REAL_ITEMS.map(item => item.ch))].map(id => {
  const channelItems = REAL_ITEMS.filter(item => item.ch === id);
  return {
    id,
    name: CHANNEL_NAMES[id] || id,
    category: channelItems[0].category,
  };
});
