"""Outcome reasoning stays versioned, evidence-aware and outside career truth."""
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
from core import learning, preflight, preview, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-learning-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()
        truth_before = store.truth_context()['truth_sha256']
        slug = store.list_jobs()[0]
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        app = {
            'app_id': slug, 'company': jd['company'], 'role': jd['title'],
            'applied': '2026-01-02', 'status': 'applied', 'hypotheses': [],
            'submission_mode': 'exact_approved_artefact',
            'release_manifest_sha256': 'a' * 64, 'cv_sha256': 'b' * 64,
            'identity': 'systems_engineer', 'coverage': 0.82,
            'exclude_from_analytics': False,
        }
        checks.append(('both exact submission modes are eligible for bounded learning',
                       learning._exact_submission(app)
                       and learning._exact_submission({
                           **app,
                           'submission_mode': 'user_confirmed_external_submission'})
                       and not learning._exact_submission({
                           **app, 'submission_mode': 'user_asserted_without_hash'})))
        store.write_jsonl(store.p('index', 'applications.jsonl'), [app])
        jl.cmd_outcome(SimpleNamespace(
            job=slug, status='rejected', date=None, latency='under_24h',
            reason=None, cat=None, conf=0.5, note=None, author='user',
            evidence_for=[], evidence_against=[]))
        app = next(row for row in store.applications() if row['app_id'] == slug)
        checks.append(('qualitative response timing does not invent an exact date',
                       app['responded'] is None
                       and app['responded_date_status'] == 'not_provided'
                       and app['response_latency'] == {
                           'band': 'under_24h', 'basis': 'user_reported'}
                       and 'days' not in app))
        metrics_out = io.StringIO()
        with contextlib.redirect_stdout(metrics_out):
            metrics_result = jl.cmd_metrics(SimpleNamespace())
        checks.append(('metrics expose capture gaps without claiming prediction',
                       metrics_result == 0
                       and 'exact submission correlation 1/1 (100%)'
                       in metrics_out.getvalue()
                       and 'portal-answer capture        0/1 (0%)'
                       in metrics_out.getvalue()
                       and 'under-24-hour outcomes       1/1 (100%)'
                       in metrics_out.getvalue()
                       and 'sample is too small' in metrics_out.getvalue()
                       and 'not hiring probabilities' in metrics_out.getvalue()))

        added = learning.record_hypothesis(
            slug, 'HARD_GATE', 0.55, 'A named platform may have decided the screen.',
            'reviewer', ['Platform was mandatory'], ['No employer reason supplied'])
        checks.append(('new hypothesis receives a stable human id', added['id'] == 'H01'))
        try:
            learning.record_hypothesis(
                slug, None, 0.70, 'Premature causal certainty.', 'reviewer',
                ['One signal'], ['No response detail'], hypothesis_id='H01',
                status='CONFIRMED', unknowns=['Screening rubric is unknown'])
            premature_refused = False
        except ValueError:
            premature_refused = True
        checks.append(('first-pass confirmation is refused', premature_refused))
        alternative = learning.record_hypothesis(
            slug, 'LOCATION_VISA', 0.35,
            'Location or work-authorisation screening is a competing explanation.',
            'reviewer', ['Role location was constrained'],
            ['Candidate mobility was visible'], unknowns=['Sponsorship policy is unknown'])
        checks.append(('a competing explanation is stored separately',
                       alternative['id'] == 'H02'))
        learning.record_hypothesis(
            slug, None, 0.62, 'The platform explanation remains stronger than location.',
            'reviewer', ['Platform was a named requirement'],
            ['No employer reason supplied'], hypothesis_id='H01', status='OPEN',
            company_context=['Named platform remained mandatory'])
        revised = learning.record_hypothesis(
            slug, None, 0.75, 'The same platform pattern recurred.', 'reviewer',
            ['Second comparable outcome'], ['Transferable evidence was visible'],
            hypothesis_id='H01', status='RETAINED_PLAUSIBLE',
            company_context=['Named platform remained mandatory'],
            profile_factors=['Transferable experience was visible'],
            other_factors=['No interview signal'], unknowns=['Screening rubric is unknown'])
        checks.append(('revision history is append-only',
                       revised['status'] == 'RETAINED_PLAUSIBLE'
                       and len(revised['revisions']) == 3
                       and revised['revisions'][-1]['stage'] == 'CHALLENGE'))
        events = store.application_events()
        event_names = [event['event'] for event in events]
        checks.append(('reasoning and confirmed learning are evented',
                       event_names == ['OUTCOME', 'HYPOTHESIS_ADDED', 'HYPOTHESIS_ADDED',
                                       'HYPOTHESIS_REVISED', 'HYPOTHESIS_REVISED',
                                       'LEARNING_RETAINED_PLAUSIBLE']))
        lessons = learning.relevant_lessons(jd)
        checks.append(('retained reasoning surfaces on a similar future review',
                       bool(lessons) and lessons[0]['hypothesis_id'] == 'H01'))
        retained = learning.confirmed_lessons()
        checks.append(('confirmed lessons retain structured context and source case',
                       retained[0]['app_id'] == slug
                       and bool(retained[0]['revisions'][-1]['company_context'])
                       and bool(retained[0]['revisions'][-1]['unknowns'])))
        future_jd = dict(jd)
        future_jd['_slug'] = 'future-similar-application'
        questions = preflight.questions(
            future_jd, {'requirements': []},
            {'primary': 'systems_engineer', 'ranked': [('systems_engineer', 1.0)]})
        checks.append(('retained rejection learning becomes a pre-generation question',
                       any(row['id'].startswith('PRIOR-REJECTION-')
                           for row in questions)))
        negative_preview = '\n'.join(preview.outcome_learning_lines({
            'learning_signals': lessons, 'positive_outcome_signals': []}))
        checks.append(('rejection-only preview retains its evidence and unknowns',
                       'PRIOR LEARNING SIGNALS' in negative_preview
                       and 'HARD_GATE' in negative_preview
                       and 'still unknown' in negative_preview
                       and 'PRIOR POSITIVE OUTCOMES' not in negative_preview))

        current = next(row for row in store.applications() if row['app_id'] == slug)
        current['status'] = 'interview'
        current['responded'] = '2026-01-10'
        current['days'] = 8
        store.write_jsonl(store.p('index', 'applications.jsonl'), [current])
        positive = learning.relevant_positive_outcomes(future_jd)
        checks.append(('exact positive outcome surfaces without a causal claim',
                       bool(positive) and positive[0]['status'] == 'interview'
                       and 'unknown' in positive[0]['observation']))
        positive_preview = '\n'.join(preview.outcome_learning_lines({
            'learning_signals': [], 'positive_outcome_signals': positive}))
        checks.append(('positive-only preview remains an observation, not a cause',
                       'PRIOR POSITIVE OUTCOMES' in positive_preview
                       and 'causal reasoning is unknown' in positive_preview
                       and 'PRIOR LEARNING SIGNALS' not in positive_preview))
        positive_questions = preflight.questions(
            future_jd, {'requirements': []},
            {'primary': 'systems_engineer', 'ranked': [('systems_engineer', 1.0)]})
        checks.append(('positive outcome becomes a bounded pre-generation question',
                       any(row['id'].startswith('PRIOR-POSITIVE-')
                           and 'does not prove why' in row['question']
                           for row in positive_questions)))
        try:
            learning.record_hypothesis(
                slug, 'ATS_KEYWORD', 0.5, 'Invalid success-cause hypothesis.',
                'reviewer', ['Interview'], ['Cause unknown'])
            positive_hypothesis_refused = False
        except ValueError:
            positive_hypothesis_refused = True
        checks.append(('rejection hypotheses are refused for positive outcomes',
                       positive_hypothesis_refused))
        checks.append(('outcome learning never mutates career truth',
                       store.truth_context()['truth_sha256'] == truth_before))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} learning invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
