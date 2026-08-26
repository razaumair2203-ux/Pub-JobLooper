"""Deterministic, evidence-reusing cover-letter assembly.

The letter does not create a second prose generator.  Candidate claims are
copied from the already-gated CV plan; only connective application language is
templated here.  This keeps the letter tailored without giving it permission
to invent a new fact, metric, ownership verb or employer relationship.
"""
import re

from . import store, vec


MAX_EVIDENCE_LINES = 3
MIN_WORDS = 100
MAX_WORDS = 350


_FIRST_PERSON_VERBS = {
    'Acted': 'acted', 'Architected': 'architected', 'Contributed': 'contributed',
    'Coordinated': 'coordinated',
    'Defined': 'defined', 'Delivered': 'delivered', 'Developed': 'developed',
    'Directed': 'directed', 'Established': 'established', 'Finalized': 'finalized',
    'Led': 'led', 'Managed': 'managed', 'Mentors': 'mentor', 'Oversaw': 'oversaw',
    'Produced': 'produced', 'Reviewed': 'reviewed', 'Selected': 'was selected',
    'Supervised': 'supervised', 'Teaches': 'teach', 'Validated': 'validated',
    'Leads': 'lead', 'Manages': 'manage',
}


def _first_person(text):
    """Turn a governed CV action fragment into grammatical first-person prose.

    Only the leading verb is transformed.  The factual payload remains the
    exact gated source text and is still checked through ``source_texts``.
    """
    match = re.match(r'^([A-Za-z]+)(\b.*)$', text.strip())
    if not match or match.group(1) not in _FIRST_PERSON_VERBS:
        raise ValueError(
            f'cover-letter evidence needs a supported first-person verb: {text!r}')
    remainder = re.sub(r'\bhas\b', 'have', match.group(2))
    return 'I ' + _FIRST_PERSON_VERBS[match.group(1)] + remainder


def _summary_first_person(text):
    """Convert a governed CV-summary paragraph into letter grammar."""
    sentences = [part.strip() for part in re.split(r'(?<=\.)\s+', text.strip())
                 if part.strip()]
    if not sentences:
        raise ValueError('cover letter requires a non-empty professional summary')
    first = sentences[0]
    if not re.match(r'^I\b', first, re.I):
        article = 'an' if first[:1].lower() in 'aeiou' else 'a'
        first = f'I am {article} {first}'
    rendered = [first]
    for sentence in sentences[1:]:
        try:
            rendered.append(_first_person(sentence))
            continue
        except ValueError:
            pass
        credential = re.match(
            r'^(.+?\b(?:PMP|PMI-ACP|Professional Engineer)\b[^;]*);\s*selected by (.+)$',
            sentence.rstrip('.'), re.I)
        if credential:
            rendered.append(
                f'I hold {credential.group(1)} credentials and was selected by '
                f'{credential.group(2)}.')
            continue
        raise ValueError(
            f'professional summary needs supported cover-letter grammar: {sentence!r}')
    return ' '.join(rendered)


def _visible_lines(cv):
    lines = []
    for section in cv.get('sections', []):
        if section.get('name') == 'PROFESSIONAL SUMMARY':
            continue
        for item in section.get('items', []):
            if section.get('type') == 'experience':
                for bullet in item.get('bullets', []):
                    lines.append({
                        'text': bullet.get('text', '').strip(),
                        'anchors': bullet.get('anchors') or [bullet.get('anchor')],
                        'serves': bullet.get('_serves') or [],
                        'section': section.get('name'),
                        'role': item.get('anchor'),
                    })
            elif section.get('name') == 'CAREER HIGHLIGHTS & RECOGNITION':
                text = re.sub(r'^\d{4}(?:[^|]{0,20})\|\s*', '', item.get('text', '')).strip()
                lines.append({
                    'text': text,
                    'anchors': item.get('anchors') or [item.get('anchor')],
                    'serves': item.get('_serves') or [],
                    'section': section.get('name'),
                    'role': None,
                })
    for line in lines:
        line['anchors'] = [anchor for anchor in line['anchors'] if anchor]
    return [line for line in lines if line['text'] and line['anchors']]


def _summary(cv):
    for section in cv.get('sections', []):
        if section.get('name') == 'PROFESSIONAL SUMMARY' and section.get('items'):
            item = section['items'][0]
            return item.get('text', '').strip(), (
                item.get('anchors') or [item.get('anchor')])
    raise ValueError('cover letter requires the governed professional summary')


def _classifications(m):
    return {row.get('n'): row.get('match') for row in m.get('requirements', [])}


def _pick_evidence(cv, m):
    classes = _classifications(m)
    weights = {'DIRECT': 7, 'TRANSFERABLE': 4, 'PARTIAL': 2, 'GAP': 0}
    scored = []
    for line in _visible_lines(cv):
        served = sorted(set(line['serves']))
        score = sum(weights.get(classes.get(number), 0) for number in served)
        score += min(len(re.findall(r'\b\d+(?:[.+%]|\b)', line['text'])), 2)
        if line['section'] == 'CAREER HIGHLIGHTS & RECOGNITION':
            score += 2
        scored.append((score, line))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1]['text'])))

    selected = []
    roles = set()
    for _, line in scored:
        if any(vec.cosine(line['text'], prior['text']) >= 0.64 for prior in selected):
            continue
        role = line.get('role')
        if role and role in roles and len(selected) >= 2:
            continue
        selected.append(line)
        if role:
            roles.add(role)
        if len(selected) == MAX_EVIDENCE_LINES:
            break
    if len(selected) < 2:
        raise ValueError('cover letter needs at least two distinct visible evidence lines')
    return selected


def assemble(jd, m, cv):
    """Build a concise letter from the exact CV plan and its JD mapping."""
    summary, summary_anchors = _summary(cv)
    evidence = _pick_evidence(cv, m)
    company = str(jd.get('company') or '').strip()
    role = str(jd.get('title') or '').strip()
    if not company or not role:
        raise ValueError('cover letter requires the recorded company and full job title')

    paragraphs = [
        {'kind': 'salutation', 'text': 'Dear Hiring Manager,'},
        {
            'kind': 'evidence',
            'text': (f'I am applying for the {role} position with {company}. '
                     + _summary_first_person(summary)),
            'anchors': [anchor for anchor in summary_anchors if anchor],
            'source_texts': [summary],
        },
        {
            'kind': 'evidence',
            'text': ('The most relevant evidence I offer is practical and customer-side. '
                     + ' '.join(_first_person(line['text']).rstrip('.') + '.'
                                for line in evidence[:2])),
            'anchors': sorted({anchor for line in evidence[:2] for anchor in line['anchors']}),
            'source_texts': [line['text'] for line in evidence[:2]],
        },
    ]
    if len(evidence) > 2:
        paragraphs.append({
            'kind': 'evidence',
            'text': (_first_person(evidence[2]['text']).rstrip('.') + '. '
                     f'I would bring this evidence-led approach to {company} and adapt it '
                     'to its specific engineering, customer and regulatory environment.'),
            'anchors': evidence[2]['anchors'],
            'source_texts': [evidence[2]['text']],
        })
    paragraphs += [
        {
            'kind': 'closing',
            'text': ('I would welcome the opportunity to discuss how this experience can '
                     f'support the {role} responsibilities.'),
        },
        {'kind': 'signoff', 'text': f"Yours sincerely,\n{cv.get('header', {}).get('name', '')}"},
    ]
    letter = {
        '_schema': 'joblooper.cover-letter.v1',
        'job': jd.get('_slug') or cv.get('job'),
        'company': company, 'role': role,
        'language': cv.get('language', 'en-US'),
        'generated': store.now(),
        'header': cv.get('header', {}),
        'subject': f'Application for {role}',
        'paragraphs': paragraphs,
        'selected_evidence': evidence,
        'cv_sha256': store.sha256_text(store.canonical_json(cv)),
        '_inputs': cv.get('_inputs'),
    }
    problems = validate(letter, jd, cv)
    if problems:
        raise ValueError('invalid cover-letter plan: ' + '; '.join(problems))
    return letter


def validate(letter, jd, cv):
    problems = []
    if letter.get('company') != jd.get('company') or letter.get('role') != jd.get('title'):
        problems.append('company or role differs from the captured JD')
    if letter.get('cv_sha256') != store.sha256_text(store.canonical_json(cv)):
        problems.append('letter is stale relative to the CV plan')
    visible = {line['text'] for line in _visible_lines(cv)}
    summary, _ = _summary(cv)
    visible.add(summary)
    selected_ids = set((cv.get('_selection') or {}).get('selected_ids') or [])
    for paragraph in letter.get('paragraphs', []):
        if paragraph.get('kind') != 'evidence':
            continue
        if not paragraph.get('anchors'):
            problems.append('an evidence paragraph has no anchor citations')
        missing = [text for text in paragraph.get('source_texts') or [] if text not in visible]
        if missing:
            problems.append('an evidence paragraph contains text absent from the CV plan')
        unknown = [anchor for anchor in paragraph.get('anchors') or []
                   if anchor not in selected_ids]
        if unknown:
            problems.append('letter cites evidence not visible in the approved CV: '
                            + ', '.join(unknown))
    words = len(' '.join(p.get('text', '') for p in letter.get('paragraphs', [])).split())
    if words > MAX_WORDS:
        problems.append(f'letter is {words} words; maximum is {MAX_WORDS}')
    if words < MIN_WORDS:
        problems.append(f'letter is {words} words; minimum is {MIN_WORDS}')
    return problems


def to_markdown(letter):
    h = letter.get('header') or {}
    contact = [x for x in h.get('contact', []) if x]
    out = [f"# {h.get('name', '')}", '', ' | '.join(contact), '',
           f"**{letter.get('subject', '')}**", '']
    for paragraph in letter.get('paragraphs', []):
        text = paragraph.get('text', '')
        if paragraph.get('kind') == 'signoff':
            out.extend(text.split('\n'))
        else:
            out.append(text)
        out.append('')
    return '\n'.join(out).strip()


def to_render_document(letter):
    """Adapt the letter to the existing single-column ATS-safe renderer."""
    items = []
    for paragraph in letter.get('paragraphs', []):
        parts = (paragraph.get('text', '').splitlines()
                 if paragraph.get('kind') == 'signoff'
                 else [paragraph.get('text', '')])
        items.extend({'text': part} for part in parts if part)
    return {
        'document_kind': 'Cover Letter',
        'language': letter.get('language', 'en-US'),
        'header': {
            **(letter.get('header') or {}),
            'headline': letter.get('subject', ''),
        },
        'sections': [{
            'name': 'COVER LETTER', 'type': 'para',
            'items': items,
        }],
    }
