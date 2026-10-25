"""Read-only consumer-context contract checks."""
import copy
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
                       packet['_schema'] == 'joblooper.consumer-context.v2'))
        checks.append(('packet is bound to the exact approved truth',
                       packet['authority']['truth_sha256'] == context['truth_sha256']
                       and packet['authority']['generation_truth_sha256']
                       == context['generation_truth_sha256']))
        checks.append(('default packet has a verifiable transport digest',
                       export_context.verify_packet(packet)))
        tampered = copy.deepcopy(packet)
        tampered['records'][0]['fact'] = str(tampered['records'][0].get('fact', '')) + ' tampered'
        checks.append(('payload mutation without a new digest is detected',
                       not export_context.verify_packet(tampered)))
        checks.append(('default career-routing scope follows least privilege',
                       packet['scope'] == 'career-routing'
                       and 'contact' not in packet['profile']
                       and 'links' not in packet['profile']
                       and 'sections' not in packet
                       and 'sources' not in packet
                       and 'indices' not in packet))

        full = export_context.build_packet('full')
        checks.append(('full scope remains available for trusted local diagnostics',
                       full['profile'] == context['profile']
                       and full['records'] == context['records']
                       and full['sections'] == context['sections']
                       and full['sources'] == context['sources']
                       and export_context.verify_packet(full)))
        checks.append(('packet carries approval provenance without becoming authority',
                       packet['authority']['truth_approval_sha256']
                       and packet['consumer_contract']['read_only'] is True
                       and 'rendering a final employer CV outside Joblooper'
                       in packet['consumer_contract']['forbidden']))
        checks.append(('application artefacts are outside the consumer packet',
                       'jobs' not in packet and 'applications' not in packet
                       and 'work' not in packet))

        before_generation = packet['authority']['generation_truth_sha256']
        before_truth = packet['authority']['truth_sha256']
        before_packet = packet['packet_sha256']
        store.log_change('consumer_context_test', 'Audit-only event.', 'No generation input changed.')
        refreshed = export_context.build_packet()
        checks.append(('audit history refreshes packet provenance without changing generation truth',
                       refreshed['authority']['truth_sha256'] != before_truth
                       and refreshed['authority']['generation_truth_sha256']
                       == before_generation
                       and refreshed['packet_sha256'] != before_packet
                       and export_context.verify_packet(refreshed)))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} consumer-context invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
