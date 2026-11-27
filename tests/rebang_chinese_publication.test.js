'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const lib = require('../web-v11/lib.js');
const search = require('../web-v11/features/search.js');
const fav = require('../web-v11/features/favorites.js');
const contract = require('../rebang/contract/channels.json');

const old = {id: 'bbc-world:1', kind: 'news', source_id: 'bbc-world', lang: 'en',
  title: 'English headline', summary: 'English summary', body: 'English body'};
const translated = {...old, translated: true, translation: {title: '中文标题', summary: '中文摘要', summary_source: old.summary}};

test('frontend gate covers all configured official web sources', () => {
  for (const c of contract.channels) for (const s of c.sources) {
    assert.equal(lib.isWebNews({...old, source_id: s.id}), s.type !== 'telegram', s.id);
  }
});

test('cached English headlines and partial translations are not search results', () => {
  assert.deepEqual(search.search([old, {...translated, translation: {title: '中文标题', summary: ''}}], 'English'), []);
  assert.equal(search.displayTitle({...old, translated: true, translation_title: '中文标题',
    translation_summary: '中文摘要', summary_source: old.summary, display_title: old.title}), '中文标题');
  assert.deepEqual(search.search([{...translated, translation: {title: '中文标题', summary: '旧正文截出的中文'}}], 'English'), []);
});

test('cached fallback never defaults to an English title, summary, or body', () => {
  assert.equal(lib.display(old).title, '中文译文尚未就绪');
  assert.doesNotMatch(fav.displayTitle(old), /English/);
  assert.equal(lib.display({...translated, translation: {...translated.translation, body: 'English body'}}).bodyPending, true);
  const d = lib.display({...translated, blocks: [{type: 'p', text: 'English body'}],
    translation: {...translated.translation, body: '中文全文'}});
  assert.equal(d.body, '中文全文');
  assert.equal(d.orig.blocks[0].text, 'English body');
  assert.equal(d.blocks, null);
});

test('GitHub repository identifier with usable Chinese preview does not need translation', () => {
  const repo = {...old, source_id: 'github-trending', lang: 'zh', title: 'example/project',
    summary: '这是中文项目简介。', body: '这是中文正文。'};
  assert.equal(lib.display(repo).summary, repo.summary);
  assert.equal(lib.display({...repo, summary: 'An English project summary'}).held, true);
});

test('legacy folded refs never substitute a Chinese title for proof of publication', () => {
  const ref = {id: old.id, source_id: old.source_id, title_zh: '中文标题'};
  assert.equal(lib.dupHTML({merged: [ref]}), '');
  assert.match(lib.dupHTML({merged: [{...ref, chinese_release: true}]}), /中文标题/);
});

test('native code blocks are allowed but echoed English prose is not', () => {
  for (const echo of ['OpenAI launches new model in 中国人工智能市场', 'OpenAI Launches New Model In 中国人工智能市场']) {
    const raw = {...old, summary: echo};
    assert.equal(lib.display({...raw, translated: true, translation: {title: '中文标题', summary: echo, summary_source: echo}}).held, true);
    assert.equal(lib.display({...translated, body: echo, translation: {...translated.translation, body: echo}}).bodyPending, true);
  }
  const preview = {...old, lang: 'zh', title: '中文标题', summary: '中文摘要'};
  assert.equal(lib.display(preview).summary, '中文摘要');
  assert.equal(lib.display(preview).bodyPending, true);
  const native = {...old, lang: 'zh', title: '中文标题', summary: '中文摘要', body: 'npm install example',
    blocks: [{type: 'pre', text: 'npm install example'}]};
  assert.equal(lib.display(native).blocks, null);
  assert.equal(lib.display(native).orig.blocks[0].type, 'pre');
  assert.equal(lib.display({...native, blocks: [{type: 'pre', text: 'This report describes the new policy.'}]}).bodyPending, true);
});
