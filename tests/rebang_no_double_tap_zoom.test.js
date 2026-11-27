// 手机双击不该把整页放大（阿欢 11/27 报：双击后页面变大、右侧被裁）。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = fs.readFileSync(path.join(__dirname, '../web-v11/app.css'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../web-v11/index.html'), 'utf8');

test('全页关掉双击放大：html、body 及所有子元素 touch-action:manipulation', () => {
  assert.match(css, /html,body,body \*\{touch-action:manipulation\}/);
});

test('已有更严的手势设置仍在，并且选择器优先级高于通配规则', () => {
  assert.match(css, /\.feed-root\.lr\{touch-action:pan-y\}/);
  assert.match(css, /\.zoom-view\{[^}]*touch-action:none/);
});

test('不靠禁用缩放来修：viewport 不写 user-scalable=no / maximum-scale=1，保留双指放大', () => {
  const vp = html.match(/<meta name="viewport" content="([^"]+)"/)[1];
  assert.doesNotMatch(vp, /user-scalable\s*=\s*(no|0)/);
  assert.doesNotMatch(vp, /maximum-scale\s*=\s*1(\.0)?\b/);
});
