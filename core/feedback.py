"""Append-only user review feedback with explicit resolution.

Feedback is neither career truth nor an automatic prompt mutation.  It becomes
an actionable review gate: an open item blocks sign-off, and every feedback
event invalidates an earlier chat presentation so the user sees the result of
the decision before documents can be rendered.
"""
from . import store


SCOPES = {'CONTENT', 'FORMAT', 'WORKFLOW', 'TRUTH', 'RULE'}
RESOLUTIONS = {'ADOPTED', 'REJECTED'}


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
            }
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
    return [item for item in current(slug) if item.get('status') == 'OPEN']


def validate_record(scope, note):
    """Validate an open-feedback command without mutating lifecycle state."""
    scope = str(scope or '').upper()
    if scope not in SCOPES:
        raise ValueError('scope must be one of ' + ', '.join(sorted(SCOPES)))
    if not str(note or '').strip():
        raise ValueError('feedback note is required')
    return scope, str(note).strip()


def record(slug, scope, note, author='user', plan_sha256=None):
    scope, note = validate_record(scope, note)
    used = [int(item['id'][1:]) for item in current()
            if item.get('id', '').startswith('F') and item['id'][1:].isdigit()]
    fid = f"F{max(used, default=0) + 1:04d}"
    event = {
        'timestamp': store.now(), 'event': 'FEEDBACK_OPENED',
        'feedback_id': fid, 'app_id': slug, 'scope': scope,
        'note': note, 'author': str(author or 'user').strip(),
        'plan_sha256': plan_sha256,
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return current(slug)[-1]


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
