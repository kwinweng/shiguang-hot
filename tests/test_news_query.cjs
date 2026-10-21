const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createModel, validDate} = require('../design/news-query.js');
const data = JSON.parse(fs.readFileSync(path.join(__dirname,'../design/samples.json'),'utf8'));
const model = createModel(data);
const brief = patch => model.query({view:'brief',...patch});
const hot = patch => model.query({view:'hot',...patch});
const allRows = result => [result.headline,...result.rows].filter(Boolean);

test('strict Shanghai civil dates reject rollover, future and missing archives', () => {
  assert.equal(validDate('2026-02-30'),false);
  assert.equal(validDate('2026-10-20'),true);
  assert.equal(brief({date:'no'}).status,'invalid-date');
  assert.equal(brief({date:'2026-10-21'}).status,'future');
  assert.equal(brief({date:'2026-10-17'}).status,'missing');
  assert.equal(brief({date:'2026-10-15'}).status,'empty-archive');
});
test('manifest navigation skips missing days without depending on filters', () => {
  assert.equal(model.adjacent('2026-10-18',-1),'2026-10-16');
  assert.equal(model.adjacent('2026-09-30',-1),undefined);
  assert.equal(model.adjacent('2026-10-20',1),undefined);
  assert.equal(brief({q:'does-not-exist'}).status,'empty-brief');
  assert.equal(model.dateStatus('2026-10-20'),'available');
});
test('old topic labels and source aliases keep exact scope', () => {
  for (const topic of ['AI','数码','开发者']) {
    const state = model.normalize({topic});
    assert.equal(state.topic,'科技'); assert.equal(state.subtopic,topic);
    assert.ok(allRows(brief({topic})).every(i => i.topic===topic));
  }
  assert.equal(model.normalize({topic:'环球'}).topic,'国际');
  for (const [old,topic,subtopic] of [['world','国际','全部'],['ai','科技','AI'],['gadgets','科技','数码'],['dev','科技','开发者'],['fun','娱乐','全部']]) {
    const s=model.normalize({topic:old}); assert.equal(s.topic,topic); assert.equal(s.subtopic,subtopic);
  }
  assert.equal(model.normalize({source:'GitHub 热门'}).source,'github');
  assert.equal(model.normalize({source:'推特爆款'}).source,'x');
});
test('technology is the union, subtopics and sources are independent intersections', () => {
  assert.deepEqual(new Set(allRows(brief({topic:'科技'})).map(i=>i.topic)),new Set(['科技','AI','开发者','数码']));
  assert.deepEqual(allRows(brief({topic:'科技',subtopic:'AI',source:'research'})).map(i=>i.id),['look-ai']);
  assert.equal(brief({topic:'国际',source:'world'}).status,'empty-brief');
  assert.equal(allRows(brief({topic:'财经',source:'world'}))[0].id,'look-column-world');
});
test('unknown records remain reachable but unknown filters never broaden silently', () => {
  assert.ok(allRows(brief()).some(i=>i.id==='look-unknown'));
  for (const patch of [{source:'unknown'},{topic:'unknown'},{topic:'__proto__'},{topic:'constructor'},{subtopic:'unknown'},{view:'unknown'},{topic:'社会',subtopic:'AI'}])
    assert.equal(model.query(patch).status,'invalid-filter');
});
test('headline appears once, rest sort newest first with date-only last', () => {
  const r=brief(); assert.equal(r.headline.id,'look-0');
  const rows=allRows(r); assert.equal(new Set(rows.map(i=>i.id)).size,rows.length);
  assert.equal(r.rows[0].time,'10:27'); assert.equal(r.rows.at(-1).time,'仅日期');
  assert.ok(!allRows(brief({topic:'科技'})).some(i=>i.id==='look-0'));
});
test('historical date never mixes today; date-only precision stays intact', () => {
  const r=brief({date:'2026-10-19'});
  assert.ok(allRows(r).every(i=>i.date==='2026-10-19'));
  assert.equal(allRows(r).at(-1).time,'仅日期');
  assert.equal(allRows(brief({date:'2026-09-30'}))[0].id,'look-history-sep');
});
test('same-source runs are consecutive rather than grouped out of chronology', () => {
  const runs=model.runs(brief().rows);
  assert.equal(runs.find(r=>r[0].id==='look-2').length,5);
  assert.ok(runs.every(r=>new Set(r.map(model.canonical)).size===1));
});
test('hot candidates are explicit events, IDs and representative rows are unique', () => {
  const r=hot(); assert.equal(r.events.length,8);
  assert.equal(new Set(r.events.map(e=>e.id)).size,r.events.length);
  assert.equal(new Set(r.events.map(e=>e.representative.id)).size,r.events.length);
  assert.ok(r.events.every(e=>e.members.every(i=>!['x','github'].includes(i.source_id))));
  assert.deepEqual(r.events.filter(e=>e.hour==='09').map(e=>e.representative.id),['look-7','look-5','look-6']);
});
test('hot source membership and member text find one event without rescoring it', () => {
  const a=hot().events.find(e=>e.id==='event-look-0');
  const b=hot({source:'research',q:'蓝色书签'}).events;
  assert.equal(b.length,1); assert.equal(b[0].id,a.id);
  assert.equal(b[0].score,a.score); assert.equal(b[0].sourceCount,4);
  assert.ok(b[0].matching.includes('look-world-member-0'));
  const c=hot({source:'tech',q:'蓝色书签'}).events;
  assert.equal(c.length,1); assert.ok(c[0].matching.includes('look-world-member-0'));
  assert.ok(c[0].matching.includes('look-world-member-1'));
});
test('aliases and duplicate member IDs never inflate source count', () => {
  const copy=structuredClone(data);
  copy.items.push({...copy.items.find(i=>i.id==='look-world-member-0'),id:'same-source-alias',source_id:undefined,source:'示例研究所'});
  copy.news.events[0].members.push('same-source-alias','look-world-member-0');
  const event=createModel(copy).query({view:'hot'}).events.find(e=>e.id==='event-look-0');
  assert.equal(event.sourceCount,4); assert.equal(event.members.length,5);
});
test('hot topic uses representative topic rather than every member tag', () => {
  const copy=structuredClone(data); copy.items.find(i=>i.id==='look-world-member-0').topic='汽车';
  const m=createModel(copy);
  assert.ok(!m.query({view:'hot',topic:'汽车'}).events.some(e=>e.id==='event-look-0'));
});
test('excluded hot source explains state while keeping selected conditions', () => {
  for (const source of ['github','x']) {
    const r=hot({source,q:'sample'}); assert.equal(r.status,'ineligible-source');
    assert.equal(r.state.source,source); assert.equal(r.state.q,'sample'); assert.equal(r.state.view,'hot');
  }
});
test('no hot day, filtered-empty hot and expired archive are distinct', () => {
  assert.equal(hot({date:'2026-10-18'}).status,'no-hot');
  assert.equal(hot({q:'does-not-exist'}).status,'empty-hot');
  const r=hot({date:'2026-10-16',topic:'国际',q:'历史'});
  assert.equal(r.status,'hot-expired'); assert.equal(r.state.date,'2026-10-16'); assert.equal(r.state.view,'hot');
  assert.equal(brief(r.state).status,'hot-expired'); // explicit switching is required
  assert.equal(brief({...r.state,view:'brief'}).status,'ok');
});
test('date changes preserve view, source, topic and query; URL round trips focus safely', () => {
  const state=model.normalize({date:'2026-10-19',view:'hot',topic:'AI',source:'示例研究所',q:'昨 天 <script>'});
  const params=model.params(state,'focus=1&unrelated=keep');
  assert.equal(params.get('focus'),'1'); assert.equal(params.get('unrelated'),'keep');
  assert.deepEqual(model.normalize(params),state);
  const next=model.normalize({...state,date:'2026-10-16'}); assert.equal(next.q,state.q); assert.equal(next.subtopic,'AI');
});

test('precomputed cross-midnight event stays on first-report day; member keeps its own publication day', () => {
  const event=hot({date:'2026-10-19',q:'跨日更新'}).events[0];
  assert.equal(event.date,'2026-10-19'); assert.equal(event.hour,'16');
  assert.ok(event.members.some(i=>i.id==='look-history-nextday-member'&&i.date==='2026-10-20'&&i.time==='00:10'));
  assert.equal(event.sourceCount,2);
  assert.ok(!allRows(brief({date:'2026-10-19'})).some(i=>i.id==='look-history-nextday-member'));
  assert.ok(allRows(brief({date:'2026-10-20'})).some(i=>i.id==='look-history-nextday-member'));
  assert.ok(!hot({date:'2026-10-20',q:'跨日更新'}).events.length);
});
