"""Local governed workspace for the Joblooper application lifecycle.

The dashboard reads the same flat files as the CLI and routes every mutation
through an allowlisted CLI action. It has no parallel database and never lets
the browser invent paths, candidate facts, approvals or employer causes.
"""
import json
import mimetypes
import os
import re
import secrets
import subprocess
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import (codex_bridge, dashboard_actions, dashboard_runtime, feedback,
               integrity, learning, preflight, release, store, truth_review)


STATIC_ROOT = store.code_p('dashboard')
CAUSE_LABELS = {
    'HARD_GATE': 'Direct requirement',
    'SENIORITY_MISMATCH': 'Seniority alignment',
    'DOMAIN_TRANSLATION': 'Domain translation',
    'ATS_KEYWORD': 'ATS / wording',
    'EVIDENCE_DEPTH': 'Evidence depth',
    'NARRATIVE_COHERENCE': 'Narrative coherence',
    'LOCATION_VISA': 'Location / eligibility',
    'COMPENSATION': 'Compensation',
    'TIMING_INTERNAL': 'Process / timing',
    'NO_SIGNAL': 'No reliable signal',
}
ATTENTION_ROUTES = frozenset({
    'artifacts', 'codex_outcome', 'codex_prepare', 'feedback', 'outcome',
    'review_bundle', 'submission', 'submission_metadata',
    'truth_integrity',
})
ARTIFACT_LABELS = {
    'pdf': ('CV · submitted format', 'Application'),
    'docx': ('CV · editable', 'Application'),
    'letter_pdf': ('Cover letter · submitted format', 'Application'),
    'letter_docx': ('Cover letter · editable', 'Application'),
    'jd_raw': ('Job description · captured', 'Source'),
    'jd': ('Job description · structured', 'Source'),
    'match': ('Requirement evidence map', 'Evidence'),
    'cv': ('CV · structured record', 'Evidence'),
    'letter': ('Cover letter · structured record', 'Evidence'),
    'ats': ('CV · ATS text', 'Evidence'),
    'letter_ats': ('Cover letter · ATS text', 'Evidence'),
    'preview': ('Evidence review', 'Evidence'),
    'risk': ('Employer-risk record', 'Evidence'),
    'risk_markdown': ('Employer-risk review', 'Evidence'),
    'employer_context': ('Employer context', 'Evidence'),
    'audit': ('Gate audit', 'Governance'),
    'approval': ('Approval record', 'Governance'),
    'presentation': ('Chat presentation receipt', 'Governance'),
    'feedback': ('Feedback snapshot', 'Governance'),
    'oversight': ('Oversight review', 'Governance'),
    'source_manifest': ('Source manifest', 'Governance'),
    'markdown': ('CV · Markdown', 'Working output'),
    'letter_markdown': ('Cover letter · Markdown', 'Working output'),
}
RECORD_ARTIFACTS = {
    'manifest': ('MANIFEST.json', 'Package manifest', 'Governance'),
    'submission': ('SUBMISSION.json', 'Submission receipt', 'Outcome'),
    'responses': ('RESPONSES.jsonl', 'Employer responses', 'Outcome'),
    'outcome': ('OUTCOME.json', 'Outcome record', 'Outcome'),
    'case': ('CASE.md', 'Decision case', 'Outcome'),
    'reasoning': ('REASONING.jsonl', 'Reasoning history', 'Outcome'),
    'status': ('STATUS.md', 'Application status and links', 'Governance'),
}
WORK_ARTIFACTS = {
    'job_description': ('jd.raw.md', 'Job description · captured', 'Source'),
    'jd_record': ('jd.json', 'Job description · structured', 'Source'),
    'match_record': ('match.json', 'Requirement evidence map', 'Evidence'),
    'preview': ('PREVIEW.md', 'Evidence review', 'Evidence'),
    'risk_review': ('EMPLOYER-RISK.md', 'Employer-risk review', 'Evidence'),
    'oversight': ('OVERSIGHT.md', 'Oversight review', 'Governance'),
    'case': ('CASE.md', 'Decision case', 'Outcome'),
    'outcome': ('outcome.json', 'Outcome record', 'Outcome'),
}


def _normalise_status(value):
    return str(value or '').strip().lower().replace(' ', '_')


def _work_state(directory):
    text = store.read_text(os.path.join(directory, 'STATUS.md'))
    match = re.search(r'^#\s+(.+?)\s*$', text, re.MULTILINE)
    return _normalise_status(match.group(1)) if match else 'captured'


def _phase(slug, app, package, work_state):
    status = _normalise_status((app or {}).get('status'))
    if status in learning.NEGATIVE_OUTCOMES:
        return 'rejected'
    if status in learning.POSITIVE_OUTCOMES:
        return 'progressed'
    if status == 'withdrawn':
        return 'closed'
    if status == 'applied':
        return 'applied'
    if app:
        return status or 'applied'
    if package and release.has_record_file(package, release.SUBMISSION_NAME):
        return 'applied'
    if package:
        return 'approved'
    if work_state in {'presented', 'planned', 'review', 'reviewed'}:
        return 'review'
    return 'captured'


def _next_action(phase, app, work_state):
    hypotheses = (app or {}).get('hypotheses') or []
    if phase == 'rejected':
        retained = [row for row in hypotheses
                    if row.get('status') in {'RETAINED_PLAUSIBLE', 'CONFIRMED'}]
        open_rows = [row for row in hypotheses if row.get('status') == 'OPEN']
        if retained:
            return ('Use the retained best guess in future preflight; '
                    'leave unresolved alternatives unknown')
        if open_rows:
            return ('No cause is established; keep current explanations as '
                    'unverified best guesses')
        return 'Record competing best guesses without claiming an employer reason'
    if phase == 'progressed':
        return 'Prepare for the next employer stage; preserve the exact observation'
    if phase == 'closed':
        return 'No action · retained for traceability'
    if phase == 'applied':
        return 'Await response and preserve all employer communication'
    if phase == 'approved':
        return 'Submit the exact approved bundle and capture portal answers'
    if phase == 'review':
        if work_state == 'presented':
            return 'Review the complete CV and cover letter in chat, then sign off'
        return 'Present the complete CV and cover letter in chat'
    return 'Run preflight and create the evidence plan'


def _artifact_state(path, expected_sha=None):
    if not path or not os.path.isfile(path):
        return 'missing'
    if expected_sha and store.sha256_file(path) != expected_sha:
        return 'digest_mismatch'
    return 'verified' if expected_sha else 'available'


def _artifact_entry(slug, artifact_id, label, group, path, expected_sha=None,
                    sent=False):
    state = _artifact_state(path, expected_sha)
    return {
        'id': artifact_id,
        'label': label,
        'group': group,
        'filename': os.path.basename(path) if path else None,
        'bytes': os.path.getsize(path) if path and os.path.isfile(path) else None,
        'state': state,
        'sent': bool(sent),
        'href': ('/artifact?job=' + urllib.parse.quote(slug)
                 + '&id=' + urllib.parse.quote(artifact_id)) if state != 'missing' else None,
        '_path': os.path.abspath(path) if path else None,
    }


def _artifacts(slug, directory, package, manifest, submission):
    rows = []
    seen = set()
    files = (manifest or {}).get('files') or {}
    sent_files = {submission.get('sent_file'), submission.get('sent_cover_letter')}
    if package:
        for key, info in files.items():
            relative = info.get('file')
            if not relative:
                continue
            path = os.path.abspath(os.path.join(package, relative))
            label, group = ARTIFACT_LABELS.get(
                key, (key.replace('_', ' ').title(), 'Other'))
            rows.append(_artifact_entry(
                slug, 'manifest-' + key, label, group, path, info.get('sha256'),
                relative in sent_files))
            seen.add(path.casefold())

        record = release.record_dir(package)
        for key, (filename, label, group) in RECORD_ARTIFACTS.items():
            path = os.path.abspath(os.path.join(record, filename))
            if path.casefold() in seen or not os.path.isfile(path):
                continue
            rows.append(_artifact_entry(slug, 'record-' + key, label, group, path))
            seen.add(path.casefold())
        if record and os.path.isdir(record):
            for filename in sorted(os.listdir(record)):
                if not filename.upper().startswith('SCREENING-ANSWERS'):
                    continue
                path = os.path.abspath(os.path.join(record, filename))
                if path.casefold() not in seen:
                    rows.append(_artifact_entry(
                        slug, 'record-screening', 'Portal screening answers',
                        'Outcome', path))
                    seen.add(path.casefold())

    for key, (filename, label, group) in WORK_ARTIFACTS.items():
        path = os.path.abspath(os.path.join(directory, filename))
        if path.casefold() in seen or not os.path.isfile(path):
            continue
        rows.append(_artifact_entry(slug, 'work-' + key, label, group, path))
        seen.add(path.casefold())
    rows.sort(key=lambda row: (
        ['Application', 'Source', 'Evidence', 'Outcome', 'Governance',
         'Working output', 'Other'].index(row['group'])
        if row['group'] in {'Application', 'Source', 'Evidence', 'Outcome',
                            'Governance', 'Working output', 'Other'} else 99,
        row['label']))
    return rows


def _hypotheses(app):
    rows = []
    for item in (app or {}).get('hypotheses') or []:
        revisions = item.get('revisions') or []
        latest = revisions[-1] if revisions else {}
        rows.append({
            'id': item.get('id'),
            'cause': item.get('cause'),
            'cause_label': CAUSE_LABELS.get(
                item.get('cause'), str(item.get('cause') or '').replace('_', ' ').title()),
            'status': item.get('status'),
            'confidence': item.get('confidence'),
            'summary': item.get('summary'),
            'revision_count': len(revisions),
            'stage': latest.get('stage'),
            'updated_at': item.get('updated_at'),
            'evidence_for': latest.get('evidence_for') or [],
            'evidence_against': latest.get('evidence_against') or [],
            'unknowns': latest.get('unknowns') or [],
            'company_context': latest.get('company_context') or [],
            'profile_factors': latest.get('profile_factors') or [],
            'other_factors': latest.get('other_factors') or [],
        })
    order = {'RETAINED_PLAUSIBLE': 0, 'CONFIRMED': 0, 'OPEN': 1, 'DISMISSED': 2}
    return sorted(rows, key=lambda row: (
        order.get(row.get('status'), 9), -(row.get('confidence') or 0)))


def _job_snapshot(slug, applications, events):
    directory = store.job_dir(slug)
    jd = store.read_json(os.path.join(directory, 'jd.json'), {}) or {}
    match = store.read_json(os.path.join(directory, 'match.json'), {}) or {}
    approval = store.read_json(os.path.join(directory, 'approval.json'), {}) or {}
    app = applications.get(slug)
    package, manifest = release.load_release(slug)
    submission = (store.read_json(
        release.record_path(package, release.SUBMISSION_NAME), {})
        if package else {}) or {}
    work_state = _work_state(directory)
    phase = _phase(slug, app, package, work_state)
    artifacts = _artifacts(slug, directory, package, manifest, submission)
    hypotheses = _hypotheses(app)

    package_errors = release.verify_release(slug)[1] if package else []
    submission_receipt, submission_errors = (
        release.verify_submission(slug) if app and package else (None, []))
    if submission and not app:
        submission_errors = [
            *submission_errors,
            'application ledger record is missing for the exact submission receipt',
        ]
    exact_submission = learning._exact_submission(app or {})
    exact_submitted_history = bool(
        app and exact_submission and submission_receipt and not submission_errors)
    if submission_receipt and not submission_errors:
        integrity_state = ('submission_verified_with_exception'
                           if package_errors else 'verified')
    elif package_errors or submission_errors:
        integrity_state = 'attention'
    elif package:
        integrity_state = 'verified'
    else:
        integrity_state = 'not_packaged'

    spread = match.get('spread') or {}
    reqs = []
    for row in match.get('requirements') or []:
        reqs.append({
            'n': row.get('n'), 'text': row.get('text'),
            'match': row.get('match'), 'hard_gate': bool(row.get('hard_gate')),
            'best': row.get('best'),
        })
    correlated_ids = {slug, *(jd.get('_legacy_slugs') or [])}
    timeline = []
    for event in events:
        if event.get('app_id') not in correlated_ids:
            continue
        timeline.append({
            'id': event.get('event_id'), 'at': event.get('timestamp'),
            'event': event.get('event'), 'status': event.get('status'),
            'hypothesis_id': event.get('hypothesis_id'),
            'cause': event.get('cause'),
        })
    timeline.sort(key=lambda row: str(row.get('at') or ''), reverse=True)

    retained_count = sum(row['status'] in {'RETAINED_PLAUSIBLE', 'CONFIRMED'}
                         for row in hypotheses)
    open_count = sum(row['status'] == 'OPEN' for row in hypotheses)
    open_feedback = [row for row in feedback.current(slug)
                     if row.get('status') == 'OPEN']
    plan_available = all(os.path.isfile(os.path.join(directory, name)) for name in (
        'match.json', 'cv.json', 'cover-letter.json', 'employer-risk.json'))
    preflight_record = store.read_json(os.path.join(directory, 'preflight.json'), {}) or {}
    preflight_errors = []
    if plan_available:
        try:
            preflight_record, preflight_errors, _ = preflight.validate(
                slug, jd, match, match.get('identity') or {})
        except (OSError, ValueError, TypeError) as error:
            preflight_errors = [str(error)]
    elif not preflight_record:
        preflight_errors = ['pre-generation review has not been completed']
    presentation_record = None
    presentation_errors = []
    if plan_available:
        try:
            presentation_record, presentation_errors = release.validate_presentation(slug)
        except (OSError, ValueError, TypeError) as error:
            presentation_errors = [str(error)]
    approval_record = None
    approval_errors = []
    if os.path.isfile(os.path.join(directory, 'approval.json')):
        try:
            approval_record, approval_errors = release.validate_approval(slug)
        except (OSError, ValueError, TypeError) as error:
            approval_errors = [str(error)]
    key_outputs = {
        'jd': any(row['group'] == 'Source' for row in artifacts),
        'cv': any(row['label'].startswith('CV ·') for row in artifacts),
        'letter': any(row['label'].startswith('Cover letter') for row in artifacts),
        'case': any(row['label'] == 'Decision case' for row in artifacts),
    }
    output_count = sum(key_outputs.values())
    identity_value = match.get('identity') or (app or {}).get('identity')
    if isinstance(identity_value, dict):
        identity_value = identity_value.get('primary')
    screening_status = ((app or {}).get('screening_evidence_status')
                        or ('captured' if (app or {}).get('screening_evidence')
                            else 'not_captured'))
    next_action = _next_action(phase, app, work_state)
    if not app:
        if preflight_errors:
            next_action = 'Complete or refresh the material pre-generation questions'
        elif open_feedback:
            next_action = 'Resolve governed feedback before approval'
        elif plan_available and presentation_errors:
            next_action = 'Review and bind the complete current CV and cover letter'
        elif presentation_record and not presentation_errors and approval_errors:
            next_action = 'Resolve the approval gate against the current presentation'
    return {
        'id': slug,
        'company': jd.get('company') or (app or {}).get('company') or 'Unknown company',
        'role': jd.get('title') or (app or {}).get('role') or 'Unknown role',
        'reference': jd.get('job_reference') or 'Not recorded',
        'official_url': jd.get('url'),
        'phase': phase,
        'source_state': work_state,
        'next_action': next_action,
        'identity': identity_value,
        'coverage': match.get('coverage'),
        'coverage_note': 'Local evidence coverage heuristic · not an ATS or hiring score',
        'spread': {
            'direct': spread.get('DIRECT', 0),
            'transferable': spread.get('TRANSFERABLE', 0),
            'partial': spread.get('PARTIAL', 0),
            'gap': spread.get('GAP', 0),
        },
        'requirements': reqs,
        'hard_gaps': match.get('hard_gate_gaps') or [],
        'mandatory_risks': match.get('mandatory_risks') or [],
        'approved_at': approval.get('approved_at') or (manifest or {}).get('approved_at'),
        'applied_date': (app or {}).get('applied'),
        'responded_date': (app or {}).get('responded'),
        'response_latency': (app or {}).get('response_latency') or {
            'band': 'unknown', 'basis': 'not_provided'},
        'channel': (app or {}).get('channel'),
        'status': (app or {}).get('status'),
        'employer_stated_reason': (app or {}).get('stated_reason'),
        'hypotheses': hypotheses,
        'retained_count': retained_count,
        'open_hypothesis_count': open_count,
        'exact_submission': exact_submission,
        'screening_captured': bool((app or {}).get('screening_evidence')),
        'screening_status': screening_status,
        'sent_file': (app or {}).get('sent_file') or submission.get('sent_file'),
        'sent_cover_letter': ((app or {}).get('sent_cover_letter')
                              or submission.get('sent_cover_letter')),
        'integrity_state': integrity_state,
        'integrity_exceptions': sorted(set(
            package_errors + submission_errors
            + list((app or {}).get('submission_integrity_exceptions') or []))),
        'outputs': key_outputs,
        'output_count': output_count,
        'workflow': {
            'captured': bool(jd),
            'preflight': bool(exact_submitted_history
                              or (preflight_record and not preflight_errors)),
            'preflight_errors': preflight_errors,
            'plan': plan_available,
            'presentation': bool(exact_submitted_history
                                 or (presentation_record and not presentation_errors)),
            'presentation_errors': presentation_errors,
            'approval': bool(exact_submitted_history
                             or (approval_record and not approval_errors)),
            'approval_errors': approval_errors,
            'package': bool(package),
            'submission': bool(app),
            'open_feedback': len(open_feedback),
            'can_review': plan_available,
            'can_approve': bool(presentation_record and not presentation_errors
                                and not open_feedback),
            'can_submit': bool(package and not app and not submission),
            'can_record_outcome': bool(
                app and exact_submission and submission_receipt
                and not submission_errors),
        },
        'open_feedback': [{
            'id': row.get('id'), 'scope': row.get('scope'),
            'note': row.get('note'), 'opened_at': row.get('opened_at'),
        } for row in open_feedback],
        'artifacts': [{key: value for key, value in row.items() if key != '_path'}
                      for row in artifacts],
        '_artifacts': {row['id']: row for row in artifacts},
        'timeline': timeline[:30],
        'package_id': (manifest or {}).get('package_id'),
        'manifest_sha256': (manifest or {}).get('manifest_sha256'),
    }


def build_snapshot(include_private=False):
    """Build the dashboard projection and optional server-only artefact registry."""
    app_rows = [row for row in store.applications()
                if not row.get('test_record') and not row.get('exclude_from_analytics')]
    applications = {row.get('app_id'): row for row in app_rows}
    events = store.application_events()
    jobs = [_job_snapshot(slug, applications, events) for slug in store.list_jobs()]
    jobs.sort(key=lambda row: (
        {'review': 0, 'captured': 1, 'approved': 2, 'applied': 3,
         'progressed': 4, 'rejected': 5, 'closed': 6}.get(row['phase'], 9),
        row['company'].casefold(), row['role'].casefold()))

    outcomes = [row for row in app_rows if row.get('status') not in {None, 'applied'}]
    positive = [row for row in outcomes
                if row.get('status') in learning.POSITIVE_OUTCOMES]
    negative = [row for row in outcomes
                if row.get('status') in learning.NEGATIVE_OUTCOMES]
    exact = sum(learning._exact_submission(row) for row in app_rows)
    screening = sum(bool(row.get('screening_evidence')) for row in app_rows)
    screening_unavailable = sum(
        row.get('screening_evidence_status') == 'unavailable' for row in app_rows)
    response_dates = sum(bool(row.get('responded')) for row in outcomes)
    timing_bands = sum(
        (row.get('response_latency') or {}).get('band') not in {None, 'unknown'}
        for row in outcomes)
    immediate = sum(
        (row.get('response_latency') or {}).get('band') == 'under_24h'
        for row in outcomes)
    phases = {name: sum(job['phase'] == name for job in jobs) for name in (
        'captured', 'review', 'approved', 'applied', 'progressed', 'rejected', 'closed')}
    milestones = {
        'captured': len(jobs),
        'reviewed': sum(bool(store.read_json(os.path.join(
            store.job_dir(job['id']), release.PRESENTATION_NAME), {}))
                        or job['phase'] in {'approved', 'applied', 'progressed', 'rejected', 'closed'}
                        for job in jobs),
        'approved': sum(bool(store.approved_dir(job['id'])) for job in jobs),
        'applied': len(app_rows),
        'progressed': len(positive),
        'rejected': len(negative),
    }

    try:
        truth = store.truth_context()
        truth_state = truth_review.readiness()
        truth_errors, truth_warnings, _ = integrity.check_truth()
        truth_problems = list(dict.fromkeys(
            list(truth_state.get('problems') or []) + list(truth_errors)))
        truth_data = {
            'ready': bool(truth_state.get('ready', False) and not truth_errors),
            'audit_due': truth_state.get('audit_due'),
            'audit_overdue': truth_state.get('audit_overdue', False),
            'records': (truth.get('stats') or {}).get('records', 0),
            'active_records': (truth.get('stats') or {}).get('active_records', 0),
            'sources': (truth.get('stats') or {}).get('sources', 0),
            'decisions': (truth.get('stats') or {}).get('changelog_entries', 0),
            'errors': len(truth_errors), 'warnings': len(truth_warnings),
            'problems': truth_problems,
            'integrity_errors': list(truth_errors),
            'integrity_warnings': list(truth_warnings),
        }
    except (OSError, ValueError, RuntimeError) as error:
        truth_data = {
            'ready': False, 'audit_due': None, 'audit_overdue': False,
            'records': 0, 'active_records': 0, 'sources': 0, 'decisions': 0,
            'errors': 1, 'warnings': 0, 'problems': [str(error)],
            'integrity_errors': [str(error)], 'integrity_warnings': [],
        }

    lessons = []
    for row in learning.confirmed_lessons():
        latest = (row.get('revisions') or [{}])[-1]
        lessons.append({
            'app_id': row.get('app_id'), 'company': row.get('company'),
            'role': row.get('role'), 'id': row.get('id'),
            'cause': row.get('cause'),
            'cause_label': CAUSE_LABELS.get(
                row.get('cause'), str(row.get('cause') or '').replace('_', ' ').title()),
            'status': row.get('status'), 'confidence': row.get('confidence'),
            'summary': row.get('summary'), 'updated_at': row.get('updated_at'),
            'unknowns': latest.get('unknowns') or [],
        })

    attention = []

    def add_attention(job, kind, title, detail, cta, route, severity='action'):
        if route not in ATTENTION_ROUTES:
            raise RuntimeError(f'unsupported dashboard attention route: {route}')
        attention.append({
            'id': f"{job['id']}:{kind}", 'job_id': job['id'],
            'company': job['company'], 'role': job['role'],
            'phase': job['phase'], 'severity': severity, 'kind': kind,
            'title': title, 'detail': detail, 'cta': cta, 'route': route,
            'action': title,
        })

    if truth_data['errors']:
        attention.append({
            'id': 'system:truth_integrity', 'job_id': None,
            'company': 'Ground truth', 'role': 'Candidate evidence',
            'phase': 'system', 'severity': 'critical',
            'kind': 'truth_integrity',
            'title': 'Resolve ground-truth integrity',
            'detail': truth_data['integrity_errors'][0],
            'cta': 'Review options', 'route': 'truth_integrity',
            'action': 'Resolve ground-truth integrity',
        })

    for job in jobs:
        workflow = job.get('workflow') or {}
        if job['integrity_state'] == 'attention':
            add_attention(
                job, 'integrity', 'Resolve package integrity errors',
                'Inspect the exact artefact and digest exceptions before doing anything else.',
                'Inspect', 'artifacts', 'critical')
            continue
        if workflow.get('open_feedback'):
            add_attention(
                job, 'feedback', 'Resolve open application feedback',
                'Current presentation and approval remain stale until the comment is resolved.',
                'Review feedback', 'feedback')
        elif job['phase'] == 'captured':
            add_attention(
                job, 'prepare', 'Complete the pre-generation review',
                'Answer only material questions before the CV or cover letter is planned.',
                'Continue', 'codex_prepare')
        elif job['phase'] == 'review':
            if workflow.get('can_approve'):
                add_attention(
                    job, 'approve', 'Sign off the complete current bundle',
                    'Approval binds the exact CV and cover letter shown in Review.',
                    'Review & approve', 'review_bundle')
            else:
                add_attention(
                    job, 'review', 'Review the complete CV and cover letter',
                    'Read every section and add feedback before any document is built.',
                    'Open review', 'review_bundle')
        elif job['phase'] == 'approved':
            add_attention(
                job, 'submit', 'Submit or record the approved bundle',
                'Use the exact verified CV and cover letter and preserve portal answers.',
                'Submission desk', 'submission')
        elif job['phase'] == 'progressed':
            add_attention(
                job, 'next_stage', 'Prepare for the observed next stage',
                'Keep the positive outcome factual and discuss only the next employer step.',
                'Work with Codex', 'codex_outcome', 'info')
        elif job['phase'] == 'rejected' and not job['retained_count']:
            add_attention(
                job, 'reasoning', 'Challenge plausible rejection explanations',
                'Keep employer facts, alternatives and unknowns separate; no cause is known.',
                'Discuss evidence', 'codex_outcome', 'info')

        if job.get('exact_submission') and job['integrity_state'] != 'attention':
            missing = []
            if not job.get('applied_date'):
                missing.append('submission date')
            if job.get('screening_status') == 'not_captured':
                missing.append('portal-answer status')
            if missing:
                add_attention(
                    job, 'submission_metadata',
                    'Complete the application record',
                    'Missing ' + ' and '.join(missing)
                    + '; add exact data or mark historical portal answers unavailable.',
                    'Update record', 'submission_metadata', 'warning')
        if job['phase'] in {'progressed', 'rejected'} and not job.get('responded_date'):
            add_attention(
                job, 'outcome_date', 'Add the observed response date',
                'Update the existing outcome; do not infer a date from when it was entered.',
                'Update outcome', 'outcome', 'warning')
    severity_rank = {'critical': 0, 'action': 1, 'warning': 2, 'info': 3}
    attention.sort(key=lambda row: (severity_rank.get(row['severity'], 9), row['company']))

    companies = {str(row.get('company') or '').strip().casefold() for row in app_rows}
    snapshot = {
        '_schema': 'joblooper.dashboard.v1',
        'generated_at': store.now(),
        'privacy': {
            'mode': 'LOCAL_ONLY', 'bind': '127.0.0.1',
            'repository_classification': store.read_repository_policy().get('classification'),
            'dashboard_analytics': False,
            'codex_processing': 'only_after_explicit_user_turn',
        },
        'truth': truth_data,
        'kpis': {
            'jobs': len(jobs),
            'in_progress': sum(phases[name] for name in ('captured', 'review', 'approved', 'applied')),
            'submitted': len(app_rows), 'progressed': len(positive),
            'rejected': len(negative), 'exact_submissions': exact,
            'screening_captured': screening,
            'screening_unavailable': screening_unavailable,
            'outcomes': len(outcomes),
            'response_dates': response_dates, 'timing_bands': timing_bands,
            'under_24h': immediate, 'retained_lessons': len(lessons),
            'application_denominator': len(app_rows),
            'outcome_denominator': len(outcomes),
            'small_sample': len(app_rows) < 10 or len(companies) < 3,
        },
        'phases': phases, 'milestones': milestones,
        'jobs': [{key: value for key, value in job.items() if key != '_artifacts'}
                 for job in jobs],
        'lessons': lessons, 'attention': attention,
    }
    if not include_private:
        return snapshot
    registry = {}
    for job in jobs:
        for artifact_id, artifact in job['_artifacts'].items():
            registry[(job['id'], artifact_id)] = artifact['_path']
    return snapshot, registry


def snapshot_json():
    return json.dumps(build_snapshot(), ensure_ascii=False, indent=2)


def _inside_data_root(path):
    try:
        root = os.path.abspath(store.DATA_ROOT)
        return os.path.commonpath([root, os.path.abspath(path)]) == root
    except (ValueError, TypeError):
        return False


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = 'JoblooperDashboard/1.0'

    def log_message(self, format_, *args):
        if getattr(self.server, 'quiet', False):
            return
        super().log_message(format_, *args)

    def _headers(self, status, content_type, length=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        if length is not None:
            self.send_header('Content-Length', str(length))
        self.end_headers()

    def _bytes(self, content, content_type, status=200):
        self._headers(status, content_type, len(content))
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _not_found(self):
        self._bytes(b'Not found', 'text/plain; charset=utf-8', 404)

    def _json(self, value, status=200):
        content = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self._bytes(content, 'application/json; charset=utf-8', status)

    def _read_json(self):
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Content-Type must be application/json')
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError as error:
            raise ValueError('Invalid Content-Length') from error
        if length <= 0 or length > 12000000:
            raise ValueError('Request body must be between 1 and 12,000,000 bytes')
        try:
            value = json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError('Request body must be valid UTF-8 JSON') from error
        if not isinstance(value, dict):
            raise ValueError('Request body must be a JSON object')
        return value

    def _authorised(self):
        host, port = self.server.server_address[:2]
        expected_origin = f'http://{host}:{port}'
        return (secrets.compare_digest(
                    self.headers.get('X-Joblooper-Token') or '',
                    self.server.session_token)
                and self.headers.get('Origin') == expected_origin)

    def _error(self, error, status=400):
        return self._json({'ok': False, 'error': str(error)}, status)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/health':
            return self._json(dashboard_runtime.health_payload(self.server))
        if parsed.path == '/api/dashboard':
            content = snapshot_json().encode('utf-8')
            return self._bytes(content, 'application/json; charset=utf-8')
        if parsed.path == '/api/session':
            return self._json({
                'csrf_token': self.server.session_token,
                'agent': self.server.codex_bridge.status(),
                'capabilities': {
                    'intake': True, 'url_intake': True, 'feedback': True, 'review': True,
                    'feedback_resolution': True, 'submission_update': True,
                    'approve_build': True, 'record_submission': True,
                    'record_outcome': True, 'outcome_update': True,
                    'agent_chat': self.server.codex_bridge.status()['available'],
                    'external_portal_submission': False,
                },
            })
        if parsed.path == '/api/review':
            query = urllib.parse.parse_qs(parsed.query)
            job = (query.get('job') or [''])[0]
            if not job:
                return self._error('job is required')
            try:
                return self._json(dashboard_actions.presentation(job))
            except (OSError, ValueError) as error:
                return self._error(error)
        if parsed.path == '/api/agent/task':
            query = urllib.parse.parse_qs(parsed.query)
            task_id = (query.get('id') or [''])[0]
            task = self.server.codex_bridge.task(task_id)
            return self._json(task) if task else self._not_found()
        if parsed.path == '/artifact':
            query = urllib.parse.parse_qs(parsed.query)
            job = (query.get('job') or [''])[0]
            artifact_id = (query.get('id') or [''])[0]
            _, registry = build_snapshot(include_private=True)
            path = registry.get((job, artifact_id))
            if not path or not _inside_data_root(path) or not os.path.isfile(path):
                return self._not_found()
            content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            with open(path, 'rb') as stream:
                content = stream.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header(
                'Content-Security-Policy',
                "default-src 'none'; img-src 'self' data:; style-src 'self'; "
                "object-src 'self'; frame-ancestors 'none'; sandbox")
            disposition = 'inline' if content_type.startswith((
                'text/', 'image/', 'application/pdf', 'application/json')) else 'attachment'
            safe_name = os.path.basename(path).replace('"', '')
            self.send_header('Content-Disposition', f'{disposition}; filename="{safe_name}"')
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass
            return

        relative = 'index.html' if parsed.path in {'', '/'} else parsed.path.lstrip('/')
        if relative not in {'index.html', 'styles.css', 'app.js'}:
            return self._not_found()
        path = os.path.join(STATIC_ROOT, relative)
        if not os.path.isfile(path):
            return self._not_found()
        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type in {
                'application/javascript', 'application/json'}:
            content_type += '; charset=utf-8'
        with open(path, 'rb') as stream:
            content = stream.read()
        self._bytes(content, content_type)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/admin/shutdown':
            supplied = self.headers.get('X-Joblooper-Shutdown') or ''
            if not secrets.compare_digest(supplied, self.server.shutdown_token):
                return self._error('Dashboard restart authorization failed', 403)
            self._json({'ok': True, 'stopping': True})
            threading.Timer(0.05, self.server.shutdown).start()
            return
        if not self._authorised():
            return self._error('Dashboard session authorization failed', 403)
        try:
            body = self._read_json()
            if parsed.path == '/api/actions/ingest':
                result = dashboard_actions.ingest(
                    body.get('jd'), body.get('company'), body.get('title'),
                    body.get('url'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/ingest-url':
                result = dashboard_actions.ingest_url(body.get('url'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/feedback':
                result = dashboard_actions.record_feedback(
                    body.get('job_id'), body.get('scope'), body.get('note'),
                    body.get('author'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/resolve-feedback':
                result = dashboard_actions.resolve_feedback(
                    body.get('job_id'), body.get('feedback_id'), body.get('status'),
                    body.get('implementation'), body.get('validation'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/present':
                result = dashboard_actions.mark_presented(body.get('job_id'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/approve-build':
                result = dashboard_actions.approve_and_build(
                    body.get('job_id'), body.get('reviewer'),
                    body.get('confirmation'), bool(body.get('no_pdf')))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/submit':
                job_id = body.get('job_id')
                cv_id = body.get('cv_artifact_id')
                letter_id = body.get('letter_artifact_id')
                if cv_id not in {'manifest-pdf', 'manifest-docx'}:
                    raise ValueError('Select a verified approved CV')
                if letter_id not in {None, '', 'manifest-letter_pdf',
                                     'manifest-letter_docx'}:
                    raise ValueError('Select a verified approved cover letter')
                _, registry = build_snapshot(include_private=True)
                cv_path = registry.get((job_id, cv_id))
                letter_path = registry.get((job_id, letter_id)) if letter_id else None
                if not cv_path or not _inside_data_root(cv_path):
                    raise ValueError('Selected CV is not available in this application')
                if letter_id and (not letter_path or not _inside_data_root(letter_path)):
                    raise ValueError('Selected cover letter is not available')
                result = dashboard_actions.record_submission(
                    job_id, cv_path, letter_path, body.get('channel') or 'portal',
                    body.get('applied_date'), body.get('screening'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/update-submission':
                result = dashboard_actions.update_submission(
                    body.get('job_id'), body.get('applied_date'),
                    body.get('channel'), body.get('screening'),
                    bool(body.get('screening_unavailable')))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/actions/outcome':
                result = dashboard_actions.record_outcome(
                    body.get('job_id'), body.get('status'),
                    body.get('response_date'), body.get('latency'),
                    body.get('employer_reason'), body.get('response_text'))
                return self._json({'ok': True, 'result': result})
            if parsed.path == '/api/agent/turn':
                task = self.server.codex_bridge.start_turn(
                    body.get('message'), body.get('intent') or 'ask',
                    body.get('job_id'))
                return self._json({'ok': True, 'task': task}, 202)
            if parsed.path == '/api/agent/respond':
                task = self.server.codex_bridge.respond(
                    body.get('task_id'), body.get('decision'), body.get('answers'))
                return self._json({'ok': True, 'task': task})
            return self._not_found()
        except ValueError as error:
            return self._error(error)
        except subprocess.TimeoutExpired as error:
            return self._error(f'Action timed out: {error}', 504)
        except RuntimeError as error:
            return self._error(error, 503)
        except OSError as error:
            return self._error(error, 500)


class DashboardServer(ThreadingHTTPServer):
    # Windows otherwise permits multiple HTTPServer processes to share the same
    # loopback port, making a familiar URL serve an unpredictable old instance.
    allow_reuse_address = False

    def server_close(self):
        try:
            bridge = getattr(self, 'codex_bridge', None)
            if bridge:
                bridge.close()
        finally:
            try:
                dashboard_runtime.unregister(getattr(self, 'instance_id', None))
            finally:
                super().server_close()


def create_server(port=8765, quiet=False, bridge=None):
    server = dashboard_runtime.configure_server(
        DashboardServer(('127.0.0.1', int(port)), DashboardHandler))
    server.quiet = quiet
    server.session_token = secrets.token_urlsafe(32)
    server.codex_bridge = bridge or codex_bridge.CodexBridge()
    return server


def serve(port=8765, open_browser=True):
    try:
        replaced = dashboard_runtime.stop_registered(port)
        # The browser polls task state frequently; per-request console logging is
        # operational noise and adds avoidable latency on some Windows terminals.
        server = create_server(port, quiet=True)
    except (OSError, RuntimeError) as error:
        print(f'Dashboard not started: port {port} is already in use.\n'
              f'{error}\nNothing outside a verified Joblooper instance was stopped.',
              flush=True)
        return 1
    dashboard_runtime.register(server)
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    print(f'Joblooper dashboard  {url}', flush=True)
    if replaced:
        print('Previous verified dashboard stopped; this page is the current instance.',
              flush=True)
    print('Local governed workspace · press Ctrl+C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nDashboard stopped.', flush=True)
    finally:
        server.server_close()
    return 0
