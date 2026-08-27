"""Personal-source and sanitized-public-mirror boundary invariants."""
import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import export_public, prepare_public_release


def main():
    checks = []
    with open(os.path.join(ROOT, 'repo-policy.json'), encoding='utf-8') as stream:
        policy = json.load(stream)
    source_private = policy.get('classification') == 'PERSONAL_PRIVATE'
    checks.append(('source repository policy is internally consistent',
                   (source_private and policy.get('personal_data_in_git') is True)
                   or (not source_private and policy.get('classification') == 'PUBLIC_SKILL'
                       and policy.get('personal_data_in_git') is False)))
    checks.append(('private and public repository identities are unambiguous',
                   (source_private
                    and policy.get('repository_name') == 'Pvt-JobLooper'
                    and policy.get('public_repository_name') == 'Pub-JobLooper'
                    and policy.get('public_repository_url')
                    == export_public.PUBLIC_REPOSITORY_URL)
                   or (not source_private
                       and policy.get('repository_name') == 'Pub-JobLooper'
                       and policy.get('canonical_repository_url')
                       == export_public.PUBLIC_REPOSITORY_URL)))
    if source_private:
        attribute = subprocess.run(
            ['git', 'check-attr', 'text', '--', '.joblooper/example-record.json'],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        byte_rule_ok = (attribute.returncode == 0
                        and attribute.stdout.strip().endswith('text: unset'))
    else:
        byte_rule_ok = not os.path.exists(os.path.join(ROOT, '.joblooper'))
    checks.append(('repository transport rule matches its privacy policy', byte_rule_ok))
    with tempfile.TemporaryDirectory(prefix='joblooper-mirror-test-') as temp:
        target = os.path.join(temp, 'public-joblooper')
        mirror, audit = export_public.export(target)
        with open(os.path.join(mirror, 'repo-policy.json'), encoding='utf-8') as stream:
            public_policy = json.load(stream)
        checks.append(('public mirror has a distinct public-skill policy',
                       public_policy.get('classification') == 'PUBLIC_SKILL'
                       and public_policy.get('personal_data_in_git') is False
                       and public_policy.get('repository_name') == 'Pub-JobLooper'
                       and public_policy.get('canonical_repository_url')
                       == export_public.PUBLIC_REPOSITORY_URL
                       and public_policy.get('release_fingerprint')
                       == export_public.release_fingerprint(mirror)))
        checks.append(('public mirror excludes private runtime and Git history',
                       not os.path.exists(os.path.join(mirror, '.joblooper'))
                       and not os.path.exists(os.path.join(mirror, '.git'))))
        checks.append(('public mirror retains a complete installable skill',
                       all(os.path.isfile(os.path.join(mirror, path)) for path in (
                           'SKILL.md', 'agents/openai.yaml', 'jl.py',
                           'core/cover_letter.py', 'core/dashboard.py',
                           'core/dashboard_runtime.py',
                           'core/language.py', 'dashboard/index.html',
                           'dashboard/styles.css', 'dashboard/app.js'))))
        checks.append(('public mirror passes its own audit',
                       'sanitized public mirror OK' in audit))
        probe = os.path.join(mirror, 'privacy-probe.txt')
        with open(probe, 'w', encoding='utf-8') as stream:
            stream.write('private candidate identifier')
        checks.append(('public scanner detects a career identifier in allowlisted text',
                       'privacy-probe.txt' in export_public._identifier_problems(
                           mirror, {'private candidate identifier'})))
        os.remove(probe)
        owner = export_public.PUBLIC_REPOSITORY_URL.split('/')[-2]
        checks.append(('only the exact public repository URL may contain its owner handle',
                       not export_public._identifier_problems(mirror, {owner})))
        with open(probe, 'w', encoding='utf-8') as stream:
            stream.write('Repository owner mentioned outside the canonical URL: ' + owner)
        checks.append(('public owner-handle exception does not permit arbitrary mentions',
                       'privacy-probe.txt' in export_public._identifier_problems(
                           mirror, {owner})))
        os.remove(probe)
        try:
            export_public.export(target)
            overwrite_refused = False
        except ValueError:
            overwrite_refused = True
        checks.append(('mirror export refuses to overwrite an existing target',
                       overwrite_refused))

        subprocess.run(['git', 'init'], cwd=mirror, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([
            'git', 'remote', 'add', 'origin',
            export_public.PUBLIC_REPOSITORY_URL + '.git'], cwd=mirror, check=True)
        obsolete = os.path.join(mirror, 'obsolete-private-sync-probe.txt')
        with open(obsolete, 'w', encoding='utf-8') as stream:
            stream.write('obsolete generated file')
        synced, sync_audit = prepare_public_release.synchronize(mirror)
        checks.append(('public updater replaces only a verified canonical clone',
                       synced == mirror and not os.path.exists(obsolete)
                       and 'sanitized public mirror OK' in sync_audit
                       and os.path.isdir(os.path.join(mirror, '.git'))))

        wrong = os.path.join(temp, 'wrong-public-target')
        shutil.copytree(mirror, wrong, ignore=shutil.ignore_patterns('.git'))
        subprocess.run(['git', 'init'], cwd=wrong, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['git', 'remote', 'add', 'origin',
                        'https://github.com/example/not-joblooper.git'],
                       cwd=wrong, check=True)
        try:
            prepare_public_release.synchronize(wrong)
            wrong_refused = False
        except ValueError:
            wrong_refused = True
        checks.append(('public updater refuses a noncanonical Git target', wrong_refused))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} repository-policy invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
