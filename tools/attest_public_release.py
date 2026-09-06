"""Bind the private source baseline to the commit actually pushed to public."""
import argparse
import datetime
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import check_repo, export_public, prepare_public_release


def _git(root, *arguments):
    result = subprocess.run(
        ['git', *arguments], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def attest(public_clone):
    """Verify local/public equality and record the reachable public commit."""
    public_clone = prepare_public_release.verify_target(public_clone)
    if _git(public_clone, 'status', '--porcelain'):
        raise ValueError('public clone has uncommitted changes')
    branch = _git(public_clone, 'branch', '--show-current')
    if not branch:
        raise ValueError('public clone is not on a named branch')
    public_commit = _git(public_clone, 'rev-parse', 'HEAD')
    remote_line = _git(
        public_clone, 'ls-remote', '--heads', 'origin', f'refs/heads/{branch}')
    remote_commit = remote_line.split()[0] if remote_line else ''
    if remote_commit != public_commit:
        raise ValueError('public origin does not contain the checked-out commit')
    with open(os.path.join(public_clone, 'repo-policy.json'), encoding='utf-8') as stream:
        policy = json.load(stream)
    fingerprint = check_repo.release_fingerprint(public_clone)
    if policy.get('release_fingerprint') != fingerprint:
        raise ValueError('public clone fingerprint does not match its release policy')

    record = {
        '_schema': 'joblooper.public-export.v2',
        'exported_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'release_fingerprint': fingerprint,
        'files': check_repo.allowlist_digests(ROOT, export_public.ALLOW_FILES),
        'public_repository_url': export_public.PUBLIC_REPOSITORY_URL,
        'public_branch': branch,
        'public_commit': public_commit,
        'remote_verified_at': datetime.datetime.now().astimezone().isoformat(
            timespec='seconds'),
        'private_source_commit': _git(ROOT, 'rev-parse', 'HEAD'),
    }
    path = os.path.join(ROOT, check_repo.EXPORT_RECORD)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('public_clone', help='clean canonical Pub-JobLooper clone')
    args = parser.parse_args()
    try:
        record = attest(args.public_clone)
    except ValueError as error:
        print(f'PUBLIC ATTESTATION REFUSED - {error}')
        return 1
    print(f"public release attested  {record['public_commit']}")
    print(f"  fingerprint  {record['release_fingerprint']}")
    print('  private baseline updated; commit and push it to complete synchronization')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
