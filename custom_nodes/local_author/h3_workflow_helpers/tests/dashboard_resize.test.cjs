const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const source = readFileSync(join(__dirname, '../web/h3_foolproof_v3_dashboard.js'), 'utf8');
const start = source.indexOf('  const syncPanelWidth =');
const end = source.indexOf('  // Preserve saved/user dimensions', start);

test('DOM widget follows resize and geometry restored by configure or undo', () => {
  const node = {
    size: [860, 1100],
    addDOMWidget(name, type, panel, options) {
      return { name, type, element: panel, width: 220, options };
    },
  };
  const widget = vm.runInNewContext(source.slice(start, end) + '\ndomWidget;', { node, panel: {} });
  assert.equal(widget.width, 860);
  for (const width of [480, 1200, 640, 860]) {
    node.size[0] = width;
    widget.options.afterResize.call(widget);
    assert.equal(widget.width, width);
  }
  node.size[0] = 1000;
  widget.width = 220;
  widget.options.onDraw(widget);
  assert.equal(widget.width, 1000);
  assert.equal(widget.options.getMinHeight(), 240);
  assert.equal(widget.options.getMaxHeight(), Infinity);
  assert.equal(widget.options.hideOnZoom, false);
  assert.equal(widget.options.serialize, false);
});

test('director applies its draft to the active native prompt without a duplicate editor', () => {
  assert.equal(source.includes('promptSection.append(prompt)'), false);
  const start = source.indexOf('  function applyDirectorDraft()');
  const end = source.indexOf('  function refresh()', start);
  for (const ref of [true, false]) {
    const refPromptNode = { value: 'reference' };
    const flPromptNode = { value: 'first-last' };
    const context = {
      directorOverlay: { __h3: { draftArea: { value: 'organized draft' } } },
      isRef: () => ref, refPromptNode, flPromptNode,
      widget: node => node,
      setWidget: (target, value) => { target.value = value; },
      hideDirectorPreview() {}, refresh() {},
    };
    vm.runInNewContext(source.slice(start, end) + '\napplyDirectorDraft();', context);
    assert.equal((ref ? refPromptNode : flPromptNode).value, 'organized draft');
    assert.equal((ref ? flPromptNode : refPromptNode).value, ref ? 'first-last' : 'reference');
  }
});
