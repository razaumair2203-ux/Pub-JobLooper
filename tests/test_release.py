"""Approval-folder and exact-submission lifecycle regression tests."""
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
from core import (build, cover_letter, employer_review, feedback, match, preview,
                  preflight, release, store, vec)


def _plan(slug):
    directory = store.job_dir(slug)
    jd = store.read_json(os.path.join(directory, 'jd.json'))
    jd['_slug'] = slug
    identity = match.pick_identity(jd)
    mapping = match.match_jd(jd, identity)
    preflight_record = preflight.create(
        slug, jd, mapping, identity, reviewer='release-test',
        note='Fictional mandatory gap reviewed for lifecycle testing.')
    mapping['_preflight'] = {
        'subject_sha256': preflight_record['subject_sha256'],
        'decision': preflight_record['decision'], 'reviewer': preflight_record['reviewer']}
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
    return directory, jd, mapping, cv


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-release-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()
        slug = store.list_jobs()[0]
        directory, jd, mapping, cv = _plan(slug)
        discovery = release.discover(slug)
        checks.append(('unapproved discovery reports chat review and no sendable CV',
                       discovery['state'] == 'CHAT_REVIEW'
                       and not discovery['artifacts']))

        refused = jl.cmd_build(SimpleNamespace(
            job=slug, force=True, reason='attempted lifecycle bypass', no_pdf=True))
        checks.append(('build cannot precede complete chat review and approval',
                       refused == 1 and not store.approved_dir(slug)))

        try:
            release.approve(slug, 'release-test',
                            {g: 'PASS' for g in release.MANUAL_GATES},
                            user_signoff=True)
            unpresented_refused = False
        except ValueError:
            unpresented_refused = True
        checks.append(('approval is refused before complete chat presentation',
                       unpresented_refused))

        content, presentation = release.present(slug)
        checks.append(('chat presentation contains every rendered section',
                       all(section['name'] in content for section in cv['sections'])
                       and '# DOCUMENT 2 — COVER LETTER' in content
                       and presentation['section_count'] == len(cv['sections'])
                       and presentation['document_count'] == 2
                       and not store.approved_dir(slug)))

        item = feedback.record(slug, 'WORKFLOW',
                               'Show the complete CV before rendering.', 'user',
                               release.plan_digest(slug))
        try:
            release.approve(slug, 'release-test',
                            {g: 'PASS' for g in release.MANUAL_GATES},
                            user_signoff=True)
            feedback_refused = False
        except ValueError:
            feedback_refused = True
        checks.append(('open feedback blocks approval', feedback_refused))
        feedback.resolve(slug, item['id'], 'ADOPTED',
                         'Added an enforced chat-presentation gate.',
                         'Release regression verifies freshness.')
        release.present(slug)

        approval = release.approve(
            slug, 'release-test', {g: 'PASS' for g in release.MANUAL_GATES},
            user_signoff=True)
        package = store.approved_dir(slug)
        folder = os.path.basename(package)
        checks.append(('approval creates one dated human-readable folder',
                       bool(approval) and folder.startswith(store.today() + '__')
                       and jd['company'] in folder and jd['title'] in folder
                       and os.path.isfile(release.record_path(package, 'APPROVAL.json'))
                       and not os.path.exists(os.path.join(package, 'REVIEW'))))

        feedback_before = feedback.digest(slug)
        try:
            jl.cmd_feedback(SimpleNamespace(
                job=slug, feedback_id='F9999', status='ADOPTED',
                implementation='This identifier does not exist.',
                validation='No mutation should have occurred.',
                scope=None, note=None, author='user'))
            invalid_feedback_refused = False
        except SystemExit:
            invalid_feedback_refused = True
        checks.append(('invalid feedback cannot remove an approved package',
                       invalid_feedback_refused and os.path.isdir(package)
                       and store.approved_dir(slug) == package
                       and feedback.digest(slug) == feedback_before))

        dummy_docx = os.path.join(directory, 'test-CV.docx')
        dummy_letter = os.path.join(directory, 'test-COVER-LETTER.docx')
        store.write_text(dummy_docx, 'fictional DOCX placeholder')
        store.write_text(dummy_letter, 'fictional cover-letter placeholder')
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
            'presentation': os.path.join(directory, release.PRESENTATION_NAME),
            'docx': dummy_docx,
            'letter_docx': dummy_letter,
        }
        for label in sorted(release.REQUIRED_RELEASE_LABELS - set(artefacts)):
            placeholder = os.path.join(directory, f'test-{label}.txt')
            store.write_text(placeholder, f'fictional {label} release artefact')
            artefacts[label] = placeholder
        release_dir, manifest = release.create_release(slug, artefacts)
        checks.append(('functional artefacts live in one application-record folder',
                       release_dir == package
                       and manifest['release_id'] == 'approved'
                       and manifest['files']['preview']['file']
                       == 'APPLICATION-RECORD/EVIDENCE.md'
                       and manifest['files']['jd_raw']['file']
                       == 'APPLICATION-RECORD/JOB-DESCRIPTION.md'
                       and os.path.isfile(release.record_path(package, 'MANIFEST.json'))))
        _, errors = release.verify_release(slug)
        checks.append(('fresh approved package verifies', not errors))

        dummy_pdf = os.path.join(directory, 'test-CV.pdf')
        dummy_letter_pdf = os.path.join(directory, 'test-COVER-LETTER.pdf')
        store.write_text(dummy_pdf, '%PDF-1.4\n/Type /Page\n')
        store.write_text(dummy_letter_pdf, '%PDF-1.4\n/Type /Page\n')
        _, manifest = release.attach_pdfs(
            slug, {'pdf': dummy_pdf, 'letter_pdf': dummy_letter_pdf},
            layout={'cv_pages': 1, 'cover_letter_pages': 1})
        checks.append(('an unsubmitted package can recover missing verified PDFs',
                       manifest['files']['pdf']['file'] == 'CV.pdf'
                       and manifest['files']['letter_pdf']['file'] == 'COVER-LETTER.pdf'
                       and not release.verify_release(slug)[1]))
        root_names = set(os.listdir(package))
        checks.append(('approved-folder root contains only sendable documents and one record folder',
                       root_names == {
                           'CV.docx', 'CV.pdf', 'COVER-LETTER.docx',
                           'COVER-LETTER.pdf', release.RECORD_DIR_NAME}))

        try:
            release.record_submission(slug, None)
            guessed_refused = False
        except ValueError:
            guessed_refused = True
        checks.append(('submission refuses to guess the sent file', guessed_refused))

        sent = os.path.join(package, 'CV.docx')
        sent_letter = os.path.join(package, 'COVER-LETTER.docx')
        release_dir, submitted_manifest, receipt = release.record_submission(
            slug, sent, cover_letter_file=sent_letter,
            channel='portal', applied_date=None)
        checks.append(('submission keeps the folder and records the exact bundle',
                       release_dir == package
                       and receipt['sent_file'] == 'CV.docx'
                       and receipt['sent_sha256'] == store.sha256_file(sent)
                       and receipt['sent_cover_letter'] == 'COVER-LETTER.docx'
                       and receipt['sent_cover_letter_sha256']
                       == store.sha256_file(sent_letter)
                       and submitted_manifest['manifest_sha256'] == manifest['manifest_sha256']))
        _, errors = release.verify_submission(slug)
        checks.append(('submission receipt and package verify together', not errors))
        checks.append(('submission receipt remains inside the application record',
                       os.path.isfile(release.record_path(package, release.SUBMISSION_NAME))
                       and not os.path.isfile(os.path.join(package, release.SUBMISSION_NAME))))

        try:
            release.invalidate_unsubmitted_package(slug, 'attempt submitted removal')
            immutable_refused = False
        except ValueError:
            immutable_refused = True
        checks.append(('submitted folder cannot be invalidated', immutable_refused))

        dashboard = store.read_text(store.data_p('START-HERE.md'))
        checks.append(('dashboard links sendable files directly and records one level down',
                       f'jobs/{folder}/CV.docx' in dashboard
                       and f'jobs/{folder}/COVER-LETTER.docx' in dashboard
                       and f'jobs/{folder}/APPLICATION-RECORD/MANIFEST.json' in dashboard
                       and '/REVIEW/' not in dashboard))
        jobs_out = io.StringIO()
        with contextlib.redirect_stdout(jobs_out):
            jl.cmd_jobs(SimpleNamespace())
        checks.append(('jobs prints both stable key and human artefact path',
                       f'key   {slug}' in jobs_out.getvalue()
                       and f'files {package}' in jobs_out.getvalue()
                       and f'use   jl artifacts {slug}' in jobs_out.getvalue()))

        cv_snapshot = os.path.join(package, manifest['files']['cv']['file'])
        with open(cv_snapshot, 'ab') as stream:
            stream.write(b' tamper')
        _, errors = release.verify_release(slug)
        checks.append(('tampered submitted package is refused',
                       any('digest mismatch' in item for item in errors)))
        discovery = release.discover(slug)
        checks.append(('integrity failure does not hide exact artifact paths',
                       discovery['state'] == 'INTEGRITY_ERROR'
                       and bool(discovery['integrity_errors'])
                       and discovery['artifacts']['cv_docx']['state'] == 'VERIFIED'
                       and discovery['artifacts']['cv_pdf']['state'] == 'VERIFIED'
                       and discovery['folder'] == package))
        open_out = io.StringIO()
        with contextlib.redirect_stdout(open_out):
            opened = jl.cmd_open(SimpleNamespace(
                job=slug, kind='cv', print_only=True))
        checks.append(('open refuses a damaged sendable file and points to its folder',
                       opened == 0 and package in open_out.getvalue()
                       and 'PACKAGE_INTEGRITY_ERROR' in open_out.getvalue()))

        # A user may confirm after the fact which manifest-verified PDF was
        # actually sent even though a different, unsent DOCX was edited later.
        # Restore the deliberately damaged evidence snapshot first: evidence
        # corruption must never be tolerated by this narrower recovery path.
        shutil.copy2(os.path.join(directory, 'cv.json'), cv_snapshot)
        os.remove(release.record_path(package, release.SUBMISSION_NAME))
        sent_docx = os.path.join(package, 'CV.docx')
        with open(sent_docx, 'ab') as stream:
            stream.write(b' later unsent edit')
        sent_pdf = os.path.join(package, 'CV.pdf')
        with open(sent_pdf, 'ab') as stream:
            stream.write(b' sent-file tamper probe')
        try:
            release.record_confirmed_external_submission(slug, sent_pdf)
            tampered_sent_refused = False
        except ValueError:
            tampered_sent_refused = True
        checks.append(('external confirmation refuses a changed selected sent file',
                       tampered_sent_refused))
        shutil.copy2(dummy_pdf, sent_pdf)
        screening_source = os.path.join(directory, 'portal-answers.txt')
        store.write_text(screening_source,
                         'Fictional test only: work authorisation = user supplied')
        _, _, external_receipt = release.record_confirmed_external_submission(
            slug, sent_pdf, cover_letter_file=os.path.join(package, 'COVER-LETTER.pdf'),
            channel='portal', screening_file=screening_source)
        verified_receipt, external_errors = release.verify_submission(slug)
        screening_record = external_receipt.get('screening_evidence') or {}
        checks.append(('external confirmation binds only manifest-matching sent files',
                       external_receipt['mode'] == 'user_confirmed_external_submission'
                       and external_receipt['sent_file'] == 'CV.pdf'
                       and bool(external_receipt['unsent_package_integrity_exceptions'])
                       and verified_receipt == external_receipt
                       and not external_errors))
        checks.append(('submission hash-binds optional portal-answer evidence',
                       screening_record.get('file')
                       == 'APPLICATION-RECORD/SCREENING-ANSWERS.txt'
                       and os.path.isfile(os.path.join(package, screening_record['file']))
                       and store.sha256_file(
                           os.path.join(package, screening_record['file']))
                       == screening_record.get('sha256')
                       and 'SCREENING-ANSWERS.txt' not in os.listdir(package)))
        with open(os.path.join(package, screening_record['file']), 'a', encoding='utf-8') as stream:
            stream.write('\ntamper')
        checks.append(('changed portal-answer evidence fails submission verification',
                       'screening-answer evidence digest mismatch'
                       in release.verify_submission(slug)[1]))
        shutil.copy2(screening_source, os.path.join(package, screening_record['file']))
        with open(cv_snapshot, 'ab') as stream:
            stream.write(b' post-confirmation evidence tamper')
        checks.append(('external confirmation never masks later evidence corruption',
                       any(error.startswith('cv:') for error in
                           release.verify_submission(slug)[1])))
        shutil.copy2(os.path.join(directory, 'cv.json'), cv_snapshot)
        checks.append(('external confirmation preserves the unsent package exception',
                       any(error.startswith('docx:') for error in
                           external_receipt['unsent_package_integrity_exceptions'])
                       and any(error.startswith('docx:') for error in
                               release.verify_release(slug)[1])))
        checks.append(('discovery distinguishes an exact submission from an unsent exception',
                       release.discover(slug)['state']
                       == 'SUBMITTED_WITH_UNSENT_EXCEPTION'))
        verify_out = io.StringIO()
        with contextlib.redirect_stdout(verify_out):
            verify_result = jl.cmd_verify(SimpleNamespace(job=slug))
        checks.append(('verify distinguishes the exact submission from its unsent exception',
                       verify_result == 0
                       and 'verified submission' in verify_out.getvalue()
                       and 'unsent-file exception' in verify_out.getvalue()))

        legacy = os.path.join(data, 'legacy-shadow-probe')
        os.makedirs(os.path.join(legacy, release.RECORD_DIR_NAME))
        store.write_json(os.path.join(legacy, release.MANIFEST_NAME), {'legacy': True})
        store.write_text(os.path.join(legacy, release.RECORD_DIR_NAME, 'CASE.md'), 'probe')
        checks.append(('a nested case file cannot shadow a legacy root manifest',
                       release.record_dir(legacy, create=True) == legacy))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} release invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
