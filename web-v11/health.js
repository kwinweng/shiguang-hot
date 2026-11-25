/* 来源健康看板的排序和文案。与主站一样按北京时间展示。 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const {esc, fmtFull} = node ? require('./lib.js') : root.RebangLib;
  const LABELS = {all: '全部', ok: '健康', failed: '失败', login_expired: '登录失效', stale: '断更', not_configured: '未配置', unknown: '状态未知'};
  const ORDER = ['login_expired', 'failed', 'stale', 'not_configured', 'unknown', 'ok'];
  const ADVICE = {
    login_expired: '请阿欢提供新的 Cookie 或扫码重新登录，操作入口见交接文档。',
    failed: '通常下一轮会自动重试。连续多轮失败时，再检查来源和采集服务。',
    stale: 'X：检查原始转储是否仍在供稿。其他来源：检查更新和采集是否中断。',
    not_configured: '来源或账号尚未接入，需要时再配置。',
    unknown: '请核对最近一次采集状态。',
  };
  const date = value => typeof value === 'string' ? Date.parse(value) : NaN;
  const byAge = value => Number.isFinite(date(value)) ? date(value) : Infinity;
  const amount = value => Number.isInteger(value) && value >= 0 ? `${value} 条` : '—';
  const statusKey = status => ORDER.includes(status) ? status : 'unknown';

  function healthSections(rows) {
    const groups = Object.fromEntries(ORDER.map(status => [status, []]));
    for (const row of rows) groups[statusKey(row.status)].push(row);
    for (const status of ORDER) {
      if (status !== 'ok') groups[status].sort((a, b) => byAge(a.issue_since) - byAge(b.issue_since));
      if (!groups[status].length) delete groups[status];
    }
    return groups;
  }

  function elapsed(value, now) {
    const age = now - date(value);
    if (!Number.isFinite(age) || age < 0) return '';
    const hours = Math.floor(age / 3600000);
    const days = Math.floor(hours / 24), rest = hours % 24;
    if (!hours) return '不到 1 小时';
    return [days && `${days} 天`, rest && `${rest} 小时`].filter(Boolean).join(' ');
  }

  function rowBody(row, now, account = false) {
    const name = account ? 'health-account-name' : 'health-name';
    const age = elapsed(row.issue_since, now);
    const last = Number.isFinite(date(row.last_ok_at)) ? fmtFull(row.last_ok_at) : '暂无记录';
    const status = statusKey(row.status);
    const group = account ? '' : `<span class="health-group">${esc(row.group)}</span>`;
    const badge = account ? `<span class="health-status" data-status="${status}">${LABELS[status]}</span>` : '';
    return `<div class="health-row-head"><div><b class="${name}">${esc(row.name)}</b>${group}</div>${badge}</div>
      ${row.reason ? `<p class="health-reason">${esc(row.reason)}</p>` : ''}
      ${age ? `<p class="health-age">${row.status === 'stale' ? '已中断' : '距上次成功'} ${age}</p>` : ''}
      <div class="health-meta"><span>上次成功 ${esc(last)}</span><span>本轮 ${amount(row.run_count)} · 最近 ${amount(row.count)}</span></div>`;
  }

  function section(status, rows, now) {
    const advice = ADVICE[status];
    return `<details class="health-section" data-health-group="${status}"${status === 'ok' ? '' : ' open'}>
      <summary class="health-section-head"><span class="health-group-title">${LABELS[status]}</span><span class="health-group-count">${rows.length} 个来源</span></summary>
      ${advice ? `<p class="health-advice"><b>怎么处理</b> ${advice}</p>` : ''}
      <ul class="health-rows">${rows.map(row => {
        const accounts = row.accounts || [];
        const details = accounts.length ? `<details class="health-accounts"><summary>查看 ${accounts.length} 个账号</summary>
          <ul>${Object.values(healthSections(accounts)).flat().map(a => `<li class="health-account">${rowBody(a, now, true)}</li>`).join('')}</ul></details>` : '';
        return `<li class="health-row">${rowBody(row, now)}${details}</li>`;
      }).join('')}</ul></details>`;
  }

  function healthHTML(rows, now) {
    if (!rows.length) return '<p class="muted">暂无来源健康数据。</p>';
    const groups = healthSections(rows);
    const good = groups.ok?.length || 0;
    const filters = Object.keys(LABELS).filter(status => status !== 'unknown' || groups.unknown);
    return `<div class="health-controls">
      <p class="health-overview"><b>${rows.length} 个来源</b> · ${good} 健康 · ${rows.length - good} 需处理</p>
      <div class="health-filters" role="group" aria-label="按来源状态筛选">${filters.map(status => {
        const total = status === 'all' ? rows.length : groups[status]?.length || 0;
        return `<button type="button" data-health-filter="${status}" aria-pressed="${status === 'all'}">${LABELS[status]} <span>${total}</span></button>`;
      }).join('')}</div>
    </div>
    <p class="health-empty muted" role="status" hidden></p>
    ${Object.entries(groups).map(([status, sources]) => section(status, sources, now)).join('')}`;
  }

  const api = {healthSections, elapsed, healthHTML};
  if (node) module.exports = api;
  else root.RebangHealth = api;
})(typeof window !== 'undefined' ? window : globalThis);
