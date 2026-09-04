"""Semantic-matching regression tests against fictional data only."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('JOBLOOPER_DATA_DIR', os.path.join(ROOT, 'examples', 'starter'))
sys.path.insert(0, ROOT)

from core import match


def req(n, text, kind='mandatory', hard=False):
    return {'n': n, 'text': text, 'kind': kind, 'hard_gate': hard,
            'gate_type': 'evidence'}


def main():
    identity = {'primary': 'systems_engineer', 'ranked': [],
                'overridden': False, 'confidence': 1.0}
    jd = {
        'title': 'Senior Systems Engineer', 'company': 'Northstar Aerospace',
        'requirements': [
            req(1, 'Bachelor degree in Electrical or Electronic Engineering.'),
            req(2, 'Experience leading compliance and certification evidence through qualification and acceptance reviews.'),
            req(3, 'Knowledge of the Northstar Falcon-X proprietary platform framework.', kind='preferred'),
        ],
    }
    result = match.match_jd(jd, identity)
    rows = {r['n']: r for r in result['requirements']}
    invisible = match.document_coverage(result, set())
    mentor_record = {
        'id': 'MENTOR-001', 'type': 'anchor',
        'fact': 'Mentored professionals to Systems Engineering certification.',
        'bullet': {'short': 'Mentored engineering professionals.'},
    }
    mentor_class = match._exact_classification(
        'Professionally mentor an engineer against a learning and development plan.',
        [{'id': 'MENTOR-001', 'score': 0.5}], {'MENTOR-001': mentor_record})
    unbulleted = match.parse_jd('''Key Responsibilities
Engineering Management & Project Integration
Accountability for the end-to-end engineering lifecycle, ensuring Quality, Cost, and Time targets.
Integrating engineering activities with Procurement, Construction, and Commissioning to prevent functional silos.
Required Qualifications
Bachelor's degree in Electrical Engineering or related field
Professional fluency in English for international stakeholders.
Understanding of project execution risks and financial processes.
Desired Characteristics
Conducting detailed design reviews for substation steel structures, electrical safety clearances, and cable routing.
Professional fluency in Arabic for effective communication with local clients.
Demonstrated understanding of High Voltage equipment design review, supplemented by Factory Acceptance Tests.
Additional Information
Relocation Assistance Provided: No''')
    parsed = unbulleted['requirements']
    checks = [
        ('degree is matched only to education evidence',
         rows[1]['match'] == 'DIRECT' and rows[1]['anchors'][0]['id'] == 'EDU-001'),
        ('system certification uses lifecycle evidence, not a credential record',
         rows[2]['match'] == 'DIRECT' and
         all(a['id'] not in {'CRED-001', 'CRED-008', 'CRED-009'} for a in rows[2]['anchors'])),
        ('named employer platform remains an explicit gap', rows[3]['match'] != 'DIRECT'),
        ('whole-ad denominator retains all material families', result['total_material'] == 3),
        ('coverage is broken out by requirement family',
         set(result['coverage_by_kind']) == {'mandatory', 'responsibility', 'preferred'}),
        ('document coverage cannot borrow omitted truth evidence',
         invisible['covered'] == 0 and invisible['coverage'] == 0),
        ('professional mentoring resolves to direct mentoring evidence',
         mentor_class[0] == 'DIRECT' and mentor_class[2] == 'MENTOR-001'),
        ('mandatory language and location eligibility are hard gates',
         match._is_hard_gate('Professional fluency in English.', 'mandatory')
         and match._is_hard_gate('Ability to live and work in Riyadh.', 'mandatory')),
        ('unbulleted section items survive normalized job-page extraction',
         len(parsed) == 8
         and [row['kind'] for row in parsed] == [
             'responsibility', 'responsibility', 'mandatory', 'mandatory',
             'mandatory', 'preferred', 'preferred', 'preferred']
         and any('fluency in English' in row['text'] for row in parsed)
         and all('Relocation Assistance' not in row['text'] for row in parsed)),
    ]
    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} matching invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
