"""Synchronize a verified Pub-JobLooper clone from the sanitized private source."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import export_public


def _read_policy(root):
    try:
        with open(os.path.join(root, 'repo-policy.json'), encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {}


def _remote(root):
    result = subprocess.run(
        ['git', 'remote', 'get-url', 'origin'], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.strip() if result.returncode == 0 else ''


def _normal_url(value):
    return str(value or '').strip().removesuffix('.git').rstrip('/').casefold()


def verify_target(target):
    target = os.path.abspath(os.path.expanduser(str(target)))
    if target == os.path.abspath(ROOT):
        raise ValueError('public target cannot be the private source checkout')
    if not os.path.isdir(os.path.join(target, '.git')):
        raise ValueError('public target must be an existing Git clone')
    policy = _read_policy(target)
    if policy.get('classification') != 'PUBLIC_SKILL':
        raise ValueError('target is not a classified Pub-JobLooper checkout')
    if policy.get('repository_name') not in {
            None, export_public.PUBLIC_REPOSITORY_NAME}:
        raise ValueError('target repository identity conflicts with Pub-JobLooper')
    if _normal_url(_remote(target)) != _normal_url(export_public.PUBLIC_REPOSITORY_URL):
        raise ValueError('target origin is not the canonical Pub-JobLooper repository')
    return target


def synchronize(target):
    """Replace only a verified public clone's working tree; preserve its Git history."""
    target = verify_target(target)
    with tempfile.TemporaryDirectory(prefix='joblooper-public-release-') as temp:
        mirror, _ = export_public.export(os.path.join(temp, 'mirror'))
        for name in os.listdir(target):
            if name == '.git':
                continue
            path = os.path.join(target, name)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
        for name in os.listdir(mirror):
            source = os.path.join(mirror, name)
            destination = os.path.join(target, name)
            if os.path.isdir(source):
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
    audit = subprocess.run(
        [sys.executable, os.path.join(target, 'tools', 'check_repo.py'),
         '--public-tree', target],
        cwd=target, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if audit.returncode:
        raise ValueError('synchronized public clone failed its audit:\n' + audit.stdout)
    return target, audit.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='existing canonical Pub-JobLooper clone')
    parser.add_argument('--apply', action='store_true',
                        help='confirm replacement of the verified public working tree')
    args = parser.parse_args()
    try:
        target = verify_target(args.target)
        if not args.apply:
            print('PUBLIC SYNC READY — target verified; rerun with --apply')
            print(f'  target  {target}')
            return 2
        target, audit = synchronize(target)
    except ValueError as error:
        print(f'PUBLIC SYNC REFUSED — {error}')
        return 1
    print(f'public working tree synchronized  {target}')
    print(f'  {audit}')
    print('  next: inspect git diff; commit and push only after human approval')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
