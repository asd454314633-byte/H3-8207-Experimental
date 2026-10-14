const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const ux = readFileSync(join(__dirname, '../web/h3_workflow_ux.js'), 'utf8');
const workflow = JSON.parse(readFileSync(join(__dirname, '../../../../workflows/history/h3_history_0089.json'), 'utf8'));

function between(a, b) { return ux.slice(ux.indexOf(a), ux.indexOf(b, ux.indexOf(a))); }
test('Native20 is exclusive; returning to PDD and switching to FL2VA disconnects it', () => {
  const graph = structuredClone(workflow.nodes);
  for (const n of graph) n.widgets = Object.entries(n.widgets_values_named || {}).map(([name,value]) => ({name,value}));
  const selector = graph.find(n => n.id === 931);
  let fl2va = false;
  const context = {
    REF2VA_BACKEND_MODES: ['稳定多参考8步', 'PDD多参考8步', 'Native Ref2VA 20步诊断'],
    graphNodes: () => graph,
    widgetByName: (n, name) => n.widgets.find(w => w.name === name),
    fl2vActive: () => fl2va,
    currentOperationKey: () => 'primary_generate', paintOperationNode() {},
    syncOutputFilenamePrefix() {}, app: {graph: {}},
  };
  const script = between('function isPermanentlyOff(', 'function selectedValue(')
    + between('function normalizeRef2vaBackend(', 'function normalizeRef2vaAttention(')
    + between('function syncRef2vaBackend(', 'function syncRef2vaAttention(');
  vm.createContext(context); vm.runInContext(script, context);
  for (const value of ['Native Ref2VA 20步诊断', 'PDD多参考8步', '稳定多参考8步', 'Native Ref2VA 20步诊断']) {
    selector.widgets[0].value = value;
    context.syncRef2vaBackend(selector);
    const expected = value.startsWith('Native') ? 'native20' : value.startsWith('PDD') ? 'pdd8' : 'stable8';
    for (const n of graph.filter(n => n.properties?.h3_ref2va_backend_branch === 'native20' || n.properties?.h3_ref2va_backend_tail)) {
      if (n.properties.h3_legacy_disabled) continue;
      assert.equal(n.mode === 0, n.properties.h3_ref2va_backend_branch === expected, `node ${n.id} in ${value}`);
    }
  }
  fl2va = true; context.syncRef2vaBackend(selector);
  for (const n of graph.filter(n => n.properties?.h3_ref2va_backend_branch === 'native20')) assert.equal(n.mode, 2);
});

test('new branch has no distillation and all existing edges are preserved', () => {
  const old = JSON.parse(readFileSync(join(__dirname, '../../../../fixtures/native20_predecessor_topology.json'), 'utf8'));
  assert.deepEqual(workflow.links.slice(0, old.links.length), old.links);
  const byId = new Map(workflow.nodes.map(n => [n.id,n]));
  assert.equal(byId.get(1010).type, 'MiniMaxH3SigmaShift');
  assert.deepEqual(byId.get(1011).widgets_values, ['beta',20,1]);
  assert.deepEqual(byId.get(1012).widgets_values, ['er_sde']);
  assert.equal(workflow.links.find(l => l[3] === 1010)[1], 691);
  for (const n of workflow.nodes) for (const [index,input] of (n.inputs || []).entries()) {
    if (input.link == null) continue;
    const link = workflow.links.find(l => l[0] === input.link);
    assert.ok(link, `missing link ${input.link}`);
    assert.equal(link[3], n.id); assert.equal(link[4],index);
    assert.ok(byId.get(link[1]).outputs[link[2]].links.includes(link[0]));
  }
  assert.equal(byId.get(931).widgets_values[0], 'PDD多参考8步');
  for (const id of [965,987,990]) assert.equal(byId.get(id).mode, 4);
});
