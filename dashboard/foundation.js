/* Shared, side-effect-free UI primitives and governed display language. */
'use strict';

export const icons = {
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

export function h(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function titleCase(value) {
  return String(value || 'unknown').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function phaseLabel(value) {
  return ({captured: 'Captured', review: 'In review', approved: 'Approved', applied: 'Applied',
    progressed: 'Progressed', rejected: 'Rejected', closed: 'Closed'})[value] || titleCase(value);
}

export function ratio(value, denominator) {
  return denominator ? `${Math.round((value / denominator) * 100)}%` : '—';
}

export function dateLabel(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {day: '2-digit', month: 'short', year: 'numeric'}).format(date);
}

export function dateTimeLabel(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function bytesLabel(value) {
  if (value === null || value === undefined) return '';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function companyInitials(company) {
  return String(company || '?').split(/\s+/).filter(Boolean).slice(0, 2)
    .map(value => value[0]).join('').toUpperCase();
}

export function latencyLabel(value) {
  return ({under_24h: 'Under 24 hours', '1_3d': '1–3 days', '4_7d': '4–7 days',
    '8_30d': '8–30 days', over_30d: 'Over 30 days', unknown: 'Unknown'})[value]
    || titleCase(value);
}

export const truthDecisionLabels = {
  ADOPTED: 'Keep this fact',
  DUPLICATE: 'Already recorded',
  REJECTED: 'Leave it out',
  UNRESOLVED: 'Decide later',
};

export const eventLabels = {
  SUBMITTED: 'Application submitted',
  SUBMISSION_UPDATED: 'Application record updated',
  OUTCOME: 'Outcome recorded',
  OUTCOME_CORRECTED: 'Outcome corrected',
  HYPOTHESIS_ADDED: 'Possible reason added',
  HYPOTHESIS_REVISED: 'Possible reason reviewed again',
  LEARNING_CONFIRMED: 'Employer-confirmed reason saved',
  LEARNING_RETAINED_PLAUSIBLE: 'Useful lesson saved for later',
};

export function fileStateLabel(value) {
  return ({
    available: 'Available',
    verified: 'Checked and ready',
    missing: 'Missing',
    digest_mismatch: 'File changed since it was checked',
  })[value] || 'Needs checking';
}

export function eventLabel(value) {
  return eventLabels[value] || 'Application record updated';
}

export function decisionLabel(value) {
  return ({LEAVE_AS_IS: 'No CV change needed', IMPROVE: 'Supported improvement available',
    HISTORICAL_RECORD: 'Saved application decision',
    PENDING_REVIEW: 'Needs review', WITHDRAWN_PENDING_COMPLETE_ANALYSIS: 'Needs fresh analysis'})[value] || 'Needs review';
}

export function wasApplied(job) {
  return Boolean(job.exact_submission || (job.milestones_reached || []).includes('applied')
    || ['applied', 'progressed', 'rejected', 'closed'].includes(job.phase));
}

// Only a complete, unambiguous drafting command may skip contextual review.
// A request with corrections, questions or extra instructions belongs in chat.
export function isPreparationRequest(message) {
  return /^(?:please\s+)?(?:create|generate|make|prepare|draft|tailor|regenerate)\s+(?:(?:my|the|a)\s+)?(?:cv|resume|résumé|cover letter|cv\s*(?:and|&)\s*(?:cover\s+)?letter|application(?:\s+(?:documents|bundle))?)(?:\s+for\s+this\s+(?:job|role|application))?[.!]?$/i.test(String(message || '').trim());
}

export function isSubmissionReport(message) {
  return /^i(?:\s+have|'ve)?\s+(?:already\s+)?(?:applied(?:\s+(?:to|for)\s+this\s+(?:job|role))?|submitted\s+(?:my|the|this)\s+application)[.!]?$/i.test(String(message || '').trim());
}
