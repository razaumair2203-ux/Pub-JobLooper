"""Versioned rejection hypotheses and cautious cross-application learning.

An outcome is evidence; an explanation is a hypothesis.  The system keeps the
two separate so a rejection cannot silently become career truth or alter a CV.
"""
import os

from . import release, store, vec


HYPOTHESIS_STATUSES = {'OPEN', 'RETAINED_PLAUSIBLE', 'CONFIRMED', 'DISMISSED'}
ROUND_STAGES = (
    'OBSERVATION', 'COMPETING_EXPLANATIONS', 'CHALLENGE', 'DISPOSITION')


def _application(slug):
    apps = store.applications()
    record = next((a for a in apps if a.get('app_id') == slug), None)
    return apps, record


def _save(slug, apps, record):
    rows = [a for a in apps if a.get('app_id') != slug] + [record]
    store.write_jsonl(store.p('index', 'applications.jsonl'), rows)
    store.write_json(os.path.join(store.job_dir(slug), 'outcome.json'), record)
    package = store.approved_dir(slug)
    if package:
        store.write_json(release.record_path(package, 'OUTCOME.json', create=True), record)


def _normalise_hypotheses(record):
    normal = []
    for n, item in enumerate(record.get('hypotheses') or [], 1):
        if item.get('id'):
            normal.append(item)
            continue
        timestamp = record.get('responded') or record.get('applied') or store.today()
        revision = {
            'at': timestamp, 'author': 'legacy',
            'confidence': item.get('conf', 0.5), 'note': item.get('note', ''),
            'evidence_for': [], 'evidence_against': [],
        }
        normal.append({
            'id': f"H{n:02d}", 'cause': item.get('cat', 'NO_SIGNAL'),
            'status': 'OPEN', 'confidence': item.get('conf', 0.5),
            'summary': item.get('note', ''), 'created_at': timestamp,
            'updated_at': timestamp, 'revisions': [revision],
        })
    record['hypotheses'] = normal
    return normal


def hypotheses(slug):
    _, record = _application(slug)
    return _normalise_hypotheses(record) if record else []


def record_hypothesis(slug, cause, confidence, note, author,
                      evidence_for=None, evidence_against=None,
                      hypothesis_id=None, status='OPEN', company_context=None,
                      profile_factors=None, other_factors=None, unknowns=None):
    """Add or revise one explanation without rewriting earlier reasoning."""
    if status not in HYPOTHESIS_STATUSES:
        raise ValueError(f"unknown hypothesis status {status!r}")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError('confidence must be between 0 and 1')
    if not author or not author.strip():
        raise ValueError('author is required')
    if not note or not note.strip():
        raise ValueError('a concise reasoning note is required')

    apps, record = _application(slug)
    if not record:
        raise ValueError('application has not been submitted/logged')
    hypotheses = _normalise_hypotheses(record)
    existing = next((h for h in hypotheses if h['id'] == hypothesis_id), None)
    if hypothesis_id and not existing:
        raise ValueError(f"unknown hypothesis {hypothesis_id!r}")
    if existing and cause and cause != existing['cause']:
        raise ValueError('cause is immutable; dismiss it and add a new hypothesis')

    prior_revisions = list((existing or {}).get('revisions') or [])
    stage_index = min(len(prior_revisions), len(ROUND_STAGES) - 1)
    stage = ROUND_STAGES[stage_index]
    signature = store.canonical_json({
        'note': str(note).strip(), 'evidence_for': list(evidence_for or []),
        'evidence_against': list(evidence_against or []),
        'company_context': list(company_context or []),
        'profile_factors': list(profile_factors or []),
        'other_factors': list(other_factors or []), 'unknowns': list(unknowns or []),
    })
    if any(revision.get('substance_sha256') == store.sha256_text(signature)
           for revision in prior_revisions):
        raise ValueError('reasoning revision adds no new information')
    resulting_rounds = len(prior_revisions) + 1
    if status in {'RETAINED_PLAUSIBLE', 'CONFIRMED'}:
        alternatives = [row for row in hypotheses
                        if row is not existing and row.get('status') != 'DISMISSED']
        if not alternatives:
            raise ValueError('retain/confirm only after recording a competing hypothesis')
        if resulting_rounds < 3:
            raise ValueError('retain/confirm only after three substantive reasoning passes')
        if not evidence_against or not unknowns:
            raise ValueError('third-pass disposition requires counterevidence and unknowns')
    if status == 'CONFIRMED' and not str(record.get('stated_reason') or '').strip():
        raise ValueError(
            'no explicit employer-stated reason is recorded; use RETAINED_PLAUSIBLE')

    now = store.now()
    revision = {
        'at': now, 'author': author.strip(), 'confidence': round(float(confidence), 2),
        'round': resulting_rounds, 'stage': stage,
        'note': note.strip(), 'evidence_for': list(evidence_for or []),
        'evidence_against': list(evidence_against or []),
        'company_context': list(company_context or []),
        'profile_factors': list(profile_factors or []),
        'other_factors': list(other_factors or []),
        'unknowns': list(unknowns or []),
        'substance_sha256': store.sha256_text(signature),
    }
    if existing:
        hypothesis = existing
        hypothesis['status'] = status
        hypothesis['confidence'] = revision['confidence']
        hypothesis['summary'] = revision['note']
        hypothesis['updated_at'] = now
        hypothesis.setdefault('revisions', []).append(revision)
        event = 'HYPOTHESIS_REVISED'
    else:
        used = [int(h['id'][1:]) for h in hypotheses
                if str(h.get('id', '')).startswith('H') and str(h['id'])[1:].isdigit()]
        hypothesis = {
            'id': f"H{max(used, default=0) + 1:02d}", 'cause': cause,
            'status': status, 'confidence': revision['confidence'],
            'summary': revision['note'], 'created_at': now, 'updated_at': now,
            'revisions': [revision],
        }
        hypotheses.append(hypothesis)
        event = 'HYPOTHESIS_ADDED'

    _save(slug, apps, record)
    package = store.approved_dir(slug)
    if package:
        store.append_jsonl(release.record_path(package, 'REASONING.jsonl', create=True), {
            'timestamp': now, 'event': event, 'hypothesis_id': hypothesis['id'],
            'cause': hypothesis['cause'], 'status': status,
            'confidence': hypothesis['confidence'], 'revision': revision,
        })
    store.append_application_event({
        'event': event, 'app_id': slug, 'hypothesis_id': hypothesis['id'],
        'cause': hypothesis['cause'], 'status': status,
        'confidence': hypothesis['confidence'], 'revision': revision,
    })
    if status in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
        store.append_application_event({
            'event': ('LEARNING_CONFIRMED' if status == 'CONFIRMED'
                      else 'LEARNING_RETAINED_PLAUSIBLE'), 'app_id': slug,
            'hypothesis_id': hypothesis['id'], 'cause': hypothesis['cause'],
            'confidence': hypothesis['confidence'], 'summary': hypothesis['summary'],
        })
    return hypothesis


def relevant_lessons(jd, exclude_slug=None, top=3):
    """Return scoped review signals, never automatic candidate truth."""
    bm = vec.job_index()
    if not bm:
        return []
    query = ' '.join([jd.get('company', ''), jd.get('title', '')]
                     + [r.get('text', '') for r in jd.get('requirements', [])])
    by_app = {a.get('app_id'): a for a in store.applications()
              if not a.get('exclude_from_analytics')}
    lessons = []
    for slug, similarity in bm.normed(query, top=12):
        if slug == exclude_slug:
            continue
        app = by_app.get(slug)
        if not app:
            continue
        for hypothesis in _normalise_hypotheses(app):
            if hypothesis.get('status') not in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
                continue
            lessons.append({
                'app_id': slug, 'company': app.get('company'), 'role': app.get('role'),
                'similarity': similarity, 'hypothesis_id': hypothesis['id'],
                'cause': hypothesis['cause'], 'confidence': hypothesis['confidence'],
                'status': hypothesis.get('status'),
                'summary': hypothesis.get('summary', ''),
                'last_revision': (hypothesis.get('revisions') or [{}])[-1],
            })
    return lessons[:top]


def confirmed_lessons():
    """Return every retained review signal with its source and evidence."""
    rows = []
    for app in store.applications():
        if app.get('exclude_from_analytics'):
            continue
        for hypothesis in _normalise_hypotheses(app):
            if hypothesis.get('status') in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
                rows.append({
                    'app_id': app.get('app_id'), 'company': app.get('company'),
                    'role': app.get('role'), **hypothesis,
                })
    return sorted(rows, key=lambda row: row.get('updated_at', ''), reverse=True)
