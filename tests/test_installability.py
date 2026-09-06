"""A linked user-skill install retains the complete executable system."""
import base64
import os
import subprocess
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

from tools import install_local_skill


def remove_link(path):
    if os.path.islink(path):
        os.unlink(path)
    elif os.name == 'nt' and os.path.exists(path):
        os.rmdir(path)  # removes the junction, never its target


with tempfile.TemporaryDirectory(prefix='joblooper-install-') as temp:
    assert install_local_skill.default_destination(
        home=temp, codex_home_override='') == os.path.join(
            os.path.abspath(temp), '.agents', 'skills', 'joblooper')
    assert install_local_skill.default_destination(
        home=temp, codex_home_override=os.path.join(temp, '.codex')) == os.path.join(
            temp, '.codex', 'skills', 'joblooper')
    destination = os.path.join(temp, '.codex', 'skills', 'joblooper')
    try:
        installed = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'tools', 'install_local_skill.py'),
             '--dest', destination], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert installed.returncode == 0, installed.stdout
        assert os.path.samefile(destination, ROOT)
        assert os.path.isfile(os.path.join(destination, 'SKILL.md'))
        assert os.path.isfile(os.path.join(destination, 'agents', 'openai.yaml'))
        assert os.path.isfile(os.path.join(destination, 'dashboard', 'index.html'))
        assert os.path.isfile(os.path.join(destination, 'core', 'dashboard.py'))
        assert os.path.isfile(os.path.join(destination, 'core', 'dashboard_runtime.py'))
        assert os.path.isfile(os.path.join(destination, 'dashboard', 'app-icon.svg'))
        with open(os.path.join(destination, 'assets', 'joblooper.ico.b64'),
                  encoding='ascii') as stream:
            assert base64.b64decode(stream.read()).startswith(b'\x00\x00\x01\x00')
        installed_fixture = os.path.join(temp, 'installed-fixture')
        import shutil
        shutil.copytree(os.path.join(destination, 'examples', 'starter'),
                        installed_fixture)
        doctor = subprocess.run(
            [sys.executable, os.path.join(destination, 'jl.py'), '--data-dir',
             installed_fixture, 'doctor'], cwd=destination, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert doctor.returncode == 0, doctor.stdout
        assert 'System is ready' in doctor.stdout
    finally:
        remove_link(destination)


# --- first-run setup on a machine that has never seen Joblooper --------------
from core import bootstrap  # noqa: E402

rows = {row['name']: row for row in bootstrap.detect()}
# Python is the only hard prerequisite; everything else changes what Joblooper
# can do and must be reported as a consequence rather than as a failure.
assert rows['Python']['blocking'] is True
assert all(not row['blocking'] for name, row in rows.items() if name != 'Python')
assert all(row['consequence'] and row['manual'] for row in rows.values())
# Detection must never change the machine it is describing.
assert bootstrap.detect() == bootstrap.detect()

# An install is only ever proposed, never performed, by the planning call.
for package in ('libreoffice', 'node', 'git'):
    command = bootstrap.install_command(package)
    assert command is None or (isinstance(command, list) and len(command) >= 2)
assert bootstrap.install_command('no-such-package') is None
codex_command = bootstrap.install_command('codex')
assert codex_command in (None, ['npm', 'install', '-g', '@openai/codex'])

# Declining an offer must leave the machine untouched, so `setup --no-install`
# reaches the workspace step without proposing anything.
with tempfile.TemporaryDirectory(prefix='joblooper-firstrun-') as fresh:
    workspace = os.path.join(fresh, 'workspace')
    first_run = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'jl.py'), '--data-dir', workspace,
         'setup', '--no-install', '--no-launch'],
        cwd=ROOT, text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    assert first_run.returncode == 0, first_run.stdout
    output = first_run.stdout
    # It must explain the system before asking anything of the user.
    assert 'WHAT IT IS' in output and 'THE LIFECYCLE, END TO END' in output
    assert 'WHAT IT IS NOT' in output
    assert 'does not apply on your behalf' in output
    assert 'ENVIRONMENT' in output and 'Python' in output
    # It must create the workspace and say where the data lives.
    assert os.path.isfile(os.path.join(workspace, 'truth', 'anchors.jsonl'))
    assert workspace in output
    # It must route a newcomer to truth, never to job capture or to a tool they
    # may not have installed.
    assert 'career-truth setup' in output
    assert '$joblooper' not in output
    # Nothing was installed while --no-install was set.
    assert 'Would run:' not in output

    # Re-running is safe and must not re-initialize an existing workspace.
    again = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'jl.py'), '--data-dir', workspace,
         'setup', '--no-install', '--no-launch'],
        cwd=ROOT, text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    assert again.returncode == 0, again.stdout
    assert 'Existing workspace found' in again.stdout

print('standalone linked skill installation: 12/12 pass')
print('first-run setup: environment, explanation and workspace verified')
