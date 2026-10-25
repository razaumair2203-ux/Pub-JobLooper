#!/usr/bin/env python3
"""Lightweight JD screening front-end.

Examples:
  python tools/jd_screen.py screen jd.txt --company "Example Aerospace" \
      --title "Project Engineer" --complete-advert --output screen.json
  python tools/jd_screen.py verify screen.json --current
  python tools/jd_screen.py promote screen.json

``screen`` creates no application/work record. ``promote`` is the explicit
boundary into the normal Joblooper lifecycle.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import screen, store, vec  # noqa: E402


def _read_json(path):
    value = store.read_json(os.path.abspath(path))
    if not isinstance(value, dict):
        raise SystemExit('JD SCREEN REFUSED — packet must be a JSON object')
    return value


def cmd_screen(args):
    raw = sys.stdin.read() if args.file == '-' else store.read_text(os.path.abspath(args.file))
    try:
        packet = screen.create(
            raw, company=args.company, title=args.title, url=args.url,
            job_reference=args.reference,
            complete_advert_confirmed=args.complete_advert,
            identity_override=args.identity)
    except ValueError as error:
        raise SystemExit(f'JD SCREEN REFUSED — {error}')
    if args.output:
        target = os.path.abspath(args.output)
        store.write_json(target, packet)
        print(target)
    else:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args):
    packet = _read_json(args.packet)
    result = screen.verify(
        packet, require_current=args.current,
        recompute_analysis=args.recompute or args.current)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['valid'] else 1


def cmd_promote(args):
    packet = _read_json(args.packet)
    try:
        with store.writer_lock():
            result = screen.promote(packet)
    except ValueError as error:
        raise SystemExit(f'JD PROMOTION REFUSED — {error}')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', help='override JOBLOOPER_DATA_DIR')
    sub = parser.add_subparsers(dest='command', required=True)

    command = sub.add_parser('screen', help='create a read-only factual JD screen')
    command.add_argument('file', help='complete JD text file, or - for stdin')
    command.add_argument('--company', required=True)
    command.add_argument('--title', required=True)
    command.add_argument('--url')
    command.add_argument('--reference')
    command.add_argument('--identity')
    command.add_argument('--complete-advert', action='store_true',
                         help='assert the input is the complete advert, not a snippet')
    command.add_argument('--output', help='write packet here instead of stdout')
    command.set_defaults(fn=cmd_screen)

    command = sub.add_parser('verify', help='verify a saved screen packet')
    command.add_argument('packet')
    command.add_argument('--current', action='store_true',
                         help='also require current truth and engine bindings')
    command.add_argument('--recompute', action='store_true',
                         help='recompute deterministic mapping from embedded JD')
    command.set_defaults(fn=cmd_verify)

    command = sub.add_parser('promote', help='promote one exact screen to application work state')
    command.add_argument('packet')
    command.set_defaults(fn=cmd_promote)

    args = parser.parse_args(argv)
    if args.data_dir:
        store.configure(args.data_dir)
        vec.reset_caches()
    return args.fn(args)


if __name__ == '__main__':
    raise SystemExit(main())
