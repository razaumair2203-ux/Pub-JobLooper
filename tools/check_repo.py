"""Validate the personal source repository or a sanitized public mirror."""
import argparse
import hashlib
import json
import os
import re
import subprocess


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE_PREFIXES = (
    '.joblooper/', 'truth/', 'jobs/', 'index/', 'base/', 'archive/',
    'audits/', 'imports/', 'Misc Documents/',
)
BINARY_SUFFIXES = ('.docx', '.pdf', '.jpg', '.jpeg', '.png', '.zip', '.bundle')
SECRET_PATTERNS = (
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'gh[opsu]_[A-Za-z0-9]{30,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
)
HISTORY_EXPRESSION = (
    r'github_pat_[A-Za-z0-9_]{20,}|gh[opsu]_[A-Za-z0-9]{30,}|'
    r'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|'
    r'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'
)
ESSENTIAL = {
    'README.md', 'SKILL.md', 'USER-GUIDE.md', 'SECURITY.md', 'LICENSE',
    'agents/openai.yaml', 'repo-policy.json', 'jl.py',
    'core/build.py', 'core/casefile.py', 'core/cover_letter.py',
    'core/dashboard.py', 'core/dashboard_actions.py', 'core/dashboard_runtime.py',
    'core/employer_review.py', 'core/gates.py', 'core/language.py',
    'core/match.py', 'core/preflight.py', 'core/release.py', 'core/store.py',
    'core/truth_review.py', 'references/ground-truth-governance.md',
    'references/rejection-learning.md', 'references/section-contracts.md',
    'tools/install_local_skill.py', 'references/installation.md',
    'tools/prepare_public_release.py', 'references/maintenance.md',
}


REPOSITORY_NAMES = {
    'PERSONAL_PRIVATE': 'Pvt-JobLooper',
    'PUBLIC_SKILL': 'Pub-JobLooper',
}


def policy(root):
    try:
        with open(os.path.join(root, 'repo-policy.json'), encoding='utf-8') as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def skill_problems(root, files, require_tracked):
    """Validate skill metadata and require release-critical files in Git."""
    problems = []
    missing = sorted(path for path in ESSENTIAL
                     if not os.path.isfile(os.path.join(root, *path.split('/'))))
    problems.extend(f'installable skill is missing {path}' for path in missing)
    if require_tracked:
        untracked = sorted(ESSENTIAL - set(files))
        problems.extend(f'installable skill file is not tracked by Git: {path}'
                        for path in untracked)
    skill_path = os.path.join(root, 'SKILL.md')
    agent_path = os.path.join(root, 'agents', 'openai.yaml')
    if not os.path.isfile(skill_path):
        return problems
    with open(skill_path, encoding='utf-8') as stream:
        text = stream.read()
    frontmatter = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not frontmatter:
        problems.append('SKILL.md has invalid YAML frontmatter boundaries')
        return problems
    fields = dict(re.findall(r'^([a-z-]+):\s*(.+)$', frontmatter.group(1), re.M))
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', fields.get('name', '')):
        problems.append('SKILL.md name must be non-empty hyphen-case')
    description = fields.get('description', '').strip()
    if not description or len(description) > 1024 or '<' in description or '>' in description:
        problems.append('SKILL.md description is missing or invalid')
    if re.search(r'\[TODO:', text):
        problems.append('SKILL.md contains an unfinished TODO')
    body = text[frontmatter.end():]
    for target in re.findall(r'\[[^\]]+\]\(([^)]+\.md)\)', body):
        path = os.path.normpath(os.path.join(root, target))
        if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
            problems.append(f'SKILL.md local reference is missing or unsafe: {target}')
    if os.path.isfile(agent_path):
        with open(agent_path, encoding='utf-8') as stream:
            agent = stream.read()
        for field in ('display_name', 'short_description', 'default_prompt'):
            if not re.search(rf'^\s*{field}:\s*.+$', agent, re.M):
                problems.append(f'agents/openai.yaml is missing {field}')
        if '$joblooper' not in agent:
            problems.append('agents/openai.yaml default prompt does not invoke $joblooper')
    return problems


def tracked_files(root):
    result = subprocess.run(
        ['git', 'ls-files', '-z'], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return [p for p in result.stdout.decode('utf-8').split('\0') if p]


def tree_files(root):
    out = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {'.git', '__pycache__'}]
        for name in names:
            rel = os.path.relpath(os.path.join(base, name), root).replace('\\', '/')
            out.append(rel)
    return sorted(out)


def path_problems(files, scope, public):
    problems = []
    if not public:
        return problems
    prefixes = tuple(prefix.casefold() for prefix in PRIVATE_PREFIXES)
    for path in files:
        normal = path.replace('\\', '/')
        folded = normal.casefold()
        if folded.startswith(prefixes):
            problems.append(f'private runtime path exists in {scope}: {normal}')
        if folded.endswith(BINARY_SUFFIXES):
            problems.append(f'generated/personal binary exists in {scope}: {normal}')
    return problems


def content_problems(root, files, scope):
    problems = []
    for path in files:
        full = os.path.join(root, *path.split('/'))
        try:
            with open(full, encoding='utf-8') as stream:
                text = stream.read()
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            problems.append(f'possible secret in {scope}: {path}')
    return problems


def file_digest(path):
    """Digest one file, ignoring line-ending style for text.

    Two checkouts of identical source differ byte-for-byte when Git applies
    different `core.autocrlf` settings. Hashing raw bytes made equivalent trees
    report drift (audit JF-11), so text is normalized to LF first. Binary files
    are hashed exactly.
    """
    with open(path, 'rb') as stream:
        content = stream.read()
    if not path.lower().endswith(BINARY_SUFFIXES):
        try:
            content = content.decode('utf-8').replace(
                '\r\n', '\n').replace('\r', '\n').encode('utf-8')
        except UnicodeDecodeError:
            pass
    return hashlib.sha256(content).hexdigest()


def release_fingerprint(root):
    digest = hashlib.sha256()
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in {'.git', '__pycache__'})
        for name in sorted(names):
            path = os.path.join(base, name)
            relative = os.path.relpath(path, root).replace('\\', '/')
            if relative == 'repo-policy.json':
                continue
            digest.update(relative.encode('utf-8') + b'\0')
            digest.update(file_digest(path).encode('ascii'))
            digest.update(b'\0')
    return digest.hexdigest()


EXPORT_RECORD = os.path.join('.joblooper', 'index', 'public_export.json')


def allowlist_digests(root, allow_files):
    """Digest every allowlisted file, keyed by public-tree relative path."""
    digests = {}
    for name in sorted(allow_files):
        source = os.path.join(root, name)
        if os.path.isfile(source):
            digests[name] = file_digest(source)
            continue
        for base, dirs, names in os.walk(source):
            dirs[:] = sorted(d for d in dirs if d not in {'.git', '__pycache__'})
            for filename in sorted(names):
                path = os.path.join(base, filename)
                relative = os.path.relpath(path, root).replace('\\', '/')
                if relative.endswith('.pyc'):
                    continue
                digests[relative] = file_digest(path)
    return digests


def mirror_drift_problems(root):
    """Report allowlisted files changed since the last public export.

    The two repositories are deliberately separate code lines kept in step by
    hand, which is exactly the situation where drift goes unnoticed. This turns
    "remember to re-export" into a check. An absent record is reported but is
    not a failure: it only means no export has been made from this checkout yet.
    """
    record_path = os.path.join(root, EXPORT_RECORD)
    if not os.path.isfile(record_path):
        return [], ['no recorded public export; run tools/export_public.py to '
                    'establish the mirror baseline']
    try:
        with open(record_path, encoding='utf-8') as stream:
            record = json.load(stream)
    except (OSError, ValueError) as error:
        return [f'public export record is unreadable: {error}'], []

    exported = record.get('files') or {}
    try:
        import export_public
    except ImportError:
        from . import export_public
    current = allowlist_digests(root, export_public.ALLOW_FILES)
    problems = []
    for name in sorted(set(exported) | set(current)):
        before, after = exported.get(name), current.get(name)
        if before == after:
            continue
        state = 'added' if not before else 'removed' if not after else 'changed'
        problems.append(f'public mirror is behind: {name} ({state} since '
                        f"export {record.get('exported_at', 'unknown')})")
    return problems, []


def _normal_url(value):
    return str(value or '').strip().removesuffix('.git').rstrip('/').casefold()


def repository_identity_problems(root, repo_policy, has_git, inspect_remote):
    problems = []
    classification = repo_policy.get('classification')
    expected_name = REPOSITORY_NAMES.get(classification)
    if expected_name and repo_policy.get('repository_name') != expected_name:
        problems.append(
            f'repository_name must be {expected_name}, got '
            f"{repo_policy.get('repository_name')!r}")
    canonical = repo_policy.get('canonical_repository_url')
    if not str(canonical or '').rstrip('/').endswith('/' + str(expected_name or '')):
        problems.append('canonical_repository_url does not match repository_name')
    if has_git and inspect_remote and canonical:
        result = subprocess.run(
            ['git', 'remote', '-v'], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        urls = [row.split()[1] for row in result.stdout.splitlines()
                if len(row.split()) >= 2] if result.returncode == 0 else []
        if _normal_url(canonical) not in {_normal_url(url) for url in urls}:
            problems.append('no Git remote matches canonical_repository_url')
    if classification == 'PUBLIC_SKILL':
        recorded = repo_policy.get('release_fingerprint')
        if not recorded or recorded != release_fingerprint(root):
            problems.append('public release fingerprint does not match its working tree')
    return problems


def history_secret_problems(root):
    """Inspect reachable historical blobs, not merely historical filenames."""
    commits = subprocess.run(
        ['git', 'rev-list', '--all'], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.splitlines()
    problems = []
    for commit in commits:
        result = subprocess.run(
            ['git', 'grep', '-I', '-l', '-E', HISTORY_EXPRESSION, commit, '--'], cwd=root,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0:
            problems.append(f'possible secret in reachable history at {commit[:12]}')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true',
                        help='also scan every reachable historical blob for secrets')
    parser.add_argument('--public-tree', metavar='PATH',
                        help='audit a generated public mirror directory instead of this repo')
    parser.add_argument('--mirror-drift', action='store_true',
                        help='report allowlisted files changed since the last public export')
    args = parser.parse_args()
    root = os.path.abspath(args.public_tree or ROOT)
    if args.mirror_drift:
        if args.public_tree:
            print('mirror drift is measured from the personal source repository')
            return 2
        drift, notes = mirror_drift_problems(root)
        for note in notes:
            print(f'mirror drift: {note}')
        if drift:
            print(f'{len(drift)} public mirror drift problem(s):')
            for problem in drift[:60]:
                print(f'  - {problem}')
            if len(drift) > 60:
                print(f'  - ...and {len(drift) - 60} more')
            print('Re-export with tools/export_public.py and review the diff.')
            return 1
        if not notes:
            print('public mirror is in step with the personal source')
        return 0
    problems = []
    repo_policy = policy(root)
    public = bool(args.public_tree) or repo_policy.get('classification') == 'PUBLIC_SKILL'
    expected = 'PUBLIC_SKILL' if public else 'PERSONAL_PRIVATE'
    if repo_policy.get('classification') != expected:
        problems.append(
            f'repository classification must be {expected}, got '
            f"{repo_policy.get('classification')!r}")
    try:
        has_git = os.path.isdir(os.path.join(root, '.git'))
        files = tree_files(root) if args.public_tree or not has_git else tracked_files(root)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'repository check unavailable: {error}')
        return 1
    problems.extend(repository_identity_problems(
        root, repo_policy, has_git, inspect_remote=not bool(args.public_tree)))
    problems.extend(skill_problems(root, files, require_tracked=has_git))
    problems.extend(path_problems(files, 'public tree' if public else 'tracked tree', public))
    problems.extend(content_problems(root, files, 'public tree' if public else 'tracked tree'))
    if args.history and has_git:
        try:
            problems.extend(history_secret_problems(root))
        except (OSError, subprocess.CalledProcessError) as error:
            problems.append(f'history check unavailable: {error}')
    if problems:
        print(f'{len(problems)} repository problem(s):')
        for problem in problems[:60]:
            print(f'  - {problem}')
        if len(problems) > 60:
            print(f'  - ...and {len(problems) - 60} more')
        return 1
    label = 'sanitized public mirror' if public else 'personal private source repository'
    suffix = ' plus reachable history' if args.history else ''
    print(f'{label} OK ({len(files)} files{suffix})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
