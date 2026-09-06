"""Dashboard-first, evidence-bounded career-truth intake.

Uploaded source bytes are private evidence. Extracted lines are proposals, not
career facts. Only candidate-reviewed ADOPT decisions are promoted into the
authoritative truth files, and generation remains blocked until the resulting
truth digest is signed separately.
"""
import hashlib
import json
import os
import re
import shutil
import zipfile
from xml.etree import ElementTree

from . import integrity, pdftext, store, truth_review


SCHEMA = 'joblooper.truth-intake.v1'
PARSER_VERSION = 'deterministic-lines-v1'
MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_CANDIDATES_PER_SOURCE = 180
EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.json'}
SOURCE_KINDS = {
    'base_cv': 'canonical_cv',
    'historical_cv': 'historical_cv',
    'certificate': 'certificate',
    'reference': 'signed_reference',
    'career_note': 'career_note',
}
FACT_TYPES = {'anchor', 'skill', 'education', 'credential', 'publication',
              'recognition', 'role'}
DISPOSITIONS = {'ADOPTED', 'DUPLICATE', 'REJECTED', 'UNRESOLVED'}


def _path():
    return store.p('index', 'truth_intake.json')


def _load():
    value = store.read_json(_path(), {}) or {}
    if value.get('_schema') != SCHEMA:
        value = {'_schema': SCHEMA, 'sources': [], 'candidates': [], 'events': []}
    return value


def _save(value):
    value['updated_at'] = store.now()
    store.write_json(_path(), value)


def _safe_name(name):
    base = os.path.basename(str(name or '').strip())
    stem, extension = os.path.splitext(base)
    stem = re.sub(r'[^A-Za-z0-9._ -]+', '-', stem).strip(' .-_') or 'career-source'
    return stem[:80] + extension.lower()


def _decode_text(path):
    extension = os.path.splitext(path)[1].lower()
    if extension == '.pdf':
        text, quality = pdftext.extract(path)
        return text, quality
    if extension == '.docx':
        try:
            with zipfile.ZipFile(path) as archive:
                raw = archive.read('word/document.xml')
            root = ElementTree.fromstring(raw)
        except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError(f'DOCX text could not be read: {error}') from error
        paragraphs = []
        for paragraph in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
            text = ''.join(node.text or '' for node in paragraph.iter(
                '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
            if text.strip():
                paragraphs.append(text.strip())
        text = '\n'.join(paragraphs)
        if len(text.split()) < 10:
            raise ValueError('DOCX contains too little readable text')
        return text, {'paragraphs': len(paragraphs), 'parser': 'docx-xml'}
    raw = open(path, 'rb').read()
    if b'\x00' in raw:
        raise ValueError('text source contains binary null bytes')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('text source must be UTF-8') from error
    if extension == '.json':
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as error:
            raise ValueError(f'JSON source is malformed: {error}') from error
    if len(text.split()) < 5:
        raise ValueError('source contains too little readable text')
    return text, {'characters': len(text), 'parser': 'utf-8'}


def _suggest_type(text):
    lower = text.casefold()
    if re.search(r'\b(?:bachelor|master|phd|doctorate|university|college)\b', lower):
        return 'education'
    if re.search(r'\b(?:certified|certificate|certification|licen[cs]e|credential)\b', lower):
        return 'credential'
    if re.search(r'\b(?:published|journal|conference|doi|publication)\b', lower):
        return 'publication'
    if re.search(r'\b(?:award|commendation|recognition|honou?r)\b', lower):
        return 'recognition'
    if re.search(r'\b(?:skills?|tools?|technologies|competenc)\b', lower):
        return 'skill'
    return 'anchor'


def _candidate_lines(text):
    rows = []
    seen = set()
    for paragraph_number, raw in enumerate(text.replace('\r', '\n').split('\n'), 1):
        line = re.sub(r'^[\s\u2022\-*\u25cf\u25aa\uf0b7]+', '', raw)
        line = re.sub(r'\s+', ' ', line).strip()
        if len(line) < 4 or len(line) > 500:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        rows.append((paragraph_number, line, _suggest_type(line)))
        if len(rows) >= MAX_CANDIDATES_PER_SOURCE:
            break
    return rows


def _next(prefix, values, width=3):
    used = []
    for value in values:
        match = re.fullmatch(re.escape(prefix) + r'-(\d+)', str(value or ''))
        if match:
            used.append(int(match.group(1)))
    return f'{prefix}-{max(used, default=0) + 1:0{width}d}'


def upload(name, content, kind='base_cv', supersedes_source_id=None):
    """Store one exact source privately and stage bounded extraction proposals."""
    if kind not in SOURCE_KINDS:
        raise ValueError('Select a valid career-source type')
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError('Career source is empty')
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError('Career source exceeds the 12 MB limit')
    safe_name = _safe_name(name)
    extension = os.path.splitext(safe_name)[1]
    if extension not in EXTENSIONS:
        raise ValueError('Career source must be PDF, DOCX, UTF-8 text, Markdown or JSON')
    digest = hashlib.sha256(content).hexdigest()
    intake = _load()
    supersedes_source_id = str(supersedes_source_id or '').strip() or None
    registered_sources = store.read_jsonl(store.p('truth', 'sources.jsonl'))
    if supersedes_source_id:
        old = next((row for row in registered_sources
                    if row.get('id') == supersedes_source_id), None)
        if not old:
            raise ValueError('The source selected for replacement is not registered')
        if old.get('lifecycle_status') == 'SUPERSEDED':
            raise ValueError('The selected source is already superseded')
    existing = next((row for row in intake['sources']
                     if row.get('sha256') == digest), None)
    registered = next((row for row in registered_sources
                       if row.get('sha256') == digest), None)
    if existing or registered:
        return {'duplicate': True, 'source': existing or registered,
                'workspace': summary()}

    directory = store.p('imports', 'truth_sources')
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, f'{digest[:16]}_{safe_name}')
    if not os.path.exists(target):
        with open(target, 'xb') as stream:
            stream.write(content)
    text, quality = _decode_text(target)
    source_id = _next('SRC', [row.get('id') for row in
                              intake['sources'] + store.sources()])
    source = {
        'id': source_id, 'name': safe_name, 'kind': SOURCE_KINDS[kind],
        'upload_kind': kind, 'sha256': digest, 'bytes': len(content),
        'path': os.path.relpath(target, store.DATA_ROOT).replace('\\', '/'),
        'uploaded_at': store.now(), 'parser_version': PARSER_VERSION,
        'extraction_quality': quality, 'status': 'EXTRACTION_REVIEW',
    }
    if supersedes_source_id:
        source['supersedes_source_id'] = supersedes_source_id
    intake['sources'].append(source)
    existing_candidate_ids = [row.get('id') for row in intake['candidates']]
    for locator, line, suggested in _candidate_lines(text):
        candidate_id = _next('TC', existing_candidate_ids, width=4)
        existing_candidate_ids.append(candidate_id)
        intake['candidates'].append({
            'id': candidate_id, 'source_id': source_id,
            'locator': f'paragraph {locator}', 'text': line,
            'suggested_type': suggested, 'confidence': 1.0,
            'parser_version': PARSER_VERSION, 'status': 'PENDING',
        })
    intake['events'].append({
        'event': 'SOURCE_STAGED', 'source_id': source_id,
        'sha256': digest, 'timestamp': store.now(),
    })
    _save(intake)
    return {'duplicate': False, 'source': source, 'workspace': summary()}


def _normal(value):
    return ' '.join(str(value or '').casefold().split())


def _role_record(decision, record_id, source_id, locator):
    title = str(decision.get('title') or '').strip()
    org = str(decision.get('org') or '').strip()
    start = str(decision.get('start') or '').strip()
    end = str(decision.get('end') or '').strip() or None
    if not title or not org or not re.fullmatch(r'\d{4}(?:-(?:0[1-9]|1[0-2]))?', start):
        raise ValueError('An adopted role needs organisation, title and YYYY or YYYY-MM start')
    if end and not re.fullmatch(r'\d{4}(?:-(?:0[1-9]|1[0-2]))?', end):
        raise ValueError('Role end must use YYYY or YYYY-MM')
    if end and start > end:
        raise ValueError('Role start cannot be after its end')
    return {
        'id': record_id, 'type': 'role', 'kind': 'employment',
        'org': org, 'title': title, 'period': [start, end],
        'status': 'SUPPORTED',
        'evidence_refs': [{'source_id': source_id, 'locator': locator}],
    }


def _fact_record(decision, record_id, source_id, locator, identity, role_ids):
    fact = re.sub(r'\s+', ' ', str(decision.get('fact') or '').strip())
    fact_type = str(decision.get('type') or '').strip().lower()
    if fact_type not in FACT_TYPES - {'role'}:
        raise ValueError('Select a valid fact type for every adopted claim')
    if len(fact) < 4 or len(fact) > 500:
        raise ValueError('Each adopted fact must contain 4 to 500 characters')
    role_id = str(decision.get('role_id') or '').strip() or None
    if role_id and role_id not in role_ids:
        raise ValueError(f'Adopted fact references unknown role {role_id!r}')
    ownership = str(decision.get('ownership') or 'supported').strip().lower()
    ladder = (store.read_json(store.p('truth', 'boundaries.json'), {}) or {}).get(
        'ownership_ladder') or []
    if ownership not in ladder:
        raise ValueError('Select a governed ownership level for every adopted fact')
    prefix = {
        'anchor': 'EXP', 'skill': 'SKILL', 'education': 'EDU',
        'credential': 'CRED', 'publication': 'PUB', 'recognition': 'REC',
    }[fact_type]
    record = {
        'id': record_id, 'type': fact_type,
        'identity': ['*'] if fact_type in {'education', 'credential'} else [identity],
        'status': 'SUPPORTED', 'ownership': ownership, 'fact': fact,
        'bullet': {'short': fact, 'std': fact, 'long': fact},
        'metrics': [], 'keywords': sorted(set(re.findall(
            r"[A-Za-z][A-Za-z0-9+#&./-]{2,}", fact.casefold())))[:20],
        'boundary': 'Candidate-reviewed wording from a registered private source.',
        'evidence_refs': [{'source_id': source_id, 'locator': locator}],
        'confidence': 1.0,
    }
    if role_id:
        record['role_id'] = role_id
    if fact_type == 'credential':
        record['tier'] = str(decision.get('tier') or 'qualification').strip().lower()
    if fact_type == 'publication':
        record['status'] = str(decision.get('publication_status') or 'SUPPORTED').upper()
    return record, prefix


def _profile_update(current, profile, identity, positioning_id, supports):
    result = dict(current or {})
    result.setdefault('_schema', 'joblooper.profile.v1')
    result['ready_for_generation'] = False
    result['_onboarding'] = {
        'state': 'NEEDS_REVIEW', 'reason': 'career-source decisions changed',
        'changed_at': store.now(),
    }
    for key in ('name',):
        supplied = str(profile.get(key) or '').strip()
        if supplied:
            result[key] = supplied
    contact = dict(result.get('contact') or {})
    for key in ('email', 'phone_primary'):
        supplied = str(profile.get(key) or '').strip()
        if supplied:
            contact[key] = supplied
    result['contact'] = contact
    based_in = str(profile.get('based_in') or '').strip()
    location = dict(result.get('location') or {})
    if based_in:
        location['based_in'] = based_in
        location['city'] = based_in
    location.setdefault('work_authorisation', {
        'mobility': False, 'phrasing_default': based_in,
        'phrasing_approved': based_in, 'display_rules': [],
        'requirement_rules': [],
    })
    result['location'] = location
    result.setdefault('languages', {})
    result.setdefault('eligibility', {})
    result.setdefault('links', {})
    result.setdefault('career', {})
    identities = dict(result.get('identities') or {})
    identities[identity] = str(profile.get('identity_description') or
                                profile.get('summary') or '').strip()
    result['identities'] = identities
    headlines = dict(result.get('headlines') or {})
    headlines[identity] = str(profile.get('headline') or '').strip()
    result['headlines'] = headlines
    result['identity_rule'] = 'Exactly one primary identity per tailored CV.'
    missing = []
    if not str(result.get('name') or '').strip():
        missing.append('candidate name')
    if not str(contact.get('email') or '').strip():
        missing.append('email')
    if not str(contact.get('phone_primary') or '').strip():
        missing.append('phone')
    if not headlines.get(identity):
        missing.append('controlled headline')
    if missing:
        raise ValueError('Profile review still needs: ' + ', '.join(missing))
    return result, {
        'id': positioning_id, 'type': 'positioning', 'identity': [identity],
        'status': 'APPROVED', 'ownership': 'supported',
        'fact': 'Candidate-approved professional positioning.',
        'supports': supports,
        'bullet': {
            'short': str(profile.get('summary') or '').strip(),
            'std': str(profile.get('summary') or '').strip(),
            'long': str(profile.get('summary') or '').strip(),
        },
        'metrics': [], 'keywords': [],
        'boundary': 'Positioning summarizes only the cited candidate-reviewed facts.',
        'evidence_refs': [{'anchor_id': supports[0]}] if supports else [],
        'confidence': 1.0, 'render': 'summary_only',
    }


def review(profile, decisions):
    """Promote explicitly reviewed candidates in one recoverable transaction."""
    intake = _load()
    pending = [row for row in intake['candidates'] if row.get('status') == 'PENDING']
    supplied = {str(row.get('candidate_id') or ''): row for row in (decisions or [])
                if isinstance(row, dict)}
    missing = [row['id'] for row in pending if row['id'] not in supplied]
    if missing:
        raise ValueError('Every extracted claim needs a disposition: ' + ', '.join(missing[:12]))
    identity = re.sub(r'[^a-z0-9]+', '_', str((profile or {}).get(
        'identity') or '').casefold()).strip('_')
    existing_profile = store.read_json(store.p('truth', 'profile.json'), {}) or {}
    if not identity:
        existing = list((existing_profile.get('identities') or {}).keys())
        identity = existing[0] if len(existing) == 1 else ''
    if not identity:
        raise ValueError('Choose a short professional identity name')

    anchors = store.read_jsonl(store.p('truth', 'anchors.jsonl'))
    sources = store.read_jsonl(store.p('truth', 'sources.jsonl'))
    existing_ids = [row.get('id') for row in anchors]
    accepted, role_records, fact_specs = [], [], []
    role_temp_ids = {}
    # Allocate roles first so fact decisions can link to either a staged
    # candidate id or the final ROLE id.
    for candidate in pending:
        decision = supplied[candidate['id']]
        disposition = str(decision.get('disposition') or '').upper()
        if disposition not in DISPOSITIONS:
            raise ValueError(f"{candidate['id']} needs a valid disposition")
        if disposition == 'UNRESOLVED':
            continue
        if disposition != 'ADOPTED' or str(decision.get('type') or '').lower() != 'role':
            continue
        record_id = _next('ROLE', existing_ids + [row['id'] for row in role_records])
        role_temp_ids[candidate['id']] = record_id
        role_records.append(_role_record(
            decision, record_id, candidate['source_id'], candidate['locator']))
    role_ids = {row['id'] for row in anchors if row.get('type') == 'role'}
    role_ids.update(row['id'] for row in role_records)

    prefix_ids = list(existing_ids)
    for candidate in pending:
        decision = dict(supplied[candidate['id']])
        disposition = str(decision.get('disposition') or '').upper()
        reason = str(decision.get('reason') or '').strip()
        if disposition in {'REJECTED', 'UNRESOLVED'} and len(reason) < 8:
            raise ValueError(f'{candidate["id"]} needs a brief decision reason')
        if disposition == 'DUPLICATE':
            duplicate = str(decision.get('duplicate_of') or '').strip()
            if duplicate not in existing_ids:
                raise ValueError(f'{candidate["id"]} duplicate target is not an existing fact')
            accepted.append((candidate, decision, None))
            continue
        if disposition != 'ADOPTED':
            accepted.append((candidate, decision, None))
            continue
        if str(decision.get('type') or '').lower() == 'role':
            record = next(row for row in role_records
                          if row['id'] == role_temp_ids[candidate['id']])
        else:
            role_ref = str(decision.get('role_id') or '')
            decision['role_id'] = role_temp_ids.get(role_ref, role_ref)
            prefix = {
                'anchor': 'EXP', 'skill': 'SKILL', 'education': 'EDU',
                'credential': 'CRED', 'publication': 'PUB',
                'recognition': 'REC',
            }.get(str(decision.get('type') or '').lower())
            record_id = _next(prefix, prefix_ids) if prefix else None
            if not record_id:
                raise ValueError(f'{candidate["id"]} needs a valid adopted fact type')
            prefix_ids.append(record_id)
            record, _ = _fact_record(
                decision, record_id, candidate['source_id'], candidate['locator'],
                identity, role_ids)
            fact_specs.append(record)
        accepted.append((candidate, decision, record))

    unresolved = [candidate['id'] for candidate, decision, _ in accepted
                  if str(decision.get('disposition') or '').upper() == 'UNRESOLVED']
    if unresolved:
        # Save decisions as resumable review state, but never touch authority.
        for candidate, decision, _ in accepted:
            candidate['draft_decision'] = decision
        _save(intake)
        raise ValueError('Resolve or reject these claims before authority changes: '
                         + ', '.join(unresolved[:12]))
    adopted_facts = role_records + fact_specs
    normalized_existing = {_normal(row.get('fact')) for row in anchors if row.get('fact')}
    seen = set(normalized_existing)
    for record in fact_specs:
        fact = _normal(record.get('fact'))
        if fact in seen:
            raise ValueError(
                f"{record['id']} duplicates an existing/adopted fact; mark it DUPLICATE")
        seen.add(fact)
    non_role_ids = [row['id'] for row in fact_specs]
    duplicate_decisions = [(candidate, decision) for candidate, decision, _ in accepted
                           if str(decision.get('disposition') or '').upper()
                           == 'DUPLICATE']
    if not non_role_ids and not anchors:
        raise ValueError('Review must adopt at least one evidence fact')
    if not anchors:
        experience = [row for row in fact_specs
                      if row.get('type') == 'anchor' and row.get('role_id')]
        roles_with_evidence = {row.get('role_id') for row in experience}
        if len(experience) < 2 or any(
                row['id'] not in roles_with_evidence for row in role_records):
            raise ValueError(
                'Initial truth needs at least two adopted experience facts linked '
                'to every adopted employment role')
    positioning_id = _next('POS', existing_ids + [row['id'] for row in adopted_facts])
    positioning_supports = non_role_ids or [
        str(decision.get('duplicate_of')) for _candidate, decision in duplicate_decisions
        if str(decision.get('duplicate_of')) in existing_ids]
    new_profile, positioning = _profile_update(
        existing_profile, profile or {}, identity, positioning_id, positioning_supports)
    if len(str(positioning['bullet']['short']).split()) < 8:
        raise ValueError('Professional summary needs at least eight words')
    # Do not create a second positioning statement for an established lane.
    has_positioning = any(row.get('type') == 'positioning'
                          and identity in (row.get('identity') or []) for row in anchors)
    if not has_positioning:
        adopted_facts.append(positioning)

    source_by_id = {row['id']: row for row in intake['sources']}
    new_sources = [dict(row) for row in sources]
    for source in intake['sources']:
        if source.get('status') == 'REGISTERED':
            continue
        source_decisions = [(candidate, decision, record)
                            for candidate, decision, record in accepted
                            if candidate['source_id'] == source['id']]
        dispositions = []
        for candidate, decision, record in source_decisions:
            disposition = str(decision.get('disposition') or '').upper()
            item = {'claim': candidate['text'], 'locator': candidate['locator'],
                    'disposition': disposition}
            if record:
                item['anchor_id'] = record['id']
            if disposition == 'DUPLICATE':
                item['anchor_id'] = decision.get('duplicate_of')
            if decision.get('reason'):
                item['reason'] = str(decision['reason']).strip()
            dispositions.append(item)
        registry = {key: value for key, value in source.items()
                    if key not in {'status', 'upload_kind', 'extraction_quality'}}
        registry['coverage_review'] = {
            'status': 'reviewed', 'reviewed_sha256': source['sha256'],
            'reviewed_at': store.today(),
            'scope': 'Every extracted material line was dispositioned in the dashboard.',
            'claim_dispositions': dispositions,
        }
        new_sources.append(registry)

    sections = store.read_json(store.p('truth', 'sections.json'), {}) or {}
    sections.setdefault('lanes', {}).setdefault(identity, {
        'order': ['summary', 'skills', 'experience', 'highlights', 'research',
                  'education', 'certifications'], 'caps': {}, 'drop': [],
    })
    aliases = store.read_json(store.p('truth', 'aliases.json'), {}) or {}
    aliases.setdefault('boost_terms', {}).setdefault(identity, {})
    # A duplicate in a replacement file is additional provenance for the
    # existing fact. Preserve the new source locator instead of discarding it.
    for candidate, decision in duplicate_decisions:
        target = next(row for row in anchors
                      if row.get('id') == decision.get('duplicate_of'))
        refs = target.setdefault('evidence_refs', [])
        ref = {'source_id': candidate['source_id'], 'locator': candidate['locator']}
        if ref not in refs:
            refs.append(ref)
    proposed_anchors = anchors + adopted_facts
    for source in intake['sources']:
        old_id = source.get('supersedes_source_id')
        if not old_id:
            continue
        old = next((row for row in new_sources if row.get('id') == old_id), None)
        if not old:
            raise ValueError(f'Replacement source refers to missing source {old_id}')
        unresolved_refs = []
        for anchor in proposed_anchors:
            if anchor.get('render') == 'superseded':
                continue
            refs = anchor.get('evidence_refs') or []
            if not any(isinstance(ref, dict) and ref.get('source_id') == old_id
                       for ref in refs):
                continue
            alternatives = [ref for ref in refs if isinstance(ref, dict) and (
                (ref.get('source_id') and ref.get('source_id') != old_id)
                or ref.get('change_id') or ref.get('anchor_id'))]
            if not alternatives:
                unresolved_refs.append(anchor.get('id'))
        if unresolved_refs:
            raise ValueError(
                f'Source {old_id} still solely supports active facts: '
                + ', '.join(unresolved_refs[:12])
                + '. Mark matching claims as duplicates of those facts first.')
        old['lifecycle_status'] = 'SUPERSEDED'
        old['superseded_by'] = source['id']
        old['superseded_at'] = store.now()
    # Preserve every authoritative file byte-for-byte if the proposed set does
    # not pass the same integrity checker used by generation.
    tracked = {
        'profile': store.p('truth', 'profile.json'),
        'anchors': store.p('truth', 'anchors.jsonl'),
        'sources': store.p('truth', 'sources.jsonl'),
        'sections': store.p('truth', 'sections.json'),
        'aliases': store.p('truth', 'aliases.json'),
    }
    backups = {key: open(path, 'rb').read() if os.path.isfile(path) else None
               for key, path in tracked.items()}
    try:
        store.write_json(tracked['profile'], new_profile)
        store.write_jsonl(tracked['anchors'], proposed_anchors)
        store.write_jsonl(tracked['sources'], new_sources)
        store.write_json(tracked['sections'], sections)
        store.write_json(tracked['aliases'], aliases)
        store.reset_context_cache()
        errors, _warnings, _stats = integrity.check_truth()
        if errors:
            raise ValueError('Proposed career truth failed validation: ' + '; '.join(errors[:8]))
    except Exception:
        for key, path in tracked.items():
            original = backups[key]
            if original is None:
                if os.path.isfile(path):
                    os.unlink(path)
            else:
                with open(path, 'wb') as stream:
                    stream.write(original)
        store.reset_context_cache()
        raise

    for candidate, decision, record in accepted:
        candidate['status'] = str(decision.get('disposition') or '').upper()
        candidate['decision'] = {key: value for key, value in decision.items()
                                 if key != 'candidate_id'}
        if record:
            candidate['anchor_id'] = record['id']
    for source in intake['sources']:
        source['status'] = 'REGISTERED'
    intake['events'].append({
        'event': 'EXTRACTION_REVIEW_COMPLETED', 'timestamp': store.now(),
        'identity': identity, 'adopted_ids': [row['id'] for row in adopted_facts],
    })
    _save(intake)
    store.log_change(
        'career source review',
        'Reviewed extracted source claims and explicitly dispositioned every proposal.',
        'Promoted only adopted, source-cited claims into candidate truth; sign-off remains required.',
        affected=['truth/profile.json', 'truth/anchors.jsonl',
                  'truth/sources.jsonl', 'truth/sections.json', 'truth/aliases.json'])
    return summary()


def summary():
    intake = _load()
    profile = store.read_json(store.p('truth', 'profile.json'), {}) or {}
    anchors = store.read_jsonl(store.p('truth', 'anchors.jsonl'))
    sources = store.read_jsonl(store.p('truth', 'sources.jsonl'))
    pending = [row for row in intake['candidates'] if row.get('status') == 'PENDING']
    fact_groups = {}
    for row in anchors:
        fact = _normal(row.get('fact'))
        if fact:
            fact_groups.setdefault(fact, []).append(row.get('id'))
    conflicts = [ids for ids in fact_groups.values() if len(ids) > 1]
    subject = store.truth_approval_subject() if os.path.isfile(
        store.p('truth', 'profile.json')) else {'sha256': None}
    positionings = [row for row in anchors if row.get('type') == 'positioning'
                    and row.get('render') != 'superseded']
    return {
        '_schema': 'joblooper.truth-workspace.v1',
        'state': ('EXTRACTION_REVIEW' if pending else
                  'TRUTH_REVIEW' if intake['sources'] and not profile.get('ready_for_generation')
                  else 'TRUTH_READY' if profile.get('ready_for_generation')
                  else 'SOURCES_REQUIRED'),
        'sources': intake['sources'], 'candidates': pending,
        'registered_source_rows': [{
            'id': row.get('id'), 'name': row.get('name'), 'kind': row.get('kind'),
            'lifecycle_status': row.get('lifecycle_status') or 'ACTIVE',
        } for row in sources],
        'truth_comments': truth_review.items(),
        'candidate_count': len(intake['candidates']),
        'pending_count': len(pending),
        'profile': {
            'name': profile.get('name'),
            'email': (profile.get('contact') or {}).get('email'),
            'phone_primary': (profile.get('contact') or {}).get('phone_primary'),
            'based_in': (profile.get('location') or {}).get('based_in'),
            'identities': profile.get('identities') or {},
            'headlines': profile.get('headlines') or {},
        },
        'positioning': {
            'summary': ((positionings[0].get('bullet') or {}).get('short')
                        if positionings else None),
        },
        'facts': [{
            'id': row.get('id'), 'type': row.get('type'),
            'fact': row.get('fact') or row.get('title'),
            'source_ids': [ref.get('source_id') for ref in row.get('evidence_refs') or []
                           if isinstance(ref, dict) and ref.get('source_id')],
        } for row in anchors if row.get('render') != 'superseded'],
        'registered_sources': len(sources),
        'conflicts': conflicts,
        'boundary_summary': {
            'restricted_patterns': len(((store.read_json(
                store.p('truth', 'boundaries.json'), {}) or {}).get('disclosure') or {}).get(
                    'restricted_patterns') or []),
            'rule': 'Employer documents may use only accepted facts and approved disclosure wording.',
        },
        'subject_sha256': subject.get('sha256'),
    }
