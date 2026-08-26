"""Expose this complete checkout as a user-scoped Codex skill.

The installer links instead of copying so code, private truth, Git updates and
generated application records retain one authoritative location.
"""
import argparse
import os
import subprocess


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ('SKILL.md', 'agents/openai.yaml', 'jl.py', 'core/store.py')


def default_destination(home=None, codex_home_override=None):
    """Return the current user skill path, honoring legacy CODEX_HOME setups."""
    codex_home = (codex_home_override if codex_home_override is not None
                  else os.environ.get('CODEX_HOME'))
    if codex_home:
        return os.path.join(os.path.expanduser(codex_home), 'skills', 'joblooper')
    user_home = os.path.abspath(os.path.expanduser(home or '~'))
    return os.path.join(user_home, '.agents', 'skills', 'joblooper')


def install(destination=None):
    destination = os.path.abspath(os.path.expanduser(
        destination or default_destination()))
    missing = [name for name in REQUIRED
               if not os.path.isfile(os.path.join(ROOT, *name.split('/')))]
    if missing:
        raise ValueError('source checkout is incomplete: ' + ', '.join(missing))
    if os.path.lexists(destination):
        try:
            if os.path.samefile(destination, ROOT):
                return destination, 'already installed'
        except OSError:
            pass
        raise ValueError(f'destination already exists: {destination}')
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.name == 'nt':
        result = subprocess.run(
            ['cmd', '/c', 'mklink', '/J', destination, ROOT],
            capture_output=True, text=True)
        if result.returncode:
            raise ValueError('could not create Windows junction: '
                             + (result.stderr or result.stdout).strip()[:300])
        method = 'directory junction'
    else:
        os.symlink(ROOT, destination, target_is_directory=True)
        method = 'symbolic link'
    if not os.path.isfile(os.path.join(destination, 'SKILL.md')):
        raise ValueError('link was created but SKILL.md is not readable')
    return destination, method


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dest',
        help='override ~/.agents/skills/joblooper or $CODEX_HOME/skills/joblooper')
    args = parser.parse_args()
    try:
        destination, method = install(args.dest)
    except ValueError as error:
        print(f'INSTALL REFUSED — {error}')
        return 1
    print(f'installed  {destination}')
    print(f'  method   {method}')
    print('  verify   python jl.py doctor')
    print('  Codex detects skill changes automatically; restart if it is not listed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
