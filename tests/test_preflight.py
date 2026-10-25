"""Material questions are resolved before CV and letter prose exists."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import dashboard_actions, feedback, match, preflight, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-preflight-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data); vec.reset_caches()
        slug = store.list_jobs()[0]
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        identity = match.pick_identity(jd)
        mapping = match.match_jd(jd, identity)
        rows = preflight.questions(jd, mapping, identity)
        checks.append(('mandatory evidence gap becomes a pre-generation question',
                       any(row['id'] == 'REQ-4' for row in rows)))
        checks.append(('no CV or letter exists before preflight resolution',
                       not os.path.exists(os.path.join(store.job_dir(slug), 'cv.json'))
                       and not os.path.exists(os.path.join(
                           store.job_dir(slug), 'cover-letter.json'))))
        try:
            preflight.create(slug, jd, mapping, identity)
            anonymous_refused = False
        except ValueError:
            anonymous_refused = True
        checks.append(('material questions cannot be silently auto-acknowledged',
                       anonymous_refused))
        record = preflight.create(
            slug, jd, mapping, identity, reviewer='candidate',
            answers={row['id']: 'PROCEED_WITH_RECORDED_GAP' for row in rows})
        _, errors, _ = preflight.validate(slug, jd, mapping, identity)
        checks.append(('structured user decisions are digest-bound and valid',
                       record['decision'] == 'STRUCTURED_DECISIONS_RECORDED'
                       and set(record['answers']) == {row['id'] for row in rows}
                       and not errors))
        blocked_answers = {
            row['id']: ({'decision': 'ADD_NEW_EVIDENCE',
                         'note': 'My source certificate contains additional evidence.'}
                        if index == 0 else 'PROCEED_WITH_RECORDED_GAP')
            for index, row in enumerate(rows)}
        blocked_record = preflight.create(
            slug, jd, mapping, identity, reviewer='candidate',
            answers=blocked_answers)
        _, blocked_errors, _ = preflight.validate(slug, jd, mapping, identity)
        checks.append(('new evidence comment is saved but still blocks draft creation',
                       blocked_record['decision'] == 'ACTION_REQUIRED'
                       and blocked_record['answers'][rows[0]['id']]['note'].startswith('My source')
                       and any('paused for' in error for error in blocked_errors)
                       and not os.path.exists(os.path.join(store.job_dir(slug), 'cv.json'))))
        checks.append(('preflight rows are explicit controls, not repeated fact questions',
                       all(row['kind'] == 'KNOWN_GAP' for row in rows)
                       and all('PROCEED_WITH_RECORDED_GAP' in {
                           option['value'] for option in row['options']} for row in rows)
                       and all('CHALLENGE_EVIDENCE_MAP' in {
                           option['value'] for option in row['options']} for row in rows)
                       and all(row.get('allow_note') for row in rows)))
        summary = preflight.review_summary_markdown(blocked_record)
        checks.append(('current-advert comments enter the bound internal review only',
                       'My source certificate contains additional evidence.' in summary
                       and 'not career facts' in summary
                       and 'Advert requirement:' in summary))
        issue = dashboard_actions.record_preflight_issue(
            slug, rows[0]['id'],
            'The approved record already contains the relevant project evidence.',
            'EXISTING_EVIDENCE_MISSED', 'candidate')
        saved_issue = issue['item']
        checks.append(('a missed-evidence comment binds to the exact current requirement',
                       saved_issue['classification'] == 'EVIDENCE_MAPPING'
                       and saved_issue['target_id'] == rows[0]['id']
                       and saved_issue['target_artifact'] == 'preflight'
                       and saved_issue['selected_text'] == rows[0]['requirement']
                       and saved_issue in feedback.open_items(slug)))
        feedback.resolve(
            slug, saved_issue['id'], 'REJECTED',
            'Fictional challenge closed after test inspection.',
            'The exact requirement binding was verified by this test.')

        exact_class, exact_note, exact_id = match._exact_classification(
            'Bachelor degree in Electrical Engineering or related field',
            [{'id': 'EDU-AV', 'score': 0.6}],
            {'EDU-AV': {
                'id': 'EDU-AV', 'type': 'education',
                'fact': 'Bachelor of Engineering in Avionics Engineering',
            }})
        checks.append(('approved avionics degree resolves an electrical-related-field gate',
                       exact_class == 'DIRECT' and exact_id == 'EDU-AV'
                       and 'related discipline' in exact_note))
        mobile_profile = {
            'location': {'based_in': 'Example Country', 'work_authorisation': {
                'mobility': True,
                'display_rules': [{'terms': ['riyadh', 'saudi'],
                                   'phrasing': 'Available for Saudi Arabia'}],
            }}}
        checks.append(('approved mobility resolves travel and Riyadh without re-asking',
                       match._resolve_profile_gate(
                           'Willingness to travel globally', mobile_profile)[0] == 'DIRECT'
                       and match._resolve_profile_gate(
                           'Ability to live and work in Riyadh', mobile_profile)[0] == 'DIRECT'))
        legacy_rows = preflight.legacy_questions(jd, mapping, identity)
        store.write_json(preflight.path(slug), {
            '_schema': preflight.SCHEMA, 'app_id': slug,
            'subject_sha256': preflight.subject(jd, mapping, identity, legacy_rows),
            'questions': legacy_rows, 'decision': 'USER_CONTEXT_REVIEWED',
            'reviewer': 'historical-candidate', 'note': 'Historical signed review.',
        })
        _, legacy_errors, _ = preflight.validate(slug, jd, mapping, identity)
        checks.append(('historical digest-bound preflight remains verifiable',
                       not legacy_errors))
        free_text = subprocess.run([
            sys.executable, os.path.join(ROOT, 'jl.py'), '--data-dir', data,
            'preflight', slug, '--user-reviewed', '--reviewer', 'candidate',
            '--note', 'Proceed with every gap',
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        checks.append(('CLI free text cannot bypass structured preflight decisions',
                       free_text.returncode != 0
                       and 'use structured --answers-file decisions' in free_text.stdout))

    with tempfile.TemporaryDirectory(prefix='joblooper-real-init-') as temp:
        data = os.path.join(temp, 'candidate-data')
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'jl.py'), '--data-dir', data, 'init'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        sections = store.read_json(os.path.join(data, 'truth', 'sections.json'), {})
        aliases = store.read_json(os.path.join(data, 'truth', 'aliases.json'), {})
        boundaries = store.read_json(os.path.join(data, 'truth', 'boundaries.json'), {})
        experience = next(section for section in sections['sections']
                          if section['source'] == 'role_bullets')
        checks.append(('real CLI init succeeds without fictional role mappings',
                       result.returncode == 0 and 'core_by_lane' not in experience
                       and 'core_by_role' not in experience
                       and not sections.get('lanes')
                       and not aliases.get('boost_terms')
                       and not boundaries.get('forbidden_patterns')))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} preflight invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
