"""One observable dashboard journey from captured JD to recorded outcome."""
import contextlib
import copy
import base64
import io
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

import jl
from core import dashboard, dashboard_actions, learning, match, preflight, release, store, vec


def check(name, condition, results):
    results.append((name, bool(condition)))


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='joblooper-journey-') as data:
        shutil.copytree(FIXTURE, data, dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()
        job_id = store.list_jobs()[0]

        captured = dashboard.build_snapshot()['jobs'][0]
        check('capture exposes exact JD and makes preflight current',
              captured['touchpoints'][0]['status'] == 'complete'
              and captured['touchpoints'][1]['status'] == 'complete'
              and captured['touchpoints'][2]['status'] == 'current'
              and captured['outputs']['cv'] is False
              and captured['outputs']['letter'] is False
              and {row['id'] for row in captured['artifacts']}
              >= {'work-job_description', 'work-jd_record'}, results)

        preflight_view = dashboard_actions.preflight_state(job_id)
        answers = {row['id']: 'PROCEED_WITH_RECORDED_GAP'
                   for row in preflight_view['questions']}
        dashboard_actions.review_preflight(job_id, answers, 'journey-user')
        reviewed = dashboard.build_snapshot()['jobs'][0]
        check('preflight writes durable answers and makes generation current',
              reviewed['workflow']['preflight'] is True
              and reviewed['touchpoints'][2]['status'] == 'complete'
              and reviewed['touchpoints'][3]['status'] == 'current'
              and reviewed['next_action']
              == 'Generate the CV and cover-letter review bundle'
              and any(row['event'] == 'PREFLIGHT_RECORDED'
                      for row in reviewed['timeline']), results)

        dashboard_actions.prepare_application(job_id)
        planned = dashboard.build_snapshot()['jobs'][0]
        plan_artifacts = {row['id'] for row in planned['artifacts']}
        review = dashboard_actions.presentation(job_id)
        check('prepare creates both documents, evidence and risk records',
              planned['phase'] == 'review'
              and planned['workflow']['plan'] is True
              and planned['outputs']['cv'] is True
              and planned['outputs']['letter'] is True
              and {'work-cv_record', 'work-letter_record', 'work-match_record',
                   'work-risk_record'} <= plan_artifacts
              and review['available'] is True
              and review['valid'] is False
              and planned['touchpoints'][3]['status'] == 'complete'
              and planned['touchpoints'][4]['status'] == 'current'
              and any(row['event'] == 'PLAN_CREATED'
                      for row in planned['timeline']), results)

        plan_receipt_path = os.path.join(
            store.job_dir(job_id), release.PLAN_RECEIPT_NAME)
        original_plan_receipt = store.read_json(plan_receipt_path)
        original_plan_events = sum(
            row['event'] == 'PLAN_CREATED' for row in planned['timeline'])
        repeated_plan = dashboard_actions.prepare_application(job_id)
        after_repeat = dashboard.build_snapshot()['jobs'][0]
        check('repeated prepare reopens the current review without regenerating files',
              repeated_plan['reused'] is True
              and store.read_json(plan_receipt_path) == original_plan_receipt
              and sum(row['event'] == 'PLAN_CREATED'
                      for row in after_repeat['timeline']) == original_plan_events,
              results)

        preflight_path = preflight.path(job_id)
        original_preflight = store.read_json(preflight_path)
        jd = store.read_json(os.path.join(store.job_dir(job_id), 'jd.json'))
        jd['_slug'] = job_id
        identity = match.pick_identity(jd)
        current_mapping = match.match_jd(jd, identity)
        preflight.create(
            job_id, jd, current_mapping, identity, reviewer='second-reviewer',
            answers=answers, note='A new explicit review of the same material gaps.')
        stale_plan = dashboard.build_snapshot()['jobs'][0]
        check('changed preflight decisions stale the plan instead of reusing old prose',
              stale_plan['workflow']['preflight'] is True
              and stale_plan['workflow']['plan_available'] is True
              and stale_plan['workflow']['plan_current'] is False
              and stale_plan['workflow']['plan'] is False
              and stale_plan['workflow']['can_approve'] is False
              and stale_plan['touchpoints'][3]['status'] == 'current', results)
        # A stale plan whose preflight is still complete is refreshed directly.
        check('a stale plan with complete decisions offers the refresh',
              next(item for item in dashboard.build_snapshot()['attention']
                   if item['job_id'] == job_id)['route'] == 'prepare', results)
        # But when the decisions themselves are outstanding -- which is what
        # happens when a retained lesson from an earlier application newly
        # applies here -- prepare would refuse, so offering "refresh the bundle"
        # would hand the user a control that fails when clicked.
        held = store.read_json(preflight_path)
        os.unlink(preflight_path)
        undecided = dashboard.build_snapshot()['jobs'][0]
        undecided_item = next(item for item in dashboard.build_snapshot()['attention']
                              if item['job_id'] == job_id)
        check('outstanding decisions route to preflight, not to a control that fails',
              undecided['workflow']['preflight'] is False
              and undecided['workflow']['plan'] is False
              and undecided_item['kind'] == 'preflight'
              and undecided_item['route'] == 'preflight', results)
        store.write_json(preflight_path, held)

        # Being told only that a plan is stale is not actionable. why-stale must
        # name the governance reason rather than restating the symptom.
        stale_report = io.StringIO()
        with contextlib.redirect_stdout(stale_report):
            stale_result = jl.cmd_why_stale(SimpleNamespace(job=job_id))
        stale_text = stale_report.getvalue()
        check('why-stale names the reason a plan was invalidated',
              stale_result == 0 and 'stale' in stale_text
              and 'preflight' in stale_text.lower(), results)
        store.write_json(preflight_path, original_preflight)
        current_report = io.StringIO()
        with contextlib.redirect_stdout(current_report):
            jl.cmd_why_stale(SimpleNamespace(job=job_id))
        check('why-stale reports a restored plan as current, not stale',
              current_report.getvalue().startswith('current'), results)

        cv_path = os.path.join(store.job_dir(job_id), 'cv.json')
        original_cv = store.read_json(cv_path)
        tampered_cv = copy.deepcopy(original_cv)
        tampered_cv['header']['headline'] += ' · Part-66'
        store.write_json(cv_path, tampered_cv)
        blocker_receipt = copy.deepcopy(original_plan_receipt)
        blocker_receipt['plan_sha256'] = release.plan_digest(job_id)
        store.write_json(plan_receipt_path, blocker_receipt)
        blocked = dashboard.build_snapshot()['jobs'][0]
        check('blocking gates are visible before an approval control is offered',
              bool(blocked['workflow']['gate_blockers'])
              and blocked['workflow']['can_approve'] is False
              and blocked['touchpoints'][5]['status'] == 'blocked'
              and next(item for item in dashboard.build_snapshot()['attention']
                       if item['job_id'] == job_id)['route'] == 'evidence', results)
        store.write_json(cv_path, original_cv)
        store.write_json(plan_receipt_path, original_plan_receipt)

        dashboard_actions.mark_presented(job_id)
        presented = dashboard.build_snapshot()['jobs'][0]
        check('review binds the complete current bundle before approval',
              presented['workflow']['presentation'] is True
              and presented['workflow']['can_approve'] is True
              and presented['touchpoints'][4]['status'] == 'complete'
              and presented['touchpoints'][5]['status'] == 'current'
              and any(row['id'] == 'work-presentation_record'
                      for row in presented['artifacts']), results)

        release.approve(
            job_id, 'journey-user',
            {gate: 'PASS' for gate in release.MANUAL_GATES},
            ('Explicitly reviewed relevance, specificity, contradictions, bloat, '
             'ATS terminology and hostile-recruiter risk.'),
            user_signoff=True)
        interrupted_build = dashboard.build_snapshot()['jobs'][0]
        interrupted_attention = next(
            item for item in dashboard.build_snapshot()['attention']
            if item['job_id'] == job_id)
        check('saved approval exposes Finish build and never a false submit state',
              interrupted_build['workflow']['approval'] is True
              and interrupted_build['workflow']['package'] is False
              and interrupted_build['workflow']['can_build'] is True
              and interrupted_build['workflow']['can_submit'] is False
              and interrupted_build['touchpoints'][6]['status'] == 'current'
              and interrupted_attention['route'] == 'build', results)

        dashboard_actions.build_application(job_id, no_pdf=True)
        built, registry = dashboard.build_snapshot(include_private=True)
        packaged = built['jobs'][0]
        check('approval and build expose a verified dated package',
              packaged['workflow']['approval'] is True
              and packaged['workflow']['package'] is True
              and packaged['workflow']['can_submit'] is True
              and packaged['touchpoints'][5]['status'] == 'complete'
              and packaged['touchpoints'][6]['status'] == 'complete'
              and packaged['touchpoints'][7]['status'] == 'current'
              and (job_id, 'manifest-docx') in registry
              and (job_id, 'manifest-letter_docx') in registry, results)

        package, manifest = release.load_release(job_id)
        manifest_digest = manifest['manifest_sha256']
        repeated_build = dashboard_actions.approve_and_build(
            job_id, 'journey-user',
            'I reviewed the complete CV and cover letter', no_pdf=True)
        check('repeated approval or build is an idempotent verified-package no-op',
              repeated_build['reused'] is True
              and release.load_release(job_id)[1]['manifest_sha256'] == manifest_digest
              and not release.verify_release(job_id)[1], results)

        # JF-06: a corrupted package that has never been submitted has one
        # typed, confirmed recovery action and is rebuilt from approved inputs.
        package_dir, package_manifest = release.load_release(job_id)
        damaged_path = os.path.join(
            package_dir, package_manifest['files']['docx']['file'])
        with open(damaged_path, 'ab') as stream:
            stream.write(b' damaged-unsubmitted-derivative')
        damaged = dashboard.build_snapshot()['jobs'][0]
        repaired = dashboard_actions.repair_unsubmitted_package(
            job_id, 'REBUILD UNSUBMITTED PACKAGE', no_pdf=True)
        repaired_job = dashboard.build_snapshot()['jobs'][0]
        check('unsubmitted package damage exposes and completes a typed rebuild',
              damaged['integrity_resolution'] == 'REBUILD_UNSUBMITTED'
              and repaired['repair'] == 'REBUILT_UNSUBMITTED_PACKAGE'
              and repaired_job['workflow']['package'] is True
              and repaired_job['integrity_resolution'] == 'NONE'
              and not release.verify_release(job_id)[1], results)
        built, registry = dashboard.build_snapshot(include_private=True)

        # Give the package unsent employer-facing derivatives so the exact
        # submission can later be proven independent of them (JF-05).
        directory = store.job_dir(job_id)
        dummy_pdf = os.path.join(directory, 'journey-CV.pdf')
        dummy_letter_pdf = os.path.join(directory, 'journey-COVER-LETTER.pdf')
        store.write_text(dummy_pdf, '%PDF-1.4\n/Type /Page\n')
        store.write_text(dummy_letter_pdf, '%PDF-1.4\n/Type /Page\n')
        release.attach_pdfs(
            job_id, {'pdf': dummy_pdf, 'letter_pdf': dummy_letter_pdf},
            layout={'cv_pages': 1, 'cover_letter_pages': 1})

        release.record_submission(
            job_id, registry[(job_id, 'manifest-docx')],
            registry[(job_id, 'manifest-letter_docx')], channel='portal')
        interrupted_submission = dashboard.build_snapshot()['jobs'][0]
        reconcile_attention = next(
            item for item in dashboard.build_snapshot()['attention']
            if item['job_id'] == job_id)
        check('submission receipt without ledger exposes one recoverable action',
              interrupted_submission['workflow']['submission_reconcile'] is True
              and interrupted_submission['workflow']['can_submit'] is True
              and interrupted_submission['exact_submission'] is False
              and reconcile_attention['kind'] == 'submission_reconcile'
              and reconcile_attention['route'] == 'submission', results)

        dashboard_actions.record_submission(
            job_id, registry[(job_id, 'manifest-docx')],
            registry[(job_id, 'manifest-letter_docx')], channel='portal',
            applied_date=store.today(),
            screening={
                'name': 'portal-answers.txt',
                'base64': base64.b64encode(
                    b'Exact fictional portal answers for journey testing.').decode('ascii'),
            })
        submitted = dashboard.build_snapshot()['jobs'][0]
        check('submission binds the exact sent files and waits without a false task',
              submitted['workflow']['submission'] is True
              and submitted['exact_submission'] is True
              and submitted['touchpoints'][7]['status'] == 'complete'
              and submitted['touchpoints'][8]['status'] == 'waiting'
              and not dashboard.build_snapshot()['attention'], results)

        # JF-05: re-rendering the unsent PDF must not retract a single completed
        # gate, invent a task, or unbind the exact files the employer received.
        package_dir, _ = release.load_release(job_id)
        unsent_pdf = os.path.join(package_dir, 'CV.pdf')
        unsent_original = open(unsent_pdf, 'rb').read()
        with open(unsent_pdf, 'ab') as stream:
            stream.write(b' unsent derivative re-render')
        drifted = dashboard.build_snapshot()['jobs'][0]
        check('unsent derivative drift cannot retract completed submitted gates',
              drifted['exact_submission'] is True
              and drifted['workflow']['submission'] is True
              and drifted['workflow']['preflight'] is True
              and drifted['workflow']['approval'] is True
              and drifted['workflow']['package'] is False
              and drifted['touchpoints'][7]['status'] == 'complete'
              and drifted['integrity_state'] == 'submission_verified_with_exception'
              and any(error.startswith('pdf:')
                      for error in drifted['integrity_exceptions'])
              and not dashboard.build_snapshot()['attention'], results)
        dashboard_actions.acknowledge_package_exception(
            job_id, 'ACKNOWLEDGE SUBMITTED EXCEPTION')
        acknowledged = dashboard.build_snapshot()['jobs'][0]
        check('submitted exception acknowledgement changes no sent-file evidence',
              acknowledged['integrity_acknowledged'] is True
              and acknowledged['integrity_resolution']
              == 'ACKNOWLEDGE_SUBMITTED_EXCEPTION'
              and release.verify_submission(job_id)[1] == [], results)
        with open(unsent_pdf, 'wb') as stream:
            stream.write(unsent_original)

        dashboard_actions.record_outcome(
            job_id, 'rejected', latency='under_24h')
        outcome = dashboard.build_snapshot()['jobs'][0]
        check('outcome records only the observation and completes the journey proof',
              outcome['phase'] == 'rejected'
              and outcome['employer_stated_reason'] is None
              and outcome['touchpoints'][8]['status'] == 'complete'
              and all(row['status'] == 'complete'
                      for row in outcome['touchpoints']), results)

        # JF-07: an integrity failure used to `continue` past every other task
        # for the job, hiding independent record work behind it.
        evidence_label, evidence_info = next(
            (label, info) for label, info
            in release.load_release(job_id)[1]['files'].items()
            if label not in release.EMPLOYER_FACING_LABELS)
        evidence_path = os.path.join(package_dir, evidence_info['file'])
        evidence_original = open(evidence_path, 'rb').read()
        with open(evidence_path, 'ab') as stream:
            stream.write(b'\ntamper')
        concurrent = dashboard.build_snapshot()
        job_items = [item for item in concurrent['attention']
                     if item['job_id'] == job_id]
        kinds = [item['kind'] for item in job_items]
        check('a package-integrity failure never hides independent record tasks',
              {'integrity', 'outcome_date', 'reasoning'} <= set(kinds)
              and kinds.index('integrity') < kinds.index('outcome_date')
              and job_items[0]['severity'] == 'critical', results)
        with open(evidence_path, 'wb') as stream:
            stream.write(evidence_original)
        restored = [item['kind'] for item in dashboard.build_snapshot()['attention']
                    if item['job_id'] == job_id]
        check('restoring the artefact clears only the integrity task',
              'integrity' not in restored
              and set(restored) == {'outcome_date', 'reasoning'}, results)

        original_outcome = learning.active_outcome_events(job_id)[-1]
        correction = dashboard_actions.correct_outcome(
            job_id, original_outcome['event_id'], 'interview',
            response_date=store.today(), latency='under_24h',
            reason='The earlier outcome was entered against the wrong message.',
            response_text='Fictional employer invitation to an interview.')
        corrected_job = dashboard.build_snapshot()['jobs'][0]
        corrected_timeline = corrected_job['timeline']
        check('outcome correction preserves exact pasted response and supersession',
              correction['response_evidence']
              and not release.verify_response_evidence(package_dir)
              and corrected_job['status'] == 'interview'
              and corrected_job['phase'] == 'progressed'
              and any(row['id'] == original_outcome['event_id'] and row['corrected']
                      for row in corrected_timeline)
              and any(row['event'] == 'OUTCOME_CORRECTED' and row['active']
                      for row in corrected_timeline), results)

    for name, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in results)
    print(f"\n  {passed}/{len(results)} dashboard journey touchpoints hold")
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
