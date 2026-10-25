"""Read-only JD screening and exact promotion into the application lifecycle.

A screen is deliberately *not* an application. It binds one complete advert to
current approved candidate truth and the existing deterministic matcher without
creating ``work/`` state, application events, CV records or approval state.

Promotion is the only transition that creates application state. It verifies
the packet against current truth/engine state, recomputes the deterministic
mapping from the embedded structured JD, and then copies the exact advert bytes
into the normal Joblooper work lifecycle. It never reparses a different source.
"""
import copy
import hmac
import os
import re

from . import advert_review, match, store, truth_review


SCHEMA = 'joblooper.jd-screen.v1'
MODE = 'READ_ONLY_FACTUAL_SCREEN'
_MATCH_CLASSES = {'DIRECT', 'TRANSFERABLE', 'PARTIAL', 'GAP', 'BEHAVIOURAL'}


def _stable_jd(jd):
    """Return the meaning-bearing structured advert, excluding capture time."""
    value = copy.deepcopy(jd or {})
    value.pop('ingested', None)
    value.pop('_slug', None)
    return value


def _engine_sha256():
    path = store.code_p('core', 'screen.py')
    return store.sha256_file(path) if os.path.isfile(path) else None


def _requirement_lines(raw, requirements):
    """Locate the exact parser-derived requirement text in the captured source.

    Line numbers are provenance aids, not parsing authority. Duplicate text may
    legitimately return more than one line, so consumers must use the exact
    requirement text plus the advert digest as the authority.
    """
    lines = str(raw or '').splitlines()
    result = {}
    for row in requirements or []:
        text = str(row.get('text') or '').strip()
        hits = []
        if text:
            for number, line in enumerate(lines, 1):
                if text in line:
                    hits.append(number)
        result[row.get('n')] = hits
    return result


def _compact_requirement(row, source_lines):
    evidence = []
    for candidate in row.get('anchors') or []:
        aid = str(candidate.get('id') or '').strip()
        if aid and aid not in evidence:
            evidence.append(aid)
    value = {
        'n': row.get('n'),
        'text': row.get('text'),
        'kind': row.get('kind'),
        'hard_gate': bool(row.get('hard_gate')),
        'gate_type': row.get('gate_type'),
        'classification': row.get('match'),
        'evidence_ids': evidence,
        'source_lines': list(source_lines or []),
        'unmatched_named': list(row.get('unmatched_named') or []),
        'unevidenced': list(row.get('unevidenced') or []),
    }
    if row.get('note'):
        value['note'] = row.get('note')
    return value


def _analysis(jd, raw, identity_override=None):
    identity = match.pick_identity(jd, override=identity_override)
    mapping = match.match_jd(jd, identity)
    lines = _requirement_lines(raw, mapping.get('requirements') or [])
    requirements = [
        _compact_requirement(row, lines.get(row.get('n')))
        for row in mapping.get('requirements') or []
    ]
    unresolved = [
        {
            'n': row['n'], 'text': row['text'],
            'classification': row['classification'],
            'gate_type': row.get('gate_type'),
        }
        for row in requirements
        if row.get('hard_gate') and row.get('classification') != 'DIRECT'
    ]
    summary = {
        'coverage': mapping.get('coverage'),
        'coverage_by_kind': mapping.get('coverage_by_kind'),
        'spread': mapping.get('spread'),
        'material_requirements': mapping.get('total_material'),
        'behavioural_requirements': mapping.get('n_behavioural'),
        'hard_gate_unresolved_count': len(unresolved),
        'hard_gate_unresolved': unresolved,
        'mandatory_risk_count': len(mapping.get('mandatory_risks') or []),
        'named_platform_gaps': list(mapping.get('named_platform_gaps') or []),
    }
    return identity, requirements, summary


def _screen_truth_subject(packet):
    """Truth fields that can change factual screening, excluding audit history.

    ``truth_sha256`` intentionally stays in the transport packet as provenance,
    but the broad truth snapshot includes changelog/audit history. An audit-only
    append must not create a different factual screen or block promotion.
    """
    truth = packet.get('candidate_truth') or {}
    return {
        'generation_truth_sha256': truth.get('generation_truth_sha256'),
        'truth_approval_subject_sha256': truth.get('truth_approval_subject_sha256'),
    }


def _subject(packet):
    """Stable factual screen subject; timestamps/audit-only history are excluded."""
    return {
        '_schema': packet.get('_schema'),
        'mode': packet.get('mode'),
        'authority': packet.get('authority'),
        'jd': packet.get('jd'),
        'candidate_truth': _screen_truth_subject(packet),
        'engine': packet.get('engine'),
        'identity': packet.get('identity'),
        'requirements': packet.get('requirements'),
        'summary': packet.get('summary'),
    }


def _screen_digest(packet):
    return store.sha256_text(store.canonical_json(_subject(packet)))


def _packet_digest(packet):
    value = copy.deepcopy(packet or {})
    value.pop('packet_sha256', None)
    return store.sha256_text(store.canonical_json(value))


def create(raw, company, title, url=None, job_reference=None,
           complete_advert_confirmed=False, identity_override=None):
    """Create one factual screen without creating application state.

    ``complete_advert_confirmed`` is intentionally explicit. Completeness is a
    source property that cannot be inferred safely from text length or from a
    search snippet. A caller that cannot establish it must not obtain an
    authoritative candidate-fit screen.
    """
    raw = str(raw or '')
    company = str(company or '').strip()
    title = str(title or '').strip()
    if not raw.strip():
        raise ValueError('exact JD text is empty')
    if not company or not title:
        raise ValueError('exact company and job title are required')
    if not complete_advert_confirmed:
        raise ValueError('complete advert has not been confirmed; factual screening refused')

    readiness = truth_review.readiness()
    if not readiness.get('ready'):
        raise ValueError(
            'candidate truth is not currently approved: '
            + '; '.join(readiness.get('problems') or ['approval unavailable']))

    parsed = match.parse_jd(
        raw, title=title, company=company, url=url,
        job_reference=str(job_reference or '').strip() or None)
    jd = _stable_jd(parsed)
    jd['raw_sha256'] = store.sha256_text(raw)
    jd['raw_normalized_sha256'] = store.sha256_advert(raw)
    if not jd.get('requirements'):
        raise ValueError('no requirements could be extracted from the confirmed advert')

    identity, requirements, summary = _analysis(
        jd, raw, identity_override=identity_override)
    truth_context = store.truth_context()
    approval = readiness.get('approval') or {}
    generation = store.generation_fingerprint(jd)
    packet = {
        '_schema': SCHEMA,
        'mode': MODE,
        'created_at': store.now(),
        'authority': {
            'owner': 'Joblooper',
            'purpose': 'factual screening only; not an application or approval',
            'complete_advert_confirmed': True,
            'candidate_truth_read_only': True,
            'application_state_created': False,
        },
        'jd': {
            'raw_text': raw,
            'structured': jd,
            'raw_sha256': jd['raw_sha256'],
            'raw_normalized_sha256': jd['raw_normalized_sha256'],
        },
        'candidate_truth': {
            # Broad snapshot provenance. It is *not* a currentness gate because
            # it includes audit/changelog history that does not change facts.
            'truth_sha256': truth_context.get('truth_sha256'),
            'generation_truth_sha256': truth_context.get('generation_truth_sha256'),
            'truth_approval_subject_sha256': readiness.get('current_subject_sha256'),
            'truth_approval_receipt_sha256': store.sha256_text(
                store.canonical_json(approval)) if approval else None,
        },
        'engine': {
            'generation_fingerprint_sha256': generation.get('sha256'),
            'screen_engine_sha256': _engine_sha256(),
        },
        'identity': identity,
        'requirements': requirements,
        'summary': summary,
    }
    packet['screen_sha256'] = _screen_digest(packet)
    packet['packet_sha256'] = _packet_digest(packet)
    return packet


def verify(packet, require_current=False, recompute_analysis=False):
    """Verify transport integrity and, optionally, current factual authority."""
    problems = []
    packet = packet or {}
    if packet.get('_schema') != SCHEMA:
        problems.append('unsupported JD-screen schema')
    if packet.get('mode') != MODE:
        problems.append('packet is not a read-only factual screen')
    authority = packet.get('authority') or {}
    if authority.get('application_state_created') is not False:
        problems.append('screen claims application state')
    if authority.get('candidate_truth_read_only') is not True:
        problems.append('screen is not read-only with respect to candidate truth')
    if authority.get('complete_advert_confirmed') is not True:
        problems.append('complete advert was not confirmed')

    expected_packet = _packet_digest(packet)
    supplied_packet = str(packet.get('packet_sha256') or '')
    if not supplied_packet or not hmac.compare_digest(supplied_packet, expected_packet):
        problems.append('packet digest mismatch')
    expected_screen = _screen_digest(packet)
    supplied_screen = str(packet.get('screen_sha256') or '')
    if not supplied_screen or not hmac.compare_digest(supplied_screen, expected_screen):
        problems.append('screen digest mismatch')

    jd_block = packet.get('jd') or {}
    raw = str(jd_block.get('raw_text') or '')
    structured = jd_block.get('structured') or {}
    if store.sha256_text(raw) != jd_block.get('raw_sha256'):
        problems.append('exact JD byte digest mismatch')
    if store.sha256_advert(raw) != jd_block.get('raw_normalized_sha256'):
        problems.append('normalized JD digest mismatch')
    if structured.get('raw_sha256') != jd_block.get('raw_sha256'):
        problems.append('structured JD does not bind the exact raw advert')
    if structured.get('raw_normalized_sha256') != jd_block.get('raw_normalized_sha256'):
        problems.append('structured JD does not bind normalized advert content')

    for row in packet.get('requirements') or []:
        if row.get('classification') not in _MATCH_CLASSES:
            problems.append(f"unsupported classification for requirement {row.get('n')}")

    if require_current:
        readiness = truth_review.readiness()
        if not readiness.get('ready'):
            problems.append('candidate truth is not currently approved')
        current_truth = store.truth_context()
        recorded_truth = packet.get('candidate_truth') or {}
        # The broad truth snapshot includes audit history, so currentness binds
        # only generation-relevant truth and the exact approved fact subject.
        if (recorded_truth.get('generation_truth_sha256')
                != current_truth.get('generation_truth_sha256')):
            problems.append('generation truth changed after screening')
        if (recorded_truth.get('truth_approval_subject_sha256')
                != readiness.get('current_subject_sha256')):
            problems.append('candidate truth approval subject changed after screening')
        generation = store.generation_fingerprint(structured)
        if ((packet.get('engine') or {}).get('generation_fingerprint_sha256')
                != generation.get('sha256')):
            problems.append('generation engine or policy changed after screening')
        if ((packet.get('engine') or {}).get('screen_engine_sha256')
                != _engine_sha256()):
            problems.append('screen contract code changed after screening')

    if recompute_analysis and not problems:
        original_identity = packet.get('identity') or {}
        # Reproduce the original decision path. Passing an automatically chosen
        # primary lane back as ``override`` changes its semantics and creates a
        # false mismatch even when every factual match is identical.
        original_override = (original_identity.get('primary')
                             if original_identity.get('overridden') else None)
        try:
            identity, requirements, summary = _analysis(
                structured, raw, identity_override=original_override)
        except (OSError, TypeError, ValueError) as error:
            problems.append(f'analysis recomputation failed: {error}')
        else:
            comparison = {
                'identity': identity,
                'requirements': requirements,
                'summary': summary,
            }
            recorded = {
                'identity': original_identity,
                'requirements': packet.get('requirements') or [],
                'summary': packet.get('summary') or {},
            }
            if store.canonical_json(comparison) != store.canonical_json(recorded):
                problems.append('factual screen no longer matches deterministic analysis')

    return {'valid': not problems, 'problems': problems}


def _base_slug(jd):
    reference = str(jd.get('job_reference') or '').strip()
    if not reference:
        url = str(jd.get('url') or '')
        found = re.search(r'(?<!\d)(\d{6,})(?:[/?#-]|$)', url)
        reference = found.group(1) if found else ''
    key = reference or store.slugify(jd.get('title'))
    return (f"{store.slugify(jd.get('company'))}--{key}")[:80]


def promote(packet):
    """Promote the exact current screen into normal Joblooper work state."""
    result = verify(packet, require_current=True, recompute_analysis=True)
    if not result['valid']:
        raise ValueError('screen cannot be promoted: ' + '; '.join(result['problems']))

    jd_block = packet['jd']
    raw = jd_block['raw_text']
    source_jd = copy.deepcopy(jd_block['structured'])
    base = _base_slug(source_jd)

    # Idempotency: an already-promoted identical source reuses its application
    # key; a different advert with the same employer/reference receives a suffix.
    slug = base
    seq = 1
    while os.path.isdir(store.job_dir(slug)):
        existing_raw = store.read_text(os.path.join(store.job_dir(slug), 'jd.raw.md'))
        existing_jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'), {}) or {}
        if (existing_raw == raw
                and existing_jd.get('company') == source_jd.get('company')
                and existing_jd.get('title') == source_jd.get('title')):
            return {'app_id': slug, 'created': False, 'screen_sha256': packet['screen_sha256']}
        seq += 1
        slug = f'{base}-{seq}'

    directory = store.job_dir(slug)
    os.makedirs(directory, exist_ok=False)
    promoted = copy.deepcopy(source_jd)
    promoted['_slug'] = slug
    promoted['ingested'] = store.now()
    promoted['raw_sha256'] = store.sha256_text(raw)
    promoted['raw_normalized_sha256'] = store.sha256_advert(raw)
    promoted['promoted_from_screen_sha256'] = packet['screen_sha256']
    store.write_json(os.path.join(directory, 'jd.json'), promoted)
    store.write_text(os.path.join(directory, 'jd.raw.md'), raw)
    advert_review.initialize(slug)
    store.write_json(os.path.join(directory, 'screen-origin.json'), {
        '_schema': 'joblooper.screen-origin.v1',
        'app_id': slug,
        'screen_sha256': packet['screen_sha256'],
        'packet_sha256': packet['packet_sha256'],
        'promoted_at': store.now(),
        'jd_raw_sha256': promoted['raw_sha256'],
        'truth_approval_subject_sha256':
            (packet.get('candidate_truth') or {}).get('truth_approval_subject_sha256'),
        'generation_fingerprint_sha256':
            (packet.get('engine') or {}).get('generation_fingerprint_sha256'),
    })
    store.append_application_event({
        'event': 'JD_SCREEN_PROMOTED', 'app_id': slug,
        'company': promoted.get('company'), 'role': promoted.get('title'),
        'jd_raw_sha256': promoted['raw_sha256'],
        'screen_sha256': packet['screen_sha256'],
        'requirements': len(promoted.get('requirements') or []),
    })
    return {'app_id': slug, 'created': True, 'screen_sha256': packet['screen_sha256']}
