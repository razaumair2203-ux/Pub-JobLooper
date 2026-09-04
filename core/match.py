"""JD parsing, identity selection, requirement -> anchor mapping, coverage.

This is the module that decides WHAT goes in the CV. It never decides how the
CV is worded -- that stays with the model, which reads PREVIEW.md.
"""
import re
from . import store, vec

# Score bands for MATCH_CLASSIFICATION (gate 3 of the release protocol).
DIRECT, TRANSFERABLE, PARTIAL = 0.70, 0.55, 0.40

_BULLET = re.compile(r'^\s*(?:[-*•●▪‣⁃o]|\d+[.)])\s+')
_REQ_HINT = re.compile(
    r'\b(experience|degree|qualification|proficien|knowledge|familiar|skill|ability'
    r'|demonstrat|proven|track record|must|required|essential|minimum|preferred'
    r'|desirable|certification|certified|licen[cs]e|years?)\b', re.I)

_MANDATORY_HDR = re.compile(
    r'\b(requirements?|qualifications?|must have|essential|minimum|what you.{0,5}ll need'
    r'|who you are|about you|skills? (and|&) experience)\b', re.I)
_PREFERRED_HDR = re.compile(
    r'\b(preferred|desirable|desired characteristics?|nice to have|bonus|advantage|plus)\b', re.I)
# JOB ACCOUNTABILITIES are duties the postholder will perform, not evidence
# demanded of the applicant. Scoring them as requirements is a category error:
# in one advert it filled the coverage denominator with duties that
# were never asked of a candidate, and filled QUESTIONS FOR YOU with things
# nobody had requested. Ported from jobpilot-local's Requirement buckets.
_RESP_HDR = re.compile(
    r'\b(job accountabilit|accountabilit|responsibilit|key tasks?|duties'
    r'|what you.{0,5}ll (be )?do|role purpose|job purpose|scope of work'
    r'|main activities|principal (duties|accountabilities))',
    re.I)
_NOISE_HDR = re.compile(
    r'\b(benefit|we offer|perks|equal opportunit|diversity|about (us|the company)'
    r'|our (mission|values)|how to apply|salary|compensation package'
    r'|additional information)\b', re.I)


_GATE_SUBJECT = re.compile(
    r'(licen[cs]e|certif\w*|accredit\w*|degree|diploma|clearance|citizen\w*|nationalit\w*'
    r'|visa|permit|authoris\w*|authoriz\w*|eligib\w*|sponsor\w*|iqama|residenc\w*'
    r'|right to work|live and work|\d+\s*\+?\s*years?|fluen\w*|native|bilingual|type rat\w*)', re.I)

_GATE_FORCE = re.compile(
    r'\b(must|mandatory|essential|minimum|required|requires|non[- ]negotiable'
    r'|only candidates)\b', re.I)


# Requirements about legal status, location or language are facts about the
# person, not about their work history. Scoring them against experience anchors
# produces nonsense matches ("work authorisation" hitting an overseas-assignment
# bullet), so they are routed to profile.json instead.
_PROFILE_GATE = re.compile(
    r'\b(work (authoris|authoriz)\w*|right to work|visa|iqama|residenc\w*|permit'
    r'|citizen\w*|nationalit\w*|security clearance|eligible to work|sponsor\w*'
    r'|relocat\w*|based in|located in|live and work|willing\w* to travel'
    r'|travel globally|global travel|fluent|native speaker|bilingual'
    r'|arabic|english|language skills?)\b', re.I)


# Behavioural requirements are real but unfalsifiable from a CV -- every
# applicant asserts them and no anchor can evidence them. Counting them as
# uncovered can drag a strong match down dramatically, which is not honesty but
# noise. They are listed separately in PREVIEW and excluded from the coverage
# denominator.
_BEHAVIOURAL = re.compile(
    r'\b(interpersonal|communication skills?|team ?work\w*|collaborat\w*|'
    r'ability to communicate|influenc\w*|mediat\w*|facilitat\w*|'
    r'self[- ]motivat\w*|proactive|attention to detail|work independently|'
    r'flexible|adaptab\w*|enthusias\w*|can[- ]do|professional manner|'
    r'promote a? ?culture|dependable relationship)\b', re.I)


def _gate_type(body):
    if _PROFILE_GATE.search(body):
        return 'profile'
    if _BEHAVIOURAL.search(body):
        return 'behavioural'
    return 'evidence'


def _resolve_profile_gate(body, prof):
    """Answer a profile-class requirement from profile.json. Returns
    (classification, note). Anything uncertain returns PARTIAL, never DIRECT --
    an unverified legal-status claim is the most expensive kind to get wrong."""
    low = body.lower()
    loc = prof.get('location', {})
    wa = loc.get('work_authorisation', {})
    languages = prof.get('languages') or {}
    eligibility = prof.get('eligibility') or {}

    for language, assessment in languages.items():
        if re.search(rf'\b{re.escape(language.lower())}\b', low):
            return (assessment.get('classification', 'PARTIAL'),
                    assessment.get('note', f'{language} requires manual verification'))
    if re.search(r'\b(bilingual|native speaker|language skills?)\b', low):
        return 'PARTIAL', 'language requirement needs a named, verified profile entry'
    if re.search(r'\bsecurity clearance\b', low):
        clearance = eligibility.get('security_clearance') or {}
        return (clearance.get('classification', 'PARTIAL'),
                clearance.get('note', 'No named clearance is recorded'))
    if re.search(r'(work (authoris|authoriz)\w*|right to work|visa|iqama|permit'
                 r'|eligible to work|sponsor)', low):
        for rule in wa.get('requirement_rules') or []:
            if any(str(term).lower() in low for term in rule.get('terms') or []):
                return (rule.get('classification', 'PARTIAL'),
                        rule.get('note', 'work-authorisation detail requires verification'))
        return 'PARTIAL', f"Based in {loc.get('based_in','?')}; sponsorship likely required"
    if re.search(r'\b(willing\w* to travel|travel globally|global travel)\b', low):
        return ('DIRECT' if wa.get('mobility') else 'PARTIAL',
                ('Approved geographic mobility is recorded.' if wa.get('mobility')
                 else 'Global travel willingness is not recorded.'))
    if re.search(r'\blive and work\b', low):
        destination_rule = next((
            rule for rule in wa.get('display_rules') or []
            if any(str(term).lower() in low for term in rule.get('terms') or [])
        ), None)
        if wa.get('mobility') and destination_rule:
            return 'DIRECT', destination_rule.get(
                'phrasing', wa.get('phrasing_approved', 'Approved mobility is recorded.'))
        return ('DIRECT' if wa.get('mobility') else 'PARTIAL',
                wa.get('phrasing_approved', 'Mobility requires confirmation.'))
    if re.search(r'\b(relocat|based in|located in)\w*', low):
        return ('DIRECT' if wa.get('mobility') else 'PARTIAL',
                wa.get('phrasing_approved', ''))
    if re.search(r'citizen|nationalit', low):
        return 'PARTIAL', 'Nationality not recorded in profile — confirm before relying on this'
    return 'PARTIAL', 'profile-class requirement — verify manually'


def _is_hard_gate(body, kind='preferred'):
    """A requirement that cannot be argued around: credential, legal status,
    hard year-count, or language.

    Two ways to qualify:

    1. A forcing keyword LEADS or TRAILS the subject -- "Must hold a valid
       licence" and "AMOS experience is required" both count.
    2. The requirement sits in a MANDATORY section and names a gate subject.
       Job ads routinely list "Valid Part-66 B1 licence" as a bare bullet under
       a "Requirements" heading -- the heading IS the forcing word. Reading only
       the bullet body hid exactly the disqualifying credentials this exists to
       surface.

    Errs toward flagging: a false hard gate costs one line in the preview, a
    missed one costs a wasted application.
    """
    if kind == 'mandatory' and _GATE_SUBJECT.search(body):
        return True
    if not _GATE_FORCE.search(body):
        return False
    return bool(_GATE_SUBJECT.search(body)) or bool(
        re.search(r'\b(must|mandatory|is required|are required)\b', body, re.I))


def parse_jd(raw, title=None, company=None, url=None, job_reference=None):
    """Turn raw job-page text into structured requirements.

    Deliberately generous: it is far cheaper to over-extract and let the model
    prune in PREVIEW.md than to silently drop a mandatory requirement.
    """
    lines = [l.rstrip() for l in (raw or '').splitlines()]
    reqs, section, seq, noise = [], 'general', 0, False

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # Short, un-punctuated lines act as section headers.
        if len(s) < 80 and not s.endswith('.'):
            if _NOISE_HDR.search(s):
                noise = True
                continue
            if _RESP_HDR.search(s):
                section, noise = 'responsibility', False
                continue
            if _MANDATORY_HDR.search(s):
                section, noise = 'mandatory', False
                continue
            if _PREFERRED_HDR.search(s):
                section, noise = 'preferred', False
                continue
        if noise:
            continue

        is_bullet = bool(_BULLET.match(line))
        body = _BULLET.sub('', line).strip()
        if len(body) < 12:
            continue
        # URL extractors and manual copy/paste frequently preserve one list
        # item per line but lose the visual bullet marker. Once a recognised
        # duties/qualifications section has started, treat sentence-like lines
        # as requirements even when they do not contain a narrow hint word.
        # Short unpunctuated sub-headings still fail this condition unless they
        # carry an explicit requirement hint.
        in_requirement_section = section in {
            'responsibility', 'mandatory', 'preferred'}
        sentence_like = (len(s) >= 80 or s.endswith(('.', ';', ':')))
        if not (is_bullet or _REQ_HINT.search(body)
                or (in_requirement_section and sentence_like)):
            continue

        seq += 1
        kind = (section if section != 'general' else
                ('mandatory' if re.search(r'\b(must|required|essential|minimum)\b', body, re.I)
                 else 'preferred'))
        reqs.append({
            'n': seq,
            'text': body,
            'kind': kind,
            'hard_gate': _is_hard_gate(body, kind),
            'gate_type': _gate_type(body),
        })

    return {
        'title': title or '',
        'company': company or '',
        'url': url or '',
        'job_reference': str(job_reference or '').strip() or None,
        'ingested': store.now(),
        'requirements': reqs,
        'raw_chars': len(raw or ''),
    }


def pick_identity(jd, override=None):
    """Choose ONE primary identity. See SPEC section 5 -- this is the mechanism
    that stops an 18-year, five-lane career reading as 'generalist'."""
    al = store.aliases()
    boosts = al.get('boost_terms', {})
    text = ' '.join([jd.get('title', '')] * 3 +      # title counts triple
                    [r['text'] for r in jd.get('requirements', [])]).lower()

    # Word-boundary matching, NOT substring counting. `text.count("ai")` finds
    # "ai" inside aircraft, maintain and airworthiness, creating phantom hits
    # and handing a job to the wrong identity lane.
    # Short lane terms (ai, ml, cv, rf, qa, bi) make this failure systematic.
    known_identities = store.profile().get('identities') or {}
    if not known_identities:
        raise ValueError('candidate profile has no reviewed identity lanes')
    scores = {}
    for ident in known_identities:
        terms = boosts.get(ident, {})
        total = 0
        for t, w in terms.items():
            n = len(re.findall(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', text))
            total += w * n
        scores[ident] = total

    total = sum(scores.values()) or 1
    ranked = sorted(((k, round(v / total, 3)) for k, v in scores.items()),
                    key=lambda x: -x[1])
    if override and override not in known_identities:
        known = ', '.join(sorted(known_identities))
        raise ValueError(f"unknown identity {override!r}; choose one of: {known}")
    chosen = override or ranked[0][0]
    return {
        'primary': chosen,
        'ranked': ranked,
        'overridden': bool(override),
        'confidence': dict(ranked).get(chosen, 0.0),
    }


def _classify(score):
    if score >= DIRECT:
        return 'DIRECT'
    if score >= TRANSFERABLE:
        return 'TRANSFERABLE'
    if score >= PARTIAL:
        return 'PARTIAL'
    return 'GAP'


# How much of a requirement each class actually answers. Counting PARTIAL as
# fully covered is how a CV ends up looking like a 100% fit to its author and a
# 60% fit to the recruiter.
COVERAGE_WEIGHT = {'DIRECT': 1.0, 'TRANSFERABLE': 0.7, 'PARTIAL': 0.4,
                   'GAP': 0.0, 'BEHAVIOURAL': 0.0}

_FORBIDDEN_CACHE = None

# Words that look like proper nouns but are ordinary domain vocabulary, so their
# absence from an anchor says nothing.
_NOT_A_PRODUCT = {
    'aeronautical', 'engineering', 'electronics', 'avionics', 'avionic', 'aircraft',
    'systems', 'system', 'safety', 'quality', 'design', 'manufacturing', 'project',
    'programme', 'program', 'management', 'ability', 'experience', 'knowledge',
    'essential', 'desirable', 'strong', 'proven', 'working', 'awareness', 'kingdom',
    'engineer', 'engineers', 'directorate', 'authority', 'section', 'manager',
    'saudi', 'arabia', 'national', 'government', 'company', 'business', 'unit',
    'authorities', 'organisations', 'organizations', 'authority', 'drawing',
    'drawings', 'equipment', 'platforms', 'requirements', 'regulations',
}


def _employer_context(jd):
    """Proper nouns that name WHERE the job is, not WHAT it needs.

    Employer, customer and department names can be the setting of an advert.
    Treating each one as missing evidence can hide a real product gap in noise.
    """
    reqs = jd.get('requirements', []) or []
    ctx = set()
    for tok in re.findall(r"[A-Za-z]{2,}", jd.get('company', '') or ''):
        ctx.add(tok.lower())
    counts = {}
    for r in reqs:
        seen = {c.lower() for c in re.findall(r'\b([A-Z]{2,}|[A-Z][a-z]+)\b', r['text'])}
        for c in seen:
            counts[c] = counts.get(c, 0) + 1
    # A name the advert repeats across a third of its requirements is the
    # setting. A platform asked for once is a capability.
    thresh = max(2, len(reqs) // 3)
    for c, n in counts.items():
        if n >= thresh:
            ctx.add(c)
    return ctx


def _unmatched_proper_nouns(text, bm, ctx=()):
    """Named products/platforms in the requirement that appear in NO anchor.

    Catches ALL-CAPS tool names (AUTOCAD, CATIA, AMOS, SAP) and capitalised
    platform names (Falcon-X, Eagle-Y) that the corpus has never seen.
    """
    cands = set()
    # ALL-CAPS tool and system names: AUTOCAD, CATIA, AMOS, SAP, AGE.
    cands |= set(re.findall(r'\b([A-Z]{3,})\b', text))
    # Capitalised names inside a parenthetical or slash list -- the two places
    # job adverts actually name platforms: "(Falcon-X/Eagle-Y)",
    # "(AUTOCAD, CATIA etc.)". Anchoring here avoids treating every
    # sentence-initial capital as a missing product.
    for grp in re.findall(r'\(([^)]{3,80})\)', text) + re.findall(r'\b((?:[A-Z][a-z]+/){1,}[A-Z][a-z]+)\b', text):
        cands |= set(re.findall(r'\b([A-Z][A-Za-z0-9]{2,})\b', grp))

    out = []
    for c in cands:
        low = c.lower()
        # Repeated organisation names are normally the setting, not a
        # capability. Keep one only when the sentence ties that
        # exact name to specific knowledge or a named framework/platform/tool.
        named_capability = bool(re.search(
            rf'(?:knowledge|awareness|familiar|experience).{{0,35}}\b{re.escape(c)}\b|'
            rf'\b{re.escape(c)}\b.{{0,65}}(?:framework|standard|platform|product|tool)',
            text, re.I))
        if low in _NOT_A_PRODUCT or (low in ctx and not named_capability) or len(low) < 3:
            continue
        if bm.df.get(low, 0) == 0:
            out.append(c)
    return sorted(out)


def _forbidden_ask(text):
    """Is the JD asking for something the boundaries forbid claiming?

    A requirement for a Six Sigma BELT retrieves the Six Sigma COURSEWORK anchor
    at high similarity -- lexically almost identical, factually a different
    thing. Without this check the report reads DIRECT for a credential that is
    not held. The CV itself stays safe either way (G5 blocks the wording), but a
    coverage report that hides the gap is worse than useless.
    """
    global _FORBIDDEN_CACHE
    if _FORBIDDEN_CACHE is None:
        _FORBIDDEN_CACHE = [(re.compile(r['pattern']), r['reason'])
                            for r in store.boundaries().get('forbidden_patterns', [])]
    for pat, reason in _FORBIDDEN_CACHE:
        if pat.search(text):
            return reason
    return None


def _surface(rec):
    return vec.record_surface(rec).lower()


def _domain_candidates(text, scored, by_id):
    """Remove high-scoring lexical collisions from domain-specific asks."""
    low = text.lower()

    def keep(item):
        rec = by_id[item['id']]
        surface = _surface(rec)
        typ = rec.get('type')

        if re.search(r'\bdegree\b', low) and re.search(
                r'\b(aeronautical|aerospace|electrical|electronics?|avionics?)\b', low):
            return typ == 'education'

        # "Systems Engineering certification" (a personal credential) is not
        # "aircraft systems certification" (an airworthiness lifecycle).
        if re.search(r'\baircraft\b.{0,30}\bcertif', low) or re.search(
                r'\bcertif\w*\b.{0,35}\baircraft\b', low):
            return typ in {'anchor', 'skill'} and bool(re.search(
                r'\b(airworthiness|aircraft certification|qualification|clearance|'
                r'release to service|regulatory)\b', surface))

        if re.search(r'\b(indigenous capability|technology transfer|transfer of technology|'
                     r'locali[sz]ation|indigeni[sz]ation)\b', low):
            return bool(re.search(
                r'\b(indigenous|technology transfer|transfer of (production|technology)|'
                r'locali[sz]|indigeni[sz]|know-how)\b', surface))
        return True

    kept = [item for item in scored if keep(item)]
    if re.search(r'\bchange management\b', low):
        kept.sort(key=lambda item: (
            not (by_id[item['id']].get('metrics') and re.search(
                r'\b(configuration|baseline|modification|change control)\b',
                _surface(by_id[item['id']]))),
            by_id[item['id']].get('type') != 'anchor',
            -item['score'],
        ))
    return kept or scored


def _exact_classification(text, scored, by_id):
    """Deterministic rules for requirements whose semantics are not scalar.

    BM25 remains the recall engine.  These rules prevent known category errors
    and recognise complementary evidence where one record cannot contain every
    phrase in a requirement.
    """
    low = text.lower()
    recs = [by_id[x['id']] for x in scored]

    if re.search(r'\bdegree\b', low) and re.search(
            r'\b(aeronautical|aerospace|electrical|electronics?|avionics?)\b', low):
        direct = [r for r in recs if r.get('type') == 'education' and re.search(
            r'\b(be|beng|bachelor|degree)\b', _surface(r)) and re.search(
            r'\b(aeronautical|aerospace|electronics?|avionics?)\b', _surface(r))]
        if direct:
            exact_discipline = bool(re.search(
                r'\b(aeronautical|aerospace|electronics?|avionics?)\b', low)
                and re.search(
                    r'\b(aeronautical|aerospace|electronics?|avionics?)\b',
                    _surface(direct[0])))
            related_electrical = bool(
                re.search(r'\belectrical engineering\b', low)
                and re.search(r'\brelated (field|discipline)\b', low)
                and re.search(r'\b(electronics?|avionics?)\b', _surface(direct[0])))
            if exact_discipline or related_electrical:
                note = ('verified degree in the advert\'s accepted related discipline'
                        if related_electrical
                        else 'exact degree-and-discipline evidence')
                return 'DIRECT', note, direct[0]['id']

    if re.search(r'\baircraft\b.{0,35}\bcertif', low) or re.search(
            r'\bcertif\w*\b.{0,40}\baircraft\b', low):
        lifecycle = [r for r in recs if re.search(
            r'\b(airworthiness|qualification|aircraft clearance|release to service|'
            r'aircraft certification)\b', _surface(r))]
        regulation = [r for r in recs if re.search(
            r'\b(regulat|airworthiness|certification requirement)\b', _surface(r))]
        if lifecycle and regulation:
            return ('DIRECT', 'complementary aircraft-certification lifecycle and regulatory evidence',
                    lifecycle[0]['id'])

    if re.search(r'\bhazard analys\w*\b', low) and re.search(r'\bsafety cases?\b', low):
        direct = [r for r in recs if re.search(r'\bhazard analys\w*\b', _surface(r))
                  and re.search(r'\bsafety cases?\b', _surface(r))]
        if direct:
            return 'DIRECT', 'exact hazard-analysis and safety-case evidence', direct[0]['id']

    if re.search(r'\b(incident|accident|occurrence|crash)', low) and re.search(
            r'\b(defect|incident) reports?\b', low):
        direct = [r for r in recs if re.search(
            r'\b(incident|accident|occurrence|crash)\w*\b', _surface(r)) and re.search(
            r'\b(defect|incident) reports?\b', _surface(r))]
        if direct:
            return 'DIRECT', 'exact investigation and report-evaluation evidence', direct[0]['id']

    if re.search(r'\bmentor\w*\b|\blearning and development\b', low):
        direct = [r for r in recs if re.search(r'\bmentor\w*\b', _surface(r))
                  and re.search(r'\b(engineer|professional|systems engineering)\b',
                                _surface(r))]
        if direct:
            return 'DIRECT', 'exact professional mentoring and engineer-development evidence', direct[0]['id']
    return None, None, None


def match_jd(jd, identity):
    """Map every requirement to its best anchors and compute coverage.

    Returns per-requirement classification plus the anchors that answer it, so
    PREVIEW.md can show exactly which evidence serves which requirement.
    """
    bm, by_id = vec.anchor_index()
    prof = store.profile()
    primary = identity['primary']
    rows, used = [], {}

    ctx = _employer_context(jd)

    for r in jd.get('requirements', []):
        # Re-evaluate the route from current deterministic rules so a captured
        # JD benefits from corrected gate taxonomy without rewriting its source
        # record. The original parsed field remains preserved in the JD.
        gate_type = _gate_type(r['text'])
        if gate_type == 'profile':
            cls, note = _resolve_profile_gate(r['text'], prof)
            rows.append({**r, 'gate_type': gate_type,
                         'match': cls, 'best': 0.0, 'anchors': [],
                         'resolved_from': 'profile.json', 'note': note})
            continue

        if gate_type == 'behavioural':
            rows.append({**r, 'gate_type': gate_type,
                         'match': 'BEHAVIOURAL', 'best': 0.0, 'anchors': [],
                         'resolved_from': 'not evidence-based',
                         'note': 'asserted by every applicant; not scored'})
            continue

        # Retrieve wider than the displayed top four: domain filtering may
        # remove tempting lexical collisions before classification.
        hits = bm.normed(r['text'], top=12)
        scored = []
        for aid, sc in hits:
            a = by_id[aid]
            idents = a.get('identity', [])
            # Anchors in the chosen lane surface first; the other lanes stay
            # available as supporting evidence but never outrank it.
            if primary in idents:
                sc = min(1.0, sc * 1.15)
            elif '*' not in idents:
                sc *= 0.90
            if a.get('render') in ('never', 'blocked_pending_validation', 'superseded'):
                continue
            scored.append({'id': aid, 'score': round(sc, 3),
                           'status': a.get('status'), 'ownership': a.get('ownership')})
        scored.sort(key=lambda x: -x['score'])
        scored = _domain_candidates(r['text'], scored, by_id)[:4]
        best = scored[0]['score'] if scored else 0.0
        cls = _classify(best)

        note = None
        exact_cls, exact_note, exact_id = _exact_classification(r['text'], scored, by_id)
        if exact_cls:
            cls, note = exact_cls, exact_note
            if exact_id:
                scored.sort(key=lambda x: (x['id'] != exact_id, -x['score']))
                best = max(best, DIRECT)
        forbidden = _forbidden_ask(r['text'])
        if forbidden:
            cls, note = 'GAP', f"cannot be claimed: {forbidden}"

        # Named products and platforms are specific knowledge, not transferable
        # skill. "Working knowledge of Falcon-X/Eagle-Y" scored TRANSFERABLE
        # off generic aircraft/avionics overlap -- the dangerous direction, since
        # it hides a real gap behind a plausible number. If a requirement names
        # something no anchor has ever seen, it cannot be better than PARTIAL.
        unknown = _unmatched_proper_nouns(r['text'], bm, ctx)
        if unknown and cls in ('DIRECT', 'TRANSFERABLE'):
            cls = 'PARTIAL'
            note = (note + '; ' if note else '') + \
                   f"no evidence for {', '.join(unknown[:4])} — specific-platform gap"
        elif unknown:
            note = (note + '; ' if note else '') + f"unmatched: {', '.join(unknown[:4])}"

        for s in scored:
            if s['score'] >= PARTIAL and cls != 'GAP':
                used.setdefault(s['id'], []).append(r['n'])
        # A deterministic exact-rule match is authoritative even when generic
        # vector similarity falls below the broad PARTIAL threshold. Without
        # this, a weaker lexical neighbour can be marked visible while the
        # exact mentoring/safety/qualification evidence is omitted.
        if exact_id and cls != 'GAP':
            exact_usage = used.setdefault(exact_id, [])
            if r['n'] not in exact_usage:
                exact_usage.append(r['n'])

        row = {**r, 'match': cls, 'best': best, 'anchors': scored}
        if note:
            row['note'] = note
        rows.append(row)

    # Keep the requirement families separate.  A single "89%" over mandatory
    # bullets must not imply 89% of the whole advert when responsibilities and
    # preferred criteria were excluded from the denominator.
    scoreable = [x for x in rows if x['match'] != 'BEHAVIOURAL']
    kind_weights = {'mandatory': 1.0, 'responsibility': 0.55, 'preferred': 0.30}

    def cov(group):
        return round(sum(COVERAGE_WEIGHT[x['match']] for x in group) /
                     max(len(group), 1), 3) if group else None

    by_kind = {k: [x for x in scoreable if x['kind'] == k]
               for k in ('mandatory', 'responsibility', 'preferred')}
    denom = sum(kind_weights.get(x['kind'], 0.5) for x in scoreable) or 1.0
    earned = sum(kind_weights.get(x['kind'], 0.5) * COVERAGE_WEIGHT[x['match']]
                 for x in scoreable)
    fully = [x for x in scoreable if x['match'] == 'DIRECT']
    hard_unresolved = [x for x in rows if x.get('hard_gate') and x['match'] != 'DIRECT']
    return {
        'identity': identity,
        'requirements': rows,
        'anchor_usage': used,
        # Weighted, not a bare non-GAP count -- PARTIAL answers 40% of a
        # requirement, and the number should say so.
        'coverage': round(earned / denom, 3),
        'coverage_by_kind': {k: cov(v) for k, v in by_kind.items()},
        'covered': len(fully),
        'total_material': len(scoreable),
        'spread': {c: sum(1 for x in scoreable if x['match'] == c)
                   for c in ('DIRECT', 'TRANSFERABLE', 'PARTIAL', 'GAP')},
        'n_behavioural': len([x for x in rows if x['match'] == 'BEHAVIOURAL']),
        'behavioural': [x for x in rows if x['match'] == 'BEHAVIOURAL'],
        'gaps': [x for x in rows if x['match'] == 'GAP'],
        # Compatibility name retained, but it now means every hard gate that is
        # not directly evidenced.  Hard gates are binary in the real world.
        'hard_gate_gaps': hard_unresolved,
        'hard_gate_unresolved': hard_unresolved,
        'mandatory_risks': [x for x in by_kind['mandatory'] if x['match'] != 'DIRECT'],
    }


def select_anchors(m, identity, budget=None):
    """Pick the anchors that will actually appear, grouped by role.

    Selection rule: every anchor that answers a material requirement, plus the
    'headline' anchors of the chosen identity for seniority credibility.
    """
    by_id, recs = store.generation_anchors()
    primary = identity['primary']
    picked = {}

    for aid, reqs in m['anchor_usage'].items():
        picked[aid] = {'anchor': by_id[aid], 'serves': sorted(set(reqs)), 'reason': 'jd_match'}

    for a in recs:
        if a.get('priority') == 'headline' and primary in a.get('identity', []):
            picked.setdefault(a['id'], {'anchor': a, 'serves': [], 'reason': 'seniority_credibility'})

    # Fill toward the page budget with same-lane evidence rather than shipping a
    # thin CV. These are marked 'lane_depth' so PREVIEW shows they answer no
    # specific requirement -- making them the first thing to cut for space.
    if budget:
        for a in sorted(recs, key=lambda r: r.get('confidence', 0), reverse=True):
            if len(picked) >= budget:
                break
            if a['id'] in picked or a.get('type') != 'anchor' or a.get('render'):
                continue
            if primary in a.get('identity', []):
                picked[a['id']] = {'anchor': a, 'serves': [], 'reason': 'lane_depth'}

    # Anything flagged blocked or never-render can't be selected, ever.
    for aid in list(picked):
        # Any render directive means "handled specially" -- competency_band,
        # summary_only, blocked, never. None of them are ordinary bullets.
        if by_id[aid].get('render'):
            picked.pop(aid)

    # An anchor spanning several roles (the MRO thread does) is assigned to
    # exactly ONE of them -- the most recent -- so it renders once. Rendering it
    # under every role it touches is what makes a CV read as padded.
    role_start = {r['id']: (r.get('period') or [''])[0]
                  for r in recs if r.get('type') == 'role'
                  and r.get('kind') not in ('umbrella', 'education_period')}
    # An anchor with no role_id used to land in '_none', which the experience
    # builder never reads -- so it could never reach a tailored CV however
    # highly it ranked. Career-wide knowledge anchors (REG-001: regulatory
    # frameworks) are exactly this shape. They now attach to the most recent
    # role, where such knowledge is most credibly exercised.
    newest = max(role_start, key=lambda r: role_start.get(r, '')) if role_start else '_none'
    by_role = {}
    for aid, info in picked.items():
        rid = info['anchor'].get('role_id')
        cands = (rid if isinstance(rid, list) else [rid]) if rid else []
        cands = [c for c in cands if c in role_start]
        home = max(cands, key=lambda r: role_start.get(r, '')) if cands else newest
        by_role.setdefault(home, []).append(info)
    for r in by_role:
        by_role[r].sort(key=lambda i: (not i['serves'], -len(i['serves'])))
    return picked, by_role


def document_coverage(m, selected_ids):
    """Measure evidence visible in the CV, separately from corpus fit.

    A requirement is not covered by the document when all of its mapped
    anchors were omitted. Profile and behavioural requirements are resolved
    outside anchor selection and retain their existing classification.
    """
    selected = set(selected_ids or [])
    rows = []
    for requirement in m.get('requirements', []):
        candidates = [a for a in requirement.get('anchors', [])
                      if a.get('id') in selected]
        visible_match = requirement.get('match')
        note = requirement.get('note')
        if (requirement.get('match') != 'BEHAVIOURAL'
                and not requirement.get('resolved_from')
                and requirement.get('anchors') and not candidates):
            visible_match = 'GAP'
            note = 'evidence exists in truth but is not visible in this CV'
        rows.append({
            'n': requirement.get('n'),
            'match': visible_match,
            'visible_anchors': [a['id'] for a in candidates],
            **({'note': note} if note else {}),
        })

    by_number = {row['n']: row for row in rows}
    scoreable = [r for r in m.get('requirements', [])
                 if r.get('match') != 'BEHAVIOURAL']
    weights = {'mandatory': 1.0, 'responsibility': 0.55, 'preferred': 0.30}

    def classification(requirement):
        return by_number[requirement.get('n')]['match']

    def coverage(group):
        return (round(sum(COVERAGE_WEIGHT[classification(r)] for r in group) /
                      max(len(group), 1), 3) if group else None)

    kinds = {kind: [r for r in scoreable if r.get('kind') == kind]
             for kind in ('mandatory', 'responsibility', 'preferred')}
    denominator = sum(weights.get(r.get('kind'), 0.5) for r in scoreable) or 1.0
    earned = sum(weights.get(r.get('kind'), 0.5) *
                 COVERAGE_WEIGHT[classification(r)] for r in scoreable)
    return {
        'coverage': round(earned / denominator, 3),
        'coverage_by_kind': {kind: coverage(group)
                             for kind, group in kinds.items()},
        'covered': sum(classification(r) == 'DIRECT' for r in scoreable),
        'total_material': len(scoreable),
        'spread': {name: sum(classification(r) == name for r in scoreable)
                   for name in ('DIRECT', 'TRANSFERABLE', 'PARTIAL', 'GAP')},
        'requirements': rows,
    }
