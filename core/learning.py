"""Versioned outcome evidence and cautious cross-application learning.

An outcome is evidence; an explanation is a hypothesis.  The system keeps the
two separate so a rejection cannot silently become career truth or alter a CV.
"""
import os

from . import release, store, vec


HYPOTHESIS_STATUSES = {'OPEN', 'RETAINED_PLAUSIBLE', 'CONFIRMED', 'DISMISSED'}
ROUND_STAGES = (
    'OBSERVATION', 'COMPETING_EXPLANATIONS', 'CHALLENGE', 'DISPOSITION')
NEGATIVE_OUTCOMES = {'rejected', 'ghosted'}
POSITIVE_OUTCOMES = {'interview', 'progressed', 'offer'}
MINIMUM_RELEVANT_SIMILARITY = 0.35

# An application's `status` field is its *current* state and is overwritten in
# place. The append-only event ledger is the only record of what it passed
# through, so a later rejection cannot erase an earlier interview.
MILESTONE_EVENTS = {
    'JOB_INGESTED': 'captured',
    'JOB_REKEYED': 'captured',
    'PREFLIGHT_RECORDED': 'preflight',
    'PLAN_CREATED': 'planned',
    'CV_PRESENTED_IN_CHAT': 'reviewed',
    'APPLICATION_BUNDLE_PRESENTED_IN_CHAT': 'reviewed',
    'PLAN_APPROVED': 'approved',
    'CANDIDATE_BUILT': 'built',
    'APPROVED_ARTEFACTS_BUILT': 'built',
    'SUBMITTED': 'applied',
    'APPLICATION_RECORDED': 'applied',
    'EXTERNAL_SUBMISSION_SEALED': 'applied',
    'EXTERNAL_SUBMISSION_CONFIRMED': 'applied',
}
MILESTONE_ORDER = (
    'captured', 'preflight', 'planned', 'reviewed', 'approved', 'built',
    'applied', 'interview', 'progressed', 'offer', 'rejected', 'ghosted',
    'withdrawn',
)
POSITIVE_RANK = {'offer': 3, 'interview': 2, 'progressed': 1}


def milestones_reached(app_ids, events=None, app=None):
    """Every stage this application has ever reached, in lifecycle order.

    Derived from the append-only ledger rather than the mutable latest status,
    so an application that reached interview and was later rejected still
    reports both. Milestones are additive history; they never rewrite `status`.
    """
    if isinstance(app_ids, str):
        app_ids = {app_ids}
    app_ids = {value for value in app_ids if value}
    reached = set()
    for event in (store.application_events() if events is None else events):
        if event.get('app_id') not in app_ids:
            continue
        stage = MILESTONE_EVENTS.get(event.get('event'))
        if stage:
            reached.add(stage)
        if event.get('event') == 'OUTCOME':
            status = str(event.get('status') or '').lower()
            if status in MILESTONE_ORDER:
                reached.add(status)
    if app:
        # Ledgers written before the event schema existed, and any outcome
        # recorded without a matching event, still count as reached.
        status = str(app.get('status') or '').lower()
        if status in MILESTONE_ORDER:
            reached.add(status)
        if _exact_submission(app):
            reached.add('applied')
    return [stage for stage in MILESTONE_ORDER if stage in reached]


def best_positive_milestone(milestones):
    """The strongest positive stage in a milestone list, or None."""
    positives = [stage for stage in milestones if stage in POSITIVE_RANK]
    return max(positives, key=POSITIVE_RANK.__getitem__) if positives else None


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


def _exact_submission(record):
    return (record.get('submission_mode') in {
                'exact_approved_artefact', 'user_confirmed_external_submission'}
            and bool(record.get('release_manifest_sha256'))
            and bool(record.get('cv_sha256') or record.get('cv_sha')))


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
    if not _exact_submission(record):
        raise ValueError('outcome learning requires one exact submitted CV and package manifest')
    if str(record.get('status') or '').lower() not in NEGATIVE_OUTCOMES:
        raise ValueError('rejection hypotheses are allowed only for rejected or ghosted applications')
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


def relevant_lessons(jd, exclude_slug=None, top=3, mapping=None):
    """Return scoped review signals, never automatic candidate truth.

    `mapping` is this application's requirement analysis. Given it, a lesson is
    selected because the situation it is about is present here; without it,
    selection falls back to advert similarity alone.
    """
    bm = vec.job_index()
    if not bm:
        return []
    query = ' '.join([jd.get('company', ''), jd.get('title', '')]
                     + [r.get('text', '') for r in jd.get('requirements', [])])
    by_app = {a.get('app_id'): a for a in store.applications()
              if not a.get('exclude_from_analytics')}
    context = transfer_context(jd, mapping)
    lessons = []
    for slug, app in by_app.items():
        if slug == exclude_slug or not _exact_submission(app):
            continue
        if str(app.get('status') or '').lower() not in NEGATIVE_OUTCOMES:
            continue
        similarity = _symmetric_similarity(bm, jd, slug, query)
        same_employer = (str(app.get('company') or '').strip().casefold()
                         == str(jd.get('company') or '').strip().casefold())
        for hypothesis in _normalise_hypotheses(app):
            if hypothesis.get('status') not in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
                continue
            applies, reason = lesson_applies(hypothesis.get('cause'), context)
            # A near-identical advert, or the same employer, is itself a reason
            # the situation recurs even when no structural trigger fired.
            if not applies and (same_employer
                                or similarity >= MINIMUM_RELEVANT_SIMILARITY):
                applies, reason = True, (
                    'this is another application to the same employer'
                    if same_employer else
                    f'this advert is {similarity:.0%} similar to that one')
            if not applies:
                continue
            lessons.append({
                'app_id': slug, 'company': app.get('company'), 'role': app.get('role'),
                'similarity': similarity, 'hypothesis_id': hypothesis['id'],
                'cause': hypothesis['cause'], 'confidence': hypothesis['confidence'],
                'status': hypothesis.get('status'),
                'summary': hypothesis.get('summary', ''),
                # Why this lesson reached this application. Shown to the user so
                # a carried-forward signal is never unexplained.
                'trigger': reason,
                'same_employer': same_employer,
                'last_revision': (hypothesis.get('revisions') or [{}])[-1],
            })
    # One lesson per cause. Without this, ten applications that each retained a
    # process lesson would bury preflight in ten restatements of it, and a queue
    # people scroll past teaches nothing.
    best_by_cause = {}
    for lesson in lessons:
        current = best_by_cause.get(lesson['cause'])
        if not current or (lesson['confidence'], lesson['similarity']) > (
                current['confidence'], current['similarity']):
            best_by_cause[lesson['cause']] = lesson
    ranked = sorted(best_by_cause.values(), key=lambda row: (
        # A lesson triggered by this advert's own properties outranks one that
        # applies to everything; specific guidance is worth more than general.
        LESSON_TRANSFER.get(row['cause'], (None, None))[0] is None,
        -row['confidence'], -row['similarity']))
    return ranked[:top]


def _trigger_named_platforms(context):
    names = context.get('named_platform_gaps') or []
    if not names:
        return None
    # Acronyms are the high-precision half of this signal: standards and
    # platforms read as IEC or GIS, while the capitalised-word sweep also picks
    # up fragments like "Builts" from "As-Builts". Lead with the ones a reader
    # will recognise, so the explanation earns its trust.
    ordered = sorted(names, key=lambda name: (not name.isupper(), name))
    return ('this advert also names ' + ', '.join(ordered[:3])
            + ', which no registered evidence covers')


def _trigger_hard_gate(context):
    named = _trigger_named_platforms(context)
    if named:
        return named
    count = context.get('hard_gaps') or 0
    return (f'this advert has {count} unresolved hard gate(s)') if count else None


def _trigger_bridging(context):
    count = context.get('bridging_count') or 0
    return (f'{count} mandatory requirement(s) here are answered by transfer '
            'rather than direct evidence') if count else None


def _trigger_profile(context):
    count = context.get('profile_gate_count') or 0
    return (f'this advert has {count} eligibility or language requirement(s)'
            ) if count else None


def _trigger_compensation(context):
    return ('this advert discusses compensation'
            if context.get('mentions_compensation') else None)


def _trigger_thin_coverage(context):
    coverage = context.get('coverage')
    return (f'evidence coverage here is {coverage:.0%}'
            if coverage is not None and coverage < 0.7 else None)


# What each retained cause is a lesson *about*, and therefore when it carries.
#
# A lesson has a scope, and it is usually stated in the lesson itself: "for
# every future portal submission" is unconditional, while "for future roles
# naming proprietary platforms or regulatory ecosystems" fires on a property of
# the next advert. Selecting instead on advert text similarity discarded that
# scope, and suppressed every process lesson the moment the next job was in a
# different sector -- which is exactly when a prior lesson is worth having.
#
# `None` means the lesson always applies. A trigger returning None means the
# situation it is about is not present here, so it stays silent.
LESSON_TRANSFER = {
    'TIMING_INTERNAL': (None, 'applies to every submission'),
    'ATS_KEYWORD': (None, 'applies to every generated document'),
    'NARRATIVE_COHERENCE': (None, 'applies to every generated document'),
    'HARD_GATE': (_trigger_hard_gate, None),
    'DOMAIN_TRANSLATION': (_trigger_bridging, None),
    'SENIORITY_MISMATCH': (_trigger_bridging, None),
    'EVIDENCE_DEPTH': (_trigger_thin_coverage, None),
    'LOCATION_VISA': (_trigger_profile, None),
    'COMPENSATION': (_trigger_compensation, None),
    # A hypothesis retained under NO_SIGNAL says explicitly that nothing was
    # learned, so it has nothing to carry.
    'NO_SIGNAL': (False, None),
}


def transfer_context(jd, mapping=None):
    """The properties of a new application that a past lesson can be about."""
    mapping = mapping or {}
    text = ' '.join([str(jd.get('title') or '')]
                    + [str(row.get('text') or '')
                       for row in jd.get('requirements') or []]).lower()
    return {
        'hard_gaps': len(mapping.get('hard_gate_unresolved') or []),
        'named_platform_gaps': mapping.get('named_platform_gaps') or [],
        'profile_gate_count': mapping.get('profile_gate_count') or 0,
        'bridging_count': mapping.get('bridging_count') or 0,
        'coverage': mapping.get('coverage'),
        'mentions_compensation': any(
            word in text for word in ('salary', 'compensation', 'remuneration',
                                      'package', 'benefits')),
    }


def lesson_applies(cause, context):
    """Whether a retained cause is about the situation in hand, and why."""
    rule = LESSON_TRANSFER.get(str(cause or '').upper())
    if rule is None:
        return False, None
    trigger, always_reason = rule
    if trigger is None:
        return True, always_reason
    if trigger is False:
        return False, None
    reason = trigger(context)
    return (True, reason) if reason else (False, None)


def _symmetric_similarity(bm, jd, slug, query):
    """Similarity that does not depend on which advert asked the question.

    BM25 scores a query against documents, so A-to-B and B-to-A differ: one
    real pair here scored 0.350 one way and 0.314 the other, straddling the
    old cutoff. Whether a lesson transferred therefore depended on the order
    the jobs happened to be applied for.
    """
    forward = dict(bm.normed(query, top=24)).get(slug, 0.0)
    other = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'), {}) or {}
    reverse_query = ' '.join(
        [other.get('company', ''), other.get('title', '')]
        + [row.get('text', '') for row in other.get('requirements', [])])
    reverse = dict(bm.normed(reverse_query, top=24)).get(jd.get('_slug'), 0.0)
    return max(forward, reverse)


def relevant_positive_outcomes(jd, exclude_slug=None, top=3):
    """Return exact similar applications that advanced, without inferring why."""
    bm = vec.job_index()
    if not bm:
        return []
    query = ' '.join([jd.get('company', ''), jd.get('title', '')]
                     + [r.get('text', '') for r in jd.get('requirements', [])])
    by_app = {a.get('app_id'): a for a in store.applications()
              if not a.get('exclude_from_analytics')}
    events = store.application_events()
    rows = []
    for slug, similarity in bm.normed(query, top=12):
        if slug == exclude_slug or similarity < MINIMUM_RELEVANT_SIMILARITY:
            continue
        app = by_app.get(slug)
        if not app or not _exact_submission(app):
            continue
        # Read the reached stage from the ledger: an application that was
        # interviewed and later rejected still evidences that it advanced.
        milestones = milestones_reached(slug, events, app)
        reached = best_positive_milestone(milestones)
        if not reached:
            continue
        current = str(app.get('status') or '').lower()
        observation = (f"The exact submitted application reached {reached}; "
                       "the employer's causal reasoning is unknown.")
        if current and current != reached:
            observation = (f"The exact submitted application reached {reached} and "
                           f"its latest recorded status is {current}; "
                           "the employer's causal reasoning is unknown.")
        rows.append({
            'app_id': slug, 'company': app.get('company'), 'role': app.get('role'),
            'similarity': similarity, 'status': reached,
            'current_status': current or None, 'milestones': milestones,
            'responded': app.get('responded'), 'days': app.get('days'),
            'identity': app.get('identity'), 'coverage': app.get('coverage'),
            'submitted_manifest_sha256': app.get('release_manifest_sha256'),
            'observation': observation,
        })
    rows.sort(key=lambda row: (-row['similarity'], -POSITIVE_RANK[row['status']],
                               str(row.get('responded') or '')))
    return rows[:top]


def confirmed_lessons():
    """Return every retained review signal with its source and evidence."""
    rows = []
    for app in store.applications():
        if (app.get('exclude_from_analytics') or not _exact_submission(app)
                or str(app.get('status') or '').lower() not in NEGATIVE_OUTCOMES):
            continue
        for hypothesis in _normalise_hypotheses(app):
            if hypothesis.get('status') in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
                rows.append({
                    'app_id': app.get('app_id'), 'company': app.get('company'),
                    'role': app.get('role'), **hypothesis,
                })
    return sorted(rows, key=lambda row: row.get('updated_at', ''), reverse=True)
