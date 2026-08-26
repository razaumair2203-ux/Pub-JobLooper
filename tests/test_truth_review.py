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
        checks.append(('fixture starts with digest-bound approval',
                       truth_review.readiness()['ready']))
        before = store.truth_approval_subject()['sha256']
        store.log_change('audit note', 'Recorded a test audit event.',
                         'No generation input changed.')
        checks.append(('audit-only changelog does not stale truth approval',
                       store.truth_approval_subject()['sha256'] == before
                       and truth_review.readiness()['ready']))

        sections_path = store.p('truth', 'sections.json')
        sections = store.read_json(sections_path)
        sections['default_pages'] = 3
        store.write_json(sections_path, sections); store.reset_context_cache()
        checks.append(('section-rule change invalidates candidate approval',
                       not truth_review.readiness()['ready']))
        with contextlib.redirect_stdout(io.StringIO()):
            jl.cmd_onboard(SimpleNamespace(
                action='finalize', confirm_reviewed=True, reviewer='truth-test'))
        checks.append(('explicit renewed review restores exact readiness',
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
        truth_review.resolve(adopted['id'], 'ADOPTED',
                             'Source was registered and anchors were reviewed.',
                             'Integrity review will run before renewed sign-off.')
        checks.append(('adopted comment forces renewed sign-off',
                       not truth_review.readiness()['ready']))
        subject_before_audit = store.truth_approval_subject()['sha256']
        report = truth_review.audit()
        checks.append(('periodic audit is read-only and inventories protected facts',
                       store.truth_approval_subject()['sha256'] == subject_before_audit
                       and 'professional_credentials' in report['protected_inventory']))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} truth-review invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
