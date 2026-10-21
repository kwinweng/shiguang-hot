/* Pure fixture queries for /design/ only; never loads production archives. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ShiguangNews = factory();
})(typeof window === 'object' ? window : this, function () {
  'use strict';
  const topics = ['全部', '国际', '财经', '科技', '汽车', '社会', '娱乐'];
  const subtopics = ['AI', '科技', '数码', '开发者'];
  const keys = ['date', 'view', 'topic', 'subtopic', 'source', 'q'];
  function validDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(value + 'T00:00:00+08:00');
    return Number.isFinite(+date) && new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(date) === value;
  }
  const topicAliases = {world:'国际',finance:'财经',ai:'AI',tech:'科技',digital:'数码',gadgets:'数码',auto:'汽车',dev:'开发者',society:'社会',entertainment:'娱乐',fun:'娱乐'};
  function parentTopic(topic) {
    topic = Object.hasOwn(topicAliases, topic) ? topicAliases[topic] : topic;
    if (['环球', '全球', '国际'].includes(topic)) return '国际';
    return subtopics.includes(topic) ? '科技' : topic;
  }
  function createModel(data) {
    const items = new Map(data.items.filter(i => i.kind === 'look').map(i => [i.id, i]));
    const sources = new Map(data.news.sources.map(s => [s.id, s]));
    const aliases = new Map();
    for (const s of sources.values()) for (const a of [s.id, s.name, ...(s.aliases || [])]) aliases.set(a, s.id);
    const dates = [...new Set(data.news.dates)].filter(d => validDate(d) && d <= data.date).sort();
    function normalize(input = {}) {
      const get = k => input instanceof URLSearchParams ? input.get(k) : input[k];
      const suppliedTopic = get('topic') || '全部';
      const rawTopic = Object.hasOwn(topicAliases, suppliedTopic) ? topicAliases[suppliedTopic] : suppliedTopic;
      const topic = parentTopic(rawTopic);
      const rawSource = get('source') || '全部';
      return {
        date: get('date') || data.date,
        view: get('view') || 'brief', topic,
        subtopic: get('subtopic') || (['AI', '数码', '开发者'].includes(rawTopic) ? rawTopic : '全部'),
        source: aliases.get(rawSource) || rawSource,
        q: String(get('q') || '').slice(0, 500),
      };
    }
    function params(state, existing = '') {
      const result = new URLSearchParams(existing);
      for (const k of keys) result.set(k, state[k]);
      return result;
    }
    function dateStatus(date) {
      if (!validDate(date)) return 'invalid-date';
      if (date > data.date) return 'future';
      return dates.includes(date) ? 'available' : 'missing';
    }
    function canonical(item) { return aliases.get(item.source_id || item.source) || item.source_id || item.source; }
    function byTime(a, b) {
      const clock = i => /^\d{2}:\d{2}$/.test(i.time || '') ? i.time : '';
      return clock(b).localeCompare(clock(a)) || a.id.localeCompare(b.id);
    }
    function matchesTopic(item, state) {
      return (state.topic === '全部' || parentTopic(item.topic) === state.topic) &&
        (state.subtopic === '全部' || item.topic === state.subtopic);
    }
    function matchesText(item, q) {
      q = q.trim();
      return !q || [item.title, item.reason].join(' ').toLocaleLowerCase().includes(q.toLocaleLowerCase());
    }
    function eventsFor(date) {
      return data.news.events.filter(e => e.date === date).map(e => {
        const members = [...new Set(e.members)].map(id => items.get(id)).filter(i => i && sources.get(canonical(i))?.hot_eligible);
        const representative = items.get(e.representative);
        return { ...e, representative, members, sourceCount: new Set(members.map(canonical)).size };
      }).filter(e => e.representative?.date === date && e.members.some(i => i.id === e.representative.id));
    }
    function query(input) {
      const state = normalize(input);
      const status = dateStatus(state.date);
      if (status !== 'available') return { state, status, rows: [], events: [] };
      if (!['brief', 'hot'].includes(state.view) || !topics.includes(state.topic) ||
          !['全部', ...subtopics].includes(state.subtopic) ||
          (state.subtopic !== '全部' && state.topic !== '科技') ||
          (state.source !== '全部' && !sources.has(state.source)))
        return { state, status: 'invalid-filter', rows: [], events: [] };
      if (state.view === 'hot' && !data.news.hot_dates.includes(state.date))
        return { state, status: 'hot-expired', rows: [], events: [] };
      if (state.view === 'hot' && state.source !== '全部' && !sources.get(state.source).hot_eligible)
        return { state, status: 'ineligible-source', rows: [], events: [] };
      const events = eventsFor(state.date);
      if (state.view === 'hot') {
        const found = events.filter(e => matchesTopic(e.representative, state) &&
          (state.source === '全部' || e.members.some(i => canonical(i) === state.source)) &&
          e.members.some(i => matchesText(i, state.q))).map(e => ({
            ...e, matching: e.members.filter(i =>
              (state.source !== '全部' && canonical(i) === state.source) || (state.q && matchesText(i, state.q))).map(i => i.id),
          })).sort((a, b) => b.hour.localeCompare(a.hour) || b.score - a.score || byTime(a.representative, b.representative));
        return { state, status: found.length ? 'ok' : (events.length ? 'empty-hot' : 'no-hot'), rows: [], events: found };
      }
      const rows = [...items.values()].filter(i => i.date === state.date && matchesTopic(i, state) &&
        (state.source === '全部' || canonical(i) === state.source) && matchesText(i, state.q)).sort(byTime);
      const hottest = [...events].sort((a, b) => b.score - a.score || byTime(a.representative, b.representative))
        .map(e => e.representative).find(i => rows.some(r => r.id === i.id));
      const headline = hottest || rows[0];
      if (headline) rows.splice(rows.findIndex(i => i.id === headline.id), 1);
      return { state, status: headline ? 'ok' : ([...items.values()].some(i => i.date === state.date) ? 'empty-brief' : 'empty-archive'), headline, rows, events: [] };
    }
    function runs(rows) {
      const result = [];
      for (const item of rows) {
        const last = result[result.length - 1];
        if (last && canonical(last[0]) === canonical(item)) last.push(item);
        else result.push([item]);
      }
      return result;
    }
    function adjacent(date, direction) {
      return direction < 0 ? dates.filter(d => d < date).at(-1) : dates.find(d => d > date);
    }
    return { normalize, params, query, dates, sources, items, canonical, runs, adjacent, dateStatus };
  }
  return { createModel, topics, subtopics, parentTopic, validDate };
});
