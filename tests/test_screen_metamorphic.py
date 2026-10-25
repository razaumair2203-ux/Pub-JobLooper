"""Metamorphic attacks on JD-screen provenance/currentness semantics.

Unlike the lifecycle scenario test, these checks mutate one dimension at a time
and assert which identities must remain stable and which must change.
"""
import copy
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import screen, store, vec

BASE = """Project Engineer

Requirements
- Must be eligible to obtain and maintain security clearance.
- Experience with aircraft systems integration is preferred.

Responsibilities
- Coordinate engineering activities across multidisciplinary teams.
"""


def _create(raw=BASE):
    return screen.create(
        raw, company='Example Aerospace', title='Project Engineer',
        url='https://example.invalid/jobs/7654321',
        complete_advert_confirmed=True)


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-screen-meta-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()

        base = _create()

        # Audit metadata is provenance, not candidate/generation content.
        store.log_change('metamorphic_test', 'Audit note only.',
                         'No candidate or generation input changed.')
        after_audit = _create()
        checks.append(('audit-only history preserves factual screen identity',
                       after_audit['screen_sha256'] == base['screen_sha256']))
        checks.append(('audit-only history still changes transport provenance',
                       after_audit['packet_sha256'] != base['packet_sha256']))
        checks.append(('pre-audit screen remains current and promotable in principle',
                       screen.verify(base, require_current=True,
                                     recompute_analysis=True)['valid']))

        # Stay within the established advert-normalization contract: line-ending
        # changes, trailing whitespace and extra padding at an already-existing
        # paragraph break are cosmetic; introducing a new paragraph boundary is
        # deliberately not assumed to be equivalent here.
        cosmetic = BASE.replace('\n', '\r\n')
        cosmetic = cosmetic.replace('Project Engineer\r\n\r\n',
                                    'Project Engineer   \r\n\r\n\r\n')
        cosmetic_packet = _create(cosmetic)
        checks.append(('cosmetic resave preserves normalized advert identity',
                       cosmetic_packet['jd']['raw_normalized_sha256']
                       == base['jd']['raw_normalized_sha256']))
        checks.append(('cosmetic resave preserves byte-exact provenance separately',
                       cosmetic_packet['jd']['raw_sha256'] != base['jd']['raw_sha256']))
        checks.append(('exact-source screen identity distinguishes different source bytes',
                       cosmetic_packet['screen_sha256'] != base['screen_sha256']))

        # A semantically stronger clearance statement is a different advert;
        # no normalization rule may collapse these two requirements.
        stronger = BASE.replace(
            'Must be eligible to obtain and maintain security clearance.',
            'Must currently hold and maintain security clearance.')
        stronger_packet = _create(stronger)
        base_clearance = next(
            row for row in base['requirements'] if 'security clearance' in row['text'].lower())
        stronger_clearance = next(
            row for row in stronger_packet['requirements']
            if 'security clearance' in row['text'].lower())
        checks.append(('meaning change produces a different normalized advert digest',
                       stronger_packet['jd']['raw_normalized_sha256']
                       != base['jd']['raw_normalized_sha256']))
        checks.append(('meaning change preserves the employer wording, not a paraphrase',
                       base_clearance['text']
                       == 'Must be eligible to obtain and maintain security clearance.'
                       and stronger_clearance['text']
                       == 'Must currently hold and maintain security clearance.'))
        checks.append(('meaning change produces a different factual screen identity',
                       stronger_packet['screen_sha256'] != base['screen_sha256']))

        # Even an editor who can recalculate non-secret integrity digests cannot
        # turn strategy-side edits into Joblooper factual authority: promotion
        # recomputes the deterministic analysis from the embedded JD.
        forged = copy.deepcopy(base)
        forged['summary']['coverage'] = 1.0
        forged['requirements'][0]['classification'] = 'DIRECT'
        forged['screen_sha256'] = screen._screen_digest(forged)
        forged['packet_sha256'] = screen._packet_digest(forged)
        result = screen.verify(forged, require_current=True,
                               recompute_analysis=True)
        checks.append(('self-consistent forged digests fail deterministic re-analysis',
                       not result['valid']
                       and 'factual screen no longer matches deterministic analysis'
                       in result['problems']))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} metamorphic JD-screen invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
