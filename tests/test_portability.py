"""Fresh-workspace, URL reference and Windows UTF-8 regressions."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jl
from core import render, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-empty-') as root:
        data = os.path.join(root, 'data')
        store.configure(data)
        doctor_output = io.StringIO()
        with contextlib.redirect_stdout(doctor_output):
            jl.cmd_init(SimpleNamespace(demo=False))
            doctor = jl.cmd_doctor(SimpleNamespace())
        profile = store.read_json(os.path.join(data, 'truth', 'profile.json'))
        checks.append(('real initialization is empty and generation-blocked',
                       profile.get('ready_for_generation') is False
                       and not store.list_jobs() and doctor == 1))
        policy = store.read_repository_policy().get('classification')
        expected_policy_note = ('governed private-Git data and writable'
                                if policy == 'PERSONAL_PRIVATE'
                                else 'outside the installed public skill and writable')
        checks.append(('doctor describes repository data policy accurately',
                       expected_policy_note in doctor_output.getvalue()))

    with tempfile.TemporaryDirectory(prefix='joblooper-ingest-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()
        raw_path = os.path.join(data, 'new-job.txt')
        store.write_text(raw_path, 'Requirements\n- Lead systems integration and verification.\n')
        args = SimpleNamespace(
            file=raw_path, company='Example Aerospace', title='Integration Lead',
            url='https://example.com/jobs/integration-lead-00123456')
        with contextlib.redirect_stdout(io.StringIO()):
            jl.cmd_ingest(args)
        slug = 'example-aerospace--00123456'
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        folder = store.approved_folder_name(jd, '2026-08-26T10:00:00Z')
        checks.append(('URL reference persists through JD and human folder name',
                       jd.get('job_reference') == '00123456'
                       and folder.endswith('__ref-00123456')))

    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'jl.py'), '--help'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        help_text = result.stdout.decode('utf-8', errors='strict')
        utf8_ok = 'Joblooper — JD in' in help_text
    except UnicodeDecodeError:
        utf8_ok = False
    checks.append(('CLI emits strict UTF-8 across subprocess boundaries', utf8_ok))

    with mock.patch.object(render, '_word_pdf_capability', return_value=(False, 'none')):
        with mock.patch.object(render, '_libreoffice_path', return_value='/opt/libreoffice'):
            checks.append(('LibreOffice provides cross-platform PDF capability',
                           render.pdf_capability()[0] is True))
        with mock.patch.object(render, '_libreoffice_path', return_value=None):
            available, detail = render.pdf_capability()
            checks.append(('missing PDF engines produce an explicit dependency message',
                           available is False and 'Microsoft Word' in detail
                           and 'LibreOffice' in detail))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} portability invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
