"""Deterministically correlate an employer response to one submitted case.

The resolver intentionally prefers refusal over a plausible guess.  An email
may identify an application by an exact job reference, or by both company and
role. The selected application must also have a verified submission receipt
bound to one immutable approved package; otherwise the system cannot truthfully
say which CV was sent.
"""
import datetime
import os
import re
import unicodedata

from . import release, store


_TITLE_STOP = {'a', 'an', 'and', 'at', 'for', 'in', 'job', 'of', 'role', 'the', 'to'}
_STATUS_PATTERNS = {
    'rejected': re.compile(
        r'\b(unsuccessful|not (?:be )?(?:progressed|progressing|selected)|'
        r'will not (?:be )?mov(?:e|ing) forward|regret to inform|'
        r'other candidates?|position (?:has been|is) filled|'
        r'unable to proceed with your application)\b', re.I),
    'interview': re.compile(r'\b(invite you (?:to|for) (?:an )?interview|schedule (?:an )?interview)\b', re.I),
    'offer': re.compile(r'\b(pleased to (?:make you an |extend an )?offer|offer of employment)\b', re.I),
}
_REASON_PATTERNS = (
    re.compile(r'\b(position (?:has been|is) filled)\b', re.I),
    re.compile(r'\b(selected|progressing|moving forward with) (?:another|other) candidates?\b', re.I),
    re.compile(r'\b(due to|because of)\b', re.I),
)


def _norm(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def _references(jd, raw=''):
    stable = ' '.join([jd.get('url') or '', jd.get('_slug') or ''])
    references = set(re.findall(r'(?<!\d)\d{6,}(?!\d)', stable))
    labelled = re.compile(
        r'\b(?:job|requisition|req|reference|vacancy)(?:\s+(?:id|number|no))?'
        r'\s*[:#-]?\s*(\d{6,})\b', re.I)
    references.update(match.group(1) for match in labelled.finditer(raw or ''))
    return sorted(references)


def _submitted_candidate(app, email_norm, email_raw):
    slug = app.get('app_id')
    d = store.job_dir(slug)
    jd = store.read_json(os.path.join(d, 'jd.json')) or {}
    jd_raw = store.read_text(os.path.join(d, 'jd.raw.md'))
    company = _norm(jd.get('company') or app.get('company'))
    title = _norm(jd.get('title') or app.get('role'))
    company_hit = bool(company and re.search(rf'\b{re.escape(company)}\b', email_norm))
    exact_title = bool(title and re.search(rf'\b{re.escape(title)}\b', email_norm))
    title_terms = [term for term in title.split() if term not in _TITLE_STOP]
    matched_terms = [term for term in title_terms if re.search(rf'\b{re.escape(term)}\b', email_norm)]
    title_terms_hit = (len(title_terms) >= 3
                       and len(matched_terms) / len(title_terms) >= 0.8)
    references = _references(jd, jd_raw)
    reference_hits = [ref for ref in references if re.search(rf'(?<!\d){ref}(?!\d)', email_raw)]

    manifest, package_errors = release.verify_release(slug)
    receipt, receipt_errors = release.verify_submission(slug)
    if (receipt or {}).get('mode') == 'user_confirmed_external_submission':
        # Exact selected sent files remain correlatable even when an unrelated,
        # unsent employer-facing file was changed later. The receipt preserves
        # that exception rather than laundering it into a clean approval.
        package_errors = list(receipt_errors)
    else:
        package_errors.extend(receipt_errors)
    if manifest and app.get('release_manifest_sha256') \
            and app['release_manifest_sha256'] != manifest.get('manifest_sha256'):
        package_errors.append('application index and approved manifest disagree')
    evidence = []
    if reference_hits:
        evidence.append('exact job reference ' + ', '.join(reference_hits))
    if company_hit:
        evidence.append('exact company')
    if exact_title:
        evidence.append('exact role title')
    elif title_terms_hit:
        evidence.append(f'role terms {len(matched_terms)}/{len(title_terms)}')
    return {
        'slug': slug, 'app': app, 'jd': jd, 'manifest': manifest,
        'package_errors': package_errors, 'reference_hits': reference_hits,
        'company_hit': company_hit, 'title_hit': exact_title or title_terms_hit,
        'evidence': evidence,
    }


def resolve(text, explicit_job=None):
    """Return one exact submitted application or a precise refusal."""
    if not str(text or '').strip():
        raise ValueError('employer response is empty')
    apps = [app for app in store.applications()
            if not app.get('test_record') and not app.get('exclude_from_analytics')]
    explicit_slug = None
    if explicit_job:
        explicit_slug = store.resolve_job(explicit_job)
        if not any(app.get('app_id') == explicit_slug for app in apps):
            raise ValueError(
                f'{explicit_slug} has no recorded submission; the sent CV cannot be identified')
    if not apps:
        raise ValueError('no submitted applications are recorded')

    email_norm = _norm(text)
    candidates = [_submitted_candidate(app, email_norm, text) for app in apps]
    if explicit_job:
        selected = next(candidate for candidate in candidates
                        if candidate['slug'] == explicit_slug)
        conflicts = [candidate for candidate in candidates
                     if candidate['slug'] != explicit_slug
                     and (candidate['reference_hits']
                          or (candidate['company_hit'] and candidate['title_hit']))]
        if conflicts and not (selected['reference_hits']
                              or (selected['company_hit'] and selected['title_hit'])):
            raise ValueError('explicit --job selection conflicts with identifiers for another application')
        selected['evidence'] = ['explicit user-selected application'] + selected['evidence']
    else:
        by_reference = [candidate for candidate in candidates if candidate['reference_hits']]
        if len(by_reference) == 1:
            selected = by_reference[0]
        elif len(by_reference) > 1:
            raise ValueError('the response matches job references for multiple submitted applications')
        else:
            qualified = [candidate for candidate in candidates
                         if candidate['company_hit'] and candidate['title_hit']]
            if len(qualified) != 1:
                if not qualified:
                    raise ValueError(
                        'cannot locate one submitted JD: no exact job reference or unique company-and-role match')
                keys = ', '.join(candidate['slug'] for candidate in qualified)
                raise ValueError('ambiguous response; multiple submitted applications match: ' + keys)
            selected = qualified[0]

    if selected['package_errors'] or not selected['manifest']:
        raise ValueError('matched application has no verifiable exact submitted package: '
                         + '; '.join(selected['package_errors'] or ['release not found']))
    return selected


def classify_status(text, explicit=None):
    if explicit:
        return explicit.lower()
    hits = [status for status, pattern in _STATUS_PATTERNS.items() if pattern.search(text or '')]
    if len(hits) != 1:
        raise ValueError('response status is ambiguous; specify --status rejected|interview|offer|progressed')
    return hits[0]


def stated_reason(text):
    """Return an employer sentence only when it contains an explicit reason signal."""
    sentences = [part.strip() for part in re.split(r'(?<=[.!?])\s+', text or '') if part.strip()]
    for sentence in sentences:
        if any(pattern.search(sentence) for pattern in _REASON_PATTERNS):
            return sentence[:600]
    return None


def ingest(text, explicit_job=None, explicit_status=None, received=None,
           latency=None, employer_reason=None):
    selected = resolve(text, explicit_job)
    status = classify_status(text, explicit_status)
    slug = selected['slug']
    d = store.job_dir(slug)
    response_path = os.path.join(d, 'responses.jsonl')
    raw_sha256 = store.sha256_text(text)
    existing = store.read_jsonl(response_path)
    duplicate = next((row for row in existing if row.get('raw_sha256') == raw_sha256), None)
    if duplicate:
        return selected, duplicate, True

    response_date = received or store.today()
    try:
        responded = datetime.date.fromisoformat(response_date)
    except (TypeError, ValueError):
        raise ValueError('response date must use YYYY-MM-DD')
    applied_raw = selected['app'].get('applied')
    try:
        applied = datetime.date.fromisoformat(applied_raw) if applied_raw else None
    except ValueError:
        raise ValueError('recorded submission date must use YYYY-MM-DD')
    if applied and responded < applied:
        raise ValueError('response date cannot precede the exact submission date')

    response_id = f"R{len(existing) + 1:03d}"
    reason = str(employer_reason or '').strip() or stated_reason(text)
    event = {
        '_schema': 'joblooper.employer-response.v1',
        'response_id': response_id, 'received': response_date,
        'raw_sha256': raw_sha256, 'raw_text': text,
        'status': status, 'employer_stated_reason': reason,
        'matched_app_id': slug, 'match_evidence': selected['evidence'],
        'submitted_manifest_sha256': selected['manifest']['manifest_sha256'],
        'submitted_package_id': selected['manifest'].get('package_id'),
    }
    store.append_jsonl(response_path, event)
    package = store.approved_dir(slug)
    if package:
        store.append_jsonl(release.record_path(package, 'RESPONSES.jsonl', create=True), event)

    apps = store.applications()
    app = next(row for row in apps if row.get('app_id') == slug)
    app['status'] = status
    app['responded'] = response_date
    app['responded_date_status'] = 'recorded'
    app['days'] = (responded - applied).days if applied else None
    app['response_latency'] = {
        'band': latency or 'unknown',
        'basis': 'user_reported' if latency else 'not_provided',
    }
    app['employer_response_id'] = response_id
    app['employer_response_sha256'] = raw_sha256
    if reason:
        app['stated_reason'] = reason
    store.write_jsonl(store.p('index', 'applications.jsonl'),
                      [row for row in apps if row.get('app_id') != slug] + [app])
    store.write_json(os.path.join(d, 'outcome.json'), app)
    if package:
        store.write_json(release.record_path(package, 'OUTCOME.json', create=True), app)
    store.append_application_event({
        'event': 'EMPLOYER_RESPONSE_INGESTED', 'app_id': slug,
        'response_id': response_id, 'raw_sha256': raw_sha256,
        'match_evidence': selected['evidence'],
        'submitted_manifest_sha256': selected['manifest']['manifest_sha256'],
    })
    store.append_application_event({
        'event': 'OUTCOME', 'app_id': slug, 'status': status,
        'responded': response_date, 'stated_reason': reason,
        'response_id': response_id, 'source': 'employer_response',
        'hypotheses': app.get('hypotheses', []),
    })
    return selected, event, False
