const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise the actual dependency-free browser handlers against a minimal DOM.
const source = fs.readFileSync('web/app.js', 'utf8');
const handlers = source.slice(source.indexOf('  // Trial lists'), source.indexOf('  // Grid spans'));
function control(category) {
  return {
    dataset: {trialFilter: category},
    attrs: {},
    addEventListener(name, handler) { this[name] = handler; },
    setAttribute(name, value) { this.attrs[name] = value; }
  };
}

test('category controls preserve order and expose selected state', () => {
  const buttons = [control('all'), control('apps'), control('games')];
  const cards = ['games', 'apps', 'games'].map(category => ({dataset: {trialCategory: category}}));
  vm.runInNewContext(handlers, {document: {querySelectorAll(selector) {
    return selector === '[data-trial-filter]' ? buttons : selector === '[data-trial-category]' ? cards : [];
  }}});
  buttons[1].click();
  assert.deepEqual(cards.map(card => card.hidden), [true, false, true]);
  assert.deepEqual(buttons.map(button => button.attrs['aria-pressed']), ['false', 'true', 'false']);
  buttons[0].click();
  assert.deepEqual(cards.map(card => card.hidden), [false, false, false]);
  assert.deepEqual(cards.map(card => card.dataset.trialCategory), ['games', 'apps', 'games']);
});

test('failed images and cached failures both reveal the same text card', () => {
  const images = [
    {complete: true, naturalWidth: 0},
    {complete: false, naturalWidth: 0},
    {complete: true, naturalWidth: 200}
  ].map(image => ({...image, hidden: false, addEventListener(name, handler) { this[name] = handler; }}));
  vm.runInNewContext(handlers, {document: {querySelectorAll(selector) {
    return selector === '.trial-media > img' ? images : [];
  }}});
  assert.deepEqual(images.map(image => image.hidden), [true, false, false]);
  images[1].error();
  assert.deepEqual(images.map(image => image.hidden), [true, true, false]);
});
