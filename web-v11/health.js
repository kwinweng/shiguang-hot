/* 来源健康看板的排序和文案。与主站一样按北京时间展示。 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const {esc, fmtFull} = node ? require('./lib.js') : root.RebangLib;
  const LABELS = {login_expired: '登录失效', failed: '失败', stale: '断更', not_configured: '未配置', ok: '正常'};
  const ORDER = Object.keys(LABELS);
  const date = value => typeof value === 'string' ? Date.parse(value) : NaN;
  const byAge = value => Number.isFinite(date(value)) ? date(value) : Infinity;
  const amount = value => Number.isInteger(value) && value >= 0 ? `${value} 条` : '—';

  function healthSections(rows) {
    const issues = [], normal = [];
    for (const row of rows) (row.status === 'ok' ? normal : issues).push(row);
    const rank = row => ORDER.includes(row.status) ? ORDER.indexOf(row.status) : ORDER.indexOf('not_configured');
    issues.sort((a, b) => rank(a) - rank(b) || byAge(a.issue_since) - byAge(b.issue_since));
    return [issues, normal];
  }

  function elapsed(value, now) {
    const age = now - date(value);
    if (!Number.isFinite(age) || age < 0) return '';
    const hours = Math.floor(age / 3600000);
    const days = Math.floor(hours / 24), rest = hours % 24;
    if (!hours) return '不到 1 小时';
    return [days && `${days} 天`, rest && `${rest} 小时`].filter(Boolean).join(' ');
  }

  function statusLabel(status) {
    const known = ORDER.includes(status);
    return `<span class="health-status" data-status="${known ? status : 'not_configured'}">${known ? LABELS[status] : '状态未知'}</span>`;
  }

  function rowBody(row, now, account = false) {
    const name = account ? 'health-account-name' : 'health-name';
    const age = elapsed(row.issue_since, now);
    const last = Number.isFinite(date(row.last_ok_at)) ? fmtFull(row.last_ok_at) : '暂无记录';
    const group = !account && `<span class="health-group">${esc(row.group)}</span>`;
    return `<div class="health-row-head"><div>${group || ''}<b class="${name}">${esc(row.name)}</b></div>${statusLabel(row.status)}</div>
      ${row.reason ? `<p class="health-reason">${esc(row.reason)}</p>` : ''}
      ${age ? `<p class="health-age">${row.status === 'stale' ? '已中断' : '距上次成功'} ${age}</p>` : ''}
      <div class="health-meta"><span>上次成功 ${esc(last)}</span><span>本轮 ${amount(row.run_count)} · 最近 ${amount(row.count)}</span></div>`;
  }

  function section(title, rows, now) {
    if (!rows.length) return '';
    return `<section class="health-section"><div class="health-section-head"><h2>${title}</h2><span>${rows.length} 个来源</span></div>
      <ul class="health-rows">${rows.map(row => {
        const accounts = row.accounts || [];
        const details = accounts.length ? `<details class="health-accounts"><summary>查看 ${accounts.length} 个账号</summary>
          <ul>${healthSections(accounts).flat().map(a => `<li class="health-account">${rowBody(a, now, true)}</li>`).join('')}</ul></details>` : '';
        return `<li class="health-row">${rowBody(row, now)}${details}</li>`;
      }).join('')}</ul></section>`;
  }

  function healthHTML(rows, now) {
    if (!rows.length) return '<p class="muted">暂无来源健康数据。</p>';
    const [issues, normal] = healthSections(rows);
    return section('待检查', issues, now) + section('运行正常', normal, now);
  }

  const api = {healthSections, elapsed, healthHTML};
  if (node) module.exports = api;
  else root.RebangHealth = api;
})(typeof window !== 'undefined' ? window : globalThis);
