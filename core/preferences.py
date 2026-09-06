"""Explicit candidate preferences, separate from facts and outcome hypotheses."""
from . import store


TYPES = {
    'WORDING_VARIANT': {'short', 'std', 'long'},
    'TARGET_PAGES': {'1', '2', '3'},
}


def _path():
    return store.p('index', 'preferences.jsonl')


def events():
    return store.read_jsonl(_path())


def current():
    state = {}
    for event in events():
        preference_id = event.get('preference_id')
        if event.get('event') == 'PREFERENCE_ADOPTED':
            state[preference_id] = {
                'id': preference_id, 'type': event.get('type'),
                'value': event.get('value'), 'note': event.get('note'),
                'status': 'ACTIVE', 'source_feedback_id': event.get('source_feedback_id'),
                'created_at': event.get('timestamp'),
            }
        elif event.get('event') == 'PREFERENCE_RETIRED' and preference_id in state:
            state[preference_id].update({
                'status': 'RETIRED', 'retired_at': event.get('timestamp'),
                'retirement_reason': event.get('reason'),
                'superseded_by': event.get('superseded_by'),
            })
    return [state[key] for key in sorted(state)]


def active():
    return [row for row in current() if row.get('status') == 'ACTIVE']


def record(preference_type, value, note, source_feedback_id, author='candidate'):
    preference_type = str(preference_type or '').upper()
    value = str(value or '').lower()
    if preference_type not in TYPES or value not in TYPES[preference_type]:
        raise ValueError('Select a supported preference type and value')
    if len(str(note or '').strip()) < 4:
        raise ValueError('Preference needs a short reason')
    existing = next((row for row in active()
                     if row['type'] == preference_type and row['value'] == value), None)
    if existing:
        return existing
    existing_rows = current()
    used = [int(row['id'][2:]) for row in existing_rows
            if str(row.get('id') or '').startswith('PR')
            and str(row['id'])[2:].isdigit()]
    preference_id = f"PR{max(used, default=0) + 1:04d}"
    for prior in existing_rows:
        if prior.get('status') != 'ACTIVE' or prior.get('type') != preference_type:
            continue
        retired = {
            'timestamp': store.now(), 'event': 'PREFERENCE_RETIRED',
            'preference_id': prior['id'], 'superseded_by': preference_id,
            'reason': f'Superseded by accepted preference feedback {source_feedback_id}.',
        }
        store.append_jsonl(_path(), retired)
        store.append_application_event(retired)
    event = {
        'timestamp': store.now(), 'event': 'PREFERENCE_ADOPTED',
        'preference_id': preference_id, 'type': preference_type, 'value': value,
        'note': str(note).strip(), 'source_feedback_id': source_feedback_id,
        'author': str(author or 'candidate').strip(),
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(row for row in current() if row['id'] == preference_id)


def retire(preference_id, reason):
    row = next((item for item in active() if item['id'] == preference_id), None)
    if not row:
        raise ValueError('Select an active preference')
    if len(str(reason or '').strip()) < 8:
        raise ValueError('Retiring a preference needs a brief reason')
    event = {
        'timestamp': store.now(), 'event': 'PREFERENCE_RETIRED',
        'preference_id': preference_id, 'reason': str(reason).strip(),
    }
    store.append_jsonl(_path(), event)
    store.append_application_event(event)
    return next(item for item in current() if item['id'] == preference_id)


def options(default_pages=2):
    result = {'target_pages': int(default_pages), 'wording_variant': None}
    for row in active():
        if row['type'] == 'TARGET_PAGES':
            result['target_pages'] = int(row['value'])
        elif row['type'] == 'WORDING_VARIANT':
            result['wording_variant'] = row['value']
    return result
