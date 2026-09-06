"""Material candidate questions that must precede CV prose generation."""
import os
import re

from . import store


SCHEMA = 'joblooper.preflight.v1'


def binding_digest(record):
    """Hash the exact reviewed decision record, excluding only its timestamp.

    ``subject_sha256`` proves which questions were asked. The binding digest
    also proves the selected answers and reviewer, so later edits cannot remain
    silently valid for an existing plan.
    """
    record = record or {}
    fields = (
        '_schema', 'app_id', 'subject_sha256', 'questions', 'decision',
        'reviewer', 'note', 'answers',
    )
    return store.sha256_text(store.canonical_json({
        key: record.get(key) for key in fields
    }))


def legacy_questions(jd, mapping, identity):
    """Return the original v1 rows so historical signed records stay verifiable."""
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
            learning.relevant_lessons(jd, exclude_slug=current_slug, top=2,
                                      mapping=mapping), 1):
        # Three parts, kept apart: what is true of THIS job, where the concern
        # came from, and the one thing being asked. Merged into a paragraph --
        # with the internal cause name and the lesson's own system-facing
        # wording in it -- this read as a wall of jargon at the exact moment a
        # person has to make a decision.
        trigger = lesson.get('trigger') or 'this advert is similar to that one'
        rows.append({
            'id': f'PRIOR-REJECTION-{n}', 'kind': 'PRIOR_OUTCOME_CONTEXT',
            'finding': trigger[0].upper() + trigger[1:] + '.',
            'reason': (
                f"You noted this after applying to {lesson.get('company')}, and it "
                "was never confirmed by any employer: "
                f"“{lesson.get('summary')}”"),
            'question': 'Does anything change that for this job?',
            'lesson_id': lesson.get('hypothesis_id'),
            'lesson_app_id': lesson.get('app_id'),
        })
    for n, outcome in enumerate(
            learning.relevant_positive_outcomes(jd, exclude_slug=current_slug, top=2), 1):
        rows.append({
            'id': f'PRIOR-POSITIVE-{n}', 'kind': 'PRIOR_OUTCOME_CONTEXT',
            'finding': (
                f"A similar application to {outcome.get('company')} reached "
                f"{outcome.get('status')}."),
            'reason': ('That is an observation of what advanced. It does not prove '
                       'why the employer advanced it.'),
            'question': 'Reuse that verified positioning here?',
            'positive': True,
        })
    return rows


def _choice(value, label, consequence, completes=True, requires_note=False):
    return {
        'value': value, 'label': label, 'consequence': consequence,
        'completes_preflight': bool(completes),
        'requires_note': bool(requires_note),
    }


def questions(jd, mapping, identity):
    """Return decisions from known state instead of speculative fact questions."""
    requirements = {
        f"REQ-{row.get('n')}": row for row in mapping.get('requirements') or []}
    rows = []
    for legacy in legacy_questions(jd, mapping, identity):
        row_id = legacy.get('id')
        if row_id == 'IDENTITY':
            rows.append({
                'id': row_id, 'kind': 'POSITIONING',
                'title': 'Select the application identity',
                'question': legacy.get('question'),
                'options': [
                    _choice(value, str(value).replace('_', ' ').title(),
                            'Recompute the evidence map in this identity lane.')
                    for value in legacy.get('options') or []
                ],
            })
            continue
        if row_id in requirements:
            requirement = requirements[row_id]
            classification = requirement.get('match') or 'GAP'
            rows.append({
                'id': row_id, 'kind': 'KNOWN_GAP',
                'title': f"Requirement {requirement.get('n')} - {classification.title()} match",
                'classification': classification,
                'requirement_number': requirement.get('n'),
                'requirement': requirement.get('text'),
                'reason': requirement.get('note') or
                          'Approved truth does not directly evidence the full requirement.',
                'question': (
                    'Choose whether to proceed with this recorded fit risk. No missing '
                    'experience will be implied or invented.'),
                'options': [
                    _choice(
                        'PROCEED_WITH_RECORDED_GAP', 'Proceed with recorded gap',
                        'Continue without claiming the missing requirement.'),
                    _choice(
                        'ADD_NEW_EVIDENCE', 'I have new evidence',
                        'Stop here and update approved ground truth before generation.',
                        completes=False),
                ],
            })
            continue
        if legacy.get('kind') == 'CANDIDATE_CONTEXT':
            rows.append({
                **legacy, 'title': 'Confirm application-specific context',
                'options': [
                    _choice('CONFIRMED_FOR_APPLICATION', 'Confirmed for this application',
                            'Record this decision without promoting it to career truth.'),
                    _choice('NOT_CONFIRMED', 'Not confirmed',
                            'Proceed with the eligibility or availability risk visible.'),
                ],
            })
            continue
        if legacy.get('kind') == 'PRIOR_OUTCOME_CONTEXT' and legacy.get('positive'):
            rows.append({
                **legacy, 'title': 'A past application that advanced',
                'options': [
                    _choice('REUSE_POSITIONING', 'Yes — reuse the verified positioning',
                            'Carry the same verified framing into this application.'),
                    _choice('NOT_RELEVANT_HERE', 'No — this job is different enough',
                            'Continue without reusing it. No career fact changes.'),
                ],
            })
            continue
        if legacy.get('kind') == 'PRIOR_OUTCOME_CONTEXT':
            rows.append({
                **legacy, 'title': 'A concern you recorded earlier',
                'options': [
                    _choice('REVIEWED_NO_CHANGE', 'No — proceed with it recorded',
                            'Continue. The risk stays visible in Cautions and in '
                            'the application record.'),
                    # A judgement that a past concern does not apply to this job
                    # asserts no new career fact, so it may complete preflight --
                    # but it must say why, or it is indistinguishable from
                    # dismissing the signal out of hand.
                    _choice('NOT_APPLICABLE_HERE', 'It does not apply to this job',
                            'Record why, and stop raising it for this application.',
                            requires_note=True),
                    _choice('ADD_NEW_CONTEXT', 'I have evidence that closes it',
                            'Generation stops until that evidence is registered '
                            'and your career truth is signed again.',
                            completes=False, requires_note=True),
                ],
            })
            continue
        rows.append(legacy)
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


def _normalise_answers(rows, answers):
    if not isinstance(answers, dict):
        raise ValueError('structured preflight answers must be a JSON object')
    expected = {row.get('id'): row for row in rows}

    def decision_for(value):
        raw = value.get('decision') if isinstance(value, dict) else value
        return str(raw or '').strip()

    missing = [row_id for row_id in expected
               if not decision_for(answers.get(row_id))]
    if missing:
        raise ValueError('answer every preflight decision: ' + ', '.join(missing))
    normalised = {}
    for row_id, row in expected.items():
        supplied = answers.get(row_id)
        decision = decision_for(supplied)
        note = str(supplied.get('note') or '').strip() if isinstance(supplied, dict) else ''
        options = {str(option.get('value')): option
                   for option in row.get('options') or []
                   if isinstance(option, dict)}
        if decision not in options:
            raise ValueError(f'{row_id} has an unsupported decision')
        if options[decision].get('requires_note') and len(note) < 8:
            raise ValueError(f'{row_id} requires a brief reason for this decision')
        if not options[decision].get('completes_preflight', True):
            if decision == 'ADD_NEW_EVIDENCE':
                raise ValueError(
                    f'{row_id} requires a ground-truth evidence update and renewed user approval')
            raise ValueError(f'{row_id} requires clarification before preflight can complete')
        normalised[row_id] = {'decision': decision}
        if note:
            normalised[row_id]['note'] = note
    return normalised


def selected_learning_signals(record, lessons):
    """Return only lessons the user kept applicable to this application."""
    answers = (record or {}).get('answers') or {}
    disposition = {}
    for row in (record or {}).get('questions') or []:
        lesson_key = (row.get('lesson_app_id'), row.get('lesson_id'))
        if not all(lesson_key):
            continue
        answer = answers.get(row.get('id')) or {}
        decision = (answer.get('decision') if isinstance(answer, dict) else answer)
        disposition[lesson_key] = str(decision or '')
    return [lesson for lesson in (lessons or [])
            if disposition.get((lesson.get('app_id'), lesson.get('hypothesis_id')))
            != 'NOT_APPLICABLE_HERE']


def create(slug, jd, mapping, identity, reviewer=None, note=None, answers=None):
    rows = questions(jd, mapping, identity)
    structured_answers = None
    if rows and answers is not None:
        structured_answers = _normalise_answers(rows, answers)
    if rows and not str(reviewer or '').strip():
        raise ValueError('material decisions require an identified user reviewer')
    if rows and structured_answers is None and not str(note or '').strip():
        raise ValueError(
            'material decisions require structured answers or a reviewed legacy context note')
    record = {
        '_schema': SCHEMA, 'app_id': slug, 'created_at': store.now(),
        'subject_sha256': subject(jd, mapping, identity, rows),
        'questions': rows,
        'decision': (('STRUCTURED_DECISIONS_RECORDED' if structured_answers is not None
                      else 'USER_CONTEXT_REVIEWED')
                     if rows else 'NO_MATERIAL_QUESTIONS'),
        'reviewer': str(reviewer or 'deterministic-preflight').strip(),
        'note': str(note or 'No material candidate question was identified.').strip(),
    }
    if structured_answers is not None:
        record['answers'] = structured_answers
    record['binding_sha256'] = binding_digest(record)
    existing = store.read_json(path(slug), {}) or {}
    comparable = ('_schema', 'app_id', 'subject_sha256', 'questions', 'decision',
                  'reviewer', 'note', 'answers')
    event = {
        'event': 'PREFLIGHT_RECORDED', 'app_id': slug,
        'subject_sha256': record['subject_sha256'],
        'binding_sha256': record['binding_sha256'],
        'decision': record['decision'], 'reviewer': record['reviewer'],
        'decision_count': len(rows),
    }
    event_exists = any(
        row.get('event') == 'PREFLIGHT_RECORDED'
        and row.get('app_id') == slug
        and row.get('subject_sha256') == record['subject_sha256']
        for row in store.application_events())
    if all(existing.get(key) == record.get(key) for key in comparable):
        if not event_exists:
            store.append_application_event(event)
        return existing
    store.write_json(path(slug), record)
    store.append_application_event(event)
    return record


def validate(slug, jd, mapping, identity):
    rows = questions(jd, mapping, identity)
    record = store.read_json(path(slug), {}) or {}
    problems = []
    if record.get('_schema') != SCHEMA:
        problems.append('pre-generation review has not been completed')
        return record, problems, rows
    if (record.get('binding_sha256')
            and record.get('binding_sha256') != binding_digest(record)):
        problems.append('pre-generation decision record digest mismatch')
    current_subject = subject(jd, mapping, identity, rows)
    if record.get('subject_sha256') != current_subject:
        # Preserve exact historical packages created before decision controls
        # replaced prose-only questions. Nothing is rewritten in place.
        old_rows = legacy_questions(jd, mapping, identity)
        if record.get('subject_sha256') != subject(jd, mapping, identity, old_rows):
            problems.append('pre-generation review is stale relative to JD or approved truth')
            return record, problems, rows
    if rows and record.get('decision') not in {
            'USER_CONTEXT_REVIEWED', 'STRUCTURED_DECISIONS_RECORDED'}:
        problems.append('material candidate questions were not reviewed with the user')
    elif rows and record.get('decision') == 'STRUCTURED_DECISIONS_RECORDED':
        try:
            # Re-validate the full answer objects, notes included. Stripping the
            # note here made a saved NOT_APPLICABLE_HERE / ADD_NEW_CONTEXT
            # decision re-fail its own requires_note check, so a plan the user
            # legitimately completed read as permanently broken.
            _normalise_answers(rows, record.get('answers') or {})
        except ValueError as error:
            problems.append(str(error))
    elif not rows and record.get('decision') != 'NO_MATERIAL_QUESTIONS':
        problems.append('pre-generation no-question decision is invalid')
    return record, problems, rows


def to_markdown(jd, identity, rows):
    out = [f"# PRE-GENERATION REVIEW - {jd.get('company')} - {jd.get('title')}", '',
           f"**Proposed identity:** `{identity.get('primary')}`  ",
           '**Rule:** resolved facts are not re-asked. Known gaps require an explicit '
           'proceed-or-stop decision; no answer becomes career truth without evidence review.',
           '**Where to answer:** use the dashboard Preflight review. Chat is optional '
           'for clarification, not the system of record.', '']
    if not rows:
        out += ['No material candidate questions were identified.', '']
    else:
        for row in rows:
            out += [f"## {row['id']} - {row['kind']}", '']
            if row.get('requirement'):
                out += [row['requirement'], '',
                        f"**Recorded state:** {row.get('classification')}",
                        f"**Reason:** {row.get('reason')}", '']
            elif row.get('finding'):
                out += [f"**About this job:** {row['finding']}"]
                if row.get('reason'):
                    out += [f"**Where it came from:** {row['reason']}"]
                out += ['']
            out += [row.get('question') or '', '']
            for option in row.get('options') or []:
                if isinstance(option, dict):
                    out += [f"- **{option.get('label')}** - {option.get('consequence')}"]
            out += ['']
    return '\n'.join(out)
