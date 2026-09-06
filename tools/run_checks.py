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

# (name, argv, scopes). Order is significant: cheap integrity first, then engine
# invariants, then the dashboard, then repository boundaries.
CHECKS = [
    ('truth integrity', ['jl.py', 'check'], {'full', 'dashboard', 'mirror'}),
    ('adversarial gates', ['tests/test_gates.py'], {'full'}),
    ('output invariants', ['tests/test_pipeline.py'], {'full'}),
    ('semantic matching', ['tests/test_match.py'], {'full'}),
    ('approval and releases', ['tests/test_release.py'], {'full'}),
    ('ground-truth context', ['tests/test_context.py'], {'full'}),
    ('ground-truth review', ['tests/test_truth_review.py'], {'full'}),
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
    ('repository policy', ['tools/check_repo.py'], {'full', 'mirror'}),
    # Passes when no export baseline exists yet; fails once the private source
    # moves ahead of the last published mirror.
    ('public mirror drift', ['tools/check_repo.py', '--mirror-drift'],
     {'full', 'mirror'}),
]
SCOPES = ('full', 'dashboard', 'mirror')


def checks_for(scope):
    return [(name, argv) for name, argv, scopes in CHECKS if scope in scopes]


def run(scope='full', echo=print):
    """Run every check for ``scope``; return the list of failed check names."""
    data = tempfile.mkdtemp(prefix='joblooper-tests-')
    failed = []
    try:
        shutil.copytree(FIXTURE, data, dirs_exist_ok=True)
        environment = os.environ.copy()
        environment['JOBLOOPER_DATA_DIR'] = data
        environment['PYTHONIOENCODING'] = 'utf-8'
        for name, argv in checks_for(scope):
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
    args = parser.parse_args(argv)
    failed = run(args.scope)
    if failed:
        print('\nCHECKS FAILED: ' + ', '.join(failed))
        return 1
    print(f'\nALL {args.scope.upper()} CHECKS PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
