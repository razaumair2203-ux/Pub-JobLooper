#!/usr/bin/env python3
"""Export a digest-bound, read-only Joblooper context for other applications.

The packet is derived from approved Joblooper truth. It is an integration
surface, never a second truth store and never a render/approval bypass.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import integrity, store, truth_review

SCHEMA = 'joblooper.consumer-context.v1'


def build_packet():
    problems, warnings, _ = integrity.check_truth()
    if problems:
        raise ValueError(
            f'candidate truth has {len(problems)} integrity error(s); run `python jl.py check`')
    readiness = truth_review.readiness()
    if not readiness.get('ready'):
        raise ValueError(
            'candidate truth is not approved: ' + '; '.join(readiness.get('problems') or []))

    context = store.truth_context()
    return {
        '_schema': SCHEMA,
        'generated_at': store.now(),
        'authority': {
            'truth_sha256': context['truth_sha256'],
            'generation_truth_sha256': context.get(
                'generation_truth_sha256', context['truth_sha256']),
            'source_of_truth': context.get('authority', {}).get(
                'source_of_truth', 'Joblooper truth/'),
            'derived_from': 'approved Joblooper truth; packet is read-only',
        },
        'stats': context.get('stats', {}),
        'profile': context.get('profile', {}),
        'records': context.get('records', []),
        'boundaries': context.get('boundaries', {}),
        'aliases': context.get('aliases', {}),
        'sections': context.get('sections', {}),
        'sources': context.get('sources', []),
        'indices': context.get('indices', {}),
        'warnings': warnings,
        'consumer_contract': {
            'read_only': True,
            'allowed': [
                'career-lane classification',
                'evidence and project routing',
                'gap and disclosure review',
                'advisory application handoff',
            ],
            'forbidden': [
                'editing this packet and treating it as truth',
                'creating candidate facts from an employer advert',
                'approving claims or submissions',
                'rendering a final employer CV outside Joblooper',
                'bypassing Joblooper truth, review or release gates',
            ],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='optional JSON file; stdout is used when omitted')
    args = parser.parse_args(argv)
    try:
        packet = build_packet()
    except ValueError as error:
        print(f'CONTEXT EXPORT REFUSED — {error}', file=sys.stderr)
        return 1

    text = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.output:
        path = os.path.abspath(os.path.expanduser(args.output))
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        print(path)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
