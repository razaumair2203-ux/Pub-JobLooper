"""Material questions are resolved before CV and letter prose exists."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import match, preflight, store, vec


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
            note='No additional verified evidence; retain the visible gap.')
        _, errors, _ = preflight.validate(slug, jd, mapping, identity)
        checks.append(('reviewed user context is digest-bound and valid',
                       record['decision'] == 'USER_CONTEXT_REVIEWED' and not errors))

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
