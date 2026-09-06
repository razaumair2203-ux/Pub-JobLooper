"""Personal-source and sanitized-public-mirror boundary invariants."""
import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import check_repo, export_public, prepare_public_release, run_checks


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
    if source_private:
        runtime_control = subprocess.run(
            ['git', 'check-ignore', '.joblooper/index/dashboard_instance.json'],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        control_ignored = runtime_control.returncode == 0
    else:
        control_ignored = not os.path.exists(
            os.path.join(ROOT, '.joblooper', 'index', 'dashboard_instance.json'))
    checks.append(('ephemeral dashboard shutdown credentials cannot enter Git',
                   control_ignored))
    with open(os.path.join(ROOT, 'run_checks.ps1'), encoding='utf-8-sig') as stream:
        windows_checks = stream.read()
    with open(os.path.join(ROOT, 'run_checks.sh'), encoding='utf-8') as stream:
        unix_checks = stream.read()
    # Both entry points are thin wrappers; the scope definition itself lives in
    # tools/run_checks.py so the two can no longer drift apart.
    full_scope = run_checks.checks_for('full')
    dashboard_scope = run_checks.checks_for('dashboard')
    mirror_scope = run_checks.checks_for('mirror')
    checks.append(('verification runner has proportional dashboard and mirror scopes',
                   set(run_checks.SCOPES) == {'full', 'dashboard', 'mirror'}
                   and 0 < len(dashboard_scope) < len(full_scope)
                   and 0 < len(mirror_scope) < len(full_scope)
                   and 'tools/run_checks.py' in windows_checks
                   and 'tools/run_checks.py' in unix_checks))
    checks.append(('every declared check is reachable from the full scope',
                   all(scopes & set(run_checks.SCOPES)
                       and 'full' in scopes for _, _, scopes in run_checks.CHECKS)))
    checks.append(('pytest runs the suite without importing standalone scripts',
                   os.path.isfile(os.path.join(ROOT, 'conftest.py'))
                   and os.path.isfile(os.path.join(ROOT, 'tests', 'test_suite.py'))))
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
        # The two repositories are separate code lines kept in step by hand,
        # which is exactly where drift goes unnoticed. Digests must be
        # line-ending independent so equivalent checkouts do not report false
        # drift (audit JF-11), while a real edit must still be caught.
        baseline = check_repo.allowlist_digests(ROOT, export_public.ALLOW_FILES)
        crlf_tree = os.path.join(temp, 'crlf-clone')
        os.makedirs(crlf_tree)
        for name in ('jl.py', 'SKILL.md'):
            with open(os.path.join(ROOT, name), encoding='utf-8') as stream:
                text = stream.read()
            with open(os.path.join(crlf_tree, name), 'w', encoding='utf-8',
                      newline='') as stream:
                stream.write(text.replace('\r\n', '\n').replace('\n', '\r\n'))
        crlf_digests = check_repo.allowlist_digests(crlf_tree, {'jl.py', 'SKILL.md'})
        checks.append(('equivalent checkouts do not report false mirror drift',
                       all(crlf_digests[name] == baseline[name]
                           for name in ('jl.py', 'SKILL.md'))))
        edited = os.path.join(crlf_tree, 'jl.py')
        with open(edited, 'a', encoding='utf-8') as stream:
            stream.write('\n# a real source change\n')
        checks.append(('a real source change is reported as mirror drift',
                       check_repo.allowlist_digests(crlf_tree, {'jl.py'})['jl.py']
                       != baseline['jl.py']))
        checks.append(('mirror drift is measured only from the private source',
                       subprocess.run(
                           [sys.executable, os.path.join(ROOT, 'tools', 'check_repo.py'),
                            '--mirror-drift', '--public-tree', mirror],
                           cwd=ROOT, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).returncode == 2))
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
