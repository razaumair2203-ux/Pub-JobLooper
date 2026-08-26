"""Material candidate questions that must precede CV prose generation."""
import os
import re

from . import store


SCHEMA = 'joblooper.preflight.v1'


def questions(jd, mapping, identity):
    rows = []
    ranked = identity.get('ranked') or []
    top = ranked[0][1] if ranked else 0.0
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if (not identity.get('overridden') and len(ranked) > 1
            and (top <= 0 or top - second < 0.15)):
        rows.append({
            'id': 'IDENTITY', 'kind': 'POSITIONING',
            'question': ('Which reviewed identity lane best represents this application? '
                         'The deterministic ranking is absent or materially tied.'),
            'options': [name for name, _ in ranked],
        })
    for requirement in mapping.get('requirements') or []:
        if not (requirement.get('hard_gate') or requirement.get('kind') == 'mandatory'):
            continue
        if requirement.get('match') in {'DIRECT', 'BEHAVIOURAL'}:
            continue
        rows.append({
            'id': f"REQ-{requirement.get('n')}", 'kind': 'EVIDENCE_OR_ELIGIBILITY',
            'classification': requirement.get('match'),
            'question': (
                f"Do you have verified, currently unregistered evidence for: "
                f"{requirement.get('text')} If yes, update and reapprove ground truth; "
                "otherwise explicitly proceed with the recorded gap."),
        })
    jd_text = ' '.join([jd.get('title', '')]
                       + [row.get('text', '') for row in jd.get('requirements') or []])
    profile = store.profile()
    open_question = str((((profile.get('location') or {})
                          .get('work_authorisation') or {}).get('_open_question') or '')).strip()
    if open_question and re.search(r'\b(availability|available|notice|start date|join)\b',
                                   jd_text, re.I):
        rows.append({'id': 'PROFILE-AVAILABILITY', 'kind': 'CANDIDATE_CONTEXT',
                     'question': open_question})
    # Outcome history is contextual evidence, never candidate truth. Surface it
    # before prose generation so the user can challenge a recurring risk or
    # decide whether verified evidence from an advancing package deserves reuse.
    from . import learning
    current_slug = jd.get('_slug')
    for n, lesson in enumerate(
            learning.relevant_lessons(jd, exclude_slug=current_slug, top=2), 1):
        rows.append({
            'id': f'PRIOR-REJECTION-{n}', 'kind': 'PRIOR_OUTCOME_CONTEXT',
            'question': (
                f"A {lesson['similarity']:.2f}-similar application to "
                f"{lesson.get('company')} retained the {lesson.get('cause')} hypothesis: "
                f"{lesson.get('summary')} Review whether new evidence changes this risk; "
                "do not treat the hypothesis as an employer-stated fact."),
        })
    for n, outcome in enumerate(
            learning.relevant_positive_outcomes(jd, exclude_slug=current_slug, top=2), 1):
        rows.append({
            'id': f'PRIOR-POSITIVE-{n}', 'kind': 'PRIOR_OUTCOME_CONTEXT',
            'question': (
                f"A {outcome['similarity']:.2f}-similar exact application to "
                f"{outcome.get('company')} reached {outcome.get('status')}. Review whether "
                "its verified positioning remains relevant here; the outcome does not prove why it advanced."),
        })
    return rows


def subject(jd, mapping, identity, rows):
    value = {
        'jd': jd, 'mapping_classes': [
            {'n': row.get('n'), 'match': row.get('match'),
             'hard_gate': row.get('hard_gate'), 'kind': row.get('kind')}
            for row in mapping.get('requirements') or []],
        'identity': identity, 'questions': rows,
        'truth_subject_sha256': store.truth_approval_subject()['sha256'],
    }
    return store.sha256_text(store.canonical_json(value))


def path(slug):
    return os.path.join(store.job_dir(slug), 'preflight.json')


def create(slug, jd, mapping, identity, reviewer=None, note=None):
    rows = questions(jd, mapping, identity)
    if rows and (not str(reviewer or '').strip() or not str(note or '').strip()):
        raise ValueError('material questions require user review, reviewer and context note')
    record = {
        '_schema': SCHEMA, 'app_id': slug, 'created_at': store.now(),
        'subject_sha256': subject(jd, mapping, identity, rows),
        'questions': rows,
        'decision': ('USER_CONTEXT_REVIEWED' if rows else 'NO_MATERIAL_QUESTIONS'),
        'reviewer': str(reviewer or 'deterministic-preflight').strip(),
        'note': str(note or 'No material candidate question was identified.').strip(),
    }
    store.write_json(path(slug), record)
    return record


def validate(slug, jd, mapping, identity):
    rows = questions(jd, mapping, identity)
    record = store.read_json(path(slug), {}) or {}
    problems = []
    if record.get('_schema') != SCHEMA:
        problems.append('pre-generation review has not been completed')
    elif record.get('subject_sha256') != subject(jd, mapping, identity, rows):
        problems.append('pre-generation review is stale relative to JD or approved truth')
    elif rows and record.get('decision') != 'USER_CONTEXT_REVIEWED':
        problems.append('material candidate questions were not reviewed with the user')
    elif not rows and record.get('decision') != 'NO_MATERIAL_QUESTIONS':
        problems.append('pre-generation no-question decision is invalid')
    return record, problems, rows


def to_markdown(jd, identity, rows):
    out = [f"# PRE-GENERATION REVIEW — {jd.get('company')} · {jd.get('title')}", '',
           f"**Proposed identity:** `{identity.get('primary')}`  ",
           '**Rule:** ask only questions that can change evidence, eligibility or '
           'positioning; answers never become truth without evidence review.', '']
    if not rows:
        out += ['No material candidate questions were identified.', '']
    else:
        for row in rows:
            out += [f"## {row['id']} · {row['kind']}", '', row['question'], '']
    return '\n'.join(out)
