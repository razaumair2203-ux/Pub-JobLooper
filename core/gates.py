"""Executable guardrails G1-G8.

These are the checks that are cheap, repeatable and mechanical. Gates 9-14 of
the release protocol (relevance, specificity, contradiction, bloat, ATS
translation, hostile review) stay with the model -- they cannot be regexed, and
pretending otherwise would be theatre.

BLOCK  -> the build stops, exit code 1.
WARN   -> surfaced in the audit and in PREVIEW.md, build continues.

ZONES
-----
Not every line in a CV is the same kind of thing, and treating them alike is how
gates fail open. Each flattened line carries a zone:

  claim     bullet and paragraph text -- a factual assertion. All gates apply.
  headline  the professional headline. Asserts seniority and credentials, so
            traceability, ownership, status, metric and boundary checks apply.
  meta      name, contact, links, section labels, role title/org/period.
            Structural text, not a claim -- but it can still carry a forbidden
            string, so the boundary scan applies here too.

Everything that reaches a rendered document must appear in exactly one zone.
A field the renderer emits but this module cannot see is a gate bypass, not an
oversight -- see verify_rendered() for the backstop.
"""
import os, re
from . import disclosure, store, vec

BLOCK, WARN, PASS = 'BLOCK', 'WARN', 'PASS'
REDUNDANCY_THRESHOLD = 0.68
# Recruiters skim. Past roughly this length a bullet is skipped, not read.
MAX_BULLET_WORDS = 34
# Calibrated against actual rendered output at Arial 10pt with 0.5in margins.
# The count includes every visible word: headings and role metadata occupy page
# space even though they are not factual claims.
WORDS_PER_PAGE = 505

CLAIM, HEADLINE, META = 'claim', 'headline', 'meta'


def _ids(item):
    """An item may draw on several anchors -- a summary paragraph legitimately
    does. Returns the full list; single-anchor items return a one-element list."""
    ids = item.get('anchors') or []
    if item.get('anchor'):
        ids = [item['anchor']] + [i for i in ids if i != item['anchor']]
    return ids


def _line_records(cv, zones=None):
    """Flatten cv.json into line records with citations and requirement links.

    Covers EVERY field the renderers emit, not just bullet text. The header,
    link labels, section labels and role metadata all reach the document, so
    they must all be visible here or the gates guarding them are decorative.
    """
    out = []

    def add(section, text, ids, zone, serves=None):
        out.append({
            'section': section, 'text': text, 'ids': list(ids or []),
            'zone': zone, 'serves': sorted(set(serves or [])),
        })

    h = cv.get('header', {})
    header_ids = _ids(h)

    if h.get('name'):
        add('HEADER', h['name'], [], META)
    if h.get('headline'):
        add('HEADER', h['headline'], header_ids, HEADLINE, h.get('_serves'))
    for c in h.get('contact', []) or []:
        if c:
            add('HEADER', str(c), [], META)
    for label, url in (h.get('links') or {}).items():
        if url:
            add('HEADER', f'{label} {url}', [], META)

    for sec in cv.get('sections', []):
        name = sec.get('name', '')
        add('SECTION_LABEL', name, [], META)
        for item in sec.get('items', []):
            if not isinstance(item, dict):
                add(name, str(item), [], CLAIM)
                continue
            if sec.get('type') == 'experience':
                for f in ('title', 'org', 'period'):
                    if item.get(f):
                        add(name, item[f], _ids(item), META)
                if item.get('framing'):
                    add(name, item['framing'], _ids(item), CLAIM,
                        item.get('_serves'))
                for sub in item.get('bullets', []):
                    add(name, sub.get('text', ''), _ids(sub), CLAIM,
                        sub.get('_serves'))
            else:
                add(name, item.get('text', ''), _ids(item), CLAIM,
                    item.get('_serves'))
                for sub in item.get('bullets', []):
                    add(name, sub.get('text', ''), _ids(sub), CLAIM,
                        sub.get('_serves'))

    if zones:
        out = [line for line in out if line['zone'] in zones]
    return out


def _lines(cv, zones=None):
    """Compatibility tuple view used by the deterministic gates."""
    return [(line['section'], line['text'], line['ids'], line['zone'])
            for line in _line_records(cv, zones)]


# ---------------------------------------------------------------- gates

def g1_traceability(cv, by_id, bnd=None):
    """Every factual line is semantically supported by its exact citations."""
    bad = []
    for sec, text, ids, _ in _lines(cv, {CLAIM, HEADLINE}):
        if not text.strip():
            continue
        unknown = [a for a in ids if a not in by_id]
        if not ids:
            bad.append(f"{sec}: no anchor citations for {text[:64]!r}")
            continue
        if unknown:
            bad.append(f"{sec}: unknown anchor(s) {', '.join(unknown[:4])}")
            continue
        evidence = []
        for anchor_id in ids:
            record = by_id[anchor_id]
            surface = vec.record_surface(record)
            external = disclosure.externalize(surface, bnd) if bnd else surface
            if external != surface:
                record = {'fact': surface + ' ' + external}
            evidence.append(record)
        coverage = vec.token_coverage(text, evidence)
        if coverage < 0.72:
            bad.append(f"{sec}: only {coverage:.0%} of claim tokens supported by "
                       f"{','.join(ids[:3])}: {text[:64]}")
    if bad:
        return BLOCK, f"{len(bad)} unsupported/untraceable line(s)", bad[:8]
    return PASS, 'all factual lines supported by their cited anchors', []


def g2_ownership(cv, by_id, bnd):
    """A CV verb may sit at or below the ownership of an anchor that ACTUALLY
    SUPPORTS that verb.

    Taking the maximum level across all cited anchors is not sufficient: it lets
    a weak claim inherit a strong anchor's cap simply by citing it alongside.
    ("Owned the export growth programme" [DEV-004=supported] blocks; add
    EDU-001=owned to the same line and it passed.) So for each verb found, at
    least one cited anchor must both permit that level AND contain that claim in
    its own recorded text.
    """
    ladder = bnd['ownership_ladder']
    verbs = bnd['ownership_verbs']
    fails = []

    for sec, text, ids, zone in _lines(cv, {CLAIM, HEADLINE}):
        recs = [by_id[a] for a in ids if a in by_id]
        if not recs:
            continue
        low = text.lower()
        cap = max((ladder.index(r['ownership']) for r in recs
                   if r.get('ownership') in ladder), default=-1)
        if cap < 0:
            continue

        for level, vlist in verbs.items():
            li = ladder.index(level)
            if li <= cap:
                continue
            for v in vlist:
                if not re.search(r'\b' + re.escape(v), low):
                    continue
                fails.append(f"{','.join(ids[:2])}: '{v}' claims {level}, "
                             f"highest supporting anchor is {ladder[cap]}")
                break

        # Composite positioning records can contain clauses with different
        # ownership levels. A claim cap requires the bounded clause to carry
        # its own verb, so a nearby stronger verb cannot silently upgrade it.
        for record in recs:
            for constraint in record.get('claim_caps') or []:
                pattern = str(constraint.get('pattern') or '').lower().strip()
                maximum = constraint.get('max')
                if not pattern or pattern not in low or maximum not in ladder:
                    continue
                before = low[:low.index(pattern)][-48:]
                grounded = any(re.search(r'\b' + re.escape(v), before)
                               for v in verbs.get(maximum, []))
                if not grounded:
                    fails.append(
                        f"{record['id']}: {pattern!r} must carry an explicit "
                        f"{maximum}-level verb")

        # Verb traceability: a permitted verb must be grounded in the specific
        # anchor that permits it, not merely co-cited with one.
        for level, vlist in verbs.items():
            li = ladder.index(level)
            if li > cap or li == 0:
                continue
            for v in vlist:
                if not re.search(r'\b' + re.escape(v), low):
                    continue
                # Match on a 5-character stem so inflections count: "coordinated"
                # grounds against "coordination", "architected" against
                # "Architected". Dropping a single trailing character (the
                # earlier approach) turned "led" into "le", which matched
                # "level" and "leverage" and grounded almost anything.
                stem = re.escape(v.split()[0][:5])
                grounded = any(
                    ladder.index(r['ownership']) >= li
                    and re.search(r'\b' + stem,
                                  ((r.get('fact') or '') + ' ' +
                                   ' '.join((r.get('bullet') or {}).values())).lower())
                    for r in recs if r.get('ownership') in ladder)
                if not grounded:
                    supporting = [r['id'] for r in recs
                                  if r.get('ownership') in ladder
                                  and ladder.index(r['ownership']) >= li]
                    fails.append(
                        f"{','.join(ids[:2])}: '{v}' ({level}) is not grounded in any cited "
                        f"anchor's own wording; {supporting or 'none'} permit the level but "
                        f"do not make the claim")
                break

    if fails:
        return BLOCK, f"{len(fails)} ownership problem(s)", sorted(set(fails))[:6]
    return PASS, 'no ownership upgrades', []


# "certification" and "accepted" are ordinary aerospace nouns as well as
# credential/publication status words. "Qualification and certification
# activities" is aircraft certification; "accepted the drawing set" is
# acceptance testing. Firing on those is a false positive that pushes real work
# off the CV, so the personal-claim sense has to be distinguished from the
# engineering sense.
_CERT_DOMAIN = re.compile(
    r'certification\s+(activit|requirement|basis|process|plan|evidence|standard|'
    r'authority|framework|programme|program|campaign|task)'
    r'|(aircraft|system|type|design|equipment|airworthiness|initial|product)\s+certification'
    # Certifying OTHERS is not a personal credential claim. "Mentored 400+
    # professionals to Systems Engineering certification" is a teaching
    # achievement; blocking it kept the single most JD-relevant fact off a
    # capability-development role.
    r'|\b(mentor|train|coach|supervis|prepar|taught|teach)\w*\b[^.]{0,70}certification'
    r'|\bto\s+[\w\s-]{0,40}certification',
    re.I)
_PUB_CONTEXT = re.compile(
    r'\b(paper|manuscript|publication|journal|conference|ieee|xplore|abstract|preprint)\b', re.I)


def g3_status(cv, by_id, bnd):
    """Status words must match the source anchors' recorded status."""
    fails = []
    pat = re.compile(r'\b(certified|certification|published|accepted|awarded|licen[cs]ed)\b', re.I)
    for sec, text, ids, zone in _lines(cv, {CLAIM, HEADLINE}):
        recs = [by_id[a] for a in ids if a in by_id]
        words = set(w.lower() for w in pat.findall(text))
        # Drop the engineering senses before judging credential status.
        if 'certification' in words and _CERT_DOMAIN.search(text):
            words.discard('certification')
        if 'accepted' in words and not _PUB_CONTEXT.search(text):
            words.discard('accepted')
        if not words:
            continue
        if not recs:
            for w in words:
                fails.append(f"{sec}: '{w}' has no cited evidence")
            continue
        sts = {(r.get('status') or '').upper() for r in recs}
        types = {r.get('type') for r in recs}
        for word in words:
            base = word.rstrip('d').rstrip('e')
            if base.startswith('publish') and 'PUBLISHED' not in sts:
                fails.append(f"{ids[0]}: says '{word}' but status is {'/'.join(sts)}")
            elif base.startswith('certif') and 'credential' not in types:
                fails.append(f"{ids[0]}: says '{word}' but no source anchor is a credential")
            elif base.startswith('certif'):
                creds = [r for r in recs if r.get('type') == 'credential']
                if max((vec.token_coverage(text, [r]) for r in creds), default=0) < 0.45:
                    fails.append(f"{ids[0]}: certification subject is not supported by the cited credential")
            elif base.startswith('accept') and not (sts & {'PUBLISHED', 'ACCEPTED'}):
                fails.append(f"{ids[0]}: says '{word}' but status is {'/'.join(sts)}")
    if fails:
        return BLOCK, f"{len(fails)} status inflation(s)", fails[:6]
    return PASS, 'no status inflation', []


# A digit belongs to a designator only when it is bound tightly to letters --
# Orion-X, Falcon-R, B1.1, A320. An earlier version allowed an optional SPACE here,
# which made "Delivered 999999 systems" look like a designator and silently
# disabled this gate for ordinary prose. Space-separated designators are handled
# by the explicit all-caps rule below, not by a general allowance.
_DESIGNATOR_TIGHT = re.compile(r'[A-Za-z][-–—/.]?$')
# An all-caps standards prefix, optionally followed by an already-consumed run of
# numbers and separators: covers "ISO 9001" and every entry in a slash list like
# "ISO 9001/21001/29997". Anchored on the caps token, so ordinary prose gains
# nothing -- "Delivered 999999" has no such prefix and still blocks.
_DESIGNATOR_CAPS = re.compile(r'\b[A-Z]{2,}[ ][\d,./–—-]*$')

# Sections whose numbers are inherently dates, titles or identifiers rather than
# asserted outcomes. Matched on the FULL section name -- matching on the first
# word wrongly exempted an entire achievements heading.
_METRIC_EXEMPT_SECTIONS = {
    'EDUCATION',
    'CERTIFICATIONS & PROFESSIONAL DEVELOPMENT',
    'RESEARCH & PUBLICATIONS',
    'SELECTED RECOGNITION',
}


def g4_metrics(cv, by_id):
    """Every number must exist in the anchors cited by that exact line."""
    fails = []
    num = re.compile(r'\d[\d,.]*')
    for sec, text, ids, zone in _lines(cv, {CLAIM, HEADLINE}):
        records = [by_id[a] for a in ids if a in by_id]
        surfaces = ' '.join(vec.record_surface(r) for r in records)
        allowed = {re.sub(r'[^0-9.]', '', x).rstrip('.')
                   for x in re.findall(r'\d[\d,.]*', surfaces)}
        for r in records:
            for m in r.get('metrics', []):
                allowed.add(re.sub(r'[^0-9.]', '', str(m.get('n', ''))).rstrip('.'))
            # A cited record may carry its own career-stage period. This allows
            # chronological labels without granting a global date exemption.
            for date in r.get('period') or []:
                if date:
                    allowed.update(re.findall(r'\d{4}', str(date)))
        allowed.discard('')
        for mt in num.finditer(text):
            tok = mt.group(0).rstrip('.')
            clean = re.sub(r'[^0-9.]', '', tok).rstrip('.')
            if not clean:
                continue
            if clean in allowed:
                continue
            fails.append(f"{ids[0] if ids else sec}: number '{tok}' is absent from cited anchors "
                         f"in \"{text[:55]}...\"")
    if fails:
        return BLOCK, f"{len(fails)} unsourced number(s)", fails[:6]
    return PASS, 'all numbers sourced', []


def g5_boundaries(cv, bnd):
    """Forbidden-pattern scan across EVERY zone.

    Runs over header, links, section labels and role metadata as well as claims.
    A forbidden credential in the headline is exactly as damaging as one in a
    bullet, and for a while this gate could not see it.
    """
    lines = _lines(cv)
    blob = '\n'.join(t for _, t, _, _ in lines)
    fails = []
    for rule in bnd.get('forbidden_patterns', []):
        m = re.search(rule['pattern'], blob)
        if m:
            where = next((s for s, t, _, _ in lines if m.group(0) in t), '?')
            fails.append(f"[{where}] '{m.group(0)}' -> {rule['reason']}")
    for pattern in bnd.get('sensitive_content_patterns', []):
        m = re.search(pattern, blob)
        if m:
            where = next((s for s, t, _, _ in lines if m.group(0) in t), '?')
            fails.append(f"[{where}] '{m.group(0)}' -> sensitive identity data")
    for rule in (bnd.get('disclosure') or {}).get('restricted_patterns', []):
        m = re.search(rule['pattern'], blob)
        if m:
            where = next((s for s, t, _, _ in lines if m.group(0) in t), '?')
            fails.append(f"[{where}] '{m.group(0)}' -> {rule['reason']}")
    for term in bnd.get('person_identity', {}).get('excluded_domains', []):
        m = re.search(r'\b' + re.escape(term) + r'\b', blob, re.I)
        if m:
            where = next((s for s, t, _, _ in lines
                          if re.search(r'\b' + re.escape(term) + r'\b', t, re.I)), '?')
            fails.append(f"[{where}] '{term}' -> person-identity boundary (Dr. Sibgha Saliha)")
    if fails:
        return BLOCK, f"{len(fails)} boundary violation(s)", fails[:8]
    return PASS, 'no boundary violations', []


def g6_duplication(cv):
    """Semantic duplicate bullets. A repeat of the SAME anchor is a build defect
    and blocks; two different anchors saying the same thing is a judgment call."""
    all_items = [(s, t, ids) for s, t, ids, z in _lines(cv, {CLAIM})
                 if len(t.split()) > 6]
    primary_counts = {}
    for _, _, ids in all_items:
        if ids:
            primary_counts[ids[0]] = primary_counts.get(ids[0], 0) + 1
    repeats = [f"anchor {anchor} rendered twice — build defect"
               for anchor, count in primary_counts.items() if count > 1]

    # Credential and education lines are labels/inventories, not claims that a
    # task was performed. Comparing them with experience prose creates false
    # warnings such as a Systems Engineering course versus mentoring engineers.
    # Primary-anchor repetition above still protects these sections.
    inventory_sections = {s.get('name') for s in store.sections().get('sections', [])
                          if s.get('source') in {'credential', 'education'}}
    items = [item for item in all_items if item[0] not in inventory_sections]
    dups = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            c = vec.cosine(items[i][1], items[j][1])
            if c < REDUNDANCY_THRESHOLD:
                continue
            a, b = items[i][2], items[j][2]
            if a and b and a[0] == b[0]:
                continue
            dups.append(f"{c}: [{a[0] if a else '?'}] {items[i][1][:42]}… == "
                        f"[{b[0] if b else '?'}] {items[j][1][:42]}…")
    detail = sorted(set(repeats)) + dups
    if detail:
        return (BLOCK if repeats else WARN), \
               f"{len(set(repeats))} repeat(s), {len(dups)} near-duplicate pair(s)", detail[:6]
    return PASS, 'no semantic duplicates', []


def g7_coverage(m, cv=None):
    """Hard gates are binary; supporting evidence must actually be visible.

    Coverage used to describe the truth corpus, not the generated document. A
    requirement could therefore be DIRECT while every supporting anchor was
    removed by selection. When a CV is supplied, verify the last mile too.
    """
    gaps = m.get('gaps', [])
    hard = m.get('hard_gate_unresolved', m.get('hard_gate_gaps', []))
    mandatory = m.get('mandatory_risks', [])
    invisible = []
    if cv is not None:
        visible_lines = _line_records(cv, {CLAIM, HEADLINE})
        for requirement in m.get('requirements', []):
            if requirement.get('match') != 'DIRECT':
                continue
            number = requirement.get('n')
            support_ids = {
                aid for aid, numbers in (m.get('anchor_usage') or {}).items()
                if number in (numbers or [])
            }
            support_ids.update(a.get('id') for a in requirement.get('anchors', [])
                               if a.get('id'))
            supported_line = any(
                number in line['serves']
                and bool(set(line['ids']) & support_ids)
                and bool(str(line['text']).strip())
                for line in visible_lines)
            if not supported_line:
                invisible.append(requirement)

    invisible_hard = [r for r in invisible
                      if r.get('hard_gate') or r.get('kind') == 'mandatory']
    if hard or invisible_hard:
        detail = [f"#{g['n']} [HARD/{g.get('match', 'GAP')}] {g['text'][:70]}"
                  for g in hard]
        detail += [f"#{g['n']} [DIRECT but not visible] {g['text'][:70]}"
                   for g in invisible_hard]
        return BLOCK, (f"{len(hard)} unresolved hard gate(s); "
                       f"{len(invisible_hard)} DIRECT mandatory item(s) not visible"), detail
    if mandatory:
        return WARN, f"{len(mandatory)} mandatory requirement(s) not directly evidenced", [
            f"#{g['n']} [{g['match']}] {g['text'][:70]}" for g in mandatory[:6]]
    if gaps or invisible:
        detail = [f"#{g['n']} {g['text'][:70]}" for g in gaps[:6]]
        detail += [f"#{g['n']} [DIRECT but not visible] {g['text'][:70]}"
                   for g in invisible[:6 - len(detail)]]
        return WARN, (f"{len(gaps)} uncovered requirement(s); "
                      f"{len(invisible)} DIRECT item(s) not visible"), detail
    if any(r.get('kind') == 'mandatory' for r in m.get('requirements', [])):
        return PASS, 'all mandatory requirements directly evidenced and visible', []
    return PASS, 'all directly matched requirements are visible; no mandatory family supplied', []


# Characters that are simply not representable in XML 1.0. Their presence in a
# generated part produces a file no parser can read.
_XML_ILLEGAL = re.compile(r'[^\x09\x0A\x0D\x20-퟿-�]')


def g8_document(cv):
    """Length, link validity and XML-representability.

    XML-illegal characters BLOCK rather than warn: they do not degrade the
    document, they make it unparseable.
    """
    notes, level = [], PASS

    # Structural completeness is a truth issue, not a styling preference. A
    # missing protected section or employment period can materially mislead a
    # reader even when every remaining sentence is individually true.
    spec = store.sections()
    present = {s.get('name') for s in cv.get('sections', [])}
    identity = cv.get('identity')
    required = {s.get('name') for s in spec.get('sections', [])
                if s.get('protected') or identity in s.get('protected_if_lane', [])}
    missing_sections = sorted(x for x in required - present if x)
    if missing_sections:
        notes.append('missing protected section(s): ' + ', '.join(missing_sections))
        level = BLOCK

    _, truth = store.generation_anchors()
    expected_roles = {r['id'] for r in truth if r.get('type') == 'role'
                      and r.get('kind') not in ('umbrella', 'education_period')}
    experience = [s for s in cv.get('sections', []) if s.get('type') == 'experience']
    shown_roles = {i.get('anchor') for s in experience for i in s.get('items', [])}
    missing_roles = sorted(expected_roles - shown_roles)
    if missing_roles:
        notes.append('employment chronology omits role(s): ' + ', '.join(missing_roles))
        level = BLOCK
    empty_roles = [i.get('anchor', '?') for s in experience for i in s.get('items', [])
                   if not i.get('bullets')]
    if empty_roles:
        notes.append('experience role(s) have no evidence bullets: ' + ', '.join(empty_roles))
        level = BLOCK

    # Summary length is a section contract, not a page-layout accident. Impact
    # remains a judgment gate; these deterministic bounds prevent both a slogan
    # and a dense biography from passing unnoticed.
    summary_spec = next((s for s in spec.get('sections', [])
                         if s.get('source') == 'positioning'), {})
    summary = next((s for s in cv.get('sections', [])
                    if s.get('name') == summary_spec.get('name')), None)
    summary_items = (summary or {}).get('items') or []
    if len(summary_items) != 1:
        notes.append('professional summary must contain exactly one paragraph')
        level = BLOCK
    else:
        summary_text = summary_items[0].get('text', '').strip()
        summary_words = len(summary_text.split())
        summary_sentences = len(re.findall(r'[.!?]+(?=\s|$)', summary_text)) or 1
        min_words = summary_spec.get('min_words', 1)
        max_words = summary_spec.get('max_words', 10**9)
        min_sentences = summary_spec.get('min_sentences', 1)
        max_sentences = summary_spec.get('max_sentences', 10**9)
        if not min_words <= summary_words <= max_words:
            notes.append(f'professional summary is {summary_words} words; contract is '
                         f'{min_words}-{max_words}')
            level = BLOCK
        if not min_sentences <= summary_sentences <= max_sentences:
            notes.append(f'professional summary is {summary_sentences} sentence(s); '
                         f'contract is {min_sentences}-{max_sentences}')
            level = BLOCK

    # A full-time study period may legitimately bridge employment roles, but
    # only if the visible degree line states that period. An audit-only role row
    # must not make an unexplained external chronology look complete.
    education_name = next((s.get('name') for s in spec.get('sections', [])
                           if s.get('source') == 'education'), None)
    education_items = next((s.get('items', []) for s in cv.get('sections', [])
                            if s.get('name') == education_name), [])
    for role in (r for r in truth if r.get('type') == 'role'
                 and r.get('kind') == 'education_period'):
        education_ids = {r['id'] for r in truth if r.get('type') == 'education'
                         and role['id'] in ((r.get('role_id') if isinstance(
                             r.get('role_id'), list) else [r.get('role_id')]) or [])}
        visible = next((item for item in education_items
                        if ({item.get('anchor')} | set(item.get('anchors') or []))
                        & education_ids), None)
        years = [str(value)[:4] for value in (role.get('period') or []) if value]
        if not visible or any(year not in visible.get('text', '') for year in years):
            notes.append(f"education chronology for {role['id']} must show "
                         f"{'-'.join(years)}")
            level = BLOCK

    # The governed career story is mandatory, not a ranked project pool.
    # Supporting anchors may be co-cited on the same line and therefore need
    # not repeat in experience.
    featured = {r['id'] for r in truth
                if r.get('placement') == 'highlights'
                and (identity in r.get('identity', []) or '*' in r.get('identity', []))}
    selected = {a for _, _, ids, _ in _lines(cv) for a in ids}
    missing_featured = sorted(featured - selected)
    if missing_featured:
        notes.append('career highlight omitted: ' + ', '.join(missing_featured))
        level = BLOCK
    section_by_source = {section.get('source'): section
                         for section in spec.get('sections', [])}
    credential_spec = section_by_source.get('credential') or {}
    education_spec = section_by_source.get('education') or {}
    publication_spec = section_by_source.get('publication') or {}
    lane = (spec.get('lanes') or {}).get(identity, {})
    protected_ids = set()
    if education_spec.get('retention') == 'all_eligible':
        protected_ids.update(row['id'] for row in truth
                             if row.get('type') == 'education' and not row.get('render'))
    protected_tiers = set(credential_spec.get('protected_tiers') or [])
    protected_ids.update(row['id'] for row in truth
                         if row.get('type') == 'credential'
                         and row.get('tier') in protected_tiers and not row.get('render'))
    research_included = publication_spec.get('id') not in lane.get('drop', []) and (
        publication_spec.get('name') in present
        or identity in ((publication_spec.get('include_if') or {}).get('lane') or []))
    if publication_spec.get('retention') == 'all_eligible' and research_included:
        protected_ids.update(row['id'] for row in truth
                             if row.get('type') == 'publication'
                             and row.get('status') == 'PUBLISHED' and not row.get('render'))
    missing_inventory = sorted(protected_ids - selected)
    if missing_inventory:
        notes.append('protected candidate inventory omitted: '
                     + ', '.join(missing_inventory[:12]))
        level = BLOCK
    lines = _lines(cv)
    words = sum(len(t.split()) for _, t, _, _ in lines)
    pages = round(words / WORDS_PER_PAGE, 2)
    target = cv.get('target_pages', 2)
    selection_rules = spec.get('selection_guardrails') or {}
    minimum_fill = max(0.8, target * selection_rules.get('minimum_fill_ratio', 0.7))
    significant = (cv.get('_selection') or {}).get('significant_omissions') or []
    protected_omissions = [row.get('id') for row in
                           (cv.get('_selection') or {}).get('omitted', [])
                           if row.get('protected')]
    if protected_omissions and not missing_inventory:
        notes.append('protected candidate inventory omitted: '
                     + ', '.join(protected_omissions[:12]))
        level = BLOCK
    if pages > target + 0.35:
        notes.append(f"~{pages} pages vs {target} target -- will overflow")
        level = WARN if level == PASS else level
    elif pages < minimum_fill:
        notes.append(f"~{pages} pages vs {target} target -- looks thin")
        if significant:
            notes.append('material evidence remains omitted: '
                         + ', '.join(significant[:8]))
            level = BLOCK
        else:
            level = WARN if level == PASS else level

    for k, v in (cv.get('header', {}).get('links') or {}).items():
        if v in (None, '', 'None'):
            notes.append(f"link '{k}' is empty -- omitted from render")
            level = WARN

    para_sections = {sec['name'] for sec in cv.get('sections', [])
                     if sec.get('type') in ('para', 'band')}
    # A grouped credential line is an inventory, not prose: "A; B; C; D" scans
    # fine at any length. The rule protects readability of sentences.
    long_bullets = [(s, t) for s, t, _, z in lines
                    if z == CLAIM and s not in para_sections
                    and t.count(';') < 3
                    and len(t.split()) > MAX_BULLET_WORDS]
    if long_bullets:
        notes.append(f"{len(long_bullets)} bullet(s) over {MAX_BULLET_WORDS} words — "
                     f"a bullet doing this much stops being read")
        for s, t in long_bullets[:3]:
            notes.append(f"    {len(t.split())}w: {t[:64]}…")
        level = WARN if level == PASS else level

    for sec, text, _, _ in lines:
        bad = _XML_ILLEGAL.findall(text or '')
        if bad:
            notes.append(f"{sec}: XML-illegal character {bad[0]!r} — "
                         f"would produce an unreadable document")
            level = BLOCK
    return level, f"~{pages} pages / {words} words", notes


# ---------------------------------------------------------------- runner

def run_all(cv, m=None):
    by_id, _ = store.anchors()
    bnd = store.boundaries()
    results = [
        ('G1', 'TRACEABILITY',   *g1_traceability(cv, by_id, bnd)),
        ('G2', 'OWNERSHIP_VERB', *g2_ownership(cv, by_id, bnd)),
        ('G3', 'STATUS',         *g3_status(cv, by_id, bnd)),
        ('G4', 'METRIC',         *g4_metrics(cv, by_id)),
        ('G5', 'BOUNDARY',       *g5_boundaries(cv, bnd)),
        ('G6', 'DUPLICATION',    *g6_duplication(cv)),
        ('G8', 'DOCUMENT',       *g8_document(cv)),
    ]
    if m is not None:
        results.insert(6, ('G7', 'COVERAGE', *g7_coverage(m, cv)))
    blocked = [r for r in results if r[2] == BLOCK]
    return results, blocked


def verify_rendered(docx_path, cv=None, pdf_path=None):
    """Post-render backstop: re-check the ACTUAL document.

    Every gate above reasons about cv.json. This one reasons about the file that
    will be sent to an employer -- it extracts the text back out of the built
    package and re-runs the boundary scan, and parses every XML part.

    If a future renderer change emits a field the line model does not cover,
    this catches it. Structural gate coverage is a claim about code; this is a
    measurement of output.
    """
    import zipfile
    from xml.etree import ElementTree as ET
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    problems = []

    def norm(value):
        value = re.sub(r'^[-•]\s*', '', str(value or '').strip())
        value = re.sub(r'[–—]', '-', value)
        return re.sub(r'\s+', ' ', value).casefold()
    try:
        with zipfile.ZipFile(docx_path) as z:
            names = z.namelist()
            for n in names:
                if not n.endswith('.xml') and not n.endswith('.rels'):
                    continue
                try:
                    ET.fromstring(z.read(n))
                except Exception as e:
                    problems.append(f"{n} is not well-formed XML: {str(e)[:80]}")
            ct = z.read('[Content_Types].xml').decode('utf-8', 'replace')
            for part in names:
                if part.endswith('.xml') and part != '[Content_Types].xml':
                    if '/' + part not in ct and not part.startswith('docProps'):
                        problems.append(f"{part} present but not declared in [Content_Types].xml")
            try:
                root = ET.fromstring(z.read('word/document.xml'))
                paragraphs = [''.join(t.text or '' for t in p.iter(W + 't'))
                              for p in root.iter(W + 'p')]
                text = '\n'.join(paragraphs)
                # ATS template contract: one linear text flow. These OOXML
                # constructs commonly reorder or hide content from parsers.
                forbidden = {
                    'table': W + 'tbl', 'text box': W + 'txbxContent',
                    'floating drawing': W + 'drawing', 'legacy picture': W + 'pict',
                }
                for label, tag in forbidden.items():
                    if any(True for _ in root.iter(tag)):
                        problems.append(f'ATS template contains a {label}')
                if any(name.startswith('word/header') or name.startswith('word/footer')
                       for name in names):
                    problems.append('ATS template places content in a header or footer part')
            except Exception:
                paragraphs = []
                text = ''
            rels = z.read('word/_rels/document.xml.rels').decode('utf-8', 'replace')
            for rid in re.findall(r'r:id="(rId\d+)"', z.read('word/document.xml').decode('utf-8', 'replace')):
                if f'Id="{rid}"' not in rels:
                    problems.append(f"hyperlink {rid} has no matching relationship")
    except Exception as e:
        return BLOCK, f"cannot read rendered package: {str(e)[:80]}", []

    bnd = store.boundaries()
    for rule in bnd.get('forbidden_patterns', []):
        m = re.search(rule['pattern'], text)
        if m:
            problems.append(f"RENDERED DOCUMENT contains '{m.group(0)}' -> {rule['reason']}")
    for pattern in bnd.get('sensitive_content_patterns', []):
        m = re.search(pattern, text)
        if m:
            problems.append(f"RENDERED DOCUMENT contains sensitive identity data '{m.group(0)}'")
    for rule in (bnd.get('disclosure') or {}).get('restricted_patterns', []):
        m = re.search(rule['pattern'], text)
        if m:
            problems.append(f"RENDERED DOCUMENT contains '{m.group(0)}' -> {rule['reason']}")
    for term in bnd.get('person_identity', {}).get('excluded_domains', []):
        if re.search(r'\b' + re.escape(term) + r'\b', text, re.I):
            problems.append(f"RENDERED DOCUMENT contains '{term}' -> person-identity boundary")

    if cv is not None:
        from . import render
        expected = [norm(x) for x in render.to_ats_text(cv).splitlines() if norm(x)]
        actual = [norm(x) for x in paragraphs if norm(x)]
        missing = [x for x in expected if not any(x == y for y in actual)]
        extra = [y for y in actual if not any(y == x for x in expected)]
        if missing:
            problems.append(f"render parity: {len(missing)} expected line(s) missing; first={missing[0][:70]}")
        if extra:
            problems.append(f"render parity: {len(extra)} unexpected line(s); first={extra[0][:70]}")

    if pdf_path is not None:
        from . import pdftext, render
        if not os.path.exists(pdf_path):
            problems.append('PDF output is missing')
        else:
            try:
                with open(pdf_path, 'rb') as f:
                    magic = f.read(5)
                if magic != b'%PDF-':
                    problems.append('PDF output does not have a PDF signature')
                if not render.pdf_pages(pdf_path):
                    problems.append('PDF page count could not be determined')
                extracted, quality = pdftext.safe_extract(pdf_path)
                if extracted is None:
                    problems.append('PDF text extraction refused: ' + str(quality)[:140])
                elif cv is not None:
                    pdf_flat = norm(extracted)
                    expected_pdf = [norm(line) for line in render.to_ats_text(cv).splitlines()
                                    if len(norm(line).split()) >= 2]
                    missing_pdf = [line for line in expected_pdf if line not in pdf_flat]
                    if missing_pdf:
                        problems.append(
                            f'PDF text parity: {len(missing_pdf)} expected line(s) missing; '
                            f'first={missing_pdf[0][:70]}')
            except OSError as e:
                problems.append(f'PDF cannot be read: {e}')

    if problems:
        return BLOCK, f"{len(problems)} problem(s) in the rendered package", problems[:8]
    return PASS, f'rendered package verified ({len(text.split())} words extracted)', []


def fmt(results):
    out = []
    for gid, name, level, summary, detail in results:
        out.append(f"  [{level:5}] {gid} {name:16} {summary}")
        for d in detail:
            out.append(f"           - {d}")
    return '\n'.join(out)
