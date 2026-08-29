"""One observable dashboard journey from captured JD to recorded outcome."""
import copy
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

from core import dashboard, dashboard_actions, store, vec


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

        preflight = dashboard_actions.preflight_state(job_id)
        answers = {row['id']: 'PROCEED_WITH_RECORDED_GAP'
                   for row in preflight['questions']}
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

        cv_path = os.path.join(store.job_dir(job_id), 'cv.json')
        original_cv = store.read_json(cv_path)
        tampered_cv = copy.deepcopy(original_cv)
        tampered_cv['header']['headline'] += ' · Part-66'
        store.write_json(cv_path, tampered_cv)
        blocked = dashboard.build_snapshot()['jobs'][0]
        check('blocking gates are visible before an approval control is offered',
              bool(blocked['workflow']['gate_blockers'])
              and blocked['workflow']['can_approve'] is False
              and blocked['touchpoints'][4]['status'] == 'blocked'
              and next(item for item in dashboard.build_snapshot()['attention']
                       if item['job_id'] == job_id)['route'] == 'evidence', results)
        store.write_json(cv_path, original_cv)

        dashboard_actions.mark_presented(job_id)
        presented = dashboard.build_snapshot()['jobs'][0]
        check('review binds the complete current bundle before approval',
              presented['workflow']['presentation'] is True
              and presented['workflow']['can_approve'] is True
              and presented['touchpoints'][3]['status'] == 'complete'
              and presented['touchpoints'][4]['status'] == 'current'
              and any(row['id'] == 'work-presentation_record'
                      for row in presented['artifacts']), results)

        dashboard_actions.approve_and_build(
            job_id, 'journey-user',
            'I reviewed the complete CV and cover letter', no_pdf=True)
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

        dashboard_actions.record_submission(
            job_id, registry[(job_id, 'manifest-docx')],
            registry[(job_id, 'manifest-letter_docx')], channel='portal')
        submitted = dashboard.build_snapshot()['jobs'][0]
        check('submission binds the exact sent files and makes outcome current',
              submitted['workflow']['submission'] is True
              and submitted['exact_submission'] is True
              and submitted['touchpoints'][6]['status'] == 'complete'
              and submitted['touchpoints'][7]['status'] == 'current', results)

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
