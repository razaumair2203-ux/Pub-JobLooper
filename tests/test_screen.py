"""Read-only JD screen and promotion invariants."""
import copy
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import advert_review, screen, store, vec

JD = """Project Engineer

Requirements
- Bachelor's degree in engineering is required.
- Minimum 5 years of engineering experience.
- Must be eligible to obtain and maintain security clearance.
- Experience with aircraft systems integration is preferred.

Responsibilities
- Coordinate engineering activities across multidisciplinary teams and suppliers.
"""


def _packet():
    return screen.create(
        JD, company='Example Aerospace', title='Project Engineer',
        url='https://example.invalid/jobs/1234567',
        complete_advert_confirmed=True)


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-screen-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()

        before_jobs = set(store.list_jobs())
        before_events = list(store.application_events())

        try:
            screen.create(
                JD, company='Example Aerospace', title='Project Engineer',
                complete_advert_confirmed=False)
            refused_incomplete = False
        except ValueError:
            refused_incomplete = True
        checks.append(('authoritative screen refuses unconfirmed/incomplete source',
                       refused_incomplete))

        packet = _packet()
        checks.append(('screen uses dedicated read-only schema',
                       packet.get('_schema') == screen.SCHEMA
                       and packet.get('mode') == screen.MODE
                       and packet['authority']['application_state_created'] is False))
        checks.append(('screening creates no application/work lifecycle state',
                       set(store.list_jobs()) == before_jobs
                       and store.application_events() == before_events))
        checks.append(('fresh screen verifies against current truth and engine',
                       screen.verify(packet, require_current=True,
                                     recompute_analysis=True)['valid']))

        repeated = _packet()
        checks.append(('same exact JD and truth produce stable screen identity',
                       repeated['screen_sha256'] == packet['screen_sha256']))

        exact_requirement = next(
            row for row in packet['requirements']
            if 'security clearance' in row['text'].lower())
        checks.append(('requirement provenance preserves exact JD wording and source line',
                       exact_requirement['text']
                       == 'Must be eligible to obtain and maintain security clearance.'
                       and bool(exact_requirement['source_lines'])))
        checks.append(('clearance wording is not rewritten into a stronger factual claim',
                       'currently hold' not in exact_requirement['text'].lower()
                       and exact_requirement['hard_gate'] is True))

        tampered = copy.deepcopy(packet)
        tampered['requirements'][0]['classification'] = 'DIRECT'
        checks.append(('ordinary packet tampering is detected',
                       not screen.verify(tampered)['valid']))

        forged = copy.deepcopy(packet)
        forged['requirements'][0]['classification'] = (
            'GAP' if forged['requirements'][0]['classification'] != 'GAP' else 'DIRECT')
        forged['screen_sha256'] = screen._screen_digest(forged)
        forged['packet_sha256'] = screen._packet_digest(forged)
        checks.append(('recomputed digest cannot smuggle a changed factual classification',
                       not screen.verify(forged, require_current=True,
                                         recompute_analysis=True)['valid']))

        # Audit-only history is not candidate/generation authority. It should
        # not force a new factual screen when the approved facts and engine are
        # unchanged.
        store.log_change('screen_test', 'Audit-only note.', 'No generation input changed.')
        audit_check = screen.verify(packet, require_current=True,
                                    recompute_analysis=True)
        checks.append(('audit-only changelog does not stale factual screen',
                       audit_check['valid']))

        # Re-screen after the audit so promotion exercises the current packet.
        current = _packet()
        promoted = screen.promote(current)
        app_id = promoted['app_id']
        directory = store.job_dir(app_id)
        checks.append(('promotion creates one normal work record from exact JD bytes',
                       promoted['created'] is True
                       and store.read_text(os.path.join(directory, 'jd.raw.md')) == JD
                       and store.read_json(os.path.join(directory, 'jd.json'))
                           .get('promoted_from_screen_sha256') == current['screen_sha256']))
        checks.append(('promoted advert still requires explicit application confirmation',
                       advert_review.state(app_id)['confirmed'] is False))
        again = screen.promote(current)
        checks.append(('repeated promotion of identical screen is idempotent',
                       again['app_id'] == app_id and again['created'] is False))

        origin = store.read_json(os.path.join(directory, 'screen-origin.json'), {})
        checks.append(('promotion lineage binds application to exact screen and source',
                       origin.get('screen_sha256') == current['screen_sha256']
                       and origin.get('jd_raw_sha256') == store.sha256_text(JD)))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} JD-screen invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
