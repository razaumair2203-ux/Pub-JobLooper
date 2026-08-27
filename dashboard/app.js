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
  agentConversations: {},
  activeTask: null,
  taskPoller: null,
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
  state.session = await response.json();
  const button = $('#agent-button');
  button.disabled = !state.session.agent.available;
  button.title = state.session.agent.available
    ? 'Open the guarded Codex workspace'
    : 'Install or expose the Codex CLI to enable agent conversation';
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
  renderPrimaryAction();
  renderKpis();
  renderPipeline();
  renderControls();
  renderFilters();
  renderJobs();
  renderAttention();
  renderLearning();
}

function renderHeader() {
  const {truth, generated_at: generatedAt} = state.data;
  const pill = $('#truth-pill');
  pill.textContent = truth.errors ? 'TRUTH BLOCKED' : truth.ready ? 'TRUTH READY' : 'TRUTH NEEDS REVIEW';
  pill.style.color = truth.errors ? 'var(--red)' : truth.ready ? 'var(--green)' : 'var(--amber)';
  $('#last-refresh').textContent = `Refreshed ${dateTimeLabel(generatedAt)}`;
}

function renderPrimaryAction() {
  const actions = state.data.attention;
  const action = actions.find(x => ['critical', 'action'].includes(x.severity)) || actions[0];
  $('#primary-action').innerHTML = action
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
  if (item.route === 'codex_truth') {
    openAgent(null, `Inspect this exact ground-truth integrity failure and guide me to a safe resolution without silently trusting or changing evidence: ${item.detail}`);
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
    if (state.session?.agent?.available) openAgent(job);
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
  const renderers = {overview: drawerOverview, artifacts: drawerArtifacts, evidence: drawerEvidence, reasoning: drawerReasoning, timeline: drawerTimeline};
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
  return `<section class="drawer-section"><div class="drawer-section-title"><h3>Requirement coverage</h3></div>
    <div class="coverage-hero"><div class="coverage-ring" style="--value:${coverage}"><strong>${job.coverage === null || job.coverage === undefined ? '—' : `${coverage}%`}</strong></div>
      <div class="coverage-bars">${bars.map(([kind, value]) => `<div class="coverage-bar" data-kind="${kind}"><span>${titleCase(kind)}</span><span class="bar"><span style="width:${(value / total) * 100}%"></span></span><b>${value}</b></div>`).join('')}</div></div>
    <div class="disclaimer">${h(job.coverage_note)}</div>
  </section>
  <section class="drawer-section"><div class="drawer-section-title"><h3>Mapped requirements</h3><span class="subtle">${reqs.length} recorded</span></div>
    <div class="requirement-list">${reqs.length ? reqs.map(req => `<article class="requirement-item"><header><span>#${h(req.n || '—')}${req.hard_gate ? ' · HARD GATE' : ''}</span><span class="match-chip ${String(req.match || '').toLowerCase()}">${h(req.match || 'UNASSESSED')}</span></header>${h(req.text)}</article>`).join('') : '<div class="empty-state"><strong>No current match record.</strong></div>'}</div>
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

function openAgent(job = null, prefill = '') {
  if (state.activeTask && ['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
    const activeJob = state.activeTask.job_id ? jobById(state.activeTask.job_id) : null;
    if ((job?.id || null) !== (state.activeTask.job_id || null)) {
      job = activeJob;
      toast('The active Codex turn remains in its original application context.');
    }
  }
  if (state.selectedJob) closeDrawer();
  state.agentJob = job;
  $('#agent-title').textContent = job ? job.role : 'Work with Codex';
  $('#agent-context').textContent = job
    ? `${job.company} · Ref ${job.reference} · ${phaseLabel(job.phase)}`
    : 'Portfolio-level conversation';
  $('#agent-message').value = prefill;
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
    label.textContent = state.activeTask.status === 'waiting' ? 'YOUR APPROVAL NEEDED' : 'CODEX WORKING';
    label.style.color = state.activeTask.status === 'waiting' ? 'var(--amber)' : 'var(--cyan)';
  } else {
    label.textContent = 'CODEX READY';
    label.style.color = 'var(--green)';
  }
}

function renderAgentQuickActions() {
  const job = state.agentJob;
  const actions = job ? [
    ['prepare', 'Prepare / update application'],
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
  root.innerHTML = welcome + messages.map(message => `<div class="message ${message.role}${message.streaming ? ' streaming' : ''}">${h(message.text || (message.streaming ? 'Thinking' : ''))}</div>`).join('');
  const scroll = $('.agent-scroll');
  scroll.scrollTop = scroll.scrollHeight;
}

function agentMessages() {
  const key = state.agentJob?.id || 'portfolio';
  if (!state.agentConversations[key]) state.agentConversations[key] = [];
  return state.agentConversations[key];
}

async function startAgentTurn(message, intent = 'ask') {
  message = String(message || '').trim();
  if (!message) return;
  if (state.activeTask && ['starting', 'running', 'waiting'].includes(state.activeTask.status)) {
    toast('Finish or cancel the current Codex turn first.');
    return;
  }
  const messages = agentMessages();
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
    pollAgentTask();
  } catch (error) {
    const answer = messages[messages.length - 1];
    answer.text = error.message;
    answer.streaming = false;
    renderConversation();
    toast(error.message);
  }
}

async function pollAgentTask() {
  clearTimeout(state.taskPoller);
  if (!state.activeTask) return;
  try {
    const response = await fetch(`/api/agent/task?id=${encodeURIComponent(state.activeTask.id)}`, {cache: 'no-store'});
    if (!response.ok) throw new Error(`Agent task returned ${response.status}`);
    state.activeTask = await response.json();
    const answer = [...agentMessages()].reverse().find(message => message.role === 'agent' && message.streaming);
    if (answer) {
      answer.text = state.activeTask.assistant || (state.activeTask.status === 'waiting' ? 'Waiting for your decision.' : 'Thinking');
      answer.streaming = ['starting', 'running', 'waiting'].includes(state.activeTask.status);
      if (state.activeTask.status === 'failed') answer.text += `\n\n${state.activeTask.error || 'The Codex turn failed.'}`;
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
      if (completedIntent === 'intake_url' && intakeBaseline) {
        const captured = state.data.jobs.filter(job => !intakeBaseline.includes(job.id));
        if (captured.length === 1) {
          $('#intake-form').reset();
          toast(`Captured ${captured[0].company} · ${captured[0].role}.`);
        } else {
          $('#manual-intake').open = true;
          toast('The link was not captured. Manual paste remains available under New application.');
        }
        state.intakeBaseline = null;
      }
    }
  } catch (error) {
    toast(error.message);
    state.taskPoller = setTimeout(pollAgentTask, 1800);
  }
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
    $('#manual-intake').open = true;
    status.textContent = 'Manual capture requires company, exact title and the complete advert.';
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
      await startAgentTurn(
        `Capture a new application from this exact official URL: ${url}\n\n` +
        `The bounded direct extractor reported: ${error.message}\n\n` +
        'Try to access the exact official page. If and only if the full employer name, exact job title and complete job description are available, run the governed Joblooper ingest command with this URL, then stop before planning. If the page remains blocked or incomplete, explicitly tell me that it cannot be captured and ask me to use the manual-paste fallback. Do not reconstruct the advert from search snippets or infer missing content.',
        'intake_url');
    } else {
      $('#manual-intake').open = true;
      status.textContent = `${error.message} Paste the complete advert in the manual fallback.`;
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

function wireEvents() {
  $('#refresh-button').addEventListener('click', () => loadData(true));
  $('#theme-button').addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  $('#new-job-button').addEventListener('click', () => $('#intake-dialog').showModal());
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
    startAgentTurn($('#agent-message').value, 'ask');
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
  const params = new URLSearchParams(location.search);
  const job = params.get('job') ? jobById(params.get('job')) : null;
  if (params.get('new') === '1') $('#intake-dialog').showModal();
  else if (params.get('view') === 'agent') openAgent(job);
  else if (job) openDrawer(job);
}
bootstrap().catch(error => toast(error.message));
