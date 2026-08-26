"""Ground-truth comments, approval readiness and lean periodic audits."""
import collections
import datetime
import os

from . import integrity, store


SCOPES = {'FACT', 'SOURCE', 'BOUNDARY', 'WORDING', 'STRUCTURE'}
STATUSES = {'OPEN', 'ADOPTED', 'REJECTED'}
AUDIT_INTERVAL_DAYS = 90


def _path():
    return store.p('index', 'truth_feedback.jsonl')


def items():
    return store.read_jsonl(_path())


def open_items():
    return [item for item in items() if item.get('status') == 'OPEN']


def digest():
    return store.sha256_text(store.canonical_json(items()))


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
        'created_at': store.now(), 'subject_sha256': store.truth_approval_subject()['sha256'],
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
    item['status'] = status
    item['resolved_at'] = store.now()
    item['implementation'] = str(implementation).strip()
    item['validation'] = str(validation).strip()
    store.write_jsonl(_path(), rows)
    if status == 'ADOPTED':
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
    status = store.truth_approval_status()
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
        '_schema': 'joblooper.truth-audit.v1', 'generated_at': store.now(),
        'subject_sha256': store.truth_approval_subject()['sha256'],
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
           f"**Truth digest:** `{report['subject_sha256']}`  ",
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
    subject = store.truth_approval_subject()
    today = datetime.date.fromisoformat(store.today())
    return {
        '_schema': 'joblooper.truth-approval.v1',
        'subject_sha256': subject['sha256'], 'reviewer': str(reviewer).strip(),
        'reviewed_at': store.now(),
        'next_audit_due': (today + datetime.timedelta(days=AUDIT_INTERVAL_DAYS)).isoformat(),
        'truth_feedback_sha256': digest(),
    }
