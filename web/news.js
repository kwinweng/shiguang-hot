/* Live feed and completed-day reviews. All inputs are build-time public JSON. */
'use strict';
const News = (() => {
  const categories = ['全部', '热门', '科技', '财经', '国际', '数码'];
  const icons = ['squares-four', 'fire', 'cpu', 'chart-line-up', 'globe', 'device-mobile'];
  const category = value => ({全球:'国际', 环球:'国际', AI:'科技', 科技AI:'科技', '科技 AI':'科技', 开发者:'科技'})[value] || value;
  const labels = new Map([['今日重点','热点'],['今日实时','实时'],['往日回顾','回顾']]);
  const escape = value => String(labels.get(value) ?? value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe = value => /^https?:\/\//i.test(value || '') ? escape(value) : '';
  const icon = (name, fill = false) => `<span class="ic">${window.ICONS[name + (fill ? '_fill' : '_line')] || ''}</span>`;
  const filter = (rows, cat) => !cat || cat === '全部' ? rows : rows.filter(row =>
    cat === '热门' ? row.hot || row.source_count > 1 || row.category === '热门' : category(row.category) === category(cat));
  const monthDays = (month, available) => {
    const [year, m] = month.split('-').map(Number);
    return Array.from({length:new Date(Date.UTC(year, m, 0)).getUTCDate()}, (_, i) => {
      const day = `${month}-${String(i + 1).padStart(2, '0')}`;
      return {day, enabled:available.includes(day)};
    });
  };
  return {categories, icons, escape, safe, icon, filter, monthDays};
})();
if (typeof module !== 'undefined') module.exports = News;
