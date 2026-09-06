"""First-run environment detection and approval-gated component installation.

Detection is deliberately free of side effects so it can be tested and so
`setup` can show a complete picture before proposing anything. Nothing here
installs software on its own: `install_command` only returns what *would* be
run, and the caller is responsible for obtaining explicit approval first.

The engine itself needs nothing beyond Python. Everything detected below is
either that floor or an optional capability that changes what Joblooper can do,
so a missing one is reported as a consequence rather than as a failure.
"""
import os
import platform
import shutil
import subprocess
import sys

REQUIRED_PYTHON = (3, 10)

# Package managers we know how to drive, in the order we prefer them per OS.
_MANAGERS = {
    'Windows': (('winget', ['winget', 'install', '--exact', '--silent',
                            '--accept-package-agreements',
                            '--accept-source-agreements', '--id']),),
    'Darwin': (('brew', ['brew', 'install']),),
    'Linux': (('apt-get', ['sudo', 'apt-get', 'install', '-y']),
              ('dnf', ['sudo', 'dnf', 'install', '-y']),
              ('pacman', ['sudo', 'pacman', '-S', '--noconfirm'])),
}
# Package identifiers differ per manager for the same product.
_PACKAGES = {
    'libreoffice': {'winget': 'TheDocumentFoundation.LibreOffice',
                    'brew': 'libreoffice', 'apt-get': 'libreoffice',
                    'dnf': 'libreoffice', 'pacman': 'libreoffice-fresh'},
    'node': {'winget': 'OpenJS.NodeJS.LTS', 'brew': 'node',
             'apt-get': 'nodejs', 'dnf': 'nodejs', 'pacman': 'nodejs'},
    'git': {'winget': 'Git.Git', 'brew': 'git', 'apt-get': 'git',
            'dnf': 'git', 'pacman': 'git'},
}


def package_manager():
    """The first available package manager for this OS, or None."""
    for name, prefix in _MANAGERS.get(platform.system(), ()):
        if shutil.which(name):
            return name, prefix
    return None


def _has(executable):
    return bool(shutil.which(executable))


def _libreoffice():
    if _has('soffice') or _has('libreoffice'):
        return True
    # macOS and Windows installs are frequently not on PATH.
    for candidate in (
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe'):
        if os.path.isfile(candidate):
            return True
    return False


def _word():
    if platform.system() != 'Windows':
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'Word.Application'):
            return True
    except (ImportError, OSError):
        return False


def _browser():
    if platform.system() == 'Windows':
        return True     # Edge ships with Windows.
    if platform.system() == 'Darwin':
        return os.path.isdir('/Applications/Safari.app') or _has('open')
    return any(_has(name) for name in (
        'xdg-open', 'google-chrome', 'chromium', 'firefox'))


def detect():
    """Describe every component Joblooper can use. Pure: changes nothing.

    Each row carries `blocking` (Joblooper cannot run without it), `present`,
    a human `detail`, and `consequence` -- what the user loses while it is
    missing. `package` names the installable product where one exists.
    """
    version = '.'.join(str(part) for part in sys.version_info[:3])
    rows = [{
        'name': 'Python', 'blocking': True, 'present': sys.version_info >= REQUIRED_PYTHON,
        'detail': f'{version} (3.10 or newer required)', 'package': None,
        'consequence': 'Joblooper cannot run.',
        'manual': 'Install Python 3.10+ from https://www.python.org/downloads/ '
                  'and re-run this command.',
    }]
    word, libre = _word(), _libreoffice()
    rows.append({
        'name': 'PDF export', 'blocking': False, 'present': word or libre,
        'detail': ('Microsoft Word automation' if word else
                   'LibreOffice' if libre else 'no office engine found'),
        'package': None if (word or libre) else 'libreoffice',
        'consequence': 'CVs still build as DOCX; use `--no-pdf` and convert later.',
        'manual': 'Install LibreOffice from https://www.libreoffice.org/download/',
    })
    node = _has('node')
    rows.append({
        'name': 'Node.js', 'blocking': False, 'present': node,
        'detail': 'available' if node else 'not found',
        'package': None if node else 'node',
        'consequence': 'Needed only to install the Codex CLI and to run the '
                       'browser test; the application workflow does not use it.',
        'manual': 'Install Node.js LTS from https://nodejs.org/',
    })
    codex = _has('codex')
    rows.append({
        'name': 'Codex CLI', 'blocking': False, 'present': codex,
        'detail': 'available' if codex else 'not found',
        'package': None if codex else 'codex',
        'consequence': 'The dashboard works fully without it. It only enables '
                       'the optional in-app assistant for reasoning about a job.',
        'manual': 'Install with `npm install -g @openai/codex` once Node.js is present.',
    })
    git = _has('git')
    rows.append({
        'name': 'Git', 'blocking': False, 'present': git,
        'detail': 'available' if git else 'not found',
        'package': None if git else 'git',
        'consequence': 'Only needed to update Joblooper itself.',
        'manual': 'Install Git from https://git-scm.com/downloads',
    })
    rows.append({
        'name': 'Web browser', 'blocking': False, 'present': _browser(),
        'detail': 'available' if _browser() else 'none detected',
        'package': None,
        'consequence': 'The dashboard is a local web page and needs one to view.',
        'manual': 'Install any modern browser, then open the printed address.',
    })
    return rows


def install_command(package):
    """The exact command that would install `package`, or None.

    Returns the argv so a caller can display it verbatim before asking for
    approval. Nothing is executed here.
    """
    if package == 'codex':
        # Distributed through npm rather than any OS package manager.
        return ['npm', 'install', '-g', '@openai/codex'] if _has('npm') else None
    manager = package_manager()
    if not manager:
        return None
    name, prefix = manager
    identifier = _PACKAGES.get(package, {}).get(name)
    return [*prefix, identifier] if identifier else None


def run_install(command, timeout=1800):
    """Run an approved install command. Returns (ok, combined output)."""
    try:
        result = subprocess.run(
            command, text=True, encoding='utf-8', errors='replace',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    return result.returncode == 0, (result.stdout or '').strip()
