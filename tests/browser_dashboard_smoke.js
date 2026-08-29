/* Real-browser smoke for the applicant's highest-value dashboard path.
 * Uses only Node's built-in WebSocket/fetch support and Chrome's DevTools
 * protocol; no browser-automation package is added to the product.
 */
'use strict';

const [debugPort, dashboardPort] = process.argv.slice(2);
if (!debugPort || !dashboardPort) throw new Error('debug and dashboard ports are required');

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const fail = message => { throw new Error(message); };

async function target() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const rows = await fetch(`http://127.0.0.1:${debugPort}/json/list`).then(r => r.json());
    const page = rows.find(row => row.type === 'page'
      && row.url.startsWith(`http://127.0.0.1:${dashboardPort}`));
    if (page) return page;
    await delay(100);
  }
  return fail('Chrome never exposed the dashboard page target');
}

async function main() {
const page = await target();
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, {once: true});
  socket.addEventListener('error', reject, {once: true});
});

let nextId = 0;
const pending = new Map();
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const {resolve, reject} = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

function call(method, params = {}) {
  const id = ++nextId;
  socket.send(JSON.stringify({id, method, params}));
  return new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
}

async function evaluate(expression) {
  const result = await call('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description
      || result.exceptionDetails.text || 'browser evaluation failed');
  }
  return result.result.value;
}

async function poll(expression, description, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await delay(150);
  }
  fail(`timed out waiting for ${description}`);
}

try {
  await call('Runtime.enable');
  await poll("document.querySelectorAll('.active-job-card').length === 1",
    'one active application card');
  const initial = await evaluate(`(() => ({
    stages: document.querySelectorAll('.active-stage-step').length,
    role: document.querySelector('.active-job-card h2')?.textContent,
    action: document.querySelector('.active-job-actions .primary-button')?.dataset.activeAction,
  }))()`);
  if (initial.stages !== 8) fail(`expected 8 touchpoints, found ${initial.stages}`);
  if (!initial.role?.includes('Senior Systems Engineer')) fail('active role is not visible');
  if (initial.action !== 'preflight') fail(`expected preflight action, found ${initial.action}`);

  await evaluate("document.querySelector('.active-job-actions .primary-button').click(); true");
  await poll("document.querySelector('#preflight-dialog')?.open && document.querySelectorAll('#preflight-decisions select').length > 0",
    'answerable preflight dialog');
  await evaluate(`(() => {
    for (const select of document.querySelectorAll('#preflight-decisions select')) {
      const option = [...select.options].find(row => row.value === 'PROCEED_WITH_RECORDED_GAP');
      if (!option) throw new Error('preflight decision has no recorded-gap option');
      select.value = option.value;
      select.dispatchEvent(new Event('change', {bubbles: true}));
    }
    document.querySelector('#preflight-form').requestSubmit();
    return true;
  })()`);

  await poll(`fetch('/api/dashboard', {cache:'no-store'}).then(r => r.json()).then(data => {
    const job = data.jobs[0];
    return job.workflow.plan && job.outputs.cv && job.outputs.letter;
  })`, 'durable CV and cover-letter records', 200000);
  await poll("!document.querySelector('#job-drawer').hidden && document.querySelector('.review-sheet pre')?.textContent.includes('# DOCUMENT 1')",
    'complete review in the application workspace');

  const finalState = await evaluate(`fetch('/api/dashboard', {cache:'no-store'})
    .then(r => r.json()).then(data => ({
      planEvents: data.jobs[0].timeline.filter(row => row.event === 'PLAN_CREATED').length,
      artifacts: data.jobs[0].artifacts.map(row => row.id),
      touchpoints: data.jobs[0].touchpoints.map(row => row.status),
    }))`);
  if (finalState.planEvents !== 1) fail('generation did not publish exactly one plan event');
  if (!finalState.artifacts.includes('work-cv_record')
      || !finalState.artifacts.includes('work-letter_record')) {
    fail('generated CV or cover-letter artefact is not accessible');
  }
  if (finalState.touchpoints[2] !== 'complete' || finalState.touchpoints[3] !== 'current') {
    fail('browser journey did not advance from Prepare to Review');
  }
  process.stdout.write('  ok   browser URL-to-review touchpoint path is observable and durable\n');
} finally {
  socket.close();
}
}

main().catch(error => {
  process.stderr.write(`  FAIL browser journey: ${error.message}\n`);
  process.exitCode = 1;
});
