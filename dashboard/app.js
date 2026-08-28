'use strict';

const state = {
  data: null,
  filter: 'all',
  search: '',
  selectedJob: null,
  tab: 'overview',
  lastFocus: null,
  session: null,
  agentJob: null,
  agentIntent: 'ask',
  agentConversations: {},
  activeTask: null,
  taskPoller: null,
  taskPollFailures: 0,
  serverInstanceId: null,
  truthIntegrityDetail: '',
  actionJob: null,
  intakeBaseline: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const icons = {
  activity: '<svg viewBox="0 0 24 24"><path d="M3 12h4l2.2-6 4 12 2.3-6H21"/></svg>',
  briefcase: '<svg viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5h8v2M3 12h18M10 12v2h4v-2"/></svg>',
  arrow: '<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>',
  database: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M6 2h8l4 4v16H6zM14 2v5h5M9 13h6M9 17h6"/></svg>',
  flag: '<svg viewBox="0 0 24 24"><path d="M5 21V4M5 5h11l-2 4 2 4H5"/></svg>',
  layers: '<svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/></svg>',
  link: '<svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"/></svg>',
  target: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M22 12h-3M12 22v-3M2 12h3"/></svg>',
  trend: '<svg viewBox="0 0 24 24"><path d="m3 17 6-6 4 4 7-8M15 7h5v5"/></svg>',
  warning: '<svg viewBox="0 0 24 24"><path d="M12 3 2.5 20h19zM12 9v5M12 17.5v.1"/></svg>',
  external: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 13v7H4V6h7"/></svg>',
};

function h(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

function titleCase(value) {
  return String(value || 'unknown').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function phaseLabel(value) {
  return ({captured: 'Captured', review: 'In review', approved: 'Approved', applied: 'Applied',
    progressed: 'Progressed', rejected: 'Rejected', closed: 'Closed'})[value] || titleCase(value);
}

function ratio(value, denominator) {
  return denominator ? `${Math.round((value / denominator) * 100)}%` : '—';
}

function dateLabel(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {day: '2-digit', month: 'short', year: 'numeric'}).format(date);
}

function dateTimeLabel(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(date);
}

function bytesLabel(value) {
  if (value === null || value === undefined) return '';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function companyInitials(company) {
  return String(company || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase();
}

function latencyLabel(value) {
  return ({under_24h: 'Under 24 hours', '1_3d': '1–3 days', '4_7d': '4–7 days',
    '8_30d': '8–30 days', over_30d: 'Over 30 days', unknown: 'Unknown'})[value] || titleCase(value);
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
}

async function loadSession() {
  const response = await fetch('/api/session', {cache: 'no-store'});
  if (!response.ok) throw new Error(`Dashboard session returned ${response.status}`);
  const session = await response.json();
  if (state.serverInstanceId && session.instance_id !== state.serverInstanceId) {
    preserveDashboardContext();
    location.reload();
    return;
  }
  state.session = session;
  state.serverInstanceId = session.instance_id;
  if (state.data) renderHeader();
  const button = $('#agent-button');
  button.disabled = !state.session.agent.available;
  button.title = state.session.agent.available
    ? 'Open the guarded Codex workspace'
    : 'Install or expose the Codex CLI to enable agent conversation';
}

function preserveDashboardContext() {
  const message = String($('#agent-message')?.value || '').trim();
  const jobId = state.agentJob?.id || state.activeTask?.job_id || null;
  if (!message && !jobId) return;
  sessionStorage.setItem('joblooper-dashboard-context', JSON.stringify({
    job_id: jobId, message, saved_at: new Date().toISOString(),
  }));
}

async function monitorDashboardInstance() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    if (!response.ok) return;
    const health = await response.json();
    if (state.serverInstanceId && health.instance_id !== state.serverInstanceId) {
      preserveDashboardContext();
      location.reload();
    }
  } catch {
    // A replacement briefly removes the listener; the next poll sees its new identity.
  }
}

async function apiPost(path, body) {
  if (!state.session) await loadSession();
  const response = await fetch(path, {
    method: 'POST',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-Joblooper-Token': state.session.csrf_token,
    },
    body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({error: `Request returned ${response.status}`}));
  if (!response.ok || result.ok === false) throw new Error(result.error || `Request returned ${response.status}`);
  return result;
}

async function loadData(showToast = false) {
  const refresh = $('#refresh-button');
  refresh.classList.add('spinning');
  try {
    const response = await fetch('/api/dashboard', {cache: 'no-store'});
    if (!response.ok) throw new Error(`Dashboard data returned ${response.status}`);
    state.data = await response.json();
    render();
    if (state.selectedJob) {
      state.selectedJob = jobById(state.selectedJob.id);
      if (state.selectedJob) renderDrawer(); else closeDrawer();
    }
    if (state.agentJob) {
      state.agentJob = jobById(state.agentJob.id);
      renderAgentQuickActions();
    }
    if (showToast) toast('Dashboard refreshed from governed files.');
  } catch (error) {
    $('#job-ledger').innerHTML = `<div class="empty-state">${icons.warning}<strong>Dashboard data could not be loaded</strong><span>${h(error.message)}</span></div>`;
    toast(error.message);
  } finally {
    refresh.classList.remove('spinning');
  }
}

function jobById(id) {
  return state.data?.jobs.find(job => job.id === id) || null;
}

function render() {
  renderHeader();
  renderActiveWorkspace();
  renderPrimaryAction();
  renderKpis();
  renderPipeline();
  renderControls();
  renderFilters();
  renderJobs();
  renderAttention();
  renderLearning();
}

function activeJobs() {
  return state.data.jobs.filter(job => ['captured', 'review', 'approved', 'applied'].includes(job.phase));
}

function workflowProgress(job) {
  const workflow = job.workflow || {};
  const steps = [
    ['Captured', workflow.captured], ['Questions', workflow.preflight],
    ['Drafted', workflow.plan], ['Reviewed', workflow.presentation],
    ['Approved', workflow.approval], ['Built', workflow.package],
    ['Submitted', workflow.submission],
  ];
  return {steps, completed: steps.filter(([, done]) => done).length};
}

function activePrimary(job) {
  const task = state.activeTask?.job_id === job.id ? state.activeTask : null;
  if (task && ['starting', 'running', 'waiting'].includes(task.status)) {
    return ['View active Codex turn', 'active-turn'];
  }
  if (task?.status === 'failed') return ['Recover interrupted turn', 'active-turn'];
  if (job.phase === 'captured') return ['Continue preflight', 'codex'];
  if (job.phase === 'review') return ['Review CV & letter', 'review'];
  if (job.phase === 'approved') return ['Open submission desk', 'submit'];
  return ['Open application record', 'overview'];
}

function renderActiveWorkspace() {
  const jobs = activeJobs();
  $('#active-count').textContent = jobs.length;
  if (!jobs.length) {
    $('#active-job-list').innerHTML = '<div class="active-empty"><div><strong>No active applications.</strong><span>Paste an official job link to create one governed workspace.</span></div><button class="primary-button" type="button" data-active-action="new">+ New application</button></div>';
    return;
  }
  $('#active-job-list').innerHTML = jobs.map(job => {
    const task = state.activeTask?.job_id === job.id ? state.activeTask : null;
    const taskRunning = task && ['starting', 'running', 'waiting'].includes(task.status);
    const taskFailed = task?.status === 'failed';
    const coverage = job.coverage === null || job.coverage === undefined
      ? 'Not assessed' : `${Math.round(job.coverage * 100)}% evidence coverage`;
    const assessed = job.requirements.length > 0;
    const gaps = assessed
      ? `${job.spread.gap} gaps · ${job.hard_gaps.length} hard-gate gaps`
      : 'Gaps not assessed';
    const documents = job.outputs.cv || job.outputs.letter
      ? `${job.outputs.cv ? 'CV ready' : 'CV missing'} · ${job.outputs.letter ? 'letter ready' : 'letter missing'}`
      : 'CV and letter not created';
    const feedbackCount = (job.feedback_items || []).length;
    const openFeedback = job.workflow?.open_feedback || 0;
    const source = job.artifacts.find(item => item.group === 'Source' && item.href);
    const {steps, completed} = workflowProgress(job);
    const [primaryLabel, primaryAction] = activePrimary(job);
    const nextAction = taskRunning
      ? `Codex is working · ${task.scope || 'application task'} · ${turnDuration(task)}`
      : taskFailed
        ? 'Codex was interrupted · durable files were refreshed · recovery is available'
        : job.next_action;
    return `<article class="active-job-card${taskRunning ? ' working' : ''}${taskFailed ? ' interrupted' : ''}" data-job-card="${h(job.id)}">
      <header class="active-job-header">
        <span class="company-avatar">${h(companyInitials(job.company))}</span>
        <div><p class="micro-label">${h(job.company)} · Ref ${h(job.reference)}</p><h2>${h(job.role)}</h2><span class="updated-label">Last activity ${h(dateTimeLabel(job.updated_at))}</span></div>
        <span class="status-badge" data-phase="${h(job.phase)}">${h(phaseLabel(job.phase))}</span>
      </header>
      <div class="active-stage" aria-label="${completed} of ${steps.length} application gates complete">
        ${steps.map(([label, done], index) => `<span class="active-stage-step ${done ? 'done' : ''} ${index === completed ? 'current' : ''}"><i></i>${h(label)}</span>`).join('')}
      </div>
      <div class="active-job-body">
        <div class="active-next"><span class="micro-label">${taskRunning ? 'Work in progress' : taskFailed ? 'Interruption detected' : 'Next required action'}</span><strong>${h(nextAction)}</strong></div>
        <div class="active-facts">
          <button type="button" data-active-action="evidence" data-job="${h(job.id)}"><span>Evidence & gaps</span><strong>${h(coverage)}</strong><small>${h(gaps)} · not an ATS score</small></button>
          <button type="button" data-active-action="artifacts" data-job="${h(job.id)}"><span>Documents</span><strong>${h(documents)}</strong><small>${job.artifacts.length} accessible artefacts</small></button>
          <button type="button" data-active-action="feedback" data-job="${h(job.id)}"><span>Comments</span><strong>${feedbackCount ? `${feedbackCount} recorded` : 'No comments yet'}</strong><small>${openFeedback ? `${openFeedback} awaiting resolution` : 'Add or review feedback'}</small></button>
        </div>
      </div>
      <footer class="active-job-actions">
        <button class="primary-button" type="button" data-active-action="${primaryAction}" data-job="${h(job.id)}">${h(primaryLabel)}</button>
        <button class="secondary-button" type="button" data-active-action="overview" data-job="${h(job.id)}">Manage application</button>
        ${source ? `<a class="secondary-button" href="${h(source.href)}" target="_blank">Open captured JD</a>` : ''}
        <span>${taskRunning ? 'Live turn · durable gates shown above' : taskFailed ? 'No completion assumed' : `${completed}/${steps.length} gates complete`}</span>
      </footer>
    </article>`;
  }).join('');
}

function renderHeader() {
  const {truth, generated_at: generatedAt} = state.data;
  const pill = $('#truth-pill');
  pill.textContent = truth.errors ? 'TRUTH BLOCKED' : truth.ready ? 'TRUTH READY' : 'TRUTH NEEDS REVIEW';
  pill.style.color = truth.errors ? 'var(--red)' : truth.ready ? 'var(--green)' : 'var(--amber)';
  const version = state.session?.dashboard_version;
  $('#last-refresh').textContent = `Refreshed ${dateTimeLabel(generatedAt)}${version ? ` · v${version}` : ''}`;
}

function renderPrimaryAction() {
  const actions = state.data.attention;
  const action = actions.find(x => ['critical', 'action'].includes(x.severity)) || actions[0];
  const control = $('#primary-action');
  control.disabled = !action;
  control.innerHTML = action
    ? `<span class="micro-label">Priority now · ${h(action.company)}</span><strong>${h(action.action)}</strong>`
    : '<span class="micro-label">Priority now</span><strong>No open application actions. Paste the next official job link when ready.</strong>';
}

function renderKpis() {
  const k = state.data.kpis;
  const cards = [
    ['In progress', k.in_progress, 'Jobs awaiting action or response', 'activity', ''],
    ['Submitted', k.submitted, 'Exact application records', 'briefcase', 'violet'],
    ['Progressed', k.progressed, 'Interview, progression or offer', 'trend', 'success'],
    ['Rejected', k.rejected, 'Observed outcomes', 'flag', 'danger'],
    ['Exact correlation', ratio(k.exact_submissions, k.application_denominator), `${k.exact_submissions}/${k.application_denominator} submitted bundles`, 'target', 'success'],
    ['Portal answers', ratio(k.screening_captured, k.application_denominator), `${k.screening_captured} exact · ${k.screening_unavailable} unavailable`, 'database', k.screening_captured + k.screening_unavailable < k.application_denominator ? 'warning' : 'success'],
  ];
  $('#kpi-grid').innerHTML = cards.map(([label, value, meta, icon, tone]) => `
    <article class="kpi-card" data-tone="${tone}">
      <div class="kpi-top"><span class="kpi-label">${h(label)}</span><span class="kpi-icon">${icons[icon]}</span></div>
      <div class="kpi-value">${h(value)}</div><div class="kpi-meta">${h(meta)}</div>
    </article>`).join('');
}

function renderPipeline() {
  const m = state.data.milestones;
  const steps = [
    ['Captured', m.captured, 'Exact JD'],
    ['Reviewed', m.reviewed, 'Chat bundle'],
    ['Approved', m.approved, 'Signed off'],
    ['Applied', m.applied, 'Exact receipt'],
    ['Progressed', m.progressed, 'Observed'],
  ];
  $('#pipeline-chart').innerHTML = `
    <div class="pipeline-track">
      ${steps.map(([label, value, detail]) => `<div class="pipeline-step"><div class="pipeline-node">${value}</div><span class="pipeline-label">${label}</span><span class="pipeline-detail">${detail}</span></div>`).join('')}
    </div>
    <div class="outcome-branch"><span class="branch-chip progressed">${m.progressed} progressed</span><span class="branch-chip rejected">${m.rejected} rejected</span></div>`;
}

function controlRow(name, note, value, tone) {
  return `<div class="control-row"><div><span class="control-name">${h(name)}</span><span class="control-note">${h(note)}</span></div><span class="control-value ${tone}">${h(value)}</span></div>`;
}

function renderControls() {
  const {truth, kpis: k} = state.data;
  const exact = ratio(k.exact_submissions, k.application_denominator);
  const screeningAccounted = k.screening_captured + k.screening_unavailable;
  const screening = `${k.screening_captured} exact · ${k.screening_unavailable} unavailable`;
  const dates = ratio(k.response_dates, k.outcome_denominator);
  const timing = ratio(k.timing_bands, k.outcome_denominator);
  $('#control-list').innerHTML = [
    controlRow('Ground-truth readiness', truth.problems?.[0] || 'Generation authority and user sign-off', truth.errors ? `${truth.errors} ERROR` : truth.ready ? 'READY' : 'REVIEW', truth.errors ? 'bad' : truth.ready ? 'good' : 'warn'),
    controlRow('Exact submission binding', 'JD + sent files + manifest', exact, k.exact_submissions === k.application_denominator ? 'good' : 'warn'),
    controlRow('Portal-answer evidence', 'Knockout and eligibility questions', screening, screeningAccounted === k.application_denominator ? 'good' : 'warn'),
    controlRow('Response dates', 'Exact date, never inferred', dates, k.response_dates === k.outcome_denominator ? 'good' : 'warn'),
    controlRow('Timing evidence', 'User-reported or exact timing band', timing, k.timing_bands === k.outcome_denominator ? 'good' : 'warn'),
  ].join('');
  $('#truth-foot').innerHTML = `<strong>${truth.active_records} active facts</strong> · ${truth.sources} registered sources · ${truth.decisions} governed decisions${k.small_sample ? '<br><span style="color:var(--amber)">Small or employer-concentrated sample: do not infer causes.</span>' : ''}`;
  const orb = $('#health-orb');
  orb.className = `health-orb${truth.errors ? ' danger' : (!truth.ready || truth.warnings ? ' warning' : '')}`;
}

function filterCounts() {
  const jobs = state.data.jobs;
  return {
    all: jobs.length,
    in_progress: jobs.filter(x => ['captured', 'review', 'approved', 'applied'].includes(x.phase)).length,
    applied: jobs.filter(x => x.phase === 'applied').length,
    progressed: jobs.filter(x => x.phase === 'progressed').length,
    rejected: jobs.filter(x => x.phase === 'rejected').length,
  };
}

function renderFilters() {
  const counts = filterCounts();
  $$('.filter-chip').forEach(button => {
    button.classList.toggle('active', button.dataset.filter === state.filter);
    $('span', button).textContent = counts[button.dataset.filter] || 0;
  });
}

function filteredJobs() {
  const query = state.search.trim().toLowerCase();
  return state.data.jobs.filter(job => {
    const filterMatch = state.filter === 'all'
      || (state.filter === 'in_progress' && ['captured', 'review', 'approved', 'applied'].includes(job.phase))
      || job.phase === state.filter;
    const haystack = `${job.company} ${job.role} ${job.reference} ${job.id}`.toLowerCase();
    return filterMatch && (!query || haystack.includes(query));
  });
}

function renderJobs() {
  const jobs = filteredJobs();
  $('#result-count').textContent = `${jobs.length} ${jobs.length === 1 ? 'job' : 'jobs'}`;
  if (!jobs.length) {
    $('#job-ledger').innerHTML = '<div class="empty-state"><strong>No applications match this view.</strong><span>Change the filter or search term.</span></div>';
    return;
  }
  $('#job-ledger').innerHTML = `
    <div class="ledger-header" aria-hidden="true"><span>Company and role</span><span>State</span><span>Evidence</span><span>Outputs</span><span>Next action</span><span></span></div>
    ${jobs.map(jobRow).join('')}`;
  $$('.job-row').forEach(button => button.addEventListener('click', () => openDrawer(jobById(button.dataset.job), button)));
}

function jobRow(job) {
  const coverage = job.coverage === null || job.coverage === undefined ? null : Math.round(job.coverage * 100);
  const timing = latencyLabel(job.response_latency?.band || 'unknown');
  return `<button class="job-row" type="button" data-job="${h(job.id)}" aria-label="Open ${h(job.company)} ${h(job.role)}">
    <span class="job-primary"><span class="company-avatar">${h(companyInitials(job.company))}</span><span><strong>${h(job.company)}</strong><small>${h(job.role)} · Ref ${h(job.reference)}</small></span></span>
    <span class="status-cell"><span class="cell-label">State</span><span class="status-badge" data-phase="${h(job.phase)}">${h(phaseLabel(job.phase))}</span></span>
    <span class="coverage-cell"><span class="mini-track"><span style="width:${coverage ?? 0}%"></span></span><b>${coverage === null ? '—' : `${coverage}%`}</b></span>
    <span class="artifact-cell">${job.output_count}/4<small>key outputs</small></span>
    <span class="action-cell">${h(job.next_action)}</span>
    <span class="row-arrow">${icons.arrow}</span>
    <span class="timing-cell" hidden>${h(timing)}<small>${h(job.response_latency?.basis || '')}</small></span>
  </button>`;
}

function renderAttention() {
  const items = state.data.attention;
  $('#attention-count').textContent = items.length;
  $('#attention-list').innerHTML = items.length ? items.map((item, index) => `
    <button class="attention-item" type="button" data-attention="${index}" data-severity="${h(item.severity)}" aria-label="${h(item.cta)}: ${h(item.title)} for ${h(item.company)}">
      <span class="attention-mark" aria-hidden="true"></span><span class="attention-copy"><strong>${h(item.title)}</strong><small>${h(item.company)} · ${h(item.role)}</small><p>${h(item.detail)}</p></span><span class="attention-cta">${h(item.cta)} ${icons.arrow}</span>
    </button>`).join('') : '<div class="empty-state"><strong>Nothing needs your input.</strong><span>Submitted work remains visible in the ledger without becoming a false task.</span></div>';
  $$('.attention-item').forEach(button => button.addEventListener('click', () => {
    const item = state.data.attention[Number(button.dataset.attention)];
    if (item) handleAttention(item, button);
  }));
}

function handleAttention(item, source) {
  if (item.route === 'truth_integrity') {
    state.truthIntegrityDetail = item.detail;
    $('#truth-integrity-detail').textContent = item.detail;
    $('#truth-integrity-dialog').showModal();
    return;
  }
  const job = jobById(item.job_id);
  if (!job) return;
  if (item.route === 'submission_metadata') {
    populateSubmissionUpdate(job); openDialog('#update-submission-dialog', job); return;
  }
  if (item.route === 'outcome') {
    populateOutcome(job); openDialog('#outcome-dialog', job); return;
  }
  if (item.route === 'submission') {
    populateSubmission(job); openDialog('#submission-dialog', job); return;
  }
  if (item.route === 'feedback') {
    populateFeedbackResolution(job); openDialog('#resolve-feedback-dialog', job); return;
  }
  if (item.route === 'codex_prepare') {
    if (state.session?.agent?.available) {
      openAgent(job);
      startAgentTurn('Continue the governed pre-generation review for this exact JD. Ask only material questions, preserve any recorded answer, and stop before planning or drafting.', 'intake_review');
    }
    else openDrawer(job, source);
    return;
  }
  if (item.route === 'codex_outcome') {
    if (state.session?.agent?.available) openAgent(job, 'Review this observed state and help me with the next evidence-backed decision. Keep facts, hypotheses and unknowns separate.');
    else { openDrawer(job, source); state.tab = 'reasoning'; renderDrawer(); }
    return;
  }
  openDrawer(job, source);
  if (item.route === 'review_bundle') state.tab = 'review';
  if (item.route === 'artifacts') state.tab = 'artifacts';
  renderDrawer();
}

function renderLearning() {
  const lessons = state.data.lessons;
  $('#learning-list').innerHTML = lessons.length ? lessons.map(item => `
    <article class="learning-item">
      <div class="learning-head"><strong>${h(item.cause_label)}</strong><span class="evidence-support">${Math.round((item.confidence || 0) * 100)}%</span></div>
      <p>${h(item.summary)}</p><div class="learning-bar"><span style="width:${Math.round((item.confidence || 0) * 100)}%"></span></div>
      <div class="learning-source"><span>${h(item.company)} · ${h(item.role)}</span><span>${h(item.id)}</span></div>
    </article>`).join('') : '<div class="empty-state"><strong>No retained lessons yet.</strong><span>Observed outcomes never become causal claims automatically.</span></div>';
}

function openDrawer(job, source) {
  if (!job) return;
  state.selectedJob = job;
  state.tab = 'overview';
  state.lastFocus = source || document.activeElement;
  const drawer = $('#job-drawer');
  $('#drawer-backdrop').hidden = false;
  drawer.hidden = false;
  document.body.style.overflow = 'hidden';
  renderDrawer();
  requestAnimationFrame(() => { drawer.classList.add('open'); $('#drawer-close').focus(); });
}

function closeDrawer() {
  const drawer = $('#job-drawer');
  drawer.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => { drawer.hidden = true; $('#drawer-backdrop').hidden = true; }, 280);
  state.selectedJob = null;
  state.lastFocus?.focus?.();
}

function artifactBy(job, predicate) {
  return job.artifacts.find(predicate);
}

function renderDrawer() {
  const job = state.selectedJob;
  if (!job) return;
  $('#drawer-phase').dataset.phase = job.phase;
  $('#drawer-phase').textContent = phaseLabel(job.phase);
  $('#drawer-company').textContent = job.company;
  $('#drawer-title').textContent = job.role;
  $('#drawer-meta').textContent = `Reference ${job.reference} · ${job.id}`;
  $('#drawer-next-action').innerHTML = `<span>Next useful action</span><strong>${h(job.next_action)}</strong>`;
  const sentCv = artifactBy(job, x => x.sent && x.label.startsWith('CV ·'));
  const sentLetter = artifactBy(job, x => x.sent && x.label.startsWith('Cover letter'));
  const caseFile = artifactBy(job, x => x.label === 'Decision case');
  const official = safeUrl(job.official_url);
  $('#drawer-actions').innerHTML = [
    official ? `<a class="action-link primary" href="${h(official)}" target="_blank" rel="noreferrer">Official advert ${icons.external}</a>` : '',
    `<button class="action-link" type="button" data-drawer-action="codex"><span class="agent-orb"></span>Work with Codex</button>`,
    job.workflow?.can_review ? `<button class="action-link" type="button" data-drawer-action="review">Review complete bundle</button>` : '',
    `<button class="action-link" type="button" data-drawer-action="feedback">Add feedback</button>`,
    job.workflow?.can_approve ? `<button class="action-link" type="button" data-drawer-action="approve">Approve & build</button>` : '',
    job.workflow?.can_submit ? `<button class="action-link" type="button" data-drawer-action="submit">Submission desk</button>` : '',
    job.exact_submission ? `<button class="action-link" type="button" data-drawer-action="update-submission">Update dates & portal evidence</button>` : '',
    job.workflow?.can_record_outcome ? `<button class="action-link" type="button" data-drawer-action="outcome">Record / update outcome</button>` : '',
    sentCv?.href ? `<a class="action-link" href="${h(sentCv.href)}" target="_blank">Exact sent CV ${icons.file}</a>` : '',
    sentLetter?.href ? `<a class="action-link" href="${h(sentLetter.href)}" target="_blank">Exact sent letter ${icons.file}</a>` : '',
    caseFile?.href ? `<a class="action-link" href="${h(caseFile.href)}" target="_blank">Decision case ${icons.link}</a>` : '',
  ].filter(Boolean).join('');
  $$('#drawer-tabs button').forEach(button => button.classList.toggle('active', button.dataset.tab === state.tab));
  renderDrawerContent();
}

function fact(label, value, tone = '') {
  return `<div class="fact-card"><span>${h(label)}</span><strong class="${tone}">${h(value)}</strong></div>`;
}

function renderDrawerContent() {
  const job = state.selectedJob;
  if (state.tab === 'review') {
    $('#drawer-content').innerHTML = '<div class="empty-state"><span class="loader"></span><strong>Loading the exact current bundle…</strong></div>';
    loadReview(job);
    return;
  }
  const renderers = {overview: drawerOverview, artifacts: drawerArtifacts, evidence: drawerEvidence, feedback: drawerFeedback, reasoning: drawerReasoning, timeline: drawerTimeline};
  $('#drawer-content').innerHTML = renderers[state.tab](job);
}

function drawerOverview(job) {
  const outputNames = Object.entries(job.outputs).map(([key, value]) => `${value ? '✓' : '—'} ${titleCase(key)}`).join(' · ');
  const workflow = job.workflow || {};
  const workflowSteps = [
    ['JD', workflow.captured], ['Questions', workflow.preflight], ['Plan', workflow.plan],
    ['Review', workflow.presentation], ['Approved', workflow.approval],
    ['Built', workflow.package], ['Submitted', workflow.submission],
  ];
  return `<section class="drawer-section">
    <div class="drawer-section-title"><h3>Application journey</h3><span class="subtle">One gate at a time</span></div>
    <div class="workflow-track">${workflowSteps.map(([label, done]) => `<div class="workflow-step ${done ? 'done' : ''}">${h(label)}</div>`).join('')}</div>
  </section>
  <section class="drawer-section">
    <div class="drawer-section-title"><h3>Observed record</h3></div>
    <div class="fact-grid">
      ${fact('Lifecycle state', phaseLabel(job.phase), job.phase === 'rejected' ? 'bad' : job.phase === 'progressed' ? 'good' : '')}
      ${fact('Identity lane', titleCase(job.identity || 'Not selected'))}
      ${fact('Approved', dateLabel(job.approved_at))}
      ${fact('Applied', dateLabel(job.applied_date), job.applied_date ? '' : 'warn')}
      ${fact('Responded', dateLabel(job.responded_date), job.responded_date ? '' : 'warn')}
      ${fact('Response timing', `${latencyLabel(job.response_latency?.band)} · ${titleCase(job.response_latency?.basis)}`)}
      ${fact('Submission correlation', job.exact_submission ? 'Exact bundle recorded' : 'Not established', job.exact_submission ? 'good' : 'warn')}
      ${fact('Portal answers', job.screening_status === 'captured' ? 'Captured' : job.screening_status === 'unavailable' ? 'Unavailable · recorded' : 'Not captured', job.screening_status === 'captured' ? 'good' : 'warn')}
    </div>
    <div class="disclaimer">Employer-stated reason: <strong>${h(job.employer_stated_reason || 'None provided')}</strong>. Hypotheses are shown separately and never relabelled as facts.</div>
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Output coverage</h3><span class="subtle">${job.output_count}/4 key groups</span></div>
    <div class="truth-foot" style="margin:0">${h(outputNames)}</div>
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Package integrity</h3></div>
    <div class="fact-grid">${fact('State', titleCase(job.integrity_state), job.integrity_state === 'attention' ? 'bad' : 'good')}${fact('Package', job.package_id || 'Not built')}</div>
    ${job.integrity_exceptions.length ? `<div class="unknown-box">${job.integrity_exceptions.map(h).join('<br>')}</div>` : ''}
  </section>`;
}

async function loadReview(job) {
  try {
    const response = await fetch(`/api/review?job=${encodeURIComponent(job.id)}`, {cache: 'no-store'});
    const review = await response.json();
    if (!review.available) {
      $('#drawer-content').innerHTML = `<div class="empty-state"><strong>No complete bundle is available yet.</strong><span>${h((review.errors || []).join(' · ') || 'Ask Codex to prepare the application first.')}</span><button class="primary-button" type="button" data-review-action="codex">Prepare with Codex</button></div>`;
      return;
    }
    $('#drawer-content').innerHTML = `<div class="review-toolbar"><span>${review.valid ? 'Presentation is current and review-bound' : 'Read the complete bundle, then mark it presented'}</span>${review.valid ? '<button class="secondary-button" type="button" data-review-action="feedback">Add feedback</button>' : '<button class="primary-button" type="button" data-review-action="present">Mark complete bundle presented</button>'}</div><div class="review-sheet"><pre>${h(review.content)}</pre></div>`;
  } catch (error) {
    $('#drawer-content').innerHTML = `<div class="empty-state"><strong>Review could not be loaded.</strong><span>${h(error.message)}</span></div>`;
  }
}

function drawerArtifacts(job) {
  if (!job.artifacts.length) return '<div class="empty-state"><strong>No generated artefacts yet.</strong><span>The exact JD remains in the working record when captured.</span></div>';
  const groups = [...new Set(job.artifacts.map(x => x.group))];
  return groups.map(group => `<section class="artifact-group"><h3>${h(group)}</h3><div class="artifact-list">
    ${job.artifacts.filter(x => x.group === group).map(item => `<a class="artifact-row" href="${h(item.href || '#')}" ${item.href ? 'target="_blank"' : 'aria-disabled="true"'}>
      <span class="file-icon">${icons.file}</span><span><strong>${h(item.label)}${item.sent ? '<span class="sent-tag">SENT</span>' : ''}</strong><small>${h(item.filename)}${item.bytes ? ` · ${bytesLabel(item.bytes)}` : ''}</small></span>
      <span class="file-state ${item.state === 'digest_mismatch' ? 'mismatch' : ''}">${h(item.state.replaceAll('_', ' '))}</span>
    </a>`).join('')}
  </div></section>`).join('');
}

function drawerEvidence(job) {
  const spread = job.spread;
  const total = Math.max(1, spread.direct + spread.transferable + spread.partial + spread.gap);
  const bars = [['direct', spread.direct], ['transferable', spread.transferable], ['partial', spread.partial], ['gap', spread.gap]];
  const coverage = Math.round((job.coverage || 0) * 100);
  const reqs = [...job.requirements].sort((a, b) => {
    const rank = {GAP: 0, PARTIAL: 1, TRANSFERABLE: 2, DIRECT: 3};
    return (rank[a.match] ?? 9) - (rank[b.match] ?? 9);
  });
  const assessed = job.requirements.length > 0;
  return `<section class="drawer-section"><div class="drawer-section-title"><h3>Requirement coverage</h3></div>
    <div class="coverage-hero"><div class="coverage-ring" style="--value:${coverage}"><strong>${job.coverage === null || job.coverage === undefined ? '—' : `${coverage}%`}</strong></div>
      <div class="coverage-bars">${bars.map(([kind, value]) => `<div class="coverage-bar" data-kind="${kind}"><span>${titleCase(kind)}</span><span class="bar"><span style="width:${(value / total) * 100}%"></span></span><b>${value}</b></div>`).join('')}</div></div>
    <div class="disclaimer">${h(job.coverage_note)}</div>
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Gaps and mandatory risks</h3><span class="subtle">${assessed ? 'From the current evidence map' : 'Assessment has not run'}</span></div>
    <div class="fact-grid">
      ${fact('Unmatched requirements', assessed ? String(job.spread.gap) : 'Not assessed', assessed && job.spread.gap ? 'warn' : '')}
      ${fact('Hard-gate gaps', assessed ? String(job.hard_gaps.length) : 'Not assessed', assessed && job.hard_gaps.length ? 'bad' : '')}
      ${fact('Mandatory risks', assessed ? String(job.mandatory_risks.length) : 'Not assessed', assessed && job.mandatory_risks.length ? 'warn' : '')}
    </div>
    ${job.hard_gaps.length ? `<div class="unknown-box"><strong>Hard-gate gaps</strong><br>${job.hard_gaps.map(h).join('<br>')}</div>` : ''}
    ${job.mandatory_risks.length ? `<div class="unknown-box"><strong>Mandatory risks</strong><br>${job.mandatory_risks.map(h).join('<br>')}</div>` : ''}
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Mapped requirements</h3><span class="subtle">${reqs.length} recorded</span></div>
    <div class="requirement-list">${reqs.length ? reqs.map(req => `<article class="requirement-item"><header><span>#${h(req.n || '—')}${req.hard_gate ? ' · HARD GATE' : ''}</span><span class="match-chip ${String(req.match || '').toLowerCase()}">${h(req.match || 'UNASSESSED')}</span></header>${h(req.text)}</article>`).join('') : '<div class="empty-state"><strong>No current match record.</strong></div>'}</div>
  </section>`;
}

function drawerFeedback(job) {
  const items = job.feedback_items || [];
  return `<section class="drawer-section">
    <div class="drawer-section-title"><h3>Application comments</h3><button class="secondary-button" type="button" data-review-action="feedback">Add comment</button></div>
    <div class="disclaimer">Comments are governed review items. Open comments block approval; adopted or rejected decisions remain visible.</div>
    <div class="feedback-history">${items.length ? items.map(item => `<article class="feedback-card">
      <header><strong>${h(item.id)} · ${h(titleCase(item.scope))}</strong><span class="reason-status ${String(item.status || '').toLowerCase()}">${h(titleCase(item.status))}</span></header>
      <p>${h(item.note)}</p><small>Opened ${h(dateTimeLabel(item.opened_at))}${item.author ? ` · ${h(item.author)}` : ''}</small>
      ${item.implementation ? `<div class="feedback-resolution"><strong>Decision</strong><span>${h(item.implementation)}</span><strong>Validation</strong><span>${h(item.validation || 'Not recorded')}</span></div>` : ''}
    </article>`).join('') : '<div class="empty-state"><strong>No comments recorded.</strong><span>Add feedback here; it will remain attached to this exact application.</span></div>'}</div>
  </section>`;
}

function evidenceList(values, empty) {
  return values.length ? `<ul>${values.map(value => `<li>${h(value)}</li>`).join('')}</ul>` : `<span class="subtle">${h(empty)}</span>`;
}

function drawerReasoning(job) {
  const observation = job.phase === 'rejected'
    ? `Rejected · ${latencyLabel(job.response_latency?.band)} (${titleCase(job.response_latency?.basis)})`
    : phaseLabel(job.phase);
  return `<section class="drawer-section"><div class="drawer-section-title"><h3>Observed outcome</h3></div>
    <div class="outcome-observation"><strong>${h(observation)}</strong><p>Employer-stated reason: ${h(job.employer_stated_reason || 'none provided')}. This observation is separate from every explanation below.</p></div>
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Reasoning record</h3><span class="subtle">Support is evidential, not predictive</span></div>
    ${job.hypotheses.length ? job.hypotheses.map(item => `<article class="reason-card">
      <div class="reason-card-head"><div><strong>${h(item.id)} · ${h(item.cause_label)}</strong><div class="reason-meta">${item.revision_count} reasoning ${item.revision_count === 1 ? 'pass' : 'passes'} · ${Math.round((item.confidence || 0) * 100)}% evidence support</div></div><span class="reason-status ${String(item.status || '').toLowerCase()}">${h(titleCase(item.status))}</span></div>
      <p class="reason-summary">${h(item.summary)}</p>
      <div class="reason-evidence"><div><h4>Evidence for</h4>${evidenceList(item.evidence_for, 'None recorded')}</div><div><h4>Counterevidence</h4>${evidenceList(item.evidence_against, 'None recorded')}</div></div>
      ${item.unknowns.length ? `<div class="unknown-box"><strong>Still unknown:</strong> ${item.unknowns.map(h).join(' · ')}</div>` : ''}
    </article>`).join('') : '<div class="empty-state"><strong>No hypotheses recorded.</strong><span>No cause has been invented.</span></div>'}
  </section>`;
}

function drawerTimeline(job) {
  return `<section class="drawer-section"><div class="drawer-section-title"><h3>Immutable event trail</h3><span class="subtle">Newest first</span></div>
    <div class="timeline">${job.timeline.length ? job.timeline.map(event => `<article class="timeline-event"><strong>${h(titleCase(event.event))}${event.hypothesis_id ? ` · ${h(event.hypothesis_id)}` : ''}</strong><small>${h(dateTimeLabel(event.at))}${event.status ? ` · ${h(titleCase(event.status))}` : ''}</small></article>`).join('') : '<div class="empty-state"><strong>No lifecycle events yet.</strong></div>'}</div>
  </section>`;
}

function openDialog(id, job = null) {
  const dialog = $(id);
  state.actionJob = job;
  $('.dialog-status', dialog).textContent = '';
  $('.dialog-status', dialog).className = 'dialog-status';
  dialog.showModal();
}

function setFormBusy(form, busy) {
  $$('button, input, textarea, select', form).forEach(node => { node.disabled = busy; });
}

function openAgent(job = null, prefill = '', intent = 'ask') {
  if (state.activeTask && ['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
    const activeJob = state.activeTask.job_id ? jobById(state.activeTask.job_id) : null;
    if ((job?.id || null) !== (state.activeTask.job_id || null)) {
      job = activeJob;
      toast('The active Codex turn remains in its original application context.');
    }
  }
  if (state.selectedJob) closeDrawer();
  state.agentJob = job;
  state.agentIntent = intent;
  $('#agent-title').textContent = job ? job.role : 'Work with Codex';
  $('#agent-context').textContent = job
    ? `${job.company} · Ref ${job.reference} · ${phaseLabel(job.phase)}`
    : 'Portfolio-level conversation';
  $('#agent-message').value = prefill;
  $('#agent-hint').textContent = intent === 'integrity_review'
    ? 'Bounded read-only diagnosis. No evidence will be changed.'
    : 'No approval or file generation is implied by a message.';
  renderAgentQuickActions();
  renderConversation();
  const panel = $('#agent-workspace');
  $('#agent-backdrop').hidden = false;
  panel.hidden = false;
  document.body.style.overflow = 'hidden';
  requestAnimationFrame(() => { panel.classList.add('open'); $('#agent-message').focus(); });
  loadSession().then(renderAgentState).catch(error => toast(error.message));
}

function closeAgent() {
  const panel = $('#agent-workspace');
  panel.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => { panel.hidden = true; $('#agent-backdrop').hidden = true; }, 280);
}

function renderAgentState() {
  const agent = state.session?.agent;
  const label = $('#agent-state');
  if (!agent?.available) {
    label.textContent = 'CODEX UNAVAILABLE';
    label.style.color = 'var(--amber)';
  } else if (state.activeTask && ['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
    const elapsed = turnDuration(state.activeTask);
    label.textContent = state.activeTask.status === 'waiting'
      ? 'YOUR APPROVAL NEEDED'
      : `CODEX WORKING${elapsed ? ` · ${elapsed}` : ''}`;
    label.style.color = state.activeTask.status === 'waiting' ? 'var(--amber)' : 'var(--cyan)';
  } else if (state.activeTask?.status === 'failed') {
    label.textContent = 'CODEX TURN INTERRUPTED';
    label.style.color = 'var(--amber)';
  } else {
    const last = state.activeTask?.duration_ms ?? agent?.performance?.last_duration_ms;
    label.textContent = `CODEX READY${last !== null && last !== undefined ? ` · last ${durationLabel(last)}` : ''}`;
    label.style.color = 'var(--green)';
  }
}

function durationLabel(milliseconds) {
  const seconds = Math.max(0, Number(milliseconds || 0) / 1000);
  return seconds < 10 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`;
}

function turnDuration(task) {
  if (task?.duration_ms !== null && task?.duration_ms !== undefined) return durationLabel(task.duration_ms);
  const started = Date.parse(task?.created_at || '');
  return Number.isFinite(started) ? durationLabel(Date.now() - started) : '';
}

function renderAgentQuickActions() {
  const job = state.agentJob;
  const actions = job ? [
    ['workspace', 'Open application workspace'],
    job.workflow?.preflight
      ? ['prepare', 'Prepare / update application']
      : ['preflight', 'Continue pre-generation review'],
    ['feedback', 'Discuss an improvement'],
    ['submission', 'Submission help'],
    ['outcome', 'Reason about an outcome'],
  ] : [['portfolio', 'What needs attention?'], ['new', 'Start a new application']];
  $('#agent-quick-actions').innerHTML = actions.map(([action, label]) => `<button class="quick-action" type="button" data-agent-action="${action}">${h(label)}</button>`).join('');
}

function renderConversation() {
  const root = $('#conversation');
  const messages = agentMessages();
  const welcome = '<div class="agent-welcome"><strong>Guarded workspace</strong><span>Candidate facts remain governed. This job resumes its private Codex thread when available; approval and external submission stay explicit.</span></div>';
  const taskMatchesJob = (state.activeTask?.job_id || null) === (state.agentJob?.id || null);
  const interrupted = state.activeTask?.status === 'failed' && taskMatchesJob;
  const recovery = interrupted ? `<div class="turn-recovery" role="alert">
    <strong>Codex stopped before completing this turn.</strong>
    <span>Joblooper refreshed the governed files. Partial work is preserved only when it appears in this application's gates or artefacts; no approval or document build is assumed.</span>
    <code>${h(turnFailureLabel(state.activeTask.error))}</code>
    <div><button class="primary-button" type="button" data-agent-recovery="resume">Resume safely</button>${state.agentJob ? '<button class="secondary-button" type="button" data-agent-recovery="workspace">Open application</button>' : ''}</div>
  </div>` : '';
  root.innerHTML = welcome + messages.map(message => `<div class="message ${message.role}${message.streaming ? ' streaming' : ''}${message.failed ? ' failed' : ''}"><span>${h(message.text || (message.streaming ? 'Thinking' : ''))}</span>${message.duration_ms !== undefined ? `<small class="turn-metrics">${h(durationLabel(message.duration_ms))} · ${h(message.scope || 'proportional')} · ${h(message.work_items || 0)} work items</small>` : ''}</div>`).join('') + recovery;
  const scroll = $('.agent-scroll');
  scroll.scrollTop = scroll.scrollHeight;
}

function turnFailureLabel(error) {
  const text = String(error || '').trim();
  if (/stream disconnected before completion/i.test(text)) {
    return 'Connection to Codex ended before a completed response was received.';
  }
  if (/task returned 404|dashboard instance changed|dashboard was replaced/i.test(text)) {
    return 'The dashboard was updated while this turn was running; its live task status is no longer available.';
  }
  return text || 'No completed response was received.';
}

function agentMessages() {
  const key = state.agentJob?.id || 'portfolio';
  if (!state.agentConversations[key]) state.agentConversations[key] = [];
  return state.agentConversations[key];
}

function composerIntent(message) {
  if (state.agentIntent && state.agentIntent !== 'ask') return state.agentIntent;
  return state.agentJob ? 'auto' : 'ask';
}

async function startAgentTurn(message, intent = 'ask') {
  message = String(message || '').trim();
  if (!message) return;
  if (state.activeTask && ['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
    toast('Finish or cancel the current Codex turn first.');
    return;
  }
  const messages = agentMessages();
  state.agentIntent = 'ask';
  messages.push({role: 'user', text: message});
  messages.push({role: 'agent', text: '', streaming: true});
  renderConversation();
  $('#agent-message').value = '';
  try {
    const result = await apiPost('/api/agent/turn', {
      job_id: state.agentJob?.id || null,
      intent,
      message,
    });
    state.activeTask = result.task;
    renderAgentState();
    renderActiveWorkspace();
    pollAgentTask();
    return true;
  } catch (error) {
    const answer = messages[messages.length - 1];
    answer.text = turnFailureLabel(error.message);
    answer.streaming = false;
    answer.failed = true;
    state.activeTask = {
      id: null, job_id: state.agentJob?.id || null, intent, user: message,
      status: 'failed', error: error.message, duration_ms: 0,
      scope: 'turn start', work_items: 0,
    };
    renderConversation();
    renderAgentState();
    renderActiveWorkspace();
    toast(error.message);
    return false;
  }
}

function openManualIntake(message) {
  const dialog = $('#intake-dialog');
  const manual = $('#manual-intake');
  const form = $('#intake-form');
  manual.open = true;
  $('#intake-status').textContent = message;
  $('#intake-status').classList.remove('good');
  if (!$('#agent-workspace').hidden) closeAgent();
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => {
    const target = ['company', 'title', 'jd']
      .map(name => form.elements[name])
      .find(field => !String(field.value || '').trim());
    target?.focus();
  });
}

async function pollAgentTask() {
  clearTimeout(state.taskPoller);
  if (!state.activeTask) return;
  try {
    const response = await fetch(`/api/agent/task?id=${encodeURIComponent(state.activeTask.id)}`, {cache: 'no-store'});
    if (response.status === 404) {
      await markAgentInterrupted('The dashboard was replaced while this Codex turn was running.');
      return;
    }
    if (!response.ok) throw new Error(`Agent task returned ${response.status}`);
    state.taskPollFailures = 0;
    state.activeTask = await response.json();
    renderActiveWorkspace();
    const answer = [...agentMessages()].reverse().find(message => message.role === 'agent' && message.streaming);
    if (answer) {
      if (state.activeTask.status === 'failed') {
        const partial = String(state.activeTask.assistant || '').trim();
        answer.text = partial && !/codexErrorInfo|stream disconnected before completion/i.test(partial)
          ? `Partial response before interruption:\n\n${partial}`
          : 'No completed response was received. Check the recovered application state below.';
        answer.failed = true;
      } else {
        answer.text = state.activeTask.assistant || (state.activeTask.status === 'waiting' ? 'Waiting for your decision.' : 'Thinking');
      }
      answer.streaming = ['starting', 'running', 'waiting'].includes(state.activeTask.status);
      if (!['starting', 'running', 'waiting'].includes(state.activeTask.status)
          && state.activeTask.duration_ms !== undefined) {
        answer.duration_ms = state.activeTask.duration_ms;
        answer.scope = state.activeTask.scope;
        answer.work_items = state.activeTask.work_items;
      }
    }
    renderConversation();
    renderPendingRequest();
    renderAgentState();
    if (['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
      state.taskPoller = setTimeout(pollAgentTask, 850);
    } else {
      const completedIntent = state.activeTask.intent;
      const intakeBaseline = state.intakeBaseline;
      await loadData();
      await loadSession();
      renderAgentState();
      renderConversation();
      if (completedIntent === 'intake_url' && intakeBaseline) {
        const captured = state.data.jobs.filter(job => !intakeBaseline.includes(job.id));
        if (captured.length === 1) {
          $('#intake-form').reset();
          toast(`Captured ${captured[0].company} · ${captured[0].role}.`);
          state.intakeBaseline = null;
          state.agentJob = captured[0];
          $('#agent-title').textContent = captured[0].role;
          $('#agent-context').textContent = `${captured[0].company} · Ref ${captured[0].reference} · ${phaseLabel(captured[0].phase)}`;
          renderAgentQuickActions();
          renderConversation();
          await startAgentTurn('Inspect the newly captured exact JD. Run only the governed preflight, identify material questions or hard gates, and explain the next decision. Do not plan, draft, approve or build yet.', 'intake_review');
          return;
        } else {
          openManualIntake(
            'The official page could not be captured. Paste the company, exact title and complete advert below.');
        }
        state.intakeBaseline = null;
      }
    }
  } catch (error) {
    state.taskPollFailures += 1;
    if (state.taskPollFailures >= 3) {
      await markAgentInterrupted(error.message);
      return;
    }
    toast(`Reconnecting to the active Codex turn (${state.taskPollFailures}/3)…`);
    state.taskPoller = setTimeout(pollAgentTask, 1800);
  }
}

async function markAgentInterrupted(error) {
  clearTimeout(state.taskPoller);
  const previous = state.activeTask || {};
  state.activeTask = {...previous, status: 'failed', error,
    duration_ms: previous.duration_ms ?? 0};
  const answer = [...agentMessages()].reverse().find(
    message => message.role === 'agent' && message.streaming);
  if (answer) {
    answer.text = 'No completed response was received. Joblooper refreshed the durable application state.';
    answer.streaming = false;
    answer.failed = true;
  }
  await loadData();
  try { await loadSession(); } catch { /* recovery remains available from governed files */ }
  renderConversation();
  renderAgentState();
  renderActiveWorkspace();
}

function resumeInterruptedTurn() {
  const failed = state.activeTask;
  if (!failed || failed.status !== 'failed') return;
  const original = String(failed.user || '').trim();
  const intent = failed.intent || 'ask';
  startAgentTurn(
    'Resume safely after the interrupted turn. Re-read the current governed job state first. Preserve completed durable work, repeat no completed mutation, and continue only from the next incomplete gate. Do not infer approval or document generation from the failed turn.\n\nOriginal request:\n' + original,
    intent);
}

function renderPendingRequest() {
  const root = $('#pending-request');
  const pending = state.activeTask?.pending;
  if (!pending) { root.hidden = true; root.innerHTML = ''; return; }
  root.hidden = false;
  if (pending.kind === 'questions') {
    root.innerHTML = `<h3>Codex needs your input</h3><form id="agent-question-form">${pending.questions.map(question => `<label class="question-field">${h(question.question)}<input name="${h(question.id)}" required></label>`).join('')}<div class="pending-actions"><button class="primary-button" type="submit">Answer and continue</button><button class="secondary-button" type="button" data-pending-decision="cancel">Cancel turn</button></div></form>`;
    return;
  }
  const title = pending.kind === 'command' ? 'Command approval required' : 'File-change approval required';
  root.innerHTML = `<h3>${title}</h3><p>${h(pending.reason || 'Codex requested permission for this operation.')}</p>${pending.command ? `<pre>${h(pending.command)}</pre>` : ''}<div class="pending-actions"><button class="primary-button" type="button" data-pending-decision="accept">Allow once</button><button class="secondary-button" type="button" data-pending-decision="decline">Decline</button><button class="secondary-button" type="button" data-pending-decision="cancel">Cancel turn</button></div>`;
}

async function respondToAgent(decision = null, answers = null) {
  if (!state.activeTask) return;
  try {
    const result = await apiPost('/api/agent/respond', {
      task_id: state.activeTask.id, decision, answers,
    });
    state.activeTask = result.task;
    renderPendingRequest();
    pollAgentTask();
  } catch (error) { toast(error.message); }
}

function agentQuickAction(action) {
  const job = state.agentJob;
  if (action === 'new') { closeAgent(); $('#intake-dialog').showModal(); return; }
  if (action === 'workspace' && job) {
    closeAgent(); openDrawer(job); return;
  }
  if (action === 'preflight' && job) {
    startAgentTurn('Continue the governed pre-generation review for this exact JD. Ask only material questions, preserve any recorded answer, and stop before planning or drafting.', 'intake_review');
    return;
  }
  if (action === 'portfolio') {
    startAgentTurn('Audit the current portfolio attention items. Tell me only what needs a decision now, what can wait, and which observations must remain unknown.', 'ask');
  } else if (action === 'prepare') {
    startAgentTurn('Prepare or update this application through the permitted pipeline. Check ground-truth readiness and preflight first. Ask me any material unanswered questions and stop for my answer. When ready, generate and present the complete CV and cover letter in this dashboard. Do not approve or build files.', 'prepare_application');
  } else if (action === 'feedback') {
    $('#agent-message').value = 'I want to improve this application. Assess this feedback against the JD and ground truth before anything is changed: ';
    $('#agent-message').focus();
  } else if (action === 'submission') {
    if (job?.workflow?.can_submit) openDialog('#submission-dialog', job);
    else startAgentTurn('Check whether this application is ready for submission. Identify the exact sendable CV and cover letter and any missing portal-evidence control. Do not claim that an external portal was submitted.', 'submission_help');
  } else if (action === 'outcome') {
    startAgentTurn('Review the observed outcome and current reasoning record. Separate employer facts, retained best guesses, alternatives and unknowns. Do not promise that the true cause can be discovered.', 'outcome_review');
  }
}

function filePayload(file) {
  if (!file || !file.size) return Promise.resolve(null);
  if (file.size > 8 * 1024 * 1024) return Promise.reject(new Error('Screening evidence exceeds the 8 MB limit.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name: file.name, base64: String(reader.result).split(',', 2)[1] || ''});
    reader.onerror = () => reject(new Error('Screening evidence could not be read.'));
    reader.readAsDataURL(file);
  });
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('joblooper-theme', theme);
}

function populateSubmission(job) {
  const form = $('#submission-form');
  const cv = job.artifacts.filter(item => ['manifest-pdf', 'manifest-docx'].includes(item.id) && item.href);
  const letters = job.artifacts.filter(item => ['manifest-letter_pdf', 'manifest-letter_docx'].includes(item.id) && item.href);
  form.elements.cv_artifact_id.innerHTML = cv.map(item => `<option value="${h(item.id)}">${h(item.label)} · ${h(item.state)}</option>`).join('');
  form.elements.letter_artifact_id.innerHTML = '<option value="">Not submitted</option>' + letters.map(item => `<option value="${h(item.id)}">${h(item.label)} · ${h(item.state)}</option>`).join('');
  if (!cv.length) $('#submission-status').textContent = 'No verified approved CV is available.';
}

function ensureSelectValue(select, value) {
  if (!value) return;
  if (![...select.options].some(option => option.value === value)) {
    select.add(new Option(titleCase(value), value));
  }
  select.value = value;
}

function populateSubmissionUpdate(job) {
  const form = $('#update-submission-form');
  form.reset();
  form.elements.applied_date.value = job.applied_date || '';
  ensureSelectValue(form.elements.channel, job.channel || 'portal');
  const captured = job.screening_status === 'captured';
  const unavailable = job.screening_status === 'unavailable';
  form.elements.screening_file.disabled = captured || unavailable;
  form.elements.screening_unavailable.disabled = captured;
  form.elements.screening_unavailable.checked = unavailable;
  $('#update-submission-bundle').innerHTML = `<strong>Immutable sent bundle</strong><br>CV: ${h(job.sent_file || 'not recorded')}<br>Cover letter: ${h(job.sent_cover_letter || 'not submitted')}<br>Portal answers: ${h(captured ? 'exact evidence captured' : unavailable ? 'unavailable — explicitly recorded' : 'not captured')}`;
}

function populateFeedbackResolution(job) {
  const form = $('#resolve-feedback-form');
  form.reset();
  const items = job.open_feedback || [];
  form.elements.feedback_id.innerHTML = items.map(item =>
    `<option value="${h(item.id)}">${h(item.id)} · ${h(titleCase(item.scope))}</option>`
  ).join('');
  const renderItem = () => {
    const item = items.find(row => row.id === form.elements.feedback_id.value);
    $('#feedback-item-detail').innerHTML = item
      ? `<strong>${h(item.id)} · ${h(titleCase(item.scope))}</strong><br>${h(item.note)}`
      : '<strong>No open feedback remains.</strong>';
  };
  form.elements.feedback_id.onchange = renderItem;
  renderItem();
}

function populateOutcome(job) {
  const form = $('#outcome-form');
  form.reset();
  const observed = ['rejected', 'interview', 'progressed', 'offer', 'ghosted', 'withdrawn']
    .includes(job.status) ? job.status : '';
  form.elements.status.value = observed;
  form.elements.response_date.value = job.responded_date || '';
  ensureSelectValue(form.elements.latency, job.response_latency?.band || 'unknown');
  form.elements.employer_reason.value = job.employer_stated_reason || '';
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#intake-status');
  const data = Object.fromEntries(new FormData(form));
  const manual = ['company', 'title', 'jd'].map(key => String(data[key] || '').trim());
  const hasManual = manual.some(Boolean);
  const completeManual = manual.every(Boolean);
  const url = String(data.url || '').trim();
  if (hasManual && !completeManual) {
    openManualIntake('Manual capture requires company, exact title and the complete advert.');
    return;
  }
  if (completeManual && url && !safeUrl(url)) {
    status.textContent = 'The optional reference URL must use public HTTP or HTTPS.';
    return;
  }
  if (!completeManual && !safeUrl(url)) {
    status.textContent = 'Paste a valid public HTTP or HTTPS job link.';
    return;
  }
  setFormBusy(form, true);
  status.textContent = completeManual
    ? 'Capturing the manually supplied exact advert…'
    : 'Opening the official link and extracting the complete advert…';
  try {
    const response = await apiPost(
      completeManual ? '/api/actions/ingest' : '/api/actions/ingest-url',
      completeManual ? data : {url});
    status.textContent = response.result.output;
    status.classList.add('good');
    await loadData();
    const job = jobById(response.result.job_id);
    form.reset();
    $('#intake-dialog').close();
    if (state.session?.agent?.available) {
      openAgent(job);
      await startAgentTurn('Inspect the newly captured exact JD. Run only the governed preflight, identify material questions or hard gates, and explain the next decision. Do not plan, draft, approve or build yet.', 'intake_review');
    } else {
      openDrawer(job);
      toast('Exact job captured. Codex is unavailable, so no contextual review was started.');
    }
  } catch (error) {
    if (!completeManual && state.session?.agent?.available) {
      state.intakeBaseline = state.data.jobs.map(job => job.id);
      status.textContent = `Direct extraction was blocked. Handing the official link to Codex…`;
      $('#intake-dialog').close();
      openAgent(null);
      const started = await startAgentTurn(
        `Capture a new application from this exact official URL: ${url}\n\n` +
        `The bounded direct extractor reported: ${error.message}\n\n` +
        'Try to access the exact official page. If and only if the full employer name, exact job title and complete job description are available, run the governed Joblooper ingest command with this URL, then stop before planning. If the page remains blocked or incomplete, explicitly tell me that it cannot be captured and ask me to use the manual-paste fallback. Do not reconstruct the advert from search snippets or infer missing content.',
        'intake_url');
      if (!started) {
        state.intakeBaseline = null;
        openManualIntake(
          'The official page could not be captured. Paste the company, exact title and complete advert below.');
      }
    } else {
      openManualIntake(`${error.message} Paste the complete advert below.`);
    }
  } finally { setFormBusy(form, false); }
}

async function submitFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#feedback-status');
  const data = Object.fromEntries(new FormData(form));
  setFormBusy(form, true);
  status.textContent = 'Recording governed feedback…';
  try {
    await apiPost('/api/actions/feedback', {
      job_id: state.actionJob.id, scope: data.scope, note: data.note,
      author: 'dashboard-user',
    });
    form.reset();
    $('#feedback-dialog').close();
    await loadData();
    toast('Feedback recorded. Old presentation and approval are now stale.');
  } catch (error) { status.textContent = error.message; }
  finally { setFormBusy(form, false); }
}

async function submitFeedbackResolution(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#resolve-feedback-status');
  const data = Object.fromEntries(new FormData(form));
  setFormBusy(form, true);
  status.textContent = 'Validating and appending the feedback decision…';
  try {
    const result = await apiPost('/api/actions/resolve-feedback', {
      job_id: state.actionJob.id, feedback_id: data.feedback_id,
      status: data.status, implementation: data.implementation,
      validation: data.validation,
    });
    status.textContent = result.result.output;
    status.classList.add('good');
    const jobId = state.actionJob.id;
    await loadData();
    setTimeout(() => {
      form.reset();
      $('#resolve-feedback-dialog').close();
      toast('Feedback decision recorded; review the refreshed bundle before approval.');
      const job = jobById(jobId);
      if (job) { openDrawer(job); state.tab = 'review'; renderDrawer(); }
    }, 700);
  } catch (error) { status.textContent = error.message; }
  finally { setFormBusy(form, false); }
}

async function submitApproval(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#approval-status');
  const data = Object.fromEntries(new FormData(form));
  setFormBusy(form, true);
  status.textContent = 'Running approval, document and package gates…';
  try {
    const result = await apiPost('/api/actions/approve-build', {
      job_id: state.actionJob.id, reviewer: data.reviewer,
      confirmation: data.confirmed ? 'I reviewed the complete CV and cover letter' : '',
      no_pdf: Boolean(data.no_pdf),
    });
    status.textContent = result.result.output;
    status.classList.add('good');
    await loadData();
    setTimeout(() => { form.reset(); $('#approval-dialog').close(); }, 900);
  } catch (error) { status.textContent = error.message; }
  finally { setFormBusy(form, false); }
}

async function submitSubmission(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#submission-status');
  const data = Object.fromEntries(new FormData(form));
  if (!data.confirmed) { status.textContent = 'Confirm that these exact files were uploaded.'; return; }
  setFormBusy(form, true);
  status.textContent = 'Binding the exact submitted bundle…';
  try {
    const screening = await filePayload(form.elements.screening_file.files[0]);
    const result = await apiPost('/api/actions/submit', {
      job_id: state.actionJob.id,
      cv_artifact_id: data.cv_artifact_id,
      letter_artifact_id: data.letter_artifact_id || null,
      channel: data.channel,
      applied_date: data.applied_date || null,
      screening,
    });
    status.textContent = result.result.output;
    status.classList.add('good');
    await loadData();
    setTimeout(() => { form.reset(); $('#submission-dialog').close(); }, 900);
  } catch (error) { status.textContent = error.message; }
  finally { setFormBusy(form, false); }
}

async function submitSubmissionUpdate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#update-submission-status');
  const data = Object.fromEntries(new FormData(form));
  const file = form.elements.screening_file.files[0];
  if (file && data.screening_unavailable) {
    status.textContent = 'Attach portal answers or mark them unavailable, not both.';
    return;
  }
  setFormBusy(form, true);
  status.textContent = 'Verifying the exact submission and appending this correction…';
  try {
    const screening = await filePayload(file);
    const result = await apiPost('/api/actions/update-submission', {
      job_id: state.actionJob.id,
      applied_date: data.applied_date || null,
      channel: data.channel || null,
      screening,
      screening_unavailable: Boolean(data.screening_unavailable),
    });
    status.textContent = result.result.output;
    status.classList.add('good');
    const jobId = state.actionJob.id;
    await loadData();
    setTimeout(() => {
      form.reset();
      $('#update-submission-dialog').close();
      toast('Application record updated; the exact sent files were unchanged.');
      const job = jobById(jobId);
      if (job) openDrawer(job);
    }, 700);
  } catch (error) { status.textContent = error.message; }
  finally {
    setFormBusy(form, false);
    const current = state.actionJob && jobById(state.actionJob.id);
    const captured = current?.screening_status === 'captured';
    const unavailable = current?.screening_status === 'unavailable'
      || form.elements.screening_unavailable.checked;
    form.elements.screening_file.disabled = captured || unavailable;
    form.elements.screening_unavailable.disabled = captured;
  }
}

async function submitOutcome(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('#outcome-status');
  const data = Object.fromEntries(new FormData(form));
  if (String(data.response_text || '').trim() && !data.response_date) {
    status.textContent = 'Give the response date when preserving exact employer text.';
    return;
  }
  setFormBusy(form, true);
  status.textContent = 'Correlating the observation to the exact submitted application…';
  try {
    const result = await apiPost('/api/actions/outcome', {
      job_id: state.actionJob.id,
      status: data.status,
      response_date: data.response_date || null,
      latency: data.latency || 'unknown',
      employer_reason: data.employer_reason || null,
      response_text: data.response_text || null,
    });
    status.textContent = result.result.output;
    status.classList.add('good');
    const jobId = state.actionJob.id;
    await loadData();
    setTimeout(() => {
      form.reset();
      $('#outcome-dialog').close();
      toast('Outcome recorded as an observation. Rejection explanations remain best guesses.');
      const job = jobById(jobId);
      if (job) openDrawer(job);
    }, 900);
  } catch (error) { status.textContent = error.message; }
  finally { setFormBusy(form, false); }
}

function trapFocus(event, root) {
  const focusable = $$('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])', root)
    .filter(node => !node.hasAttribute('aria-disabled'));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
}

function handleActiveAction(event) {
  const control = event.target.closest('[data-active-action]');
  if (!control) return;
  const action = control.dataset.activeAction;
  if (action === 'new') { $('#intake-dialog').showModal(); return; }
  const job = jobById(control.dataset.job);
  if (!job) return;
  if (action === 'active-turn') { openAgent(job); return; }
  if (action === 'codex') {
    if (state.session?.agent?.available) {
      openAgent(job);
      startAgentTurn('Continue the governed pre-generation review for this exact JD. Ask only material questions, preserve any recorded answer, and stop before planning or drafting.', 'intake_review');
    } else {
      openDrawer(job, control);
      toast('Codex is unavailable. The captured job and artefacts remain accessible.');
    }
    return;
  }
  if (action === 'submit') { populateSubmission(job); openDialog('#submission-dialog', job); return; }
  openDrawer(job, control);
  if (['artifacts', 'review', 'evidence', 'feedback'].includes(action)) state.tab = action;
  renderDrawer();
}

function wireEvents() {
  $('#refresh-button').addEventListener('click', () => loadData(true));
  $('#theme-button').addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  $('#new-job-button').addEventListener('click', () => $('#intake-dialog').showModal());
  $('#active-job-list').addEventListener('click', handleActiveAction);
  $('#primary-action').addEventListener('click', event => {
    const actions = state.data?.attention || [];
    const action = actions.find(x => ['critical', 'action'].includes(x.severity)) || actions[0];
    if (action) handleAttention(action, event.currentTarget);
  });
  $('#agent-button').addEventListener('click', () => openAgent(null));
  $('#global-search').addEventListener('input', event => { state.search = event.target.value; renderJobs(); });
  $('#filter-row').addEventListener('click', event => {
    const button = event.target.closest('.filter-chip');
    if (!button) return;
    state.filter = button.dataset.filter;
    renderFilters(); renderJobs();
  });
  $('#drawer-close').addEventListener('click', closeDrawer);
  $('#drawer-backdrop').addEventListener('click', closeDrawer);
  $('#drawer-tabs').addEventListener('click', event => {
    const button = event.target.closest('button[data-tab]');
    if (!button) return;
    state.tab = button.dataset.tab;
    renderDrawer();
  });
  $('#drawer-actions').addEventListener('click', event => {
    const button = event.target.closest('[data-drawer-action]');
    if (!button || !state.selectedJob) return;
    const job = state.selectedJob;
    if (button.dataset.drawerAction === 'codex') openAgent(job);
    if (button.dataset.drawerAction === 'review') { state.tab = 'review'; renderDrawer(); }
    if (button.dataset.drawerAction === 'feedback') openDialog('#feedback-dialog', job);
    if (button.dataset.drawerAction === 'approve') openDialog('#approval-dialog', job);
    if (button.dataset.drawerAction === 'submit') { populateSubmission(job); openDialog('#submission-dialog', job); }
    if (button.dataset.drawerAction === 'update-submission') { populateSubmissionUpdate(job); openDialog('#update-submission-dialog', job); }
    if (button.dataset.drawerAction === 'outcome') { populateOutcome(job); openDialog('#outcome-dialog', job); }
  });
  $('#drawer-content').addEventListener('click', event => {
    if (event.target.closest('[aria-disabled="true"]')) event.preventDefault();
    const action = event.target.closest('[data-review-action]')?.dataset.reviewAction;
    if (!action || !state.selectedJob) return;
    if (action === 'codex') openAgent(state.selectedJob);
    if (action === 'feedback') openDialog('#feedback-dialog', state.selectedJob);
    if (action === 'present') {
      const button = event.target.closest('button');
      button.disabled = true;
      apiPost('/api/actions/present', {job_id: state.selectedJob.id})
        .then(async () => { await loadData(); state.tab = 'review'; renderDrawer(); toast('Complete bundle is now bound to this review.'); })
        .catch(error => { toast(error.message); button.disabled = false; });
    }
  });
  $('#agent-close').addEventListener('click', closeAgent);
  $('#agent-backdrop').addEventListener('click', closeAgent);
  $('#agent-form').addEventListener('submit', event => {
    event.preventDefault();
    const message = $('#agent-message').value;
    startAgentTurn(message, composerIntent(message));
  });
  $('#conversation').addEventListener('click', event => {
    const action = event.target.closest('[data-agent-recovery]')?.dataset.agentRecovery;
    if (action === 'resume') resumeInterruptedTurn();
    if (action === 'workspace' && state.agentJob) { closeAgent(); openDrawer(state.agentJob); }
  });
  $('#truth-integrity-codex').addEventListener('click', () => {
    $('#truth-integrity-dialog').close();
    openAgent(
      null,
      `Explain this exact deterministic ground-truth integrity failure and the safe user choices: ${state.truthIntegrityDetail}`,
      'integrity_review');
  });
  $('#agent-quick-actions').addEventListener('click', event => {
    const action = event.target.closest('[data-agent-action]')?.dataset.agentAction;
    if (action) agentQuickAction(action);
  });
  $('#pending-request').addEventListener('click', event => {
    const decision = event.target.closest('[data-pending-decision]')?.dataset.pendingDecision;
    if (decision) respondToAgent(decision);
  });
  $('#pending-request').addEventListener('submit', event => {
    if (event.target.id !== 'agent-question-form') return;
    event.preventDefault();
    respondToAgent(null, Object.fromEntries(new FormData(event.target)));
  });
  $$('.dialog-close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  $('#intake-form').addEventListener('submit', submitIntake);
  $('#feedback-form').addEventListener('submit', submitFeedback);
  $('#resolve-feedback-form').addEventListener('submit', submitFeedbackResolution);
  $('#approval-form').addEventListener('submit', submitApproval);
  $('#submission-form').addEventListener('submit', submitSubmission);
  $('#update-submission-form').addEventListener('submit', submitSubmissionUpdate);
  $('#update-submission-form').elements.screening_unavailable.addEventListener('change', event => {
    const file = $('#update-submission-form').elements.screening_file;
    if (event.target.checked) file.value = '';
    file.disabled = event.target.checked;
  });
  $('#update-submission-form').elements.screening_file.addEventListener('change', event => {
    if (event.target.files.length) {
      $('#update-submission-form').elements.screening_unavailable.checked = false;
    }
  });
  $('#outcome-form').addEventListener('submit', submitOutcome);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.selectedJob) closeDrawer();
    if (event.key === 'Escape' && !$('#agent-workspace').hidden) closeAgent();
    if (event.key === 'Tab' && state.selectedJob) {
      trapFocus(event, $('#job-drawer'));
    } else if (event.key === 'Tab' && !$('#agent-workspace').hidden) {
      trapFocus(event, $('#agent-workspace'));
    }
    if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      event.preventDefault(); $('#global-search').focus();
    }
  });
}

const preferredTheme = localStorage.getItem('joblooper-theme')
  || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
setTheme(preferredTheme);
wireEvents();
async function bootstrap() {
  await Promise.all([loadSession(), loadData()]);
  const restoredRaw = sessionStorage.getItem('joblooper-dashboard-context');
  sessionStorage.removeItem('joblooper-dashboard-context');
  let restored = null;
  try { restored = restoredRaw ? JSON.parse(restoredRaw) : null; } catch { restored = null; }
  const restoredJob = restored?.job_id ? jobById(restored.job_id) : null;
  const params = new URLSearchParams(location.search);
  const job = params.get('job') ? jobById(params.get('job')) : null;
  if (restoredJob || restored?.message) {
    openAgent(restoredJob, restored?.message || '');
    toast('Dashboard updated. Your application context was restored.');
  } else if (params.get('new') === '1') $('#intake-dialog').showModal();
  else if (params.get('view') === 'agent') openAgent(job);
  else if (job) openDrawer(job);
  setInterval(monitorDashboardInstance, 4000);
}
bootstrap().catch(error => toast(error.message));
