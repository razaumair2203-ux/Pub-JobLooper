"""Allowlisted deterministic mutations initiated by the local dashboard."""
import base64
import binascii
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

from . import (advert_review, feedback, job_fetch, learning, match, preflight, release, store,
               preferences, truth_intake, truth_review)


_ACTION_LOCK = threading.RLock()
FEEDBACK_SCOPES = {'content', 'format', 'workflow', 'truth', 'rule'}
OUTCOME_STATES = {'rejected', 'interview', 'offer', 'progressed', 'ghosted', 'withdrawn'}
LATENCY_BANDS = {'under_24h', '1_3d', '4_7d', '8_30d', 'over_30d', 'unknown'}
SCREENING_EXTENSIONS = {'.pdf', '.txt', '.md', '.json', '.html', '.png', '.jpg',
                        '.jpeg', '.webp'}
RESPONSE_EXTENSIONS = SCREENING_EXTENSIONS | {'.eml', '.msg'}
MAX_SCREENING_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_BATCH_BYTES = 24 * 1024 * 1024


def truth_workspace():
    """Return the resumable source-to-sign-off workbench projection."""
    return truth_intake.summary()


def upload_truth_sources(files, kind='base_cv', supersedes_source_id=None):
    if not isinstance(files, list) or not files:
        raise ValueError('Select at least one career source')
    if len(files) > 12:
        raise ValueError('Upload no more than 12 career sources at once')
    if supersedes_source_id and len(files) != 1:
        raise ValueError('Replace one registered source with one reviewed file at a time')
    decoded = []
    total = 0
    for supplied in files:
        if not isinstance(supplied, dict):
            raise ValueError('Each career source must be an uploaded file')
        encoded = str(supplied.get('base64') or '')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError('Career source is not valid base64 data') from error
        total += len(content)
        if total > MAX_UPLOAD_BATCH_BYTES:
            raise ValueError('Career-source batch exceeds 24 MB; upload it in smaller batches')
        decoded.append((supplied.get('name'), content))
    results = []
    with _ACTION_LOCK, store.writer_lock():
        for name, content in decoded:
            results.append(truth_intake.upload(
                name, content, kind=kind,
                supersedes_source_id=supersedes_source_id))
    return {'ok': True, 'sources': [row['source'] for row in results],
            'workspace': truth_intake.summary()}


def review_truth_candidates(profile, decisions):
    if not isinstance(profile, dict) or not isinstance(decisions, list):
        raise ValueError('Career-truth review requires profile fields and claim decisions')
    with _ACTION_LOCK, store.writer_lock():
        workspace = truth_intake.review(profile, decisions)
    return {'ok': True, 'workspace': workspace,
            'message': 'Source decisions saved. Review the complete summary and sign its exact digest.'}


def sign_truth(reviewer, confirmation):
    reviewer = str(reviewer or '').strip()
    if len(reviewer) < 2 or len(reviewer) > 200:
        raise ValueError('Enter the name of the person reviewing career truth')
    if confirmation != 'I reviewed the identity, sources, facts and boundaries':
        raise ValueError('Confirm the complete identity, source, fact and boundary review')
    with _ACTION_LOCK:
        result = _run_cli([
            'onboard', 'finalize', '--reviewer', reviewer, '--confirm-reviewed',
        ], timeout=90)
    if not result['ok']:
        raise ValueError(result['output'] or 'Career-truth sign-off was refused')
    result['workspace'] = truth_intake.summary()
    return result


def record_truth_comment(scope, note, author, evidence=None):
    values = evidence if isinstance(evidence, list) else str(evidence or '').splitlines()
    with _ACTION_LOCK, store.writer_lock():
        item = truth_review.record(scope, note, author, values)
    return {'ok': True, 'item': item, 'workspace': truth_intake.summary()}


def resolve_truth_comment(item_id, status, implementation, validation):
    with _ACTION_LOCK, store.writer_lock():
        item = truth_review.resolve(item_id, status, implementation, validation)
    return {'ok': True, 'item': item, 'workspace': truth_intake.summary()}


def _run_cli(arguments, timeout=300):
    command = [sys.executable, store.code_p('jl.py'), '--data-dir', store.DATA_ROOT]
    command.extend(str(value) for value in arguments)
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'utf-8'
    with _ACTION_LOCK:
        result = subprocess.run(
            command, cwd=store.ROOT, env=environment, text=True, encoding='utf-8',
            errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout)
    return {
        'ok': result.returncode == 0,
        'returncode': result.returncode,
        'output': result.stdout.strip(),
    }


def require_capture_ready():
    """Refuse job capture until candidate truth is signed.

    An advert can only be tailored against facts the system is allowed to use,
    so capture is gated on the entry state rather than being the first-run
    action. This fails closed for the same reason every other gate does.
    """
    entry = truth_review.entry_state()
    if not entry['can_capture']:
        raise ValueError(
            f"{entry['next_action']} before capturing a job — {entry['reason']}")
    return entry


def ingest(raw, company, title, url=None):
    require_capture_ready()
    raw = str(raw or '').strip()
    company = str(company or '').strip()
    title = str(title or '').strip()
    url = str(url or '').strip() or None
    if not raw:
        raise ValueError('Paste the exact job description before continuing')
    if len(raw) > 120000:
        raise ValueError('Job description exceeds the 120,000-character limit')
    if not company or not title:
        raise ValueError('Exact company and job title are required')
    if len(company) > 200 or len(title) > 300 or (url and len(url) > 2000):
        raise ValueError('One or more intake fields exceed the safe length limit')
    if url:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise ValueError('Reference URL must use public HTTP or HTTPS')
    path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.md', prefix='joblooper-jd-',
                encoding='utf-8', delete=False) as stream:
            stream.write(raw)
            path = stream.name
        arguments = ['ingest', path, '--company', company, '--title', title]
        if url:
            arguments += ['--url', url]
        result = _run_cli(arguments, timeout=60)
    finally:
        if path and os.path.isfile(path):
            os.unlink(path)
    if not result['ok']:
        raise ValueError(result['output'] or 'Job intake failed')
    match = re.search(r'(?:ingested|already ingested)\s+([^\s]+)', result['output'])
    if not match:
        raise RuntimeError('Job was captured but its application key was not returned')
    result['job_id'] = match.group(1)
    result['advert_review'] = advert_review.state(result['job_id'])
    return result


def ingest_url(url):
    """Extract and capture a public advert without asking for duplicate fields."""
    require_capture_ready()
    requested_url = str(url or '').strip()
    extracted = job_fetch.fetch(requested_url)
    result = ingest(
        extracted['jd'], extracted['company'], extracted['title'], extracted['url'])
    result['extraction'] = {
        key: extracted[key] for key in (
            'company', 'title', 'url', 'extractor', 'characters')
    }
    result['extraction']['requested_url'] = requested_url
    return result


def refresh_job_analysis(job_id):
    """Refresh parser-owned JD structure through the governed CLI transition."""
    result = _run_cli(['refresh-jd', job_id], timeout=90)
    if not result['ok']:
        raise ValueError(result['output'] or 'Job analysis could not be refreshed')
    return result


def advert_review_state(job_id):
    slug = store.resolve_job(job_id)
    return advert_review.state(slug)


def confirm_advert(job_id, company, title, reviewer='dashboard-user'):
    slug = store.resolve_job(job_id)
    with _ACTION_LOCK, store.writer_lock():
        receipt = advert_review.confirm(slug, company, title, reviewer)
    return {'ok': True, 'receipt': receipt,
            'message': 'Exact advert confirmed. Deterministic preflight is now enabled.'}


def preflight_state(job_id):
    """Read the exact current decision set without changing application state."""
    slug = store.resolve_job(job_id)
    directory = store.job_dir(slug)
    jd = store.read_json(os.path.join(directory, 'jd.json'), {}) or {}
    if not jd:
        raise ValueError('The exact captured job description is unavailable')
    advert_review.require(slug)
    jd['_slug'] = slug
    identity = match.pick_identity(jd)
    mapping = match.match_jd(jd, identity)
    rows = preflight.questions(jd, mapping, identity)
    record, errors, _ = preflight.validate(slug, jd, mapping, identity)
    resolved = [
        row for row in mapping.get('requirements') or []
        if (row.get('hard_gate') or row.get('kind') == 'mandatory')
        and row.get('match') in {'DIRECT', 'BEHAVIOURAL'}]
    return {
        'job_id': slug,
        'company': jd.get('company'),
        'role': jd.get('title'),
        'reference': jd.get('job_reference'),
        'identity': identity.get('primary'),
        'questions': rows,
        'resolved_count': len(resolved),
        'decision_count': len(rows),
        'complete': bool(record and not errors),
        'errors': errors,
        'answers': record.get('answers') or {},
        'decision': record.get('decision'),
        'subject_sha256': record.get('subject_sha256'),
        'binding_sha256': (preflight.binding_digest(record) if record else None),
    }


def plan_state(job_id):
    """Project whether the existing review bundle is complete and current."""
    slug = store.resolve_job(job_id)
    directory = store.job_dir(slug)
    names = ('match.json', 'cv.json', 'cover-letter.json', 'employer-risk.json')
    missing = [name for name in names
               if not os.path.isfile(os.path.join(directory, name))]
    if missing:
        return {
            'job_id': slug, 'available': False, 'current': False,
            'errors': ['missing plan artefact(s): ' + ', '.join(missing)],
        }
    jd = store.read_json(os.path.join(directory, 'jd.json'), {}) or {}
    mapping = store.read_json(os.path.join(directory, 'match.json'), {}) or {}
    cv = store.read_json(os.path.join(directory, 'cv.json'), {}) or {}
    letter = store.read_json(os.path.join(directory, 'cover-letter.json'), {}) or {}
    receipt = store.read_json(os.path.join(directory, release.PLAN_RECEIPT_NAME), {}) or {}
    if not jd:
        return {
            'job_id': slug, 'available': True, 'current': False,
            'errors': ['captured job description is missing'],
        }
    jd['_slug'] = slug
    current_inputs = store.generation_fingerprint(jd).get('sha256')
    errors = []
    accepted_feedback = feedback.accepted_overrides(slug)
    if accepted_feedback:
        errors.append('accepted feedback requires deterministic regeneration: '
                      + ', '.join(row['id'] for row in accepted_feedback))
    if (receipt.get('_schema') != 'joblooper.plan-receipt.v1'
            or receipt.get('app_id') != slug
            or receipt.get('plan_sha256') != release.plan_digest(slug)):
        errors.append('plan publication receipt is missing or stale')
    for label, record in (('match', mapping), ('CV', cv), ('cover letter', letter)):
        planned = (record.get('_inputs') or {}).get('sha256')
        if planned != current_inputs:
            errors.append(f'{label} is stale relative to the current JD, truth or engine')
    identity = mapping.get('identity') or {}
    preflight_record, preflight_errors, _ = preflight.validate(
        slug, jd, mapping, identity)
    errors.extend(preflight_errors)
    planned_preflight = mapping.get('_preflight') or {}
    if (preflight_record.get('subject_sha256')
            != planned_preflight.get('subject_sha256')
            or not planned_preflight.get('binding_sha256')
            or preflight.binding_digest(preflight_record)
            != planned_preflight.get('binding_sha256')):
        errors.append('plan is not bound to the exact current preflight decisions')
    if (receipt.get('preflight_binding_sha256')
            != planned_preflight.get('binding_sha256')):
        errors.append('plan receipt is not bound to the exact preflight decisions')
    return {
        'job_id': slug, 'available': True, 'current': not errors,
        'errors': list(dict.fromkeys(errors)),
        'inputs_sha256': current_inputs,
    }


def review_preflight(job_id, answers, reviewer='dashboard-user'):
    """Record explicit per-item decisions through the governed CLI."""
    if not isinstance(answers, dict):
        raise ValueError('Preflight decisions must be a JSON object')
    clean = {}
    for key, value in answers.items():
        key = str(key or '').strip()
        if not re.fullmatch(r'[A-Z0-9_-]{2,80}', key):
            raise ValueError('Preflight contains an invalid decision value')
        if isinstance(value, dict):
            decision = str(value.get('decision') or '').strip()
            note = str(value.get('note') or '').strip()
            if len(decision) > 120 or len(note) > 2000:
                raise ValueError('Preflight contains an invalid decision value')
            clean[key] = {'decision': decision, 'note': note}
        else:
            value = str(value or '').strip()
            if len(value) > 120:
                raise ValueError('Preflight contains an invalid decision value')
            clean[key] = value
    current = preflight_state(job_id)
    identity_choice = None
    if any(row.get('id') == 'IDENTITY' for row in current['questions']):
        identity_value = clean.pop('IDENTITY', None)
        identity_choice = (identity_value.get('decision')
                           if isinstance(identity_value, dict) else identity_value)
        if not identity_choice:
            raise ValueError('Select the application identity before continuing')
    answer_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix='joblooper-preflight-',
                encoding='utf-8', delete=False) as stream:
            json.dump(clean, stream, ensure_ascii=False)
            answer_path = stream.name
        arguments = [
            'preflight', job_id, '--user-reviewed', '--reviewer',
            str(reviewer or 'dashboard-user')[:200], '--answers-file', answer_path,
            '--note', 'Structured decisions recorded through the local dashboard',
        ]
        if identity_choice:
            arguments += ['--identity', identity_choice]
        result = _run_cli(arguments, timeout=60)
    finally:
        if answer_path and os.path.isfile(answer_path):
            os.unlink(answer_path)
    if not result['ok']:
        raise ValueError(result['output'] or 'Preflight decisions could not be recorded')
    result['preflight'] = preflight_state(job_id)
    return result


def prepare_application(job_id):
    """Create the governed review records without relying on a Codex turn.

    Planning is already deterministic: the CLI revalidates truth, the exact JD,
    preflight decisions and open feedback before writing any output.  Keeping
    this as one allowlisted dashboard action means a dropped conversation can
    never leave the user wondering whether the CV was actually created.
    """
    with _ACTION_LOCK:
        current = preflight_state(job_id)
        if not current['complete']:
            raise ValueError(
                'Preflight decisions are not complete for the current JD and approved truth')
        package, manifest = release.load_release(current['job_id'])
        if package:
            if manifest:
                _, errors = release.verify_release(current['job_id'])
                if errors:
                    raise ValueError('Approved package integrity requires attention: '
                                     + '; '.join(errors))
                raise ValueError(
                    'A verified approved package already exists. Open Submission; '
                    'record feedback before requesting a new plan.')
            approval, approval_errors = release.validate_approval(current['job_id'])
            if approval and not approval_errors:
                raise ValueError(
                    'Approval is already recorded and document build is incomplete. '
                    'Use Finish build instead of regenerating the plan.')
        existing = plan_state(current['job_id'])
        if existing['current']:
            review = presentation(current['job_id'])
            if not review['available']:
                raise RuntimeError(
                    'Current plan exists but the complete CV-and-cover-letter review is unavailable')
            return {
                'ok': True, 'returncode': 0,
                'output': 'Current CV and cover-letter review bundle reused; no files changed.',
                'reused': True, 'review': review,
            }
        result = _run_cli(['plan', current['job_id']], timeout=180)
        if not result['ok']:
            raise ValueError(result['output'] or 'CV and cover-letter preparation failed')
        review = presentation(current['job_id'])
        if not review['available']:
            raise RuntimeError(
                'Planning completed but the complete CV-and-cover-letter review is unavailable')
        result['review'] = review
        result['reused'] = False
        return result


def feedback_targets(job_id):
    slug = store.resolve_job(job_id)
    return {'job_id': slug, 'targets': feedback.document_targets(slug)}


def record_feedback(job_id, scope, note, author='dashboard-user',
                    classification=None, target_id=None,
                    requested_scope='THIS_APPLICATION', preference_type=None,
                    preference_value=None):
    scope = str(scope or '').strip().lower()
    note = str(note or '').strip()
    if scope not in FEEDBACK_SCOPES:
        raise ValueError('Select a valid feedback scope')
    if not note:
        raise ValueError('Feedback cannot be empty')
    if len(note) > 8000:
        raise ValueError('Feedback exceeds the 8,000-character limit')
    slug = store.resolve_job(job_id)
    selected_target = feedback.target(slug, target_id) if target_id else None
    feedback.validate_record(scope, note)
    with _ACTION_LOCK, store.writer_lock():
        retired = release.invalidate_unsubmitted_package(
            slug, 'user feedback invalidated the approved unsubmitted package')
        item = feedback.record(
            slug, scope, note, str(author or 'dashboard-user')[:200],
            plan_sha256=release.plan_digest(slug),
            classification=classification, target=selected_target,
            requested_scope=requested_scope, preference_type=preference_type,
            preference_value=preference_value)
        release.write_status(slug, 'PLAN')
    return {
        'ok': True, 'item': item,
        'output': (f"recorded {item['id']} · {item.get('classification') or item['scope']} · OPEN"
                   + ('; approved unsubmitted package retired' if retired else '')),
    }


def propose_feedback(job_id, feedback_id, after_text):
    slug = store.resolve_job(job_id)
    with _ACTION_LOCK, store.writer_lock():
        item = feedback.propose(slug, feedback_id, after_text)
    return {'ok': True, 'item': item,
            'output': f"proposal {item.get('proposal_id')} saved for {item['id']}"}


def decide_feedback(job_id, feedback_id, decision, note='', edited_text=None):
    slug = store.resolve_job(job_id)
    with _ACTION_LOCK, store.writer_lock():
        item = next((row for row in feedback.current(slug)
                     if row.get('id') == feedback_id), None)
        if not item:
            raise ValueError('Select an open feedback item')
        normalized = str(decision or '').upper()
        if item.get('classification') == 'REUSABLE_PREFERENCE' and normalized == 'ACCEPT':
            preference = preferences.record(
                item.get('preference_type'), item.get('preference_value'),
                item.get('note'), item['id'])
            receipt = {
                '_schema': 'joblooper.preference-receipt.v1',
                'preference_id': preference['id'], 'type': preference['type'],
                'value': preference['value'], 'source_feedback_id': item['id'],
            }
            item = feedback.complete_governed(
                slug, item['id'],
                f"Adopted governed preference {preference['id']}.",
                'The preference is included in generation fingerprints and plan previews.',
                receipt)
        elif item.get('classification') == 'FACTUAL_CORRECTION' and normalized == 'ACCEPT':
            current_truth = store.truth_approval_subject()['sha256']
            if current_truth == item.get('truth_sha256'):
                raise ValueError('Career truth has not changed since this correction was recorded')
            if not truth_review.readiness()['ready']:
                raise ValueError('Review and sign the changed career truth before closing this correction')
            receipt = {
                '_schema': 'joblooper.truth-feedback-receipt.v1',
                'before_truth_sha256': item.get('truth_sha256'),
                'after_truth_sha256': current_truth,
            }
            item = feedback.complete_governed(
                slug, item['id'], 'Applied through the governed career-truth workbench.',
                'Changed career truth passed integrity and exact digest sign-off.', receipt)
        elif (item.get('classification') in {'WORKFLOW_REQUEST', 'REJECTION'}
              and normalized in {'ACCEPT', 'EDIT'}):
            raise ValueError('A workflow request cannot mutate the product from this application; defer or reject it')
        else:
            item = feedback.decide(slug, feedback_id, decision, note, edited_text)
    return {'ok': True, 'item': item,
            'output': (f"{item['id']} {item['status']}" +
                       ('; regenerate to apply and verify the exact change'
                       if item['status'] == 'ACCEPTED_PENDING_REPLAN' else ''))}


def retire_preference(preference_id, reason):
    with _ACTION_LOCK, store.writer_lock():
        row = preferences.retire(preference_id, reason)
    return {'ok': True, 'preference': row,
            'output': f"retired preference {row['id']}"}


def resolve_feedback(job_id, feedback_id, status, implementation, validation):
    """Resolve one existing review comment through the governed CLI path."""
    feedback_id = str(feedback_id or '').strip()
    status = str(status or '').strip().lower()
    implementation = str(implementation or '').strip()
    validation = str(validation or '').strip()
    if not re.fullmatch(r'F\d{4,}', feedback_id):
        raise ValueError('Select a valid open feedback item')
    if status not in {'adopted', 'rejected'}:
        raise ValueError('Select whether the feedback was adopted or rejected')
    if len(implementation) < 8 or len(validation) < 8:
        raise ValueError('Decision rationale and validation must each be explicit')
    if len(implementation) > 8000 or len(validation) > 8000:
        raise ValueError('Feedback resolution exceeds the 8,000-character limit')
    result = _run_cli([
        'feedback', job_id, '--id', feedback_id, '--status', status,
        '--implementation', implementation, '--validation', validation,
    ], timeout=60)
    if not result['ok']:
        raise ValueError(result['output'] or 'Feedback could not be resolved')
    return result


def presentation(job_id):
    """Return exact review content without manufacturing a new plan."""
    slug = store.resolve_job(job_id)
    try:
        content = release.document_presentation_content(slug)
        internal_content = release.internal_signoff_content(slug)
        bound_content = release.presentation_content(slug)
        record, errors = release.validate_presentation(slug)
    except ValueError as error:
        return {'available': False, 'content': None, 'valid': False,
                'errors': [str(error)]}
    return {
        'available': True,
        'content': content,
        'internal_content': internal_content,
        'valid': bool(record and not errors),
        'errors': errors,
        'content_sha256': store.sha256_text(bound_content),
        'document_content_sha256': store.sha256_text(content),
    }


def mark_presented(job_id):
    result = _run_cli(['present', job_id], timeout=90)
    if not result['ok']:
        raise ValueError(result['output'] or 'Application could not be presented')
    review = presentation(job_id)
    result['review'] = review
    return result


def approve_and_build(job_id, reviewer, confirmation, no_pdf=False):
    reviewer = str(reviewer or '').strip()
    if confirmation != 'I reviewed the complete CV and cover letter':
        raise ValueError('Exact CV-and-cover-letter review confirmation is required')
    if not reviewer:
        raise ValueError('Reviewer name is required')
    with _ACTION_LOCK:
        slug = store.resolve_job(job_id)
        package, manifest = release.load_release(slug)
        if manifest:
            _, errors = release.verify_release(slug)
            if errors:
                raise ValueError('Approved package integrity requires attention: '
                                 + '; '.join(errors))
            return {
                'ok': True,
                'output': 'Approval and verified document package already exist; no files changed.',
                'reused': True,
            }
        current_approval, approval_errors = release.validate_approval(slug)
        if not current_approval or approval_errors:
            approved = _run_cli([
                'approve', slug, '--reviewer', reviewer, '--all-pass', '--user-signoff',
                '--note', ('Dashboard reviewer explicitly confirmed relevance, specificity, '
                           'contradictions, bloat, ATS terminology and hostile-recruiter risk.'),
            ], timeout=90)
            if not approved['ok']:
                raise ValueError(approved['output'] or 'Approval was refused')
            approval_output = approved['output']
        else:
            approval_output = 'Current exact-bundle approval reused.'
        built = build_application(slug, no_pdf=no_pdf)
        return {
            'ok': True,
            'output': approval_output + '\n\n' + built['output'],
            'reused': bool(current_approval and not approval_errors),
        }


def build_application(job_id, no_pdf=False):
    """Finish an interrupted build without repeating user approval."""
    with _ACTION_LOCK:
        slug = store.resolve_job(job_id)
        package, manifest = release.load_release(slug)
        if manifest:
            _, errors = release.verify_release(slug)
            if errors:
                raise ValueError('Approved package integrity requires attention: '
                                 + '; '.join(errors))
            return {
                'ok': True,
                'output': 'Verified document package already exists; no files changed.',
                'reused': True,
            }
        approval, errors = release.validate_approval(slug)
        if not approval or errors:
            raise ValueError('A current exact-bundle approval is required before build: '
                             + '; '.join(errors or ['approval missing']))
        arguments = ['build', slug]
        if no_pdf:
            arguments.append('--no-pdf')
        built = _run_cli(arguments, timeout=300)
        if not built['ok']:
            raise ValueError(built['output'] or 'Build was refused')
        built['reused'] = False
        return built


def repair_unsubmitted_package(job_id, confirmation, no_pdf=False):
    """Rebuild a damaged, never-submitted derivative from its approved plan."""
    if confirmation != 'REBUILD UNSUBMITTED PACKAGE':
        raise ValueError('Confirm the exact unsubmitted-package rebuild')
    slug = store.resolve_job(job_id)
    with _ACTION_LOCK, store.writer_lock():
        package, _manifest = release.load_release(slug)
        if not package:
            raise ValueError('No approved package exists to rebuild')
        if release.has_record_file(package, release.SUBMISSION_NAME):
            raise ValueError('Submitted packages are immutable and cannot be rebuilt')
        _verified, errors = release.verify_release(slug)
        if not errors:
            raise ValueError('Package already verifies; no repair is needed')
        approval, approval_errors = release.validate_approval(slug)
        if not approval or approval_errors:
            raise ValueError('The damaged package has no current approved source plan: '
                             + '; '.join(approval_errors or ['approval missing']))
        release.invalidate_unsubmitted_package(
            slug, 'User-approved integrity recovery from the current approved plan')
        # Plan invalidation removes the case registry intentionally. A repair is
        # different: re-create the empty approved destination bound to the same
        # approval before the renderer starts in its own process.
        store.create_approved_case(
            slug, approval['approved_at'], approval['plan_sha256'])
    rebuilt = build_application(slug, no_pdf=no_pdf)
    rebuilt['repair'] = 'REBUILT_UNSUBMITTED_PACKAGE'
    return rebuilt


def acknowledge_package_exception(job_id, confirmation):
    """Acknowledge unsent-derivative drift without altering submitted evidence."""
    if confirmation != 'ACKNOWLEDGE SUBMITTED EXCEPTION':
        raise ValueError('Confirm the exact submitted-package exception')
    slug = store.resolve_job(job_id)
    package, manifest = release.load_release(slug)
    receipt, submission_errors = release.verify_submission(slug)
    _verified, package_errors = release.verify_release(slug)
    if not package or not receipt or submission_errors or not package_errors:
        raise ValueError('No safely bounded submitted-package exception is available')
    signature = store.sha256_text(store.canonical_json(sorted(package_errors)))
    existing = store.read_jsonl(release.record_path(
        package, 'INTEGRITY-ACKNOWLEDGEMENTS.jsonl'))
    if any(row.get('exception_sha256') == signature for row in existing):
        return {'output': 'Current submitted-package exception was already acknowledged.',
                'reused': True}
    row = {
        '_schema': 'joblooper.integrity-acknowledgement.v1',
        'timestamp': store.now(), 'app_id': slug,
        'package_id': (manifest or {}).get('package_id'),
        'exception_sha256': signature, 'exceptions': sorted(package_errors),
        'basis': ('Exact submitted files still verify; only unsent derivatives differ. '
                  'No submitted evidence was modified.'),
    }
    store.append_jsonl(release.record_path(
        package, 'INTEGRITY-ACKNOWLEDGEMENTS.jsonl', create=True), row)
    store.append_application_event({
        'event': 'SUBMITTED_INTEGRITY_EXCEPTION_ACKNOWLEDGED',
        'app_id': slug, 'package_id': row['package_id'],
        'exception_sha256': signature,
    })
    return {'output': 'Submitted-package exception acknowledged; sent files remain immutable.',
            'acknowledgement': row}


def _screening_file(screening):
    """Decode one bounded browser-supplied evidence file into a temporary path."""
    if not screening:
        return None
    if not isinstance(screening, dict):
        raise ValueError('Screening evidence must be one uploaded file')
    filename = os.path.basename(str(screening.get('name') or '').strip())
    extension = os.path.splitext(filename)[1].lower()
    if extension not in SCREENING_EXTENSIONS:
        raise ValueError('Screening evidence must be PDF, text, JSON, HTML or an image')
    encoded = str(screening.get('base64') or '')
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Screening evidence is not valid base64 data') from error
    if not content:
        raise ValueError('Screening evidence is empty')
    if len(content) > MAX_SCREENING_BYTES:
        raise ValueError('Screening evidence exceeds the 8 MB limit')
    with tempfile.NamedTemporaryFile(
            mode='wb', suffix=extension, prefix='joblooper-screening-',
            delete=False) as stream:
        stream.write(content)
        return stream.name


def _screening_files(screening):
    supplied = screening if isinstance(screening, list) else ([screening] if screening else [])
    if len(supplied) > 12:
        raise ValueError('Upload no more than 12 portal-evidence files at once')
    paths = []
    try:
        for item in supplied:
            paths.append(_screening_file(item))
        if sum(os.path.getsize(path) for path in paths) > MAX_UPLOAD_BATCH_BYTES:
            raise ValueError('Portal-evidence batch exceeds 24 MB; add it in smaller updates')
        return paths
    except Exception:
        for path in paths:
            if path and os.path.isfile(path):
                os.unlink(path)
        raise


def _response_files(responses):
    supplied = responses if isinstance(responses, list) else ([responses] if responses else [])
    if len(supplied) > 12:
        raise ValueError('Upload no more than 12 employer-response files at once')
    paths = []
    total = 0
    try:
        for response in supplied:
            if not isinstance(response, dict):
                raise ValueError('Employer response evidence must be uploaded files')
            filename = os.path.basename(str(response.get('name') or '').strip())
            extension = os.path.splitext(filename)[1].lower()
            if extension not in RESPONSE_EXTENSIONS:
                raise ValueError('Employer response must be email, PDF, text, JSON, HTML or an image')
            encoded = str(response.get('base64') or '')
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError('Employer response evidence is not valid base64 data') from error
            if not content:
                raise ValueError('Employer response evidence is empty')
            if len(content) > MAX_SCREENING_BYTES:
                raise ValueError('Employer response evidence exceeds the 8 MB limit')
            total += len(content)
            if total > MAX_UPLOAD_BATCH_BYTES:
                raise ValueError('Employer-response evidence for one observation exceeds 24 MB')
            with tempfile.NamedTemporaryFile(
                    mode='wb', suffix=extension, prefix='joblooper-response-file-',
                    delete=False) as stream:
                stream.write(content)
                paths.append(stream.name)
        return paths
    except Exception:
        for path in paths:
            if os.path.isfile(path):
                os.unlink(path)
        raise


def record_submission(job_id, sent_file, cover_letter_file=None, channel='portal',
                      applied_date=None, screening=None):
    if not sent_file:
        raise ValueError('Select the exact CV that was actually submitted')
    screening_paths = []
    try:
        screening_paths = _screening_files(screening)
        arguments = ['submit', job_id, '--sent-file', sent_file]
        if cover_letter_file:
            arguments += ['--cover-letter-file', cover_letter_file]
        if channel:
            arguments += ['--channel', str(channel)[:100]]
        if applied_date:
            arguments += ['--date', applied_date]
        for screening_path in screening_paths:
            arguments += ['--screening-file', screening_path]
        result = _run_cli(arguments, timeout=90)
    finally:
        for screening_path in screening_paths:
            if os.path.isfile(screening_path):
                os.unlink(screening_path)
    if not result['ok']:
        raise ValueError(result['output'] or 'Submission could not be recorded')
    return result


def update_submission(job_id, applied_date=None, channel=None, screening=None,
                      screening_unavailable=False):
    """Correct user-reported submission metadata without changing sent files."""
    applied_date = str(applied_date or '').strip() or None
    channel = str(channel or '').strip() or None
    if applied_date:
        try:
            parsed = datetime.date.fromisoformat(applied_date)
        except ValueError as error:
            raise ValueError('Submission date must use YYYY-MM-DD') from error
        if parsed > datetime.date.today():
            raise ValueError('Submission date cannot be in the future')
    if channel and len(channel) > 100:
        raise ValueError('Submission channel exceeds 100 characters')
    if screening and screening_unavailable:
        raise ValueError('Attach portal answers or mark them unavailable, not both')
    screening_paths = []
    try:
        screening_paths = _screening_files(screening)
        arguments = ['update-submission', job_id]
        if applied_date:
            arguments += ['--date', applied_date]
        if channel:
            arguments += ['--channel', channel]
        for screening_path in screening_paths:
            arguments += ['--screening-file', screening_path]
        if screening_unavailable:
            arguments.append('--screening-unavailable')
        result = _run_cli(arguments, timeout=90)
    finally:
        for screening_path in screening_paths:
            if os.path.isfile(screening_path):
                os.unlink(screening_path)
    if not result['ok']:
        raise ValueError(result['output'] or 'Submission metadata could not be updated')
    return result


def record_outcome(job_id, status, response_date=None, latency=None,
                   employer_reason=None, response_text=None, responses=None):
    """Record an observation, preserving exact email text when the user has it."""
    slug = store.resolve_job(job_id)
    application = next(
        (row for row in store.applications() if row.get('app_id') == slug), None)
    if not application or not learning._exact_submission(application):
        raise ValueError('Outcome requires an exact recorded submission for this application')
    receipt, submission_errors = release.verify_submission(slug)
    if not receipt or submission_errors:
        raise ValueError('Outcome requires a verifiable exact submitted package: '
                         + '; '.join(submission_errors or ['submission receipt missing']))
    status = str(status or '').strip().lower()
    latency = str(latency or '').strip().lower() or None
    if latency == 'unknown':
        latency = None
    response_date = str(response_date or '').strip() or None
    employer_reason = str(employer_reason or '').strip() or None
    response_text = str(response_text or '').strip() or None
    if status not in OUTCOME_STATES:
        raise ValueError('Select a valid observed outcome')
    if latency and latency not in LATENCY_BANDS:
        raise ValueError('Select a valid response-time band')
    if response_date:
        try:
            parsed = datetime.date.fromisoformat(response_date)
        except ValueError as error:
            raise ValueError('Response date must use YYYY-MM-DD') from error
        if parsed > datetime.date.today():
            raise ValueError('Response date cannot be in the future')
    if employer_reason and len(employer_reason) > 600:
        raise ValueError('Employer-stated reason exceeds 600 characters')
    if response_text and len(response_text) > 120000:
        raise ValueError('Employer response exceeds 120,000 characters')
    if response_text and not response_date:
        raise ValueError('Give the response date when preserving exact employer text')
    if responses and not response_date:
        raise ValueError('Give the response date when preserving employer response files')
    if response_text and status not in {'rejected', 'interview', 'offer', 'progressed'}:
        raise ValueError('Exact response ingestion supports rejected, interview, offer or progressed')

    response_path = None
    response_paths = _response_files(responses)
    try:
        if response_text:
            with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', prefix='joblooper-response-',
                    encoding='utf-8', delete=False) as stream:
                stream.write(response_text)
                response_path = stream.name
            arguments = [
                'response', response_path, '--job', slug, '--status', status,
                '--date', response_date,
            ]
            if latency:
                arguments += ['--latency', latency]
            if employer_reason:
                arguments += ['--reason', employer_reason]
            captured = _run_cli(arguments, timeout=90)
            if not captured['ok']:
                raise ValueError(captured['output'] or 'Employer response could not be correlated')
            evidence = release.capture_response_evidence(
                slug, response_paths, status, response_date) if response_paths else []
            return {'ok': True, 'output': captured['output'],
                    'response_evidence': evidence}

        arguments = ['outcome', slug, '--status', status]
        if response_date:
            arguments += ['--date', response_date]
        if latency:
            arguments += ['--latency', latency]
        if employer_reason:
            arguments += ['--reason', employer_reason]
        observed = _run_cli(arguments, timeout=90)
        if not observed['ok']:
            raise ValueError(observed['output'] or 'Outcome could not be recorded')
        evidence = release.capture_response_evidence(
            slug, response_paths, status, response_date) if response_paths else []
        return {'ok': True, 'output': observed['output'],
                'response_evidence': evidence}
    finally:
        if response_path and os.path.isfile(response_path):
            os.unlink(response_path)
        for path in response_paths:
            if os.path.isfile(path):
                os.unlink(path)


def _outcome_values(application, status, response_date=None, latency=None,
                    employer_reason=None):
    status = str(status or '').strip().lower()
    latency = str(latency or '').strip().lower() or None
    if latency == 'unknown':
        latency = None
    response_date = str(response_date or '').strip() or None
    employer_reason = str(employer_reason or '').strip() or None
    if status not in OUTCOME_STATES:
        raise ValueError('Select a valid observed outcome')
    if latency and latency not in LATENCY_BANDS:
        raise ValueError('Select a valid response-time band')
    responded = None
    if response_date:
        try:
            responded = datetime.date.fromisoformat(response_date)
        except ValueError as error:
            raise ValueError('Response date must use YYYY-MM-DD') from error
        if responded > datetime.date.today():
            raise ValueError('Response date cannot be in the future')
    applied = None
    if application.get('applied'):
        try:
            applied = datetime.date.fromisoformat(application['applied'])
        except ValueError as error:
            raise ValueError('Recorded submission date must use YYYY-MM-DD') from error
    if responded and applied and responded < applied:
        raise ValueError('Response date cannot precede submission date')
    if employer_reason and len(employer_reason) > 600:
        raise ValueError('Employer-stated reason exceeds 600 characters')
    return {
        'status': status, 'responded': response_date,
        'responded_date_status': 'recorded' if response_date else 'not_provided',
        'days': (responded - applied).days if responded and applied else None,
        'stated_reason': employer_reason,
        'response_latency': {
            'band': latency or 'unknown',
            'basis': 'user_reported' if latency else 'not_provided',
        },
    }


def correct_outcome(job_id, event_id, status, response_date=None, latency=None,
                    employer_reason=None, reason=None, responses=None,
                    response_text=None):
    """Supersede the active outcome while preserving both ledger records."""
    slug = store.resolve_job(job_id)
    event_id = str(event_id or '').strip()
    reason = str(reason or '').strip()
    if not event_id:
        raise ValueError('Select the outcome observation being corrected')
    if len(reason) < 5:
        raise ValueError('Explain why this observation is being corrected')
    response_text = str(response_text or '').strip() or None
    if response_text and len(response_text) > 120000:
        raise ValueError('Employer response exceeds 120,000 characters')
    if response_text and not response_date:
        raise ValueError('Give the response date when preserving exact employer text')
    if responses and not response_date:
        raise ValueError('Give the response date when preserving employer response files')
    apps = store.applications()
    application = next((row for row in apps if row.get('app_id') == slug), None)
    if not application or not learning._exact_submission(application):
        raise ValueError('Outcome correction requires an exact recorded submission')
    receipt, submission_errors = release.verify_submission(slug)
    if not receipt or submission_errors:
        raise ValueError('Outcome correction requires a verifiable submitted package')
    active = learning.active_outcome_events(slug)
    target = active[-1] if active else None
    if not target or target.get('event_id') != event_id:
        raise ValueError('Only the latest active outcome observation can be corrected')
    values = _outcome_values(
        application, status, response_date, latency, employer_reason)
    response_paths = _response_files(responses)
    response_text_path = None
    try:
        if response_text:
            with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', prefix='joblooper-response-',
                    encoding='utf-8', delete=False) as stream:
                stream.write(response_text)
                response_text_path = stream.name
            response_paths.insert(0, response_text_path)
        with _ACTION_LOCK, store.writer_lock():
            application.update(values)
            store.write_jsonl(store.p('index', 'applications.jsonl'),
                              [row for row in apps if row.get('app_id') != slug]
                              + [application])
            store.write_json(os.path.join(store.job_dir(slug), 'outcome.json'), application)
            package = store.approved_dir(slug)
            if package:
                store.write_json(release.record_path(package, 'OUTCOME.json', create=True),
                                 application)
                _, manifest = release.load_release(slug)
                release.write_status(slug, 'SUBMITTED', manifest)
            event = store.append_application_event({
                'event': 'OUTCOME_CORRECTED', 'app_id': slug,
                'supersedes_event_id': event_id, 'status': values['status'],
                'responded': values['responded'],
                'stated_reason': values['stated_reason'],
                'response_latency': values['response_latency'],
                'correction_reason': reason,
            })
        evidence = release.capture_response_evidence(
            slug, response_paths, values['status'], values['responded']) \
            if response_paths else []
        return {'event': event, 'response_evidence': evidence, 'output': (
            f"outcome corrected  {slug} -> {values['status']}\n"
            f"  supersedes  {event_id}")}
    finally:
        for path in response_paths:
            if os.path.isfile(path):
                os.unlink(path)


def _text_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or '').splitlines() if item.strip()]


def record_hypothesis(job_id, cause, confidence, note, author,
                      evidence_for=None, evidence_against=None,
                      hypothesis_id=None, status='OPEN', company_context=None,
                      profile_factors=None, other_factors=None, unknowns=None):
    """Create or revise an explicitly labelled rejection hypothesis."""
    slug = store.resolve_job(job_id)
    cause = str(cause or '').strip().upper() or None
    hypothesis_id = str(hypothesis_id or '').strip() or None
    status = str(status or 'OPEN').strip().upper()
    if not hypothesis_id and cause not in learning.LESSON_TRANSFER:
        raise ValueError('Select a valid hypothesis category')
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as error:
        raise ValueError('Evidence support must be a number from 0 to 1') from error
    with _ACTION_LOCK, store.writer_lock():
        row = learning.record_hypothesis(
            slug, cause, confidence, str(note or '').strip(),
            str(author or '').strip(), _text_list(evidence_for),
            _text_list(evidence_against), hypothesis_id=hypothesis_id,
            status=status, company_context=_text_list(company_context),
            profile_factors=_text_list(profile_factors),
            other_factors=_text_list(other_factors), unknowns=_text_list(unknowns))
    return {'hypothesis': row, 'output': (
        f"hypothesis {row['id']} saved · {row['status']} · "
        f"{len(row.get('revisions') or [])} reasoning pass(es)")}
