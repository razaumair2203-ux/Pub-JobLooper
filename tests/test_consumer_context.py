"""Read-only consumer-context contract checks."""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import store, vec
from tools import export_context


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-consumer-context-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()

        packet = export_context.build_packet()
        context = store.truth_context()
        checks.append(('packet uses the versioned consumer schema',
                       packet['_schema'] == 'joblooper.consumer-context.v1'))
        checks.append(('packet is bound to the exact approved truth',
                       packet['authority']['truth_sha256'] == context['truth_sha256']
                       and packet['authority']['generation_truth_sha256']
                       == context['generation_truth_sha256']))
        checks.append(('packet exposes the same governed records and profile',
                       packet['records'] == context['records']
                       and packet['profile'] == context['profile']))
        checks.append(('packet carries generation policy without becoming authority',
                       packet['sections'] == context['sections']
                       and packet['consumer_contract']['read_only'] is True
                       and 'rendering a final employer CV outside Joblooper'
                       in packet['consumer_contract']['forbidden']))
        checks.append(('application artefacts are outside the consumer packet',
                       'jobs' not in packet and 'applications' not in packet
                       and 'work' not in packet))

        before_generation = packet['authority']['generation_truth_sha256']
        before_truth = packet['authority']['truth_sha256']
        store.log_change('consumer_context_test', 'Audit-only event.', 'No generation input changed.')
        refreshed = export_context.build_packet()
        checks.append(('audit history refreshes packet provenance without changing generation truth',
                       refreshed['authority']['truth_sha256'] != before_truth
                       and refreshed['authority']['generation_truth_sha256']
                       == before_generation))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} consumer-context invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
