"""Create a new-history, allowlisted public Joblooper skill mirror."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW_FILES = {
    '.gitattributes', '.gitignore', 'CONTRIBUTING.md', 'LICENSE', 'README.md',
    'SECURITY.md', 'SKILL.md', 'USER-GUIDE.md', 'agents', 'core', 'examples', 'jl.py',
    'references', 'repo-policy.json', 'run_checks.ps1', 'run_checks.sh',
    'templates', 'tests', 'tools',
}
PUBLIC_IGNORE = """__pycache__/
*.py[cod]
*.tmp
.pytest_cache/
.venv/
venv/
.env*
!.env.example
.config/
*token*
*.pat

# Public skills never version candidate truth or generated applications.
/.joblooper/
/truth/
/work/
/jobs/
/index/
/base/
/archive/
/audits/
/imports/
/Misc Documents/
**/index/truth_context.json
*.docx
*.pdf
*.jpg
*.jpeg
*.png
*.zip
*.bundle
"""


def _copy_entry(source, target):
    if os.path.isdir(source):
        shutil.copytree(
            source, target,
            ignore=shutil.ignore_patterns(
                '__pycache__', '*.pyc', '*.tmp', '.writer.lock', 'TRUTH-AUDIT.*'))
    elif os.path.isfile(source):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def _private_tokens():
    """Known direct and career-specific strings that must not cross the boundary."""
    path = os.path.join(ROOT, '.joblooper', 'truth', 'profile.json')
    try:
        with open(path, encoding='utf-8') as stream:
            profile = json.load(stream)
    except (OSError, ValueError):
        return set()
    values = [profile.get('name')]
    for group in ('contact', 'links'):
        values.extend((profile.get(group) or {}).values())
    location = profile.get('location') or {}
    values.extend(value for value in location.values() if isinstance(value, str))
    name_parts = str(profile.get('name') or '').split()
    values.extend(part for part in name_parts if len(part) >= 4)
    for record in store_rows(os.path.join(ROOT, '.joblooper', 'truth', 'anchors.jsonl')):
        values.extend([record.get('org'), record.get('fact')])
    work = os.path.join(ROOT, '.joblooper', 'work')
    if os.path.isdir(work):
        for name in os.listdir(work):
            path = os.path.join(work, name, 'jd.json')
            try:
                with open(path, encoding='utf-8') as stream:
                    jd = json.load(stream)
            except (OSError, ValueError):
                continue
            values.extend([jd.get('url'), jd.get('job_reference')])
    return {str(value).strip().casefold() for value in values
            if isinstance(value, str) and len(value.strip()) >= 5}


def store_rows(path):
    rows = []
    try:
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                if line.strip() and not line.lstrip().startswith('#'):
                    rows.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return rows


def _identifier_problems(root, tokens=None):
    tokens = _private_tokens() if tokens is None else {
        str(value).casefold() for value in tokens if str(value).strip()}
    problems = []
    if not tokens:
        return problems
    for base, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name != '__pycache__']
        for name in names:
            path = os.path.join(base, name)
            relative = os.path.relpath(path, root).replace('\\', '/').casefold()
            if any(token in relative for token in tokens):
                problems.append(relative)
            try:
                with open(path, encoding='utf-8') as stream:
                    text = stream.read().casefold()
            except (OSError, UnicodeDecodeError):
                continue
            if any(token in text for token in tokens):
                problems.append(os.path.relpath(path, root).replace('\\', '/'))
    return sorted(set(problems))


def export(target):
    target = os.path.abspath(target)
    if os.path.exists(target):
        raise ValueError('target already exists; choose a new empty path')
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix='.joblooper-public-', dir=parent)
    try:
        for name in sorted(ALLOW_FILES):
            _copy_entry(os.path.join(ROOT, name), os.path.join(staging, name))
        with open(os.path.join(staging, '.gitignore'), 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(PUBLIC_IGNORE)
        with open(os.path.join(staging, 'repo-policy.json'), 'w', encoding='utf-8') as stream:
            json.dump({
                '_schema': 'joblooper.repository-policy.v1',
                'classification': 'PUBLIC_SKILL',
                'purpose': 'Reusable evidence-governed Joblooper engine and fictional examples',
                'personal_data_in_git': False,
                'runtime_data_location': 'USER_HOME_OR_EXPLICIT_DATA_DIR',
                'source': 'SANITIZED_MIRROR_WITH_NEW_HISTORY',
            }, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        leaked = _identifier_problems(staging)
        if leaked:
            raise ValueError('known personal identifier reached public mirror: '
                             + ', '.join(leaked[:10]))
        result = subprocess.run(
            [sys.executable, os.path.join(staging, 'tools', 'check_repo.py'),
             '--public-tree', staging], cwd=staging, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise ValueError('public-mirror audit failed:\n' + result.stdout)
        os.replace(staging, target)
        staging = None
        return target, result.stdout.strip()
    finally:
        if staging and os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='new directory; it must not already exist')
    args = parser.parse_args()
    try:
        target, audit = export(args.target)
    except ValueError as error:
        print(f'PUBLIC EXPORT REFUSED — {error}')
        return 1
    print(f'public mirror created  {target}')
    print(f'  {audit}')
    print('  next: inspect files, run checks, then initialize NEW Git history there')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
