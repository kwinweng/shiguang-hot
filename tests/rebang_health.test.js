'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const H = require('../web-v11/health.js');

const base = Date.parse('2026-11-15T20:00:00+08:00');
const row = (status, name, issue_since = null) => ({status, name, issue_since, group: '环球', count: 0, run_count: null});

test('health lists login failures first and orders comparable issues by age', () => {
  const newer = '2026-11-15T08:00:00+08:00';
  const older = '2026-11-13T08:00:00+08:00';
  const rows = [row('ok', '正常源'), row('stale', '较新', newer), row('failed', '失败'),
    row('stale', '较旧', older), row('login_expired', '登录'), row('not_configured', '未配')];
  const groups = H.healthSections(rows);
  assert.deepEqual(Object.keys(groups), ['login_expired', 'failed', 'stale', 'not_configured', 'ok']);
  assert.deepEqual(groups.stale.map(r => r.name), ['较旧', '较新']);
  assert.deepEqual(groups.ok.map(r => r.name), ['正常源']);
  assert.equal(rows[0].name, '正常源');
});

test('age renders one relative unit, with no fabricated duration', () => {
  assert.equal(H.elapsed('2026-11-13T14:00:00+08:00', base), '2 天前');
  assert.equal(H.elapsed('2026-11-15T16:30:00+08:00', base), '3 小时前');
  assert.equal(H.elapsed('2026-11-15T19:30:00+08:00', base), '刚刚');
  for (const value of [null, 'garbage', '2026-11-16T20:00:00+08:00']) assert.equal(H.elapsed(value, base), '');
});

test('health HTML escapes data and distinguishes zero from an unknown count', () => {
  const source = {...row('failed', '<img onerror=boom>'), reason: '<script>boom</script>', run_count: 0};
  const html = H.healthHTML([source, row('ok', '正常')], base);
  assert.doesNotMatch(html, /<img onerror|<script>/);
  assert.match(html, /&lt;img onerror=boom&gt;/);
  assert.match(html, /&lt;script&gt;boom&lt;\/script&gt;/);
  assert.match(html, /本轮 0 条/);
  assert.doesNotMatch(html, /本轮 —/);
  assert.match(H.healthHTML([], base), /暂无来源健康数据/);
});


test('health counts each source once and shows fixed recovery advice by group', () => {
  const rows = ['login_expired', 'failed', 'stale', 'not_configured', 'ok'].map(status => row(status, status));
  rows[0].accounts = [row('ok', '健康账号'), row('login_expired', '失效账号')];
  const html = H.healthHTML(rows, base);
  assert.match(html, /4 个来源需处理.*1 正常/);
  assert.match(html, /data-health-filter="issues" aria-pressed="true"/);
  assert.doesNotMatch(html, /data-health-filter="all"/);
  for (const [status, label] of Object.entries({ok: '正常', failed: '失败', login_expired: '登录失效', stale: '断更', not_configured: '未配置'})) {
    assert.ok(html.includes(`data-health-filter="${status}" aria-pressed="false">${label} <span>1</span>`));
    assert.ok(html.includes(`data-health-group="${status}"${status === 'ok' ? '' : ' open'}>`));
  }
  for (const advice of ['扫码重新登录', '下轮重试', '检查原始转储', '需要时再接入']) {
    assert.ok(html.includes(advice));
  }
  assert.match(html, /查看 2 个账号/);
});

test('health omits zero-count filters and keeps unrecognized states visible', () => {
  const html = H.healthHTML([row('other', '新状态来源')], base);
  assert.doesNotMatch(html, /data-health-filter="(?:ok|failed|stale|not_configured|login_expired)"/);
  assert.match(html, /data-health-group="unknown" open>/);
  assert.match(html, /新状态来源/);
});


test('rows keep exact times and specific reasons without generic failure or empty metadata', () => {
  const last_ok_at = '2026-11-13T14:00:00+08:00';
  const failed = {...row('failed', '失败源', last_ok_at), last_ok_at, reason: 'Telegram 本轮采集失败'};
  const stale = {...row('stale', '断更源', last_ok_at), last_ok_at, reason: '超过 48 小时未更新采集数据', count: 14};
  const html = H.healthHTML([failed, stale], base);
  assert.match(html, /<time[^>]*title="上次成功 2026年11月13日 14:00（北京时间）"[^>]*>2 天前<\/time>/);
  assert.doesNotMatch(html, /Telegram 本轮采集失败|最近 0 条/);
  assert.match(html, /超过 48 小时未更新采集数据.*最近 14 条/);
});


test('health skips malformed sources and accounts while showing one warning', () => {
  const rows = [null, 4, {}, row('ok', '有效源'), {
    ...row('stale', '有效平台'), accounts: [null, false, row('stale', '有效账号'), {}],
  }, {...row('failed', '另一平台'), accounts: 'bad'}];
  const html = H.healthHTML(rows, base);
  assert.match(html, /2 个来源需处理.*1 正常/);
  assert.match(html, /查看 1 个账号/);
  assert.match(html, /有效账号/);
  assert.match(html, /另一平台/);
  assert.equal([...html.matchAll(/部分数据缺损/g)].length, 1);
  assert.match(H.healthHTML([null], base), /部分数据缺损/);
});
