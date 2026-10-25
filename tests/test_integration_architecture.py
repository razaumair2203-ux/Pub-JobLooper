"""Adversarial architecture checks across truth, context transport and public export."""
import copy
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import store, truth_review, vec
from tools import export_context, export_public


def _migrate_fixture_to_v2():
    profile_path = store.p('truth', 'profile.json')
    profile = store.read_json(profile_path, {}) or {}
    profile['_truth_approval'] = truth_review.approval_record('architecture-test')
    store.write_json(profile_path, profile)
    store.reset_context_cache()


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-architecture-') as temp:
        data = os.path.join(temp, 'data')
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data)
        store.configure(data); vec.reset_caches()

        packet = export_context.build_packet()
        checks.append(('fresh advisory packet verifies', export_context.verify_packet(packet)))
        forged = copy.deepcopy(packet)
        forged['profile']['name'] = 'Different Candidate'
        checks.append(('post-export identity mutation fails transport integrity',
                       not export_context.verify_packet(forged)))
        checks.append(('advisory packet excludes contact and render policy',
                       'contact' not in packet['profile']
                       and 'links' not in packet['profile']
                       and 'sections' not in packet))

        # v1 included render policy in the approval subject. Renew the fictional
        # fixture to v2 first so this attack tests the new contract itself.
        _migrate_fixture_to_v2()
        candidate_before = truth_review.approval_subject()['sha256']
        generation_before = store.generation_fingerprint()['sha256']
        sections_path = store.p('truth', 'sections.json')
        sections = store.read_json(sections_path, {}) or {}
        sections['default_pages'] = int(sections.get('default_pages') or 2) + 1
        store.write_json(sections_path, sections); store.reset_context_cache()
        checks.append(('render-policy mutation does not masquerade as candidate-fact mutation',
                       truth_review.approval_subject()['sha256'] == candidate_before
                       and truth_review.readiness()['ready']
                       and store.generation_fingerprint()['sha256'] != generation_before))

        mirror = os.path.join(temp, 'public')
        public_root, _audit = export_public.export(mirror)
        with open(os.path.join(public_root, 'repo-policy.json'), encoding='utf-8') as stream:
            policy = json.load(stream)
        source_revision = export_public._git_source_revision()[0]
        checks.append(('public export records exact private source revision when available',
                       policy.get('source_commit_sha') == source_revision
                       and 'exporter_sha256' in policy))
        checks.append(('public provenance metadata is outside the release fingerprint cycle',
                       policy.get('release_fingerprint')
                       == export_public.release_fingerprint(public_root)))
        checks.append(('public artifact declares generated-mirror semantics',
                       policy.get('source') == 'SANITIZED_GENERATED_MIRROR_WITH_NEW_HISTORY'))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} integration-architecture attacks contained")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
