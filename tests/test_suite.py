"""Pytest entry point for the Joblooper check suite.

The engine's own tests are standalone scripts (see ``conftest.py``). This module
runs each one as a subprocess against an isolated copy of ``examples/starter``,
so ``pytest`` and ``tools/run_checks.py`` execute exactly the same checks in the
same order without a second list to maintain.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.run_checks import FIXTURE, checks_for  # noqa: E402


@pytest.fixture(scope='session')
def isolated_data(tmp_path_factory):
    """A private workspace seeded from the fictional starter fixture."""
    data = tmp_path_factory.mktemp('joblooper-data')
    shutil.copytree(FIXTURE, data, dirs_exist_ok=True)
    return str(data)


@pytest.mark.parametrize(
    'name,argv', checks_for('full'), ids=[name for name, _ in checks_for('full')])
def test_check(name, argv, isolated_data):
    environment = os.environ.copy()
    environment['JOBLOOPER_DATA_DIR'] = isolated_data
    environment['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run(
        [sys.executable, '-B', *argv], cwd=ROOT, env=environment,
        text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f'{name} failed:\n{result.stdout}'
