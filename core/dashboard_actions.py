"""Allowlisted deterministic mutations initiated by the local dashboard."""
import base64
import binascii
import datetime
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

from . import job_fetch, learning, release, store


_ACTION_LOCK = threading.Lock()
FEEDBACK_SCOPES = {'content', 'format', 'workflow', 'truth', 'rule'}
OUTCOME_STATES = {'rejected', 'interview', 'offer', 'progressed', 'ghosted', 'withdrawn'}
LATENCY_BANDS = {'under_24h', '1_3d', '4_7d', '8_30d', 'over_30d', 'unknown'}
SCREENING_EXTENSIONS = {'.pdf', '.txt', '.md', '.json', '.html', '.png', '.jpg',
                        '.jpeg', '.webp'}
MAX_SCREENING_BYTES = 8 * 1024 * 1024


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


def ingest(raw, company, title, url=None):
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
    return result


def ingest_url(url):
    """Extract and capture a public advert without asking for duplicate fields."""
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


def record_feedback(job_id, scope, note, author='dashboard-user'):
    scope = str(scope or '').strip().lower()
    note = str(note or '').strip()
    if scope not in FEEDBACK_SCOPES:
        raise ValueError('Select a valid feedback scope')
    if not note:
        raise ValueError('Feedback cannot be empty')
    if len(note) > 8000:
        raise ValueError('Feedback exceeds the 8,000-character limit')
    result = _run_cli([
        'feedback', job_id, '--scope', scope, '--note', note,
        '--author', str(author or 'dashboard-user')[:200],
    ], timeout=60)
    if not result['ok']:
        raise ValueError(result['output'] or 'Feedback could not be recorded')
    return result


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
        content = release.presentation_content(slug)
        record, errors = release.validate_presentation(slug)
    except ValueError as error:
        return {'available': False, 'content': None, 'valid': False,
                'errors': [str(error)]}
    return {
        'available': True,
        'content': content,
        'valid': bool(record and not errors),
        'errors': errors,
        'content_sha256': store.sha256_text(content),
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
    approved = _run_cli([
        'approve', job_id, '--reviewer', reviewer, '--all-pass', '--user-signoff',
        '--note', 'Explicit approval recorded through the local dashboard',
    ], timeout=90)
    if not approved['ok']:
        raise ValueError(approved['output'] or 'Approval was refused')
    arguments = ['build', job_id]
    if no_pdf:
        arguments.append('--no-pdf')
    built = _run_cli(arguments, timeout=300)
    if not built['ok']:
        raise ValueError(built['output'] or 'Build was refused')
    return {'ok': True, 'output': approved['output'] + '\n\n' + built['output']}


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


def record_submission(job_id, sent_file, cover_letter_file=None, channel='portal',
                      applied_date=None, screening=None):
    if not sent_file:
        raise ValueError('Select the exact CV that was actually submitted')
    screening_path = None
    try:
        screening_path = _screening_file(screening)
        arguments = ['submit', job_id, '--sent-file', sent_file]
        if cover_letter_file:
            arguments += ['--cover-letter-file', cover_letter_file]
        if channel:
            arguments += ['--channel', str(channel)[:100]]
        if applied_date:
            arguments += ['--date', applied_date]
        if screening_path:
            arguments += ['--screening-file', screening_path]
        result = _run_cli(arguments, timeout=90)
    finally:
        if screening_path and os.path.isfile(screening_path):
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
    screening_path = None
    try:
        screening_path = _screening_file(screening)
        arguments = ['update-submission', job_id]
        if applied_date:
            arguments += ['--date', applied_date]
        if channel:
            arguments += ['--channel', channel]
        if screening_path:
            arguments += ['--screening-file', screening_path]
        if screening_unavailable:
            arguments.append('--screening-unavailable')
        result = _run_cli(arguments, timeout=90)
    finally:
        if screening_path and os.path.isfile(screening_path):
            os.unlink(screening_path)
    if not result['ok']:
        raise ValueError(result['output'] or 'Submission metadata could not be updated')
    return result


def record_outcome(job_id, status, response_date=None, latency=None,
                   employer_reason=None, response_text=None):
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
    if response_text and status not in {'rejected', 'interview', 'offer', 'progressed'}:
        raise ValueError('Exact response ingestion supports rejected, interview, offer or progressed')

    outputs = []
    response_path = None
    try:
        if response_text:
            with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', prefix='joblooper-response-',
                    encoding='utf-8', delete=False) as stream:
                stream.write(response_text)
                response_path = stream.name
            captured = _run_cli([
                'response', response_path, '--job', slug, '--status', status,
                '--date', response_date,
            ], timeout=90)
            if not captured['ok']:
                raise ValueError(captured['output'] or 'Employer response could not be correlated')
            outputs.append(captured['output'])

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
        outputs.append(observed['output'])
    finally:
        if response_path and os.path.isfile(response_path):
            os.unlink(response_path)
    return {'ok': True, 'output': '\n\n'.join(part for part in outputs if part)}
