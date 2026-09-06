"""Semantic-matching regression tests against fictional data only."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('JOBLOOPER_DATA_DIR', os.path.join(ROOT, 'examples', 'starter'))
sys.path.insert(0, ROOT)

from core import match, vec


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
    bm, by_id = vec.anchor_index()
    compound_hits = [aid for aid, _ in bm.normed('Project-management certification.', top=2)]
    broad = match._concept_coverage(
        'Lead requirements, interfaces, integration and verification.', bm)
    thin = match._concept_coverage(
        'Practical experience with 400kV GIS substations in Riyadh.', bm)

    checks = [
        # Responsibilities are written as gerunds while evidence is registered
        # as nouns. A plural-only stemmer could never relate the two, so no
        # responsibility could reach DIRECT however strong the evidence was.
        ('gerund and noun forms of one concept share a stem',
         vec._stem('commissioning') == vec._stem('commission')
         and vec._stem('integrating') == vec._stem('integration')
         and vec._stem('managing') == vec._stem('management')
         and vec._stem('procurement') == vec._stem('procure')
         and vec._stem('engineering') == vec._stem('engineer')),
        ('plural normalisation still holds',
         vec._stem('avionic') == vec._stem('avionics')
         and vec._stem('drawing') == vec._stem('drawings')),
        ('short words are never stemmed into collisions',
         vec._stem('ring') == 'ring' and vec._stem('being') == 'being'
         and vec._stem('using') == 'using'),
        # Identifiers are not morphological forms of anything; stemming them
        # only corrupts them, and "node.js" once became "node.j".
        ('identifiers survive tokenisation intact',
         set(vec.tokens('Node.js and A320 and ISO9001 and C#'))
         >= {'node.js', 'a320', 'iso9001', 'c#'}),
        ('sentence-final words lose their trailing stop',
         'silo' in vec.tokens('prevent functional silos.')
         and not any(t.endswith('.') and t != 'node.js'
                     for t in vec.tokens('meet targets.'))),
        # A compound must match its parts, or a shared word can retrieve the
        # wrong anchor while the real evidence ranks nowhere.
        ('hyphenated compounds also match their parts',
         set(vec.tokens('Project-management certification'))
         >= {'project-management', 'project'}),
        ('a compound retrieves the credential, not a lexical collision',
         compound_hits and compound_hits[0] == 'CRED-001'),
        # An advert that expands its own acronym is labelling its own phrase.
        ('an acronym the advert defines itself is not an unknown platform',
         match._inline_acronyms(
             'deliverables meet project Quality, Cost, and Time (QCT) targets.')
         == {'QCT'}
         and match._inline_acronyms('Design tools (CATIA) required.') == set()),
        # Concept coverage is the second opinion the single-anchor score cannot
        # give, and it must name what it could not find.
        ('concept coverage separates broad evidence from a thin match',
         broad[0] > match.CONCEPT_BROAD and thin[0] < match.CONCEPT_THIN),
        ('unevidenced concepts are named, not summarised as a bare gap',
         any('400kv' in term.lower() or 'riyadh' in term.lower()
             for term in thin[1])),
        # Behavioural detection must not depend on the advert's grammar. These
        # four say the same unfalsifiable thing and once landed in four classes.
        ('a disposition is behavioural whatever grammar states it',
         all(match._gate_type(text) == 'behavioural' for text in (
             'Proven communication and team working skills.',
             'Sound communication and negotiation skills.',
             'Experience in fostering a collaborative team environment.',
             'Demonstrating commitment, sound judgment, and a purposeful '
             'approach to technical strategy while inspiring team members.'))),
        ('personal context survives the governed stopword list',
         match._gate_type(
             'Ability to communicate at all organisational levels.')
         == 'behavioural'),
        # The inflating direction. A behavioural requirement leaves the coverage
        # denominator entirely, so a false positive silently raises the score.
        ('an engineering sense of an ambiguous word is not a disposition',
         match._gate_type('Technical Compliance & Integrity: ensuring all '
                          'engineering deliverables comply with the design.')
         == 'evidence'
         and match._gate_type('Flexible design of substation layouts.')
         == 'evidence'
         and match._gate_type('Deliver against contractual commitments.')
         == 'evidence'),
        ('a personal sense of the same word still resolves',
         match._gate_type('Remain flexible to support remote bases.')
         == 'behavioural'),
        # A language requirement routes to the profile gate rather than to
        # evidence; what matters here is that none of these leave the
        # coverage denominator as unfalsifiable assertions.
        ('a specific technical requirement is never called unfalsifiable',
         all(match._gate_type(text) != 'behavioural' for text in (
             'Practical experience with High Voltage GIS/AIS substations.',
             'Professional fluency in Arabic for local clients.',
             'Experience engaging with Saudi utility providers.',
             'Steering final documentation (As-Builts, O&M Manuals).'))),
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
        # A forcing word alone is not a gate. Adverts phrase ordinary duties
        # forcefully, and G7 refuses to build on an unresolved hard gate, so a
        # misread duty blocks the whole application.
        ('a forcefully phrased duty is not a hard gate',
         not match._is_hard_gate(
             'Must ensure designs comply with client specifications.',
             'responsibility')
         and not match._is_hard_gate(
             'Ensuring deliverables adhere to all mandatory national standards.',
             'responsibility')),
        ('a real credential, year count or status is still a hard gate',
         all(match._is_hard_gate(text, kind) for text, kind in (
             ('Valid Part-66 B1 licence', 'mandatory'),
             ('Must hold valid work authorisation for Saudi Arabia', 'mandatory'),
             ('Minimum 7 years of EPC experience leading teams', 'mandatory'),
             ('Must hold SC security clearance', 'preferred'),
             ('Professional fluency in English is required', 'preferred')))),
        ('hard-gate status is re-derived, not frozen at parse time',
         match.match_jd(
             {'title': 'T', 'company': 'C', 'requirements': [
                 dict(req(1, 'Must ensure designs comply with specifications.',
                          kind='responsibility'), hard_gate=True)]},
             identity)['requirements'][0]['hard_gate'] is False),
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
