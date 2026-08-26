"""Validate the personal source repository or a sanitized public mirror."""
import argparse
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
    'core/employer_review.py', 'core/gates.py', 'core/language.py',
    'core/match.py', 'core/preflight.py', 'core/release.py', 'core/store.py',
    'core/truth_review.py', 'references/ground-truth-governance.md',
    'references/rejection-learning.md', 'references/section-contracts.md',
    'tools/install_local_skill.py', 'references/installation.md',
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
    args = parser.parse_args()
    root = os.path.abspath(args.public_tree or ROOT)
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
