#!/usr/bin/env python3
"""Single cross-platform driver for the Joblooper check suite.

`run_checks.sh` and `run_checks.ps1` are thin wrappers over this file. Keeping
one ordered list here removes the drift that appeared when the same suite was
maintained twice, and lets `tests/test_suite.py` run the identical checks under
pytest without a third copy.

Every check runs against an isolated copy of ``examples/starter`` so a developer
machine's governed personal data is never a test input.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
PUBLIC_MIRROR_DRIFT = 'public mirror drift'

# (name, argv, scopes). Order is significant: cheap integrity first, then engine
# invariants, then the dashboard, then repository boundaries.
CHECKS = [
    ('truth integrity', ['jl.py', 'check'], {'full', 'dashboard', 'mirror'}),
    ('adversarial gates', ['tests/test_gates.py'], {'full'}),
    ('output invariants', ['tests/test_pipeline.py'], {'full'}),
    ('semantic matching', ['tests/test_match.py'], {'full'}),
    ('approval and releases', ['tests/test_release.py'], {'full'}),
    ('typed feedback changes', ['tests/test_feedback_changes.py'], {'full', 'dashboard'}),
    ('ground-truth context', ['tests/test_context.py'], {'full'}),
    ('consumer context contract', ['tests/test_consumer_context.py'], {'full', 'mirror'}),
    ('integration architecture attacks', ['tests/test_integration_architecture.py'], {'full', 'mirror'}),
    ('JD screen and promotion', ['tests/test_screen.py'], {'full'}),
    ('JD screen metamorphic attacks', ['tests/test_screen_metamorphic.py'], {'full'}),
    ('ground-truth review', ['tests/test_truth_review.py'], {'full'}),
    ('dashboard truth intake', ['tests/test_truth_intake.py'], {'full', 'dashboard'}),
    ('pre-generation questions', ['tests/test_preflight.py'], {'full'}),
    ('protected inventory', ['tests/test_inventory_retention.py'], {'full'}),
    ('outcome learning', ['tests/test_learning.py'], {'full'}),
    ('case lifecycle', ['tests/test_case_lifecycle.py'], {'full'}),
    ('PDF extraction', ['tests/test_pdftext.py'], {'full'}),
    ('portability and onboarding', ['tests/test_portability.py'], {'full'}),
    ('single-writer safety', ['tests/test_locking.py'], {'full'}),
    ('local dashboard', ['tests/test_dashboard.py'], {'full', 'dashboard'}),
    ('dashboard journey', ['tests/test_dashboard_journey.py'], {'full', 'dashboard'}),
    ('browser dashboard journey', ['tests/test_dashboard_browser.py'],
     {'full', 'dashboard'}),
    ('standalone skill installation', ['tests/test_installability.py'],
     {'full', 'dashboard', 'mirror'}),
    ('personal/public repository boundary', ['tests/test_repo_policy.py'],
     {'full', 'mirror'}),
    ('application mark', ['tools/build_app_icon.py', '--check'],
     {'full', 'dashboard', 'mirror'}),
    ('repository policy', ['tools/check_repo.py'], {'full', 'mirror'}),
    # Release freshness is a real publication condition, but not an engine
    # correctness condition. CI may report it separately while the functional
    # suite remains authoritative for code changes.
    (PUBLIC_MIRROR_DRIFT, ['tools/check_repo.py', '--mirror-drift'],
     {'full', 'mirror'}),
]
SCOPES = ('full', 'dashboard', 'mirror')


def checks_for(scope):
    return [(name, argv) for name, argv, scopes in CHECKS if scope in scopes]


def run(scope='full', echo=print, skip=()):
    """Run checks for ``scope``; return failed names, optionally skipping named checks."""
    skip = set(skip or ())
    data = tempfile.mkdtemp(prefix='joblooper-tests-')
    failed = []
    try:
        shutil.copytree(FIXTURE, data, dirs_exist_ok=True)
        environment = os.environ.copy()
        environment['JOBLOOPER_DATA_DIR'] = data
        environment['PYTHONIOENCODING'] = 'utf-8'
        environment.update({'TEMP': data, 'TMP': data, 'TMPDIR': data})
        for name, argv in checks_for(scope):
            if name in skip:
                echo(f'\n== {name} ==\nSKIPPED by explicit caller policy')
                continue
            echo(f'\n== {name} ==')
            result = subprocess.run(
                [sys.executable, '-B', *argv], cwd=ROOT, env=environment)
            if result.returncode != 0:
                failed.append(name)
    finally:
        shutil.rmtree(data, ignore_errors=True)
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope', nargs='?', default='full', choices=SCOPES)
    parser.add_argument('--skip-public-mirror-drift', action='store_true',
                        help='functional CI only; formal release checks must not use this')
    args = parser.parse_args(argv)
    skip = {PUBLIC_MIRROR_DRIFT} if args.skip_public_mirror_drift else set()
    failed = run(args.scope, skip=skip)
    if failed:
        print('\nCHECKS FAILED: ' + ', '.join(failed))
        return 1
    print(f'\nALL {args.scope.upper()} CHECKS PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
