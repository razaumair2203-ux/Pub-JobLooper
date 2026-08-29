"""One observable dashboard journey from captured JD to recorded outcome."""
import copy
import base64
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

from core import dashboard, dashboard_actions, match, preflight, release, store, vec


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
              and captured['touchpoints'][1]['status'] == 'current'
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
              and reviewed['touchpoints'][1]['status'] == 'complete'
              and reviewed['touchpoints'][2]['status'] == 'current'
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
              and planned['touchpoints'][2]['status'] == 'complete'
              and planned['touchpoints'][3]['status'] == 'current'
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
              and stale_plan['touchpoints'][2]['status'] == 'current', results)
        store.write_json(preflight_path, original_preflight)

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
              and blocked['touchpoints'][4]['status'] == 'blocked'
              and next(item for item in dashboard.build_snapshot()['attention']
                       if item['job_id'] == job_id)['route'] == 'evidence', results)
        store.write_json(cv_path, original_cv)
        store.write_json(plan_receipt_path, original_plan_receipt)

        dashboard_actions.mark_presented(job_id)
        presented = dashboard.build_snapshot()['jobs'][0]
        check('review binds the complete current bundle before approval',
              presented['workflow']['presentation'] is True
              and presented['workflow']['can_approve'] is True
              and presented['touchpoints'][3]['status'] == 'complete'
              and presented['touchpoints'][4]['status'] == 'current'
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
              and interrupted_build['touchpoints'][5]['status'] == 'current'
              and interrupted_attention['route'] == 'build', results)

        dashboard_actions.build_application(job_id, no_pdf=True)
        built, registry = dashboard.build_snapshot(include_private=True)
        packaged = built['jobs'][0]
        check('approval and build expose a verified dated package',
              packaged['workflow']['approval'] is True
              and packaged['workflow']['package'] is True
              and packaged['workflow']['can_submit'] is True
              and packaged['touchpoints'][4]['status'] == 'complete'
              and packaged['touchpoints'][5]['status'] == 'complete'
              and packaged['touchpoints'][6]['status'] == 'current'
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
              and submitted['touchpoints'][6]['status'] == 'complete'
              and submitted['touchpoints'][7]['status'] == 'waiting'
              and not dashboard.build_snapshot()['attention'], results)

        dashboard_actions.record_outcome(
            job_id, 'rejected', latency='under_24h')
        outcome = dashboard.build_snapshot()['jobs'][0]
        check('outcome records only the observation and completes the journey proof',
              outcome['phase'] == 'rejected'
              and outcome['employer_stated_reason'] is None
              and outcome['touchpoints'][7]['status'] == 'complete'
              and all(row['status'] == 'complete'
                      for row in outcome['touchpoints']), results)

    for name, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in results)
    print(f"\n  {passed}/{len(results)} dashboard journey touchpoints hold")
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
