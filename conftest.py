"""Pytest collection rules for the Joblooper check suite.

Most files under ``tests/`` are standalone scripts: they assert at module scope
and call ``sys.exit()`` when finished. Importing one during collection raises
``SystemExit``, which pytest reports as an INTERNALERROR rather than a failure,
so plain ``pytest`` used to abort before running anything at all.

They are ignored here and executed as subprocesses by ``tests/test_suite.py``
instead, which is also how ``tools/run_checks.py`` runs them. That keeps one
definition of the suite while making ``pytest`` behave normally.
"""
import glob
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTEST_NATIVE = {'test_suite.py'}

collect_ignore = sorted(
    os.path.join('tests', os.path.basename(path))
    for path in glob.glob(os.path.join(ROOT, 'tests', 'test_*.py'))
    if os.path.basename(path) not in PYTEST_NATIVE
)
