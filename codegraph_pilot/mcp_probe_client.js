// Deterministic CodeGraph MCP stdio probe (no model dependency).
// Spawns the verified CodeGraph CLI in `serve --mcp` mode, performs the
// JSON-RPC handshake, lists tools, and actually CALLS search/callers/impact/
// status/files with real args. Prints raw server responses.
const { spawn } = require('child_process');

const ROOT = 'D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027';
const NODE = ROOT + '/codegraph-bin/codegraph-win32-x64/node.exe';
const SCRIPT = ROOT + '/codegraph-bin/codegraph-win32-x64/lib/dist/bin/codegraph.js';
const REPO = ROOT + '/H3-8207-Experimental';

const child = spawn(NODE,
  ['--liftoff-only', '--disable-warning=ExperimentalWarning', SCRIPT, 'serve', '--mcp'],
  {
    cwd: REPO,
    env: {
      ...process.env,
      DO_NOT_TRACK: '1',
      CODEGRAPH_NO_UPDATE_CHECK: '1',
      CODEGRAPH_MCP_TOOLS: 'search,callers,callees,impact,node,explore,status,files',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

let buf = '';
let nextId = 1;
const pending = new Map();

function send(obj) { child.stdin.write(JSON.stringify(obj) + '\n'); }

function onLine(line) {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  if (msg.id && pending.has(msg.id)) {
    const cb = pending.get(msg.id);
    pending.delete(msg.id);
    cb(msg);
  }
  // ignore notifications (logging etc.)
}

child.stdout.on('data', (d) => {
  buf += d.toString();
  let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const l = buf.slice(0, i);
    buf = buf.slice(i + 1);
    onLine(l);
  }
});
child.stderr.on('data', (d) => { process.stderr.write('[srv-err] ' + d.toString()); });

function request(method, params) {
  return new Promise((resolve) => {
    const myid = nextId++;
    pending.set(myid, resolve);
    send({ jsonrpc: '2.0', id: myid, method, params: params || {} });
  });
}

function truncate(s, n) {
  s = String(s);
  return s.length > n ? s.slice(0, n) + `\n...[truncated ${s.length - n} chars]` : s;
}

(async () => {
  const t0 = Date.now();
  // 1) initialize
  const init = await request('initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'probe', version: '1.0' },
  });
  console.log('INIT ok:', !!init.result, 'serverInfo=', JSON.stringify(init.result && init.result.serverInfo));
  // 2) initialized notification
  send({ jsonrpc: '2.0', method: 'notifications/initialized' });
  // 3) tools/list
  const list = await request('tools/list', {});
  const names = (list.result && list.result.tools || []).map((t) => t.name);
  console.log('\n=== TOOLS/LIST (' + names.length + ') ===');
  console.log(names.join('\n'));
  // 4) real tool calls
  const calls = [
    ['codegraph_search', { query: 'authorize_recovery' }],
    ['codegraph_callers', { symbol: 'recovery' }],
    ['codegraph_impact', { symbol: 'authorize_recovery' }],
    ['codegraph_status', {}],
    ['codegraph_files', { format: 'flat', includeMetadata: false }],
  ];
  for (const [name, args] of calls) {
    const r = await request('tools/call', { name, arguments: args });
    const content = r.result && r.result.content;
    let text = '';
    if (Array.isArray(content)) {
      text = content.map((c) => (c.type === 'text' ? c.text : JSON.stringify(c))).join('\n');
    } else {
      text = JSON.stringify(r.result || r.error);
    }
    const isError = r.result && r.result.isError;
    console.log(`\n=== CALL ${name} (error=${!!isError}) ===`);
    console.log(truncate(text, 1200));
  }
  console.log('\nTOTAL PROBE TIME: ' + (Date.now() - t0) + 'ms');
  child.kill('SIGTERM');
  process.exit(0);
})().catch((e) => {
  console.error('PROBE ERROR:', e);
  child.kill('SIGTERM');
  process.exit(1);
});

setTimeout(() => { console.error('PROBE TIMEOUT'); child.kill('SIGKILL'); process.exit(2); }, 90000);
