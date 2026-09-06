"""Typed document feedback becomes an exact, gated before/after change."""
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import jl
from core import dashboard_actions, feedback, match, preferences, preflight, release, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-feedback-change-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data); vec.reset_caches()
        slug = store.list_jobs()[0]
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        jd['_slug'] = slug
        identity = match.pick_identity(jd)
        mapping = match.match_jd(jd, identity)
        rows = preflight.questions(jd, mapping, identity)
        preflight.create(
            slug, jd, mapping, identity, reviewer='feedback-reviewer',
            answers={row['id']: 'PROCEED_WITH_RECORDED_GAP' for row in rows})
        jl.cmd_plan(SimpleNamespace(job=slug, pages=None, identity=None))
        targets = [row for row in feedback.document_targets(slug)
                   if any(value != row['text'] for value in row['alternatives'])]
        target = targets[0]
        replacement = next(value for value in target['alternatives']
                           if value != target['text'])
        item = feedback.record(
            slug, 'CONTENT', 'Use the approved fuller wording for this sentence.',
            'candidate', plan_sha256=release.plan_digest(slug),
            classification='APPLICATION_WORDING', target=target)
        checks.append(('comment binds an exact versioned document sentence',
                       item['target_id'] == target['id']
                       and item['target_sha256'] == target['sha256']
                       and item['selected_text'] == target['text']))
        try:
            feedback.propose(slug, item['id'], replacement + ' invented claim')
            unsupported_refused = False
        except ValueError:
            unsupported_refused = True
        checks.append(('unsupported replacement is refused before proposal',
                       unsupported_refused))
        proposed = feedback.propose(slug, item['id'], replacement)
        accepted = feedback.decide(slug, item['id'], 'ACCEPT')
        checks.append(('before/after proposal requires explicit acceptance',
                       proposed['status'] == 'PROPOSED'
                       and proposed['before_text'] == target['text']
                       and proposed['after_text'] == replacement
                       and accepted['status'] == 'ACCEPTED_PENDING_REPLAN'
                       and bool(feedback.open_items(slug))))
        jl.cmd_plan(SimpleNamespace(job=slug, pages=None, identity=None))
        resolved = next(row for row in feedback.current(slug)
                        if row['id'] == item['id'])
        cv = store.read_json(os.path.join(store.job_dir(slug), 'cv.json'))
        rendered = [bullet.get('text')
                    for section in cv['sections'] for entry in section.get('items', [])
                    for bullet in (entry.get('bullets') or [entry])]
        checks.append(('replan applies exact change and emits validation receipt',
                       resolved['status'] == 'ADOPTED'
                       and replacement in rendered and target['text'] not in rendered
                       and resolved['change_receipt']['before_text'] == target['text']
                       and resolved['change_receipt']['after_text'] == replacement
                       and resolved['change_receipt']['receipt_sha256']
                       and feedback.open_items(slug) == []))

        first_preference = feedback.record(
            slug, 'RULE', 'Keep future CVs to one page.', 'candidate',
            plan_sha256=release.plan_digest(slug),
            classification='REUSABLE_PREFERENCE',
            requested_scope='ALL_APPLICATIONS',
            preference_type='TARGET_PAGES', preference_value='1')
        dashboard_actions.decide_feedback(
            slug, first_preference['id'], 'ACCEPT')
        second_preference = feedback.record(
            slug, 'RULE', 'Use three pages for evidence-heavy applications.', 'candidate',
            plan_sha256=release.plan_digest(slug),
            classification='REUSABLE_PREFERENCE',
            requested_scope='ALL_APPLICATIONS',
            preference_type='TARGET_PAGES', preference_value='3')
        dashboard_actions.decide_feedback(
            slug, second_preference['id'], 'ACCEPT')
        current_preferences = preferences.current()
        checks.append(('a newer preference supersedes the conflicting active value',
                       preferences.options()['target_pages'] == 3
                       and len(preferences.active()) == 1
                       and preferences.active()[0]['value'] == '3'
                       and current_preferences[0]['status'] == 'RETIRED'
                       and current_preferences[0]['superseded_by']
                       == current_preferences[1]['id']))
        retired = dashboard_actions.retire_preference(
            preferences.active()[0]['id'],
            'Candidate no longer wants a global page limit.')
        checks.append(('retiring a preference removes its downstream effect',
                       retired['preference']['status'] == 'RETIRED'
                       and preferences.active() == []
                       and preferences.options()['target_pages'] == 2))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} typed-feedback invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
