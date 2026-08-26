"""Ground-truth context freshness and authority-boundary checks."""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import integrity, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-context-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()

        first = store.truth_context()
        snapshot = store.p('index', 'truth_context.json')
        checks.append(('context is private and materialised', os.path.isfile(snapshot)))
        checks.append(('fictional truth is loaded once as a coherent set',
                       first['stats']['records'] == 23 and len(store.anchors()[1]) == 23))
        second = store.truth_context()
        checks.append(('unchanged truth reuses the in-process context', first is second))
        checks.append(('context declares authority and reviewer limits',
                       bool(first['oversight_contract']['reviewer_must_not'])
                       and first['authority']['derived_cache'] == 'index/truth_context.json'))

        profile = store.read_json(store.p('truth', 'profile.json'))
        profile['_context_test_marker'] = True
        store.write_json(store.p('truth', 'profile.json'), profile)
        changed = store.truth_context()
        checks.append(('truth change invalidates and rebuilds the snapshot',
                       changed['truth_sha256'] != first['truth_sha256']
                       and changed['profile'].get('_context_test_marker') is True))
        fingerprint = store.generation_fingerprint()
        checks.append(('generation records the exact context fingerprint',
                       fingerprint['files']['truth_context']
                       == changed['generation_truth_sha256']))
        checks.append(('approval fingerprint includes deterministic engine code',
                       fingerprint['files']['engine/core/build.py']
                       == store.sha256_file(os.path.join(ROOT, 'core', 'build.py'))
                       and fingerprint['files']['engine/core/gates.py']
                       == store.sha256_file(os.path.join(ROOT, 'core', 'gates.py'))
                       and fingerprint['files']['engine/core/language.py']
                       == store.sha256_file(os.path.join(ROOT, 'core', 'language.py'))
                       and fingerprint['files']['engine/core/pdftext.py']
                       == store.sha256_file(os.path.join(ROOT, 'core', 'pdftext.py'))))

        before_audit = store.generation_fingerprint()
        store.log_change('test_audit_only', 'Record why; alter no truth input.',
                         'Audit event only.')
        after_audit = store.generation_fingerprint()
        checks.append(('audit-only changelog append does not stale generation',
                       before_audit['sha256'] == after_audit['sha256']
                       and store.truth_context()['truth_sha256']
                       != changed['truth_sha256']))

        unreviewed_path = store.p('truth', 'UNREVIEWED-NOTES.md')
        context_before_notes = store.truth_context()
        fingerprint_before_notes = store.generation_fingerprint()
        store.write_text(unreviewed_path, '# Notes\n\nUnreviewed prose is not truth.\n')
        checks.append(('unregistered notes stay outside truth and generation authority',
                       store.truth_context() is context_before_notes
                       and store.generation_fingerprint()['sha256']
                       == fingerprint_before_notes['sha256']))

        sections_path = store.p('truth', 'sections.json')
        sections = store.read_json(sections_path)
        sections['sections'][0]['tailoring'] = 'invent_from_jd'
        store.write_json(sections_path, sections)
        contract_errors, _, _ = integrity.check_truth()
        checks.append(('invalid section-tailoring contracts block integrity',
                       any('unknown tailoring contract' in error
                           for error in contract_errors)))

        sources_path = store.p('truth', 'sources.jsonl')
        store.write_text(
            sources_path,
            store.read_text(sources_path).rstrip() + '\n' +
            '{"id":"SRC-UNREVIEWED","kind":"historical_cv",'
            '"sha256":"abc","note":"fictional broad source"}\n')
        source_errors, _, _ = integrity.check_truth()
        checks.append(('an unreviewed broad source blocks generation authority',
                       any('SRC-UNREVIEWED' in error and 'coverage_review' in error
                           for error in source_errors)))

        store.write_text(
            sources_path,
            store.read_text(sources_path).rstrip() + '\n' +
            '{"id":"SRC-V2-INCOMPLETE","kind":"historical_cv",'
            '"sha256":"def","coverage_review":{"status":"reviewed",'
            '"reviewed_at":"2026-08-26","reviewed_sha256":"def",'
            '"scope":"fictional current review"}}\n')
        disposition_errors, _, _ = integrity.check_truth()
        checks.append(('new broad-source reviews require claim dispositions',
                       any('SRC-V2-INCOMPLETE' in error and 'claim_dispositions' in error
                           for error in disposition_errors)))

        anchors_path = store.p('truth', 'anchors.jsonl')
        anchors = store.read_jsonl(anchors_path)
        pair = [row for row in anchors if row.get('id') in {'SYS-001', 'MRO-002'}]
        for row in pair:
            other = 'MRO-002' if row['id'] == 'SYS-001' else 'SYS-001'
            row['evidence_refs'] = [{'anchor_id': other}]
        store.write_jsonl(anchors_path, anchors)
        cycle_errors, _, _ = integrity.check_truth()
        checks.append(('cyclic anchor citations cannot masquerade as provenance',
                       any('evidence-reference cycle' in error for error in cycle_errors)))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} context invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
