"""Source upload, extraction review and exact career-truth sign-off."""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import dashboard_actions, store, truth_intake, truth_review, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-truth-intake-') as data:
        initialized = subprocess.run([
            sys.executable, os.path.join(ROOT, 'jl.py'), '--data-dir', data, 'init'
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        store.configure(data); vec.reset_caches()
        checks.append(('fresh real workspace initializes blocked',
                       initialized.returncode == 0
                       and truth_review.entry_state()['can_capture'] is False))
        content = (
            b'Example Systems Ltd\nSenior Systems Engineer | 2020 - Present\n'
            b'Led requirements, integration and acceptance for complex systems.\n'
            b'Managed verification evidence through customer approval.\n'
            b'Python, requirements traceability and configuration control.\n')
        uploaded = truth_intake.upload('base-cv.txt', content, 'base_cv')
        workspace = uploaded['workspace']
        checks.append(('source bytes are hash-bound and proposals remain non-authoritative',
                       uploaded['duplicate'] is False
                       and workspace['pending_count'] == 5
                       and not store.sources()
                       and truth_review.entry_state()['state'] == 'EXTRACTION_REVIEW'))
        duplicate = truth_intake.upload('renamed.txt', content, 'base_cv')
        checks.append(('same source bytes deduplicate by digest',
                       duplicate['duplicate'] is True
                       and len(duplicate['workspace']['sources']) == 1))

        candidates = workspace['candidates']
        role = candidates[0]
        decisions = []
        for number, candidate in enumerate(candidates):
            decision = {'candidate_id': candidate['id']}
            if number == 0:
                decision.update({
                    'disposition': 'ADOPTED', 'type': 'role',
                    'org': 'Example Systems Ltd', 'title': 'Senior Systems Engineer',
                    'start': '2020', 'end': '',
                })
            elif number in {2, 3}:
                decision.update({
                    'disposition': 'ADOPTED', 'type': 'anchor',
                    'fact': candidate['text'], 'ownership': 'led',
                    'role_id': role['id'],
                })
            elif number == 4:
                decision.update({
                    'disposition': 'ADOPTED', 'type': 'skill',
                    'fact': candidate['text'], 'ownership': 'supported',
                })
            else:
                decision.update({
                    'disposition': 'REJECTED',
                    'reason': 'This heading does not state an atomic career fact.',
                })
            decisions.append(decision)
        reviewed = truth_intake.review({
            'name': 'Taylor Example', 'email': 'taylor@example.test',
            'phone_primary': '+1 555 0199', 'based_in': 'Example City',
            'identity': 'systems_engineer',
            'identity_description': 'Systems engineering and delivery.',
            'headline': 'Systems Engineer | Integration | Verification',
            'summary': ('Systems engineer with source-backed experience in requirements, '
                        'integration, verification and customer acceptance.'),
        }, decisions)
        checks.append(('review promotes only adopted source-cited facts',
                       reviewed['pending_count'] == 0
                       and reviewed['registered_sources'] == 1
                       and len([row for row in reviewed['facts']
                                if row['type'] == 'anchor']) == 2
                       and truth_review.entry_state()['state'] == 'TRUTH_REVIEW'))
        result = dashboard_actions.sign_truth(
            'Taylor Example',
            'I reviewed the identity, sources, facts and boundaries')
        checks.append(('separate sign-off binds exact truth and enables capture',
                       result['ok'] is True
                       and truth_review.entry_state()['state'] == 'TRUTH_READY'
                       and truth_review.readiness()['approval']['subject_sha256']
                       == store.truth_approval_subject()['sha256']))
        source_path = os.path.join(data, store.sources()[0]['path'])
        with open(source_path, 'ab') as stream:
            stream.write(b'changed')
        checks.append(('source-byte drift fails closed after sign-off',
                       truth_review.entry_state()['state'] == 'TRUTH_BLOCKED'))

        old_source = store.sources()[0]
        replacement = truth_intake.upload(
            'base-cv-revised.txt', content + b'\nUpdated formatting only.\n',
            'base_cv', supersedes_source_id=old_source['id'])
        existing = truth_intake.summary()['facts']
        roles = [row for row in existing if row['type'] == 'role']
        other = [row for row in existing if row['type'] not in {'role', 'positioning'}]
        replacement_decisions = []
        for candidate in replacement['workspace']['candidates']:
            text = candidate['text']
            decision = {'candidate_id': candidate['id']}
            if 'Senior Systems Engineer' in text:
                target = roles[0]
                decision.update({'disposition': 'DUPLICATE',
                                 'duplicate_of': target['id']})
            elif 'Led requirements' in text:
                target = next(row for row in other if 'Led requirements' in row['fact'])
                decision.update({'disposition': 'DUPLICATE',
                                 'duplicate_of': target['id']})
            elif 'Managed verification' in text:
                target = next(row for row in other if 'Managed verification' in row['fact'])
                decision.update({'disposition': 'DUPLICATE',
                                 'duplicate_of': target['id']})
            elif 'Python' in text:
                target = next(row for row in other if 'Python' in row['fact'])
                decision.update({'disposition': 'DUPLICATE',
                                 'duplicate_of': target['id']})
            else:
                decision.update({'disposition': 'REJECTED',
                                 'reason': 'No new atomic career fact is present.'})
            replacement_decisions.append(decision)
        truth_intake.review({
            'name': 'Taylor Example', 'email': 'taylor@example.test',
            'phone_primary': '+1 555 0199', 'based_in': 'Example City',
            'identity': 'systems_engineer',
            'identity_description': 'Systems engineering and delivery.',
            'headline': 'Systems Engineer | Integration | Verification',
            'summary': ('Systems engineer with source-backed experience in requirements, '
                        'integration, verification and customer acceptance.'),
        }, replacement_decisions)
        sources = {row['id']: row for row in store.sources()}
        new_source_id = replacement['source']['id']
        checks.append(('intentional source revision re-evidences facts before supersession',
                       sources[old_source['id']]['lifecycle_status'] == 'SUPERSEDED'
                       and sources[old_source['id']]['superseded_by'] == new_source_id
                       and all(any(ref.get('source_id') == new_source_id
                                   for ref in row.get('evidence_refs') or [])
                               for row in store.read_jsonl(store.p('truth', 'anchors.jsonl'))
                               if any(ref.get('source_id') == old_source['id']
                                      for ref in row.get('evidence_refs') or []))
                       and truth_review.entry_state()['state'] == 'TRUTH_REVIEW'))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} truth-intake invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
