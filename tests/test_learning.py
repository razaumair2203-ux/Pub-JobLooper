"""Outcome reasoning stays versioned, evidence-aware and outside career truth."""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import learning, store, vec


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
            'applied': '2026-01-02', 'status': 'rejected', 'hypotheses': [],
            'exclude_from_analytics': False,
        }
        store.write_jsonl(store.p('index', 'applications.jsonl'), [app])

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
                       event_names == ['HYPOTHESIS_ADDED', 'HYPOTHESIS_ADDED',
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
        checks.append(('outcome learning never mutates career truth',
                       store.truth_context()['truth_sha256'] == truth_before))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} learning invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
