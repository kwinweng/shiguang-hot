/* 来源健康看板的排序和文案。与主站一样按北京时间展示。 */
(function (root) {
  'use strict';
  const node = typeof module !== 'undefined' && module.exports;
  const {esc, fmtFull} = node ? require('./lib.js') : root.RebangLib;
  const LABELS = {ok: '正常', failed: '失败', login_expired: '登录失效', stale: '断更', not_configured: '未配置', unknown: '状态未知'};
  const ORDER = ['login_expired', 'failed', 'stale', 'not_configured', 'unknown', 'ok'];
  const ADVICE = {
    login_expired: '更新 Cookie 或扫码重新登录。',
    failed: '等下轮重试，若仍失败则检查采集。',
    stale: '检查来源更新，X 请检查原始转储。',
    not_configured: '来源或账号需要时再接入。',
    unknown: '请核对最近一次采集状态。',
  };
  // 这些固定文案只重述状态。保留网络异常、未收到导出数据、断更阈值等具体线索。
  const REPEATED_REASONS = {
    failed: ['本轮采集失败', 'Telegram 本轮采集失败', '微博本轮采集失败'],
    login_expired: ['登录已失效，需要重新登录', '微博需要重新登录', '微信读书需要重新登录'],
    not_configured: ['尚未配置账号'],
  };
  const STALE_SNAPSHOT_MS = 3 * 60 * 60 * 1000; // 每小时发布，给连续延迟留出余量
  const date = value => typeof value === 'string' ? Date.parse(value) : NaN;
  const byAge = value => Number.isFinite(date(value)) ? date(value) : Infinity;
  const isCount = value => Number.isInteger(value) && value >= 0;
  const statusKey = status => ORDER.includes(status) ? status : 'unknown';
  const isSnapshotStale = (value, now) => now - date(value) > STALE_SNAPSHOT_MS;
  const validRow = row => row && typeof row.name === 'string' && row.name.trim()
    && typeof row.status === 'string' && row.status.trim();

  function healthSections(rows) {
    const groups = Object.fromEntries(ORDER.map(status => [status, []]));
    for (const row of rows) if (validRow(row)) groups[statusKey(row.status)].push(row);
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
    if (hours >= 24) return `${Math.floor(hours / 24)} 天前`;
    return hours ? `${hours} 小时前` : '刚刚';
  }

  function rowTime(row, now) {
    const since = Number.isFinite(date(row.issue_since)) ? row.issue_since : row.last_ok_at;
    const age = elapsed(since, now);
    if (!age) return '';
    const label = since === row.last_ok_at ? '上次成功' : '数据时间';
    const exact = `${label} ${fmtFull(since)}（北京时间）`;
    return `<time class="health-age" tabindex="0" datetime="${esc(since)}" aria-label="${esc(exact)}" title="${esc(exact)}">${age}</time>`;
  }

  function rowBody(row, now, account = false) {
    const name = account ? 'health-account-name' : 'health-name';
    const status = statusKey(row.status);
    const tag = account ? `<span class="health-group" data-status="${status}">${LABELS[status]}</span>`
      : row.group ? `<span class="health-group">${esc(row.group)}</span>` : '';
    const meta = [];
    if (row.reason && !REPEATED_REASONS[status]?.includes(row.reason)) meta.push(esc(row.reason));
    if (isCount(row.run_count)) meta.push(`本轮 ${row.run_count} 条`);
    if (isCount(row.count) && (row.count > 0 || isCount(row.run_count))) meta.push(`最近 ${row.count} 条`);
    return `<div class="health-row-head"><div><b class="${name}">${esc(row.name)}</b>${tag}</div>${rowTime(row, now)}</div>
      ${meta.length ? `<p class="health-meta">${meta.join(' · ')}</p>` : ''}`;
  }

  function section(status, rows, now, initial) {
    const advice = ADVICE[status];
    return `<details class="health-section" data-health-group="${status}"${status !== 'ok' || initial === status ? ' open' : ''}>
      <summary class="health-section-head"${initial === status ? ' hidden' : ''}><span>${LABELS[status]} <span class="health-group-count">${rows.length}</span></span></summary>
      ${advice ? `<p class="health-advice">${advice}</p>` : ''}
      <ul class="health-rows">${rows.map(row => {
        const accounts = row.accounts || [];
        const details = accounts.length ? `<details class="health-accounts"><summary>查看 ${accounts.length} 个账号</summary>
          <ul>${Object.values(healthSections(accounts)).flat().map(a => `<li class="health-account">${rowBody(a, now, true)}</li>`).join('')}</ul></details>` : '';
        return `<li class="health-row">${rowBody(row, now)}${details}</li>`;
      }).join('')}</ul></details>`;
  }

  function healthHTML(sources, now, stale = false) {
    let damaged = false;
    const rows = sources.filter(validRow).map(row => {
      if (row.accounts === undefined) return row;
      const accounts = Array.isArray(row.accounts) ? row.accounts.filter(validRow) : [];
      if (!Array.isArray(row.accounts) || accounts.length !== row.accounts.length) damaged = true;
      return {...row, accounts};
    });
    const warning = damaged || rows.length !== sources.length
      ? '<p class="health-data-warning" role="status">部分数据缺损。</p>' : '';
    if (!rows.length) return `${warning}<p class="muted">暂无来源健康数据。</p>`;
    const groups = healthSections(rows);
    const good = groups.ok?.length || 0;
    const issues = rows.length - good;
    const initial = issues ? 'issues' : 'ok';
    const summary = issues
      ? `<button type="button" data-health-filter="issues" aria-pressed="true"><b>${issues} 个来源需处理</b> · ${good} 正常</button>`
      : stale || warning ? `<b>${good} 个可用来源记录为正常</b>` : `<b>${good} 个来源全部正常</b>`;
    return `<div class="health-controls">
      ${warning}
      <p class="health-overview" data-overview="${stale || warning ? 'warning' : initial}">${summary}</p>
      <div class="health-filters" role="group" aria-label="按来源状态筛选">${Object.entries(groups).map(([status, sources]) =>
        `<button type="button" data-health-filter="${status}" aria-pressed="${status === initial}">${LABELS[status]} <span>${sources.length}</span></button>`
      ).join('')}</div>
    </div>
    ${Object.entries(groups).map(([status, sources]) => section(status, sources, now, initial)).join('')}`;
  }

  const api = {healthSections, elapsed, isSnapshotStale, healthHTML};
  if (node) module.exports = api;
  else root.RebangHealth = api;
})(typeof window !== 'undefined' ? window : globalThis);
