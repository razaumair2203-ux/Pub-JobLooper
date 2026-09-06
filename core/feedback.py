"""Append-only user review feedback with explicit resolution.

Feedback is neither career truth nor an automatic prompt mutation.  It becomes
an actionable review gate: an open item blocks sign-off, and every feedback
event invalidates an earlier complete-review presentation so the user sees the result of
the decision before documents can be rendered.
"""
from . import store


SCOPES = {'CONTENT', 'FORMAT', 'WORKFLOW', 'TRUTH', 'RULE'}
RESOLUTIONS = {'ADOPTED', 'REJECTED'}
CLASSIFICATIONS = {
    'APPLICATION_WORDING', 'FACTUAL_CORRECTION', 'REUSABLE_PREFERENCE',
    'WORKFLOW_REQUEST', 'REJECTION',
}
DECISIONS = {'ACCEPT', 'EDIT', 'REJECT', 'DEFER'}


def _path():
    return store.p('index', 'review_feedback.jsonl')


def events(slug=None):
    rows = store.read_jsonl(_path())
    return [row for row in rows if slug is None or row.get('app_id') == slug]


def current(slug=None):
    """Fold append-only events into current feedback state."""
    state = {}
    for event in events(slug):
        fid = event.get('feedback_id')
        if not fid:
            continue
        if event.get('event') == 'FEEDBACK_OPENED':
            state[fid] = {
                'id': fid, 'app_id': event.get('app_id'),
                'scope': event.get('scope'), 'note': event.get('note'),
                'author': event.get('author'), 'status': 'OPEN',
                'opened_at': event.get('timestamp'),
                'plan_sha256': event.get('plan_sha256'),
                'classification': event.get('classification'),
                'target_id': event.get('target_id'),
                'target_artifact': event.get('target_artifact'),
                'target_sha256': event.get('target_sha256'),
                'section': event.get('section'),
                'selected_text': event.get('selected_text'),
                'requested_scope': event.get('requested_scope'),
                'truth_sha256': event.get('truth_sha256'),
                'preference_type': event.get('preference_type'),
                'preference_value': event.get('preference_value'),
            }
        elif event.get('event') == 'FEEDBACK_PROPOSED' and fid in state:
            state[fid].update({
                'status': 'PROPOSED', 'proposal_id': event.get('proposal_id'),
                'proposed_at': event.get('timestamp'),
                'before_text': event.get('before_text'),
                'after_text': event.get('after_text'),
                'evidence': event.get('evidence') or [],
                'affected_documents': event.get('affected_documents') or [],
                'proposal_sha256': event.get('proposal_sha256'),
            })
        elif event.get('event') == 'FEEDBACK_DECIDED' and fid in state:
            decision = event.get('decision')
            state[fid].update({
                'status': ({'ACCEPT': 'ACCEPTED_PENDING_REPLAN',
                            'EDIT': 'ACCEPTED_PENDING_REPLAN',
                            'REJECT': 'REJECTED', 'DEFER': 'DEFERRED'}.get(
                                decision, state[fid].get('status'))),
                'decision': decision, 'decided_at': event.get('timestamp'),
                'decision_note': event.get('note'),
                'after_text': event.get('after_text', state[fid].get('after_text')),
                'proposal_sha256': event.get(
                    'proposal_sha256', state[fid].get('proposal_sha256')),
            })
        elif event.get('event') == 'FEEDBACK_APPLIED' and fid in state:
            state[fid].update({
                'status': 'ADOPTED', 'resolved_at': event.get('timestamp'),
                'implementation': event.get('implementation'),
                'validation': event.get('validation'),
                'change_receipt': event.get('change_receipt'),
            })
        elif event.get('event') == 'FEEDBACK_RESOLVED' and fid in state:
            state[fid].update({
                'status': event.get('status'),
                'resolved_at': event.get('timestamp'),
                'implementation': event.get('implementation'),
                'validation': event.get('validation'),
            })
    return [state[key] for key in sorted(state)]


def digest(slug):
    """Fingerprint the complete review conversation for freshness checks."""
    return store.sha256_text(store.canonical_json(events(slug)))


def open_items(slug):
    return [item for item in current(slug) if item.get('status') in {
        'OPEN', 'PROPOSED', 'ACCEPTED_PENDING_REPLAN'}]


def validate_record(scope, note):
    """Validate an open-feedback command without mutating lifecycle state."""
    scope = str(scope or '').upper()
    if scope not in SCOPES:
        raise ValueError('scope must be one of ' + ', '.join(sorted(SCOPES)))
    if not str(note or '').strip():
        raise ValueError('feedback note is required')
    return scope, str(note).strip()


def record(slug, scope, note, author='user', plan_sha256=None,
           classification=None, target=None, requested_scope='THIS_APPLICATION',
           preference_type=None, preference_value=None):
    scope, note = validate_record(scope, note)
    used = [int(item['id'][1:]) for item in current()
            if item.get('id', '').startswith('F') and item['id'][1:].isdigit()]
    fid = f"F{max(used, default=0) + 1:04d}"
    classification = str(classification or '').upper() or None
    if classification and classification not in CLASSIFICATIONS:
        raise ValueError('feedback classification is invalid')
    if classification == 'APPLICATION_WORDING' and not target:
        raise ValueError('application wording feedback needs an exact document target')
    if classification == 'REUSABLE_PREFERENCE':
        from . import preferences
        preference_type = str(preference_type or '').upper()
        preference_value = str(preference_value or '').lower()
        if (preference_type not in preferences.TYPES
                or preference_value not in preferences.TYPES[preference_type]):
            raise ValueError('reusable feedback needs a supported preference control')
    event = {
        'timestamp': store.now(), 'event': 'FEEDBACK_OPENED',
        'feedback_id': fid, 'app_id': slug, 'scope': scope,
        'note': note, 'author': str(author or 'user').strip(),
        'plan_sha256': plan_sha256,
        'classification': classification,
        'requested_scope': str(requested_scope or 'THIS_APPLICATION').upper(),
        'truth_sha256': store.truth_approval_subject()['sha256'],
        'preference_type': preference_type,
        'preference_value': preference_value,
    }
    if target:
        event.update({
            'target_id': target.get('id'),
            'target_artifact': target.get('artifact'),
            'target_sha256': target.get('sha256'),
            'section': target.get('section'),
            'selected_text': target.get('text'),
        })
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return current(slug)[-1]


def _target_id(slug, artifact, section, text, anchors):
    subject = {
        'app_id': slug, 'artifact': artifact, 'section': section,
        'text': text, 'anchors': sorted(anchor for anchor in anchors if anchor),
    }
    return 'DT-' + store.sha256_text(store.canonical_json(subject))[:16]


def document_targets(slug):
    """Return stable selectable CV lines and source-authorized alternatives."""
    cv = store.read_json(store.p('work', slug, 'cv.json')) or store.read_json(
        store.p('jobs', slug, 'cv.json')) or {}
    if not cv:
        return []
    from . import disclosure, language
    by_id, _ = store.generation_anchors()
    output_language = (store.profile().get('output') or {}).get('language', 'en-US')
    boundaries = store.boundaries()
    rows = []

    def add(section, text, anchors):
        anchors = [anchor for anchor in anchors if anchor in by_id]
        alternatives = []
        for anchor_id in anchors:
            for candidate in (by_id[anchor_id].get('bullet') or {}).values():
                candidate = language.localize(
                    disclosure.externalize(candidate, boundaries), output_language)
                if candidate and candidate not in alternatives:
                    alternatives.append(candidate)
        if text and text not in alternatives:
            alternatives.insert(0, text)
        target_id = _target_id(slug, 'cv', section, text, anchors)
        rows.append({
            'id': target_id, 'artifact': 'cv', 'section': section,
            'text': text, 'anchors': anchors, 'alternatives': alternatives,
            'sha256': store.sha256_text(store.canonical_json({
                'plan_sha256': _plan_sha(slug), 'target_id': target_id,
                'text': text, 'alternatives': alternatives,
            })),
        })

    for section in cv.get('sections') or []:
        section_name = section.get('name')
        for item in section.get('items') or []:
            if section.get('type') == 'experience':
                for bullet in item.get('bullets') or []:
                    add(section_name, bullet.get('text'),
                        bullet.get('anchors') or [bullet.get('anchor')])
            else:
                add(section_name, item.get('text'),
                    item.get('anchors') or [item.get('anchor')])
    return rows


def _plan_sha(slug):
    # Imported lazily: release imports feedback.
    from . import release
    return release.plan_digest(slug)


def target(slug, target_id):
    return next((row for row in document_targets(slug)
                 if row.get('id') == target_id), None)


def propose(slug, feedback_id, after_text):
    item = next((row for row in current(slug) if row['id'] == feedback_id), None)
    if not item or item.get('status') != 'OPEN':
        raise ValueError('Select an open feedback item')
    if item.get('classification') != 'APPLICATION_WORDING':
        raise ValueError('Only application-wording feedback uses a document change proposal')
    current_target = target(slug, item.get('target_id'))
    if not current_target or current_target.get('sha256') != item.get('target_sha256'):
        raise ValueError('The selected document sentence is stale; reopen feedback from the current plan')
    after_text = str(after_text or '').strip()
    if after_text == current_target['text']:
        raise ValueError('The proposal does not change the selected sentence')
    if after_text not in current_target['alternatives']:
        raise ValueError(
            'Replacement must be a source-authorized wording variant for the same evidence')
    proposal_id = 'FP-' + store.sha256_text(
        feedback_id + current_target['sha256'] + after_text)[:16]
    proposal = {
        'feedback_id': feedback_id, 'proposal_id': proposal_id,
        'before_text': current_target['text'], 'after_text': after_text,
        'target_id': current_target['id'], 'target_sha256': current_target['sha256'],
        'evidence': current_target['anchors'],
        'affected_documents': ['cv', 'cover_letter'],
    }
    proposal['proposal_sha256'] = store.sha256_text(store.canonical_json(proposal))
    event = {'timestamp': store.now(), 'event': 'FEEDBACK_PROPOSED',
             'app_id': slug, **proposal}
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(row for row in current(slug) if row['id'] == feedback_id)


def decide(slug, feedback_id, decision, note='', edited_text=None):
    item = next((row for row in current(slug) if row['id'] == feedback_id), None)
    decision = str(decision or '').upper()
    if not item or item.get('status') not in {'OPEN', 'PROPOSED'}:
        raise ValueError('Select feedback that is awaiting a decision')
    if decision not in DECISIONS:
        raise ValueError('Select accept, edit, reject or defer')
    note = str(note or '').strip()
    if decision in {'REJECT', 'DEFER'} and len(note) < 8:
        raise ValueError('Rejected or deferred feedback needs a brief reason')
    if decision in {'ACCEPT', 'EDIT'}:
        if item.get('status') != 'PROPOSED':
            raise ValueError('Accept or edit only after reviewing a before/after proposal')
        after_text = str(edited_text or item.get('after_text') or '').strip()
        current_target = target(slug, item.get('target_id'))
        if not current_target or after_text not in current_target['alternatives']:
            raise ValueError('Edited replacement is not an authorized variant for this evidence')
        proposal = {
            'feedback_id': feedback_id, 'proposal_id': item.get('proposal_id'),
            'before_text': item.get('before_text'), 'after_text': after_text,
            'target_id': item.get('target_id'), 'target_sha256': item.get('target_sha256'),
            'evidence': item.get('evidence') or [],
            'affected_documents': item.get('affected_documents') or [],
        }
        proposal_sha = store.sha256_text(store.canonical_json(proposal))
    else:
        after_text = None
        proposal_sha = item.get('proposal_sha256')
    event = {
        'timestamp': store.now(), 'event': 'FEEDBACK_DECIDED',
        'feedback_id': feedback_id, 'app_id': slug, 'decision': decision,
        'note': note, 'after_text': after_text,
        'proposal_sha256': proposal_sha,
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(row for row in current(slug) if row['id'] == feedback_id)


def accepted_overrides(slug):
    return [row for row in current(slug)
            if row.get('status') == 'ACCEPTED_PENDING_REPLAN'
            and row.get('classification') == 'APPLICATION_WORDING']


def apply_cv(slug, cv):
    """Apply accepted exact-text replacements to a newly assembled CV."""
    changes = []
    for item in accepted_overrides(slug):
        found = 0
        for section in cv.get('sections') or []:
            if section.get('name') != item.get('section'):
                continue
            for row in section.get('items') or []:
                leaves = row.get('bullets') or [row]
                for leaf in leaves:
                    if leaf.get('text') == item.get('before_text'):
                        leaf['text'] = item.get('after_text')
                        found += 1
        if found != 1:
            raise ValueError(
                f"{item['id']} target was found {found} times in the regenerated CV; "
                'the accepted change cannot be applied safely')
        changes.append({
            'feedback_id': item['id'], 'proposal_id': item.get('proposal_id'),
            'proposal_sha256': item.get('proposal_sha256'),
            'section': item.get('section'), 'before_text': item.get('before_text'),
            'after_text': item.get('after_text'), 'evidence': item.get('evidence') or [],
            'affected_documents': item.get('affected_documents') or [],
        })
    return changes


def record_applied(slug, changes, plan_sha256, validation):
    for change in changes:
        receipt = {
            '_schema': 'joblooper.feedback-change-receipt.v1',
            **change, 'plan_sha256': plan_sha256,
            'applied_at': store.now(), 'validation': validation,
        }
        receipt['receipt_sha256'] = store.sha256_text(store.canonical_json(receipt))
        event = {
            'timestamp': store.now(), 'event': 'FEEDBACK_APPLIED',
            'feedback_id': change['feedback_id'], 'app_id': slug,
            'implementation': ('Replaced the exact selected CV sentence with the '
                               'accepted source-authorized variant and regenerated the letter.'),
            'validation': validation, 'change_receipt': receipt,
        }
        store.append_jsonl(_path(), event)
        store.append_application_event(event)
    return [row for row in current(slug)
            if row.get('id') in {change['feedback_id'] for change in changes}]


def complete_governed(slug, feedback_id, implementation, validation, receipt):
    """Close a typed non-document comment after its own governed control ran."""
    item = next((row for row in current(slug) if row['id'] == feedback_id), None)
    if not item or item.get('status') not in {'OPEN', 'PROPOSED'}:
        raise ValueError('Select open typed feedback')
    event = {
        'timestamp': store.now(), 'event': 'FEEDBACK_APPLIED',
        'feedback_id': feedback_id, 'app_id': slug,
        'implementation': str(implementation).strip(),
        'validation': str(validation).strip(), 'change_receipt': receipt,
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(row for row in current(slug) if row['id'] == feedback_id)


def validate_resolution(slug, feedback_id, status, implementation, validation):
    """Validate a resolution before an approved package is invalidated."""
    status = str(status or '').upper()
    if status not in RESOLUTIONS:
        raise ValueError('status must be ADOPTED or REJECTED')
    item = next((row for row in current(slug) if row['id'] == feedback_id), None)
    if not item:
        raise ValueError(f'unknown feedback item {feedback_id!r}')
    if item.get('status') != 'OPEN':
        raise ValueError(f'feedback item {feedback_id} is already resolved')
    if len(str(implementation or '').strip()) < 8:
        raise ValueError('implementation/rejection rationale must be explicit')
    if len(str(validation or '').strip()) < 8:
        raise ValueError('validation evidence must be explicit')
    return item, status, str(implementation).strip(), str(validation).strip()


def resolve(slug, feedback_id, status, implementation, validation):
    item, status, implementation, validation = validate_resolution(
        slug, feedback_id, status, implementation, validation)
    event = {
        'timestamp': store.now(), 'event': 'FEEDBACK_RESOLVED',
        'feedback_id': feedback_id, 'app_id': slug, 'status': status,
        'implementation': implementation,
        'validation': validation,
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(row for row in current(slug) if row['id'] == feedback_id)
