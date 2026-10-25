"""Truth approval is exact, incremental comments block safely, audits are read-only."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import jl
from core import store, truth_review, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-truth-review-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data); vec.reset_caches()
        state = truth_review.readiness()
        checks.append(('fixture starts with digest-bound approval', state['ready']))
        legacy_before = truth_review.approval_subject()['sha256']
        store.log_change('audit note', 'Recorded a test audit event.',
                         'No generation input changed.')
        checks.append(('audit-only changelog does not stale truth approval',
                       truth_review.approval_subject()['sha256'] == legacy_before
                       and truth_review.readiness()['ready']))

        # The starter intentionally carries a v1 approval to exercise migration.
        # Renew it to v2 before testing the new split so subsequent section-policy
        # mutations are judged against the candidate-only approval surface.
        with contextlib.redirect_stdout(io.StringIO()):
            jl.cmd_onboard(SimpleNamespace(
                action='finalize', confirm_reviewed=True, reviewer='fixture-migration'))
        migrated = truth_review.readiness()
        checks.append(('explicit migration writes a v2 candidate-only approval',
                       migrated['ready']
                       and migrated['approval'].get('_schema') == 'joblooper.truth-approval.v2'
                       and migrated['approval']['subject_sha256']
                       == truth_review.approval_subject()['sha256']))
        before = truth_review.approval_subject()['sha256']

        sections_path = store.p('truth', 'sections.json')
        sections = store.read_json(sections_path)
        before_generation = store.generation_fingerprint()['sha256']
        sections['default_pages'] = 3
        store.write_json(sections_path, sections); store.reset_context_cache()
        after_generation = store.generation_fingerprint()['sha256']
        checks.append(('section policy changes generation without invalidating candidate facts',
                       truth_review.readiness()['ready']
                       and truth_review.approval_subject()['sha256'] == before
                       and after_generation != before_generation))

        structure = truth_review.record(
            'structure', 'Test a document-structure policy change.', 'candidate')
        sections['default_pages'] = 2
        store.write_json(sections_path, sections); store.reset_context_cache()
        truth_review.resolve(structure['id'], 'ADOPTED',
                             'Updated the governed section policy.',
                             'Generation fingerprint changed; candidate facts did not.')
        checks.append(('adopted structure feedback preserves candidate sign-off',
                       truth_review.readiness()['ready']))

        item = truth_review.record('fact', 'Check whether a metric is still current.',
                                   'candidate', ['user comment'])
        checks.append(('open candidate comment blocks generation',
                       item['status'] == 'OPEN' and not truth_review.readiness()['ready']))
        truth_review.resolve(item['id'], 'REJECTED',
                             'No truth change was made.',
                             'Candidate rejected the proposed update.')
        checks.append(('rejected comment restores unchanged approved truth',
                       truth_review.readiness()['ready']))

        adopted = truth_review.record('source', 'Adopt evidence from a new source.',
                                       'candidate')
        try:
            truth_review.resolve(adopted['id'], 'ADOPTED',
                                 'Claimed a change without making one.',
                                 'No different digest exists.')
            unchanged_adoption_refused = False
        except ValueError:
            unchanged_adoption_refused = True
        checks.append(('adopted truth comment requires an actual candidate-truth change',
                       unchanged_adoption_refused))
        profile_path = store.p('truth', 'profile.json')
        profile = store.read_json(profile_path, {}) or {}
        profile['test_review_marker'] = 'changed candidate fact for fixture'
        store.write_json(profile_path, profile); store.reset_context_cache()
        truth_review.resolve(adopted['id'], 'ADOPTED',
                             'Source was registered and candidate truth changed.',
                             'Integrity review will run before renewed sign-off.')
        checks.append(('adopted candidate truth change forces renewed sign-off',
                       not truth_review.readiness()['ready']))
        with contextlib.redirect_stdout(io.StringIO()):
            jl.cmd_onboard(SimpleNamespace(
                action='finalize', confirm_reviewed=True, reviewer='truth-test'))
        checks.append(('explicit renewed review restores exact candidate readiness',
                       truth_review.readiness()['ready']))
        subject_before_audit = truth_review.approval_subject()['sha256']
        report = truth_review.audit()
        checks.append(('periodic audit is read-only and inventories protected facts',
                       truth_review.approval_subject()['sha256'] == subject_before_audit
                       and 'professional_credentials' in report['protected_inventory']))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} truth-review invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
