"""A linked user-skill install retains the complete executable system."""
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
        doctor = subprocess.run(
            [sys.executable, os.path.join(destination, 'jl.py'), '--data-dir', FIXTURE,
             'doctor'], cwd=destination, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert doctor.returncode == 0, doctor.stdout
        assert 'System is ready' in doctor.stdout
    finally:
        remove_link(destination)

print('standalone linked skill installation: 10/10 pass')
