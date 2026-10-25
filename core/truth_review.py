"""Ground-truth comments, approval readiness and lean periodic audits."""
import collections
import datetime
import os

from . import integrity, store


SCOPES = {'FACT', 'SOURCE', 'BOUNDARY', 'WORDING', 'STRUCTURE'}
STATUSES = {'OPEN', 'ADOPTED', 'REJECTED'}
AUDIT_INTERVAL_DAYS = 90
# Section order, caps and activation are generation policy, not biographical truth.
# They remain in store.generation_fingerprint(), so any plan/approval is still
# invalidated when policy changes; the candidate does not have to re-attest
# unrelated career facts merely because document structure changed.
_GENERATION_POLICY_ONLY = {'truth/sections.json'}


def _path():
    return store.p('index', 'truth_feedback.jsonl')


def items():
    return store.read_jsonl(_path())


def open_items():
    return [item for item in items() if item.get('status') == 'OPEN']


def digest():
    return store.sha256_text(store.canonical_json(items()))


def approval_subject():
    """Digest candidate facts/disclosure authority, excluding render policy."""
    base = store.truth_approval_subject()
    files = dict(base.get('files') or {})
    for rel in _GENERATION_POLICY_ONLY:
        files.pop(rel, None)
    return {'files': files, 'sha256': store.sha256_text(store.canonical_json(files))}


def _approval_status():
    profile = store.read_json(store.p('truth', 'profile.json'), {}) or {}
    approval = profile.get('_truth_approval') or {}
    current = approval_subject()
    problems = []
    migrated_legacy = False
    if profile.get('ready_for_generation') is not True:
        problems.append('candidate truth is marked NEEDS_REVIEW')
    if not approval:
        problems.append('candidate truth has no digest-bound approval')
    elif approval.get('subject_sha256') != current['sha256']:
        # Backward-compatible migration is intentionally narrow. A v1 approval
        # included sections.json in the signed subject. If that *exact old full
        # subject* still matches current governed files, no candidate fact has
        # changed and it is safe to recognize the approval under the new split.
        # If any old governed input changed, fail closed and require review.
        legacy_schema = approval.get('_schema') == 'joblooper.truth-approval.v1'
        legacy_current = store.truth_approval_subject()['sha256']
        if legacy_schema and approval.get('subject_sha256') == legacy_current:
            migrated_legacy = True
        else:
            problems.append('candidate truth changed after its last approval')
    return {
        'ready': not problems,
        'problems': problems,
        'approval': approval,
        'current_subject_sha256': current['sha256'],
        'current_files': current['files'],
        'legacy_approval_recognized': migrated_legacy,
    }


def _next_id(rows):
    used = [int(str(row.get('id', ''))[2:]) for row in rows
            if str(row.get('id', '')).startswith('TF')
            and str(row.get('id', ''))[2:].isdigit()]
    return f"TF{max(used, default=0) + 1:04d}"


def record(scope, note, author, evidence=None):
    scope = str(scope or '').upper()
    if scope not in SCOPES:
        raise ValueError('scope must be one of ' + ', '.join(sorted(SCOPES)))
    if not str(note or '').strip() or not str(author or '').strip():
        raise ValueError('truth comment requires a note and author')
    rows = items()
    item = {
        'id': _next_id(rows), 'scope': scope, 'status': 'OPEN',
        'note': str(note).strip(), 'author': str(author).strip(),
        'evidence': [str(value).strip() for value in (evidence or [])
                     if str(value).strip()],
        'created_at': store.now(), 'subject_sha256': approval_subject()['sha256'],
        'generation_sha256': store.generation_fingerprint()['sha256'],
    }
    store.write_jsonl(_path(), rows + [item])
    return item


def resolve(item_id, status, implementation, validation):
    status = str(status or '').upper()
    if status not in {'ADOPTED', 'REJECTED'}:
        raise ValueError('resolution status must be ADOPTED or REJECTED')
    if not str(implementation or '').strip() or not str(validation or '').strip():
        raise ValueError('resolution requires implementation and validation notes')
    rows = items()
    item = next((row for row in rows if row.get('id') == item_id), None)
    if not item:
        raise ValueError(f'unknown truth comment {item_id!r}')
    if item.get('status') != 'OPEN':
        raise ValueError(f'truth comment {item_id} is already {item.get("status")}')
    if status == 'ADOPTED':
        if item.get('scope') == 'STRUCTURE':
            current_generation = store.generation_fingerprint()['sha256']
            if current_generation == item.get('generation_sha256'):
                raise ValueError(
                    'adopted structure feedback requires a changed generation-policy fingerprint first')
        else:
            current = approval_subject()['sha256']
            if current == item.get('subject_sha256'):
                raise ValueError(
                    'adopted truth feedback requires a changed career-truth digest first')
        errors, _warnings, _stats = integrity.check_truth()
        if errors:
            raise ValueError('changed governed data still fails integrity: '
                             + '; '.join(errors[:8]))
    item['status'] = status
    item['resolved_at'] = store.now()
    item['implementation'] = str(implementation).strip()
    item['validation'] = str(validation).strip()
    store.write_jsonl(_path(), rows)
    if status == 'ADOPTED' and item.get('scope') != 'STRUCTURE':
        profile_path = store.p('truth', 'profile.json')
        profile = store.read_json(profile_path, {}) or {}
        profile['ready_for_generation'] = False
        profile['_onboarding'] = {
            'state': 'NEEDS_REVIEW', 'reason': f'adopted truth comment {item_id}',
            'changed_at': store.now(),
        }
        store.write_json(profile_path, profile)
        store.reset_context_cache()
    return item


def readiness():
    status = _approval_status()
    pending = open_items()
    problems = list(status['problems'])
    if pending:
        problems.append('open truth comments: ' + ', '.join(item['id'] for item in pending))
    approval = status.get('approval') or {}
    due = approval.get('next_audit_due')
    overdue = bool(due and due < store.today())
    return {
        **status, 'ready': not problems, 'problems': problems,
        'open_comments': pending, 'audit_due': due, 'audit_overdue': overdue,
    }


ENTRY_STATES = ('UNINITIALIZED', 'SOURCES_REQUIRED', 'EXTRACTION_REVIEW', 'TRUTH_REVIEW',
                'TRUTH_READY', 'TRUTH_BLOCKED')


def entry_state():
    """Decide which surface the dashboard must open on.

    A job advert is only useful once the system knows which candidate facts it
    is allowed to use, so job capture is not a first-run action: it is gated on
    a signed truth digest. A returning user whose truth is current goes straight
    to their working applications.

    A contradictory or unreadable workspace is TRUTH_BLOCKED, never silently
    reset, and never TRUTH_READY.
    """
    try:
        # Import lazily to avoid making the truth-intake staging ledger part of
        # generation authority. It only decides which dashboard step resumes.
        from . import truth_intake
        intake = truth_intake.summary()
        context = store.truth_context()
        state = readiness()
        errors, _warnings, _stats = integrity.check_truth()
    except (OSError, ValueError, RuntimeError) as error:
        return {
            'state': 'TRUTH_BLOCKED', 'can_capture': False,
            'reason': str(error),
            'next_action': 'Repair the governed truth workspace before applying',
            'problems': [str(error)],
        }

    stats = context.get('stats') or {}
    problems = list(dict.fromkeys(list(state.get('problems') or []) + list(errors)))
    if intake.get('pending_count'):
        return {
            'state': 'EXTRACTION_REVIEW', 'can_capture': False,
            'reason': f"{intake['pending_count']} extracted source claim(s) need a decision.",
            'next_action': 'Review extracted career evidence',
            'problems': problems,
        }
    if errors:
        return {
            'state': 'TRUTH_BLOCKED', 'can_capture': False,
            'reason': errors[0],
            'next_action': 'Resolve the ground-truth integrity failure',
            'problems': problems,
        }
    if not stats.get('sources'):
        state_name = 'UNINITIALIZED' if not stats.get('records') else 'SOURCES_REQUIRED'
        return {
            'state': state_name, 'can_capture': False,
            'reason': 'No reviewed career source is registered.',
            'next_action': 'Set up career truth from a base CV',
            'problems': problems,
        }
    if not stats.get('active_records'):
        return {
            'state': 'SOURCES_REQUIRED', 'can_capture': False,
            'reason': 'No active candidate fact is registered.',
            'next_action': 'Set up career truth from a base CV',
            'problems': problems,
        }
    if not state.get('ready'):
        return {
            'state': 'TRUTH_REVIEW', 'can_capture': False,
            'reason': (problems[0] if problems
                       else 'Candidate truth is not signed off.'),
            'next_action': 'Review and sign the exact career-truth digest',
            'problems': problems,
        }
    return {
        'state': 'TRUTH_READY', 'can_capture': True,
        'reason': 'Candidate truth is signed and current.',
        'next_action': ('Review the affected career truth'
                        if state.get('audit_overdue')
                        else 'Continue with working applications'),
        'problems': problems,
        'audit_overdue': bool(state.get('audit_overdue')),
        'audit_due': state.get('audit_due'),
    }


def audit():
    """Return actionable bloat, provenance and protected-inventory signals."""
    errors, warnings, stats = integrity.check_truth()
    _, records = store.anchors()
    sources = store.sources()
    active = [row for row in records if row.get('render') != 'superseded']
    facts = collections.defaultdict(list)
    referenced_sources = set()
    long_variants = []
    for row in active:
        fact = ' '.join(str(row.get('fact') or '').casefold().split())
        if fact:
            facts[fact].append(row.get('id'))
        for ref in row.get('evidence_refs') or []:
            if isinstance(ref, dict) and ref.get('source_id'):
                referenced_sources.add(ref['source_id'])
        for variant, text in (row.get('bullet') or {}).items():
            if len(str(text).split()) > 60:
                long_variants.append({'id': row.get('id'), 'variant': variant,
                                      'words': len(str(text).split())})
    duplicate_facts = [ids for ids in facts.values() if len(ids) > 1]
    unreferenced_sources = [row.get('id') for row in sources
                            if row.get('id') not in referenced_sources]
    counts = collections.Counter(row.get('type') for row in active)
    protected = {
        'published_publications': sorted(row['id'] for row in active
                                         if row.get('type') == 'publication'
                                         and row.get('status') == 'PUBLISHED'),
        'professional_credentials': sorted(row['id'] for row in active
                                            if row.get('type') == 'credential'
                                            and row.get('tier') == 'professional'),
        'governed_highlights': sorted(row['id'] for row in active
                                      if row.get('placement') == 'highlights'),
        'education': sorted(row['id'] for row in active
                            if row.get('type') == 'education'),
    }
    return {
        '_schema': 'joblooper.truth-audit.v2', 'generated_at': store.now(),
        'subject_sha256': approval_subject()['sha256'],
        'generation_policy_sha256': store.generation_fingerprint()['sha256'],
        'readiness': readiness(), 'integrity_errors': errors,
        'integrity_warnings': warnings, 'stats': stats,
        'active_by_type': dict(sorted(counts.items())),
        'protected_inventory': protected,
        'bloat_signals': {
            'superseded_records': len(records) - len(active),
            'exact_duplicate_facts': duplicate_facts,
            'wording_variants_over_60_words': long_variants,
            'unreferenced_sources': unreferenced_sources,
        },
    }


def to_markdown(report):
    state = report['readiness']
    out = ['# GROUND-TRUTH AUDIT', '',
           f"**State:** {'READY' if state['ready'] else 'NEEDS REVIEW'}  ",
           f"**Candidate-truth digest:** `{report['subject_sha256']}`  ",
           f"**Generation-policy fingerprint:** `{report.get('generation_policy_sha256', 'n/a')}`  ",
           f"**Generated:** {report['generated_at']}", '',
           '## PROTECTED INVENTORY', '']
    for name, values in report['protected_inventory'].items():
        out.append(f"- {name.replace('_', ' ').title()}: {len(values)}"
                   + (f" — {', '.join(values)}" if values else ''))
    out += ['', '## INTEGRITY', '',
            f"- Errors: {len(report['integrity_errors'])}",
            f"- Warnings: {len(report['integrity_warnings'])}"]
    for value in report['integrity_errors']:
        out.append(f'- BLOCK: {value}')
    for value in report['integrity_warnings']:
        out.append(f'- REVIEW: {value}')
    bloat = report['bloat_signals']
    out += ['', '## LEANNESS SIGNALS', '',
            f"- Superseded records retained for audit: {bloat['superseded_records']}",
            f"- Exact duplicate fact groups: {len(bloat['exact_duplicate_facts'])}",
            f"- Wording variants over 60 words: {len(bloat['wording_variants_over_60_words'])}",
            f"- Registered sources not cited by active truth: {len(bloat['unreferenced_sources'])}",
            '', 'No fact is deleted automatically. Resolve duplicates and stale material with '
                'evidence, an append-only change record and renewed candidate sign-off.', '']
    return '\n'.join(out)


def approval_record(reviewer):
    subject = approval_subject()
    today = datetime.date.fromisoformat(store.today())
    return {
        '_schema': 'joblooper.truth-approval.v2',
        'subject_sha256': subject['sha256'], 'reviewer': str(reviewer).strip(),
        'reviewed_at': store.now(),
        'next_audit_due': (today + datetime.timedelta(days=AUDIT_INTERVAL_DAYS)).isoformat(),
        'truth_feedback_sha256': digest(),
    }
