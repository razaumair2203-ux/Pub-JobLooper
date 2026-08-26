"""Adversarial gate tests — proof that the guardrails are not decorative.

Every gate gets attacked in BOTH directions:
  EXPLOIT     a CV that should be refused. If it passes, the gate is decorative.
  LEGITIMATE  a real claim the gate must NOT block. If it blocks, the gate is
              obstructive, which gets it disabled in practice and is just as bad.

Run:  python tests/test_gates.py            (exit 1 on any failure)
"""
import sys, os, json, zipfile, tempfile
FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'examples', 'starter')
os.environ['JOBLOOPER_DATA_DIR'] = FIXTURE
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import gates, store, render, match

BY_ID, RECS = store.anchors()
BND = store.boundaries()
RESULTS = []


def cv(bullets, header=None, section='PROFESSIONAL EXPERIENCE', stype='experience'):
    """Minimal CV skeleton. bullets: list of (text, anchor_or_list)."""
    def item(t, a):
        ids = a if isinstance(a, list) else [a]
        return {'text': t, 'anchor': ids[0], 'anchors': ids}
    body = ({'name': section, 'type': stype,
             'items': [{'title': 'Role', 'org': 'Org', 'period': 'Jan 2020 – Dec 2022',
                        'anchor': 'ROLE-005', 'text': 'Role',
                        'bullets': [item(t, a) for t, a in bullets]}]}
            if stype == 'experience' else
            {'name': section, 'type': stype, 'items': [item(t, a) for t, a in bullets]})
    return {'target_pages': 2,
            'header': header or {'name': 'ALEX MORGAN', 'headline': '', 'contact': [], 'links': {}},
            'sections': [body]}


def check(gate, name, kind, got, want):
    ok = got == want
    RESULTS.append((gate, name, kind, got, want, ok))
    return ok


def run(gate_fn, doc):
    """Normalise every gate signature to a level string."""
    import inspect
    n = len(inspect.signature(gate_fn).parameters)
    args = [doc, BY_ID, BND][:n] if n > 1 else [doc]
    if gate_fn is gates.g5_boundaries:
        args = [doc, BND]
    if gate_fn in (gates.g6_duplication, gates.g8_document):
        args = [doc]
    return gate_fn(*args)[0]


# ---------------------------------------------------------------- G1
check('G1', 'line citing a non-existent anchor', 'EXPLOIT',
      run(gates.g1_traceability, cv([('Invented achievement.', 'NOPE-999')])), 'BLOCK')
check('G1', 'line with no anchor at all', 'EXPLOIT',
      run(gates.g1_traceability, {'target_pages': 2, 'header': {},
          'sections': [{'name': 'X', 'type': 'para', 'items': [{'text': 'Floating claim.'}]}]}), 'BLOCK')
check('G1', 'properly cited line', 'LEGITIMATE',
      run(gates.g1_traceability,
          cv([('Led maintenance engineering on the fictional Orion-X research demonstrator.', 'MRO-002')])), 'PASS')
check('G1', 'approved external alias remains traceable', 'LEGITIMATE',
      run(gates.g1_traceability,
          cv([('Led maintenance engineering on the fictional research demonstrator.', 'MRO-002')])), 'PASS')
check('G1', 'unrelated claim laundering through a live anchor', 'EXPLOIT',
      run(gates.g1_traceability,
          cv([('Led nuclear-reactor integration across 777 installations.', 'MRO-002')])), 'BLOCK')
check('G1', 'unsupported factual headline', 'EXPLOIT',
      run(gates.g1_traceability, cv([('Led flight-line MRO engineering.', 'MRO-002')],
          header={'name': 'Candidate', 'headline': 'Certified CATIA expert; delivered 999999 aircraft',
                  'contact': [], 'links': {}})), 'BLOCK')

# ---------------------------------------------------------------- G2
check('G2', 'verb above anchor ownership', 'EXPLOIT',
      run(gates.g2_ownership, cv([('Owned the export growth programme.', 'DEV-004')])), 'BLOCK')
check('G2', 'laundering via co-cited high anchor', 'EXPLOIT',
      run(gates.g2_ownership, cv([('Owned the export growth programme.', ['DEV-004', 'EDU-001'])])), 'BLOCK')
check('G2', 'upgrading contribution to achievement', 'EXPLOIT',
      run(gates.g2_ownership, cv([('Led readiness work sustaining availability above 92%.', 'PMO-004')])), 'BLOCK')
check('G2', 'genuine owned-level claim', 'LEGITIMATE',
      run(gates.g2_ownership, cv([('Architected and deployed a fleet configuration-management application.', 'PMO-003')])), 'PASS')
check('G2', 'multi-anchor summary drawing on an owned anchor', 'LEGITIMATE',
      run(gates.g2_ownership, cv([('Architected and deployed a fleet configuration-management application.',
                                   ['PMO-003', 'MRO-001'])], stype='para', section='PROFESSIONAL SUMMARY')), 'PASS')
_capped = dict(BY_ID['MRO-002'])
_capped['id'] = 'CAP-001'
_capped['fact'] = 'Led systems engineering and coordinated technology transfer.'
_capped['bullet'] = {'short': _capped['fact']}
_capped['claim_caps'] = [{'pattern': 'technology transfer', 'max': 'coordinated'}]
_cap_ids = dict(BY_ID)
_cap_ids['CAP-001'] = _capped
check('G2', 'composite claim cannot launder bounded technology-transfer ownership', 'EXPLOIT',
      gates.g2_ownership(
          cv([('Led systems engineering and technology transfer.', 'CAP-001')]),
          _cap_ids, BND)[0], 'BLOCK')
check('G2', 'composite claim carries its bounded clause verb explicitly', 'LEGITIMATE',
      gates.g2_ownership(
          cv([('Led systems engineering and coordinated technology transfer.', 'CAP-001')]),
          _cap_ids, BND)[0], 'PASS')

# ---------------------------------------------------------------- G3
check('G3', 'pipeline paper claimed as published', 'EXPLOIT',
      run(gates.g3_status, cv([('Published research on runway FOD detection.', 'PUB-003')])), 'BLOCK')
check('G3', 'coursework claimed as certification', 'EXPLOIT',
      run(gates.g3_status, cv([('Six Sigma certification completed.', 'MRO-001')])), 'BLOCK')
check('G3', 'genuinely published paper', 'LEGITIMATE',
      run(gates.g3_status, cv([('Published in IEEE Xplore, 2025.', 'PUB-001')])), 'PASS')
check('G3', 'uncited certification claim in headline', 'EXPLOIT',
      run(gates.g3_status, cv([('Clean claim.', 'MRO-002')],
          header={'name': 'Candidate', 'headline': 'Certified CATIA expert',
                  'contact': [], 'links': {}})), 'BLOCK')

# ---------------------------------------------------------------- G4
check('G4', 'invented headline metric', 'EXPLOIT',
      run(gates.g4_metrics, cv([('Delivered 999999 systems to 4242 customers.', 'DEV-001')])), 'BLOCK')
check('G4', 'invented team size', 'EXPLOIT',
      run(gates.g4_metrics, cv([('Managed a team of 47 engineers.', 'PMO-002')])), 'BLOCK')
check('G4', 'invented budget', 'EXPLOIT',
      run(gates.g4_metrics, cv([('Controlled a 25 million dollar programme budget.', 'PMO-002')])), 'BLOCK')
check('G4', 'metric laundering from an unrelated global anchor', 'EXPLOIT',
      run(gates.g4_metrics, cv([('Led integration across 999 assets.', 'MRO-002')])), 'BLOCK')
check('G4', 'real anchored metrics', 'LEGITIMATE',
      run(gates.g4_metrics, cv([('Controlled 24 changes across 18 fictional test assets.', 'PMO-003')])), 'PASS')
check('G4', 'platform designators', 'LEGITIMATE',
      run(gates.g4_metrics,
          cv([('Supported Orion-X and Falcon-R Block B demonstrators.', ['MRO-002', 'PMO-009'])])), 'PASS')
check('G4', 'ISO standards list', 'LEGITIMATE',
      run(gates.g4_metrics, cv([('ISO 9001 gap review and internal audit.', 'QA-001')])), 'PASS')
check('G4', 'career years cannot appear on an unrelated claim', 'EXPLOIT',
      run(gates.g4_metrics, cv([('Delivered 12 systems.', 'EDU-001')])), 'BLOCK')

# ---------------------------------------------------------------- G5
for term, label in [('EASA Part-145 certifying staff', 'EASA/Part-145'),
                    ('Part-66 B1.1 licence held', 'Part-66 licence'),
                    ('Six Sigma Green Belt', 'Six Sigma belt'),
                    ('CSEP certified systems engineering professional', 'CSEP as held'),
                    ('CFM56 engine experience', 'CFM engine'),
                    ('AHA BLS instructor and ICU clinical lead', 'unrelated clinical credentials')]:
    check('G5', label + ' in a bullet', 'EXPLOIT',
          run(gates.g5_boundaries, cv([(term, 'MRO-002')])), 'BLOCK')
check('G5', 'forbidden claim hidden in the HEADER', 'EXPLOIT',
      run(gates.g5_boundaries, cv([('Clean bullet.', 'MRO-002')],
          header={'name': 'ALEX MORGAN', 'headline': 'EASA Part-145 certifying staff',
                  'contact': ['ICU clinical BLS instructor'], 'links': {}})), 'BLOCK')
check('G5', 'CNIC pattern in contact metadata', 'EXPLOIT',
      run(gates.g5_boundaries, cv([('Clean bullet.', 'MRO-002')],
          header={'name': 'Candidate', 'headline': '',
                  'contact': ['CNIC 12345-1234567-1'], 'links': {}})), 'BLOCK')
check('G5', 'lawful generic type qualification', 'LEGITIMATE',
      run(gates.g5_boundaries, cv([('Research Demonstrator Type Qualification.', 'CRED-009')])), 'PASS')
check('G5', 'lawful quality coursework wording', 'LEGITIMATE',
      run(gates.g5_boundaries, cv([('Quality-improvement foundations coursework.', 'CRED-008')])), 'PASS')

# ---------------------------------------------------------------- G6
check('G6', 'same anchor rendered twice', 'EXPLOIT',
      run(gates.g6_duplication, cv([('Led flight-line MRO engineering on a high-availability AEW&C platform.', 'MRO-002'),
                                    ('Led flight-line MRO engineering on a high-availability AEW&C platform.', 'MRO-002')])), 'BLOCK')
check('G6', 'two genuinely different bullets', 'LEGITIMATE',
      run(gates.g6_duplication, cv([('Led flight-line MRO engineering on a high-availability AEW&C platform.', 'MRO-002'),
                                    ('Architected a fleet configuration-management application.', 'PMO-003')])), 'PASS')

# ---------------------------------------------------------------- G7
_m = {'gaps': [{'n': 1, 'text': 'EASA Part-66 licence required', 'hard_gate': True}],
      'hard_gate_gaps': [{'n': 1, 'text': 'EASA Part-66 licence required', 'hard_gate': True}]}
check('G7', 'unmeetable hard gate blocks release', 'EXPLOIT', gates.g7_coverage(_m)[0], 'BLOCK')
check('G7', 'full coverage stays quiet', 'LEGITIMATE',
      gates.g7_coverage({'gaps': [], 'hard_gate_gaps': []})[0], 'PASS')
_invisible = {'gaps': [], 'hard_gate_gaps': [], 'requirements': [{
    'n': 1, 'text': 'Mandatory integration evidence', 'kind': 'mandatory',
    'hard_gate': False, 'match': 'DIRECT', 'anchors': [{'id': 'SYS-001'}]}]}
_invisible_cv = cv([('Led maintenance engineering.', 'MRO-002')])
_invisible_cv['_selection'] = {'selected_ids': ['MRO-002']}
check('G7', 'DIRECT mandatory evidence deleted from the CV', 'EXPLOIT',
      gates.g7_coverage(_invisible, _invisible_cv)[0], 'BLOCK')
_visible_cv = cv([('Led maintenance engineering.', 'MRO-002')])
_visible_cv['sections'][0]['items'][0]['bullets'][0]['_serves'] = [1]
check('G7', 'unrelated line cannot launder DIRECT coverage metadata', 'EXPLOIT',
      gates.g7_coverage(_invisible, _visible_cv)[0], 'BLOCK')
_supported_cv = cv([('Led systems integration and verification.', 'SYS-001')])
_supported_cv['sections'][0]['items'][0]['bullets'][0]['_serves'] = [1]
check('G7', 'DIRECT supporting evidence is cited and visible', 'LEGITIMATE',
      gates.g7_coverage(_invisible, _supported_cv)[0], 'PASS')

# ---------------------------------------------------------------- G8
check('G8', 'XML-illegal control character', 'EXPLOIT',
      run(gates.g8_document, cv([('Corrupt\x01text in a bullet.', 'MRO-002')])), 'BLOCK')
_structure_details = gates.g8_document(cv([('Clean claim.', 'MRO-002')]))[2]
check('G8', 'omitted employment role is detected', 'EXPLOIT',
      any('chronology omits' in x for x in _structure_details), True)
check('G8', 'omitted protected section is detected', 'EXPLOIT',
      any('protected section' in x for x in _structure_details), True)
_thin = cv([('Clean claim.', 'MRO-002')])
_thin['target_pages'] = 3
_thin['_selection'] = {'significant_omissions': ['SYS-001']}
check('G8', 'thin CV with material evidence omitted is blocked', 'EXPLOIT',
      gates.g8_document(_thin)[0], 'BLOCK')
_missing_featured = cv([('Clean claim.', 'MRO-002')])
_missing_featured['identity'] = 'systems_engineer'
check('G8', 'governed career highlight cannot disappear', 'EXPLOIT',
      any('career highlight omitted' in x
          for x in gates.g8_document(_missing_featured)[2]), True)

# ---------------------------------------------------------------- G9
def g9_probe():
    """Render a document whose header carries a forbidden claim, then verify the
    post-render backstop reads it back out of the actual .docx."""
    doc = cv([('Clean bullet.', 'MRO-002')],
             header={'name': 'ALEX MORGAN', 'headline': 'EASA Part-145 certifying staff',
                     'contact': [], 'links': {}})
    tmp = os.path.join(tempfile.gettempdir(), 'jl_g9_probe.docx')
    render.to_docx(doc, tmp)
    lvl = gates.verify_rendered(tmp)[0]
    os.remove(tmp)
    return lvl

check('G9', 'forbidden claim inside the rendered .docx', 'EXPLOIT', g9_probe(), 'BLOCK')

def g9_clean():
    doc = cv([('Led flight-line MRO engineering.', 'MRO-002')])
    tmp = os.path.join(tempfile.gettempdir(), 'jl_g9_clean.docx')
    render.to_docx(doc, tmp)
    lvl = gates.verify_rendered(tmp)[0]
    os.remove(tmp)
    return lvl

check('G9', 'clean rendered package', 'LEGITIMATE', g9_clean(), 'PASS')

def g9_table_probe():
    """A syntactically valid table still violates the linear ATS contract."""
    import zipfile
    doc = cv([('Led flight-line MRO engineering.', 'MRO-002')])
    tmp = os.path.join(tempfile.gettempdir(), 'jl_g9_table_probe.docx')
    mutated = tmp + '.mutated'
    render.to_docx(doc, tmp)
    with zipfile.ZipFile(tmp) as source, zipfile.ZipFile(mutated, 'w') as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == 'word/document.xml':
                xml = data.decode('utf-8').replace(
                    '</w:body>',
                    '<w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl></w:body>')
                data = xml.encode('utf-8')
            target.writestr(info, data)
    os.replace(mutated, tmp)
    lvl = gates.verify_rendered(tmp)[0]
    os.remove(tmp)
    return lvl

check('G9', 'table-based layout in the rendered .docx', 'EXPLOIT', g9_table_probe(), 'BLOCK')

def prose_is_justified():
    import zipfile
    doc = cv([('Led flight-line MRO engineering.', 'MRO-002')])
    tmp = os.path.join(tempfile.gettempdir(), 'jl_g9_justified.docx')
    render.to_docx(doc, tmp)
    with zipfile.ZipFile(tmp) as package:
        xml = package.read('word/document.xml').decode('utf-8')
    os.remove(tmp)
    return '<w:jc w:val="both"/>' in xml

check('G9', 'evidence prose uses controlled full justification', 'LEGITIMATE',
      prose_is_justified(), True)

# ---------------------------------------------------------------- hard gates
for text, kind, want in [('Valid Part-66 B1 licence', 'mandatory', True),
                         ('Must hold valid work authorisation for Saudi Arabia', 'mandatory', True),
                         ('5+ years aircraft maintenance experience', 'mandatory', True),
                         ('Strong communication skills', 'mandatory', False),
                         ('Nice to have: Arabic', 'preferred', False)]:
    check('JD', f'hard gate: {text[:38]}', 'EXPLOIT' if want else 'LEGITIMATE',
          match._is_hard_gate(text, kind), want)

# ---------------------------------------------------------------- report
print()
w = max(len(n) for _, n, _, _, _, _ in RESULTS)
fails = 0
for gate, name, kind, got, want, ok in RESULTS:
    if not ok:
        fails += 1
    print(f"  {'ok ' if ok else 'FAIL'}  {gate:3} {kind:10} {name:{w}}  -> {got}")
print(f"\n  {len(RESULTS) - fails}/{len(RESULTS)} passed"
      + (f", {fails} FAILED" if fails else ""))
sys.exit(1 if fails else 0)
