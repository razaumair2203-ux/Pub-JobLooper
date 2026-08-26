"""The exact JD, submitted package, outcome and reasoning remain correlated."""
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import jl
from core import (build, casefile, cover_letter, employer_response,
                  employer_review, learning, match, preview, release, render,
                  preflight, store, vec)


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-case-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()
        slug = store.list_jobs()[0]
        directory = store.job_dir(slug)
        jd = store.read_json(os.path.join(directory, 'jd.json'))
        jd['_slug'] = slug
        identity = match.pick_identity(jd)
        mapping = match.match_jd(jd, identity)
        preflight_record = preflight.create(
            slug, jd, mapping, identity, reviewer='lifecycle-test',
            note='Fictional mandatory gap reviewed for lifecycle testing.')
        mapping['_preflight'] = {
            'subject_sha256': preflight_record['subject_sha256'],
            'decision': preflight_record['decision'],
            'reviewer': preflight_record['reviewer']}
        mapping['learning_signals'] = []
        mapping['_inputs'] = store.generation_fingerprint(jd)
        cv = build.assemble(jd, mapping, target_pages=2)
        letter = cover_letter.assemble(jd, mapping, cv)
        risk = employer_review.assess(jd, mapping, cv)
        store.write_json(os.path.join(directory, 'match.json'), mapping)
        store.write_json(os.path.join(directory, 'cv.json'), cv)
        store.write_json(os.path.join(directory, 'cover-letter.json'), letter)
        store.write_json(os.path.join(directory, 'employer-risk.json'), risk)
        store.write_text(os.path.join(directory, 'EMPLOYER-RISK.md'),
                         employer_review.to_markdown(risk))
        store.write_text(os.path.join(directory, 'PREVIEW.md'),
                         preview.render(jd, mapping, cv, slug))
        ats = os.path.join(directory, 'cv.ats.txt')
        docx = os.path.join(directory, 'CV.docx')
        store.write_text(ats, render.to_ats_text(cv))
        store.write_text(docx, 'fictional exact DOCX submitted by lifecycle test')
        release.present(slug)
        release.approve(slug, 'lifecycle-test',
                        {gate: 'PASS' for gate in release.MANUAL_GATES},
                        user_signoff=True)
        artefacts = {
            'jd': os.path.join(directory, 'jd.json'),
            'jd_raw': os.path.join(directory, 'jd.raw.md'),
            'match': os.path.join(directory, 'match.json'),
            'cv': os.path.join(directory, 'cv.json'),
            'letter': os.path.join(directory, 'cover-letter.json'),
            'risk': os.path.join(directory, 'employer-risk.json'),
            'risk_markdown': os.path.join(directory, 'EMPLOYER-RISK.md'),
            'preview': os.path.join(directory, 'PREVIEW.md'),
            'approval': os.path.join(directory, 'approval.json'),
            'ats': ats, 'docx': docx,
        }
        for label in sorted(release.REQUIRED_RELEASE_LABELS - set(artefacts)):
            placeholder = os.path.join(directory, f'test-{label}.txt')
            store.write_text(placeholder, f'fictional {label} release artefact')
            artefacts[label] = placeholder
        package, manifest = release.create_release(slug, artefacts)

        jl.cmd_apply(SimpleNamespace(
            job=slug, release=None, channel=None, date=None,
            sent_file=os.path.join(package, 'CV.docx')))
        try:
            employer_response.resolve(
                'A generic rejection with no company, role or reference.')
            unlocated_refused = False
        except ValueError:
            unlocated_refused = True
        checks.append(('unidentifiable employer response is refused rather than guessed',
                       unlocated_refused))
        email = ('Thank you for applying for Senior Systems Engineer at Example Aerospace. '
                 'We will not be moving forward because the position has been filled.')
        duplicate_slug = slug + '-duplicate'
        shutil.copytree(directory, store.job_dir(duplicate_slug))
        original_app = next(app for app in store.applications() if app['app_id'] == slug)
        duplicate_app = dict(original_app)
        duplicate_app['app_id'] = duplicate_slug
        store.write_jsonl(store.p('index', 'applications.jsonl'),
                          store.applications() + [duplicate_app])
        try:
            employer_response.resolve(email)
            ambiguous_refused = False
        except ValueError:
            ambiguous_refused = True
        checks.append(('multiple company-and-role matches are refused as ambiguous',
                       ambiguous_refused))
        store.write_jsonl(store.p('index', 'applications.jsonl'),
                          [app for app in store.applications()
                           if app['app_id'] != duplicate_slug])
        shutil.rmtree(store.job_dir(duplicate_slug))
        selected, response, duplicate = employer_response.ingest(
            email,
            received=store.today())
        checks.append(('response resolves to one exact submitted JD and CV manifest',
                       selected['slug'] == slug and not duplicate
                       and selected['app']['applied'] is None
                       and response['submitted_manifest_sha256']
                       == manifest['manifest_sha256']))
        learning.record_hypothesis(
            slug, 'TIMING_INTERNAL', 0.7, 'Fast closure suggests an advanced candidate.',
            'reviewer', ['Outcome arrived quickly'], ['No direct employer confirmation'],
            company_context=['Employer said the position was filled'],
            profile_factors=['No profile mismatch was stated'],
            other_factors=['Decision arrived on submission day'],
            unknowns=['Internal candidate status is unknown'])

        case = casefile.build(slug)
        checks.append(('submission points to the one exact submitted package',
                       case['release_id'] == 'approved'
                       and case['release_manifest']['manifest_sha256']
                       == manifest['manifest_sha256']))
        checks.append(('case reconstructs company, role and immutable JD/CV data',
                       case['company'] == jd['company'] and case['role'] == jd['title']
                       and case['ats_text_words'] > 0 and not case['snapshot_errors']
                       and case['profile_context'].get('based_in') == 'Example City'
                       and case['days'] is None))
        checks.append(('case reconstructs cover letter and pre-application risk decision',
                       case['cover_letter_words'] > 0
                       and case['employer_risk_decision'] == 'LEAVE_AS_IS'))
        checks.append(('case retains requirement-to-rendered-line mappings',
                       any(line[3] for line in case['lines'])))
        selected_ids = set((cv.get('_selection') or {}).get('selected_ids') or [])
        omitted_ids = {item['id'] for item in case['omitted']}
        checks.append(('selected supporting evidence is never labeled held back',
                       selected_ids.isdisjoint(omitted_ids)))
        checks.append(('case retains employer response correlation evidence',
                       case['employer_responses'][0]['response_id'] == 'R001'
                       and bool(case['employer_responses'][0]['match_evidence'])))
        labels = {item['label'] for item in case['release_files']}
        checks.append(('artifact ledger retains the review and submission set',
                       {'jd', 'jd_raw', 'match', 'cv', 'letter', 'risk',
                        'preview', 'approval', 'ats'} <= labels))
        checks.append(('response, outcome and reasoning stay in the nested record',
                       all(os.path.isfile(release.record_path(package, name)) for name in (
                           'RESPONSES.jsonl', 'OUTCOME.json', 'REASONING.jsonl'))
                       and all(not os.path.isfile(os.path.join(package, name)) for name in (
                           'RESPONSES.jsonl', 'OUTCOME.json', 'REASONING.jsonl'))))
        event_names = [event['event'] for event in case['events']]
        checks.append(('timeline connects package, submission, outcome and reasoning',
                       event_names == ['APPLICATION_BUNDLE_PRESENTED_IN_CHAT',
                                       'APPROVED_ARTEFACTS_BUILT',
                                       'SUBMITTED', 'APPLICATION_RECORDED',
                                       'EMPLOYER_RESPONSE_INGESTED', 'OUTCOME',
                                       'HYPOTHESIS_ADDED']))
        checks.append(('reason is separate from the employer-stated outcome',
                       'position has been filled' in case['stated_reason']
                       and case['hypotheses'][0]['cause'] == 'TIMING_INTERNAL'
                       and bool(case['hypotheses'][0]['revisions'][0]['unknowns'])))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} case-lifecycle invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
