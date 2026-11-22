import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const migration = fs.readFileSync(new URL('../App/LegacyFavoriteMigration.swift', import.meta.url), 'utf8');
const body = migration.match(/static let script = """\n([\s\S]*?)\n\s*"""/)[1];
const favorites = fs.readFileSync(new URL('../../web-v11/features/favorites.js', import.meta.url), 'utf8');
const site = 'https://news.kwinweng.com';

function fixture() {
  const entries = new Map();
  let writable = true;
  const sandbox = vm.createContext({window: {}, localStorage: {
    getItem: key => entries.get(key) ?? null,
    setItem(key, value) {
      if (!writable) throw Error('storage unavailable');
      entries.set(key, value);
    }
  }, location: {origin: site, pathname: '/'}});
  vm.runInContext(favorites, sandbox);
  const f = sandbox.window.RebangFavorites;
  const run = items => {
    sandbox.payload = JSON.stringify(items);
    return vm.runInContext(`(function(){${body}})()`, sandbox);
  };
  return { entries, run, sandbox, f, write: value => { writable = value; } };
}

const native = {id: 'tg:1', kind: 'news', source_name: '来源', title: '原题', body: '脱机正文',
  translation: {title: '译题', body: '译文'}, image: {url: 'media/safe.jpg'}};

test('preserves web entries, deduplicates IDs and retains the article snapshot', () => {
  const { f, run } = fixture();
  f.save([{id: 'tg:2', title: '已有'}, {id: 'tg:3', title: '网页版本'}]);
  assert.equal(run([native, native, {...native, id:'tg:3'}]), true);
  const items = Array.from(f.load());
  assert.deepEqual(items.map(x => x.id), ['tg:2', 'tg:3', 'tg:1']);
  assert.equal(items[1].title, '网页版本');
  assert.equal(f.displayTitle(items[2]), '译题');
  assert.equal(items[2].translation.body, '译文');
  assert.equal(run([native]), true);
  assert.equal(f.load().length, 3);
});

test('failed storage write does not merge or mark complete; retry succeeds', () => {
  const { f, run, write } = fixture();
  f.save([{id: 'tg:2', title: '已有'}]);
  write(false);
  assert.throws(() => run([native]), /storage unavailable/);
  assert.equal(f.load().length, 1);
  write(true);
  assert.equal(run([native]), true);
  assert.equal(f.load().length, 2);
});

test('wrong origin and malformed existing data fail without overwriting', () => {
  const { entries, f, run, sandbox } = fixture();
  entries.set(f.STORAGE_KEY, 'not JSON');
  sandbox.location.origin = 'https://example.com';
  assert.throws(() => run([native]), /unexpected document/);
  sandbox.location.origin = site;
  assert.throws(() => run([native]), /JSON/);
  assert.equal(entries.get(f.STORAGE_KEY), 'not JSON');
});
