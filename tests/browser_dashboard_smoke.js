/* Real-browser smoke for the applicant's highest-value dashboard path.
 * Uses only Node's built-in WebSocket/fetch support and Chrome's DevTools
 * protocol; no browser-automation package is added to the product.
 */
'use strict';

const fs = require('node:fs');

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
const browserLogs = [];
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (!message.id) {
    if (message.method === 'Log.entryAdded') browserLogs.push(message.params.entry.text || '');
    return;
  }
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

async function capture(name) {
  const prefix = process.env.JOBLOOPER_BROWSER_SCREENSHOT_PREFIX;
  if (!prefix) return;
  const result = await call('Page.captureScreenshot', {format: 'png', fromSurface: true});
  fs.writeFileSync(`${prefix}-${name}.png`, Buffer.from(result.data, 'base64'));
}

try {
  await call('Runtime.enable');
  await call('Page.enable');
  await call('Log.enable');
  await poll("document.querySelectorAll('.active-job-card').length === 1",
    'one active application card');
  const initial = await evaluate(`(() => ({
    stages: document.querySelectorAll('.active-stage-step').length,
    role: document.querySelector('.active-job-card h2')?.textContent,
    action: document.querySelector('.active-job-actions .primary-button')?.dataset.activeAction,
  }))()`);
  if (initial.stages !== 9) fail(`expected 9 touchpoints, found ${initial.stages}`);
  if (!initial.role?.includes('Senior Systems Engineer')) fail('active role is not visible');
  if (initial.action !== 'advert-review') {
    fail(`expected advert-review action, found ${initial.action}`);
  }
  await call('Emulation.setDeviceMetricsOverride', {
    width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false,
  });
  await delay(250);
  await evaluate("if (document.documentElement.dataset.theme !== 'dark') document.querySelector('#theme-button').click(); true");
  await capture('desktop');
  const routing = await evaluate(`import('/foundation.js').then(ui => ({
    drafts: ['Create my CV and cover letter', 'please generate the CV for this job.']
      .every(ui.isPreparationRequest),
    feedback: ['Do not generate my CV', 'Update the CV, you missed my evidence',
      'Generate my CV but remove the unsupported claim', 'Can you explain this CV gap?']
      .every(value => !ui.isPreparationRequest(value)),
    submitted: ui.isSubmissionReport('I applied to this job'),
    uncertain: !ui.isSubmissionReport('I might have applied to this job'),
    history: ui.wasApplied({phase:'rejected', exact_submission:true}),
  }))`);
  if (Object.values(routing).some(value => !value)) fail('a message or history filter changed its meaning');
  await evaluate("document.querySelector('#theme-button').click(); true");
  await capture('desktop-light');
  const brand = await evaluate(`({
    light: document.documentElement.dataset.theme === 'light',
    icon: document.querySelector('.brand img').naturalWidth > 0,
    promise: document.querySelector('#overview-title').textContent.includes('Invent nothing'),
    order: Boolean(document.querySelector('#applications').compareDocumentPosition(document.querySelector('.hero')) & Node.DOCUMENT_POSITION_FOLLOWING),
    noInternalDecision: !/PENDING_REVIEW|LEAVE_AS_IS/.test(document.querySelector('#active-job-list').innerText),
  })`);
  if (Object.values(brand).some(value => !value)) fail(`brand or application-first hierarchy is inconsistent: ${JSON.stringify(brand)}`);
  await evaluate("document.querySelector('#theme-button').click(); true");

  await call('Emulation.setDeviceMetricsOverride', {
    width: 768, height: 900, deviceScaleFactor: 1, mobile: false,
  });
  await delay(250);
  const tabletStagesFit = await evaluate(`(() => {
    const stages = document.querySelector('.active-stage');
    return stages.scrollWidth <= stages.clientWidth;
  })()`);
  if (!tabletStagesFit) fail('768px application stages overflow');

  await call('Emulation.setDeviceMetricsOverride', {
    width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
  });
  await delay(250);
  const mobile = await evaluate(`(() => {
    const search = document.querySelector('.search-box').getBoundingClientRect();
    const stages = document.querySelector('.active-stage');
    return {
      pageFits: document.documentElement.scrollWidth <= window.innerWidth,
      searchFits: search.left >= 0 && search.right <= window.innerWidth,
      stagesFit: stages.scrollWidth <= stages.clientWidth,
      inlineStyles: document.querySelectorAll('[style]').length,
      careerRecordVisible: document.querySelector('#mobile-truth-button').offsetParent !== null,
    };
  })()`);
  if (!mobile.pageFits || !mobile.searchFits || !mobile.stagesFit
      || !mobile.careerRecordVisible) {
    fail(`390px layout overflows: ${JSON.stringify(mobile)}`);
  }
  if (mobile.inlineStyles) fail(`strict CSP found ${mobile.inlineStyles} inline style attributes`);
  await capture('mobile');

  await evaluate("document.querySelector('.active-job-actions .primary-button').click(); true");
  await poll("document.querySelector('#advert-review-dialog')?.open && document.querySelector('#advert-review-form textarea[name=raw]')?.value.length > 0",
    'complete captured-advert review');
  await evaluate(`(() => {
    document.querySelector('#advert-review-form input[name=confirmed]').checked = true;
    document.querySelector('#advert-review-form').requestSubmit();
    return true;
  })()`);
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
  if (finalState.touchpoints[3] !== 'complete' || finalState.touchpoints[4] !== 'current') {
    fail('browser journey did not advance from Prepare to Review');
  }
  // Hold a real review response across a tab switch. It must not repaint the
  // old view after the user has moved to documents (also the build handoff).
  await evaluate(`(() => {
    window.__journeyFetch = window.fetch;
    window.fetch = async (...args) => {
      const response = await window.__journeyFetch(...args);
      if (String(args[0]).startsWith('/api/review?')) {
        await new Promise(resolve => { window.__releaseReview = resolve; });
      }
      return response;
    };
    document.querySelector('#drawer-tabs [data-tab=review]').click(); return true;
  })()`);
  await poll("typeof window.__releaseReview === 'function'", 'held review response');
  await evaluate(`(() => {
    document.querySelector('#drawer-tabs [data-tab=artifacts]').click();
    window.fetch = window.__journeyFetch;
    window.__releaseReview(); return true;
  })()`);
  await delay(350);
  if (!await evaluate("Boolean(document.querySelector('.artifact-group')) && !document.querySelector('.review-sheet')")) {
    fail('a delayed review response overwrote the documents tab');
  }
  await evaluate("document.querySelector('#drawer-tabs [data-tab=review]').click(); true");
  await poll("document.querySelector('[data-review-action=feedback]')", 'current review after switching tabs');
  // Feedback must be reachable on the first reading, before presentation.
  await evaluate("document.querySelector('[data-review-action=feedback]').click(); true");
  await poll("document.querySelector('#feedback-dialog').open", 'first-review feedback');
  await evaluate(`(() => {
    const form = document.querySelector('#feedback-form');
    form.elements.classification.value = 'REUSABLE_PREFERENCE';
    form.elements.classification.dispatchEvent(new Event('change'));
    if (form.elements.requested_scope.value !== 'FUTURE_APPLICATIONS') throw new Error('preference scope missing');
    form.elements.classification.value = 'REJECTION';
    form.elements.classification.dispatchEvent(new Event('change'));
    if (form.elements.requested_scope.value !== 'THIS_APPLICATION') throw new Error('job feedback implies future reach');
    form.elements.note.value = 'Keep the supported wording. No editorial change is needed.';
    form.requestSubmit();
    return true;
  })()`);
  await poll("document.querySelector('#resolve-feedback-dialog').open && document.querySelector('#resolve-feedback-form select[name=decision]').options.length === 2", 'saved feedback decision');
  await evaluate(`(() => {
    const form = document.querySelector('#resolve-feedback-form');
    form.elements.decision.value = 'REJECT';
    form.elements.decision_note.value = 'Checked the approved evidence; the current wording is accurate.';
    form.requestSubmit(); return true;
  })()`);
  await poll("!document.querySelector('#resolve-feedback-dialog').open", 'feedback decision saved');
  await evaluate("document.querySelector('#drawer-tabs [data-tab=feedback]').click(); true");
  await poll("document.querySelector('.feedback-history')?.textContent.includes('current wording is accurate')", 'durable rejection rationale');
  await evaluate("document.querySelector('#drawer-close').click(); document.querySelector('.active-job-actions .primary-button').click(); true");
  await poll("document.querySelector('[data-review-action=present]') && !document.querySelector('#job-drawer').hidden", 'refreshed complete review');
  await evaluate("document.querySelector('[data-review-action=present]').click(); true");
  await poll("document.querySelector('[data-drawer-action=approve]')", 'exact document sign-off');
  await evaluate(`(() => {
    document.querySelector('[data-drawer-action=approve]').click();
    const form = document.querySelector('#approval-form');
    form.elements.reviewer.value = 'Fictional browser reviewer';
    form.elements.confirmed.checked = true;
    form.requestSubmit(); return true;
  })()`);
  await poll("!document.querySelector('#approval-dialog').open && document.querySelector('[data-drawer-action=build]')", 'separate approved/build-incomplete state');
  await evaluate("document.querySelector('[data-drawer-action=build]').click(); true");
  await poll("document.querySelector('[data-drawer-action=submit]') && document.querySelector('.artifact-list')", 'built and verified application documents', 160000);
  await capture('documents');
  const files = await evaluate(`fetch('/api/dashboard').then(r=>r.json()).then(async data => {
    const docs = data.jobs[0].artifacts.filter(item => ['manifest-docx','manifest-letter_docx'].includes(item.id));
    return docs.length === 2 && (await Promise.all(docs.map(async item => {
      const response = await fetch(item.href); const bytes = new Uint8Array(await response.arrayBuffer());
      return response.ok && bytes[0] === 80 && bytes[1] === 75;
    }))).every(Boolean);
  })`);
  if (!files) fail('direct CV and cover-letter downloads did not return DOCX files');
  // The natural-language report opens the exact-file control without Codex.
  await evaluate(`(() => {
    document.querySelector('[data-drawer-action=codex]').click();
    document.querySelector('#agent-message').value = 'I applied to this job';
    document.querySelector('#agent-form').dispatchEvent(new Event('submit', {cancelable:true}));
    return true;
  })()`);
  await poll("document.querySelector('#submission-dialog').open", 'applied report exact-file selection');
  await evaluate(`(() => {
    const form = document.querySelector('#submission-form');
    if (form.elements.cv_artifact_id.value) throw new Error('sent CV was guessed');
    form.elements.cv_artifact_id.value = 'manifest-docx';
    form.elements.letter_artifact_id.value = 'manifest-letter_docx';
    const today = new Date();
    form.elements.applied_date.value = today.getFullYear()+'-'+String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['Fictional saved portal answers.'], 'screening.txt', {type:'text/plain'}));
    form.elements.screening_file.files = transfer.files;
    form.elements.confirmed.checked = true;
    form.requestSubmit(); return true;
  })()`);
  await poll("!document.querySelector('#submission-dialog').open && document.querySelectorAll('.active-job-card').length === 0", 'submitted job leaves drafting workspace');
  await evaluate("document.querySelector('#drawer-close').click(); document.querySelector('[data-filter=applied]').click(); true");
  await poll("document.querySelectorAll('.job-row').length === 1", 'applied history');
  await evaluate(`(() => {
    document.querySelector('.job-row').click();
    document.querySelector('[data-drawer-action=outcome]').click();
    const form = document.querySelector('#outcome-form');
    form.elements.status.value = 'rejected';
    const today = new Date();
    form.elements.response_date.value = today.getFullYear()+'-'+String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');
    form.requestSubmit(); return true;
  })()`);
  await poll("!document.querySelector('#outcome-dialog').open", 'observed rejection');
  const closed = await evaluate(`fetch('/api/dashboard').then(r=>r.json()).then(data => ({
    rejected: data.jobs[0].status === 'rejected',
    retained: data.lessons.length,
    falseTasks: data.attention.filter(item => ['reasoning','silent_application'].includes(item.kind)).length,
    appliedVisible: document.querySelectorAll('.job-row').length === 1,
    submission: data.jobs[0].exact_submission,
  }))`);
  if (!closed.rejected || closed.retained || closed.falseTasks || !closed.appliedVisible || !closed.submission) {
    fail('an outcome erased submitted history or invented learning work');
  }
  const cspErrors = browserLogs.filter(text => /Content Security Policy/i.test(text));
  if (cspErrors.length) fail(`browser reported CSP violations: ${cspErrors.join(' | ')}`);
  process.stdout.write('  ok   browser capture, feedback, review, build, applied record and no-lesson outcome are durable\n');
} finally {
  socket.close();
}
}

main().catch(error => {
  process.stderr.write(`  FAIL browser journey: ${error.message}\n`);
  process.exitCode = 1;
});
