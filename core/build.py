"""Assemble cv.json by interpreting truth/sections.json.

Section order, item caps, lane drops and role floors are declared in
`truth/sections.json`. The source/tailoring contract selects one fixed assembly
algorithm here. The engine selects approved prose; it never writes claim prose.

Two properties this preserves:

  ASSEMBLY, NOT COMPOSITION. Every line comes from a pre-written bullet variant
  on an anchor, so output cannot drift from ground truth.

  IMPACT RANKING, NOT FIRST-N. Every candidate is scored on whether it answers
  a JD requirement, carries a hard metric, how strongly it is owned and
  evidenced, and whether it sits in the chosen lane. Only the top `max` survive.
  For a career this broad that is the difference between a CV and an inventory:
  the breadth stays in the truth layer, but only the load-bearing parts reach
  the page.
"""
import re

from . import disclosure, language, store, vec

# Above this cosine, a candidate repeats evidence already on the page.
DIVERSITY_MAX = 0.62
# Outside mandatory coverage reservations, richer wording must improve
# requirement similarity materially before it earns extra page space.
VARIANT_RELEVANCE_GAIN = 0.08

# Naive .title() turns MRO into "Mro", which reads as carelessness in the one
# band a recruiter scans first.
ACRONYMS = {
    'mro', 'sms', 'v&v', 'fat', 'sat', 'ats', 'atr', 'pmo', 'evm', 'raid', 'wbs',
    'mbse', 'sysml', 'doors', 'ils', 'ips', 'oem', 'qa', 'qms', 'rf', 'ai', 'ml',
    'uav', 'uas', 'c2', 'aew&c', 'isr', 'mtbf', 'mttr', 'fmeca', 'fmea', 'lora',
    'rcm', 'icao', 'iata', 'gaca', 'faa', 'easa', 'rca', 'capa', 'hpc', 'iv&v',
    'lwir', 'aesa', 'aog', 'dmsms', 'icd', 'ipt', 'sop', 'iso', 'pmp', 'ceng',
    'gpu', 'cpu', 'slurm', 'm&e', 'kpi', 'bi',
}
DISPLAY = {
    'sysml': 'SysML', 'aew&c': 'AEW&C', 'iso 9001': 'ISO 9001', 'iso 21001': 'ISO 21001',
    'iso 29997': 'ISO 29997', 'v&v': 'V&V', 'iv&v': 'IV&V', 'r&d': 'R&D',
    'mtbf': 'MTBF', 'mttr': 'MTTR', 'c-check': 'C-Check', 'd-check': 'D-Check',
    'doors': 'DOORS', 'matlab': 'MATLAB', 'labview': 'LabVIEW', 'sap pm': 'SAP PM',
    'power bi': 'Power BI', 'ms project': 'MS Project',
}


def smart_title(term):
    if term.lower() in DISPLAY:
        return DISPLAY[term.lower()]
    out = []
    for w in term.split():
        k = w.lower().strip('/,')
        if k in DISPLAY:
            out.append(DISPLAY[k])
        elif k in ACRONYMS:
            out.append(w.upper())
        elif any(c.isupper() for c in w[1:]):
            out.append(w)
        else:
            out.append(w.capitalize())
    return ' '.join(out)


_MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _period(rec):
    p = rec.get('period') or [None, None]
    fmt = lambda d: '' if not d else (f"{_MONTHS[int(d[5:7])]} {d[:4]}" if len(d) >= 7 else d[:4])
    return f"{fmt(p[0])} – {fmt(p[1]) or 'Present'}" if p[0] else ''


# ---------------------------------------------------------------- ranking

def _impact(rec, serves, primary, weights, ladder, jd_specified=True):
    """Score one candidate. Higher wins the limited slots."""
    s = 0.0
    s += weights['serves_requirement'] * min(len(serves or []), 3)
    # The penalty is for EXPERIENCE that answers nothing in the advert. A
    # credential, publication or degree is worth showing on its own merits.
    if jd_specified and not serves and rec.get('type') in {
            'anchor', 'skill', 'publication', 'recognition'}:
        s += weights.get('no_requirement_penalty', -1.5)
    if jd_specified and not serves and rec.get('type') == 'credential' \
            and rec.get('tier') != 'professional':
        s += weights.get('no_requirement_penalty', -1.5) * 1.5
    if rec.get('type') == 'credential':
        s += weights.get('tier_' + (rec.get('tier') or 'coursework'), 1.0)
    if rec.get('metrics'):
        s += weights['has_metric']
    if rec.get('priority') == 'headline':
        s += weights['headline_priority']
    ident = rec.get('identity', [])
    if primary in ident or '*' in ident:
        s += weights['lane_match']
    if rec.get('ownership') in ladder:
        s += weights['ownership_level'] * ladder.index(rec['ownership'])
    s += weights['confidence'] * rec.get('confidence', 1.0)
    p = (rec.get('period') or [None])[0]
    if p and p >= '2017':
        s += weights['recency_bonus']
    return s


def _claim_variant(bullets, preferred, max_words, query='', min_gain=0.0):
    """Return one approved claim variant; JD context may select, never rewrite."""
    text = bullets.get(preferred) or bullets.get('std') or bullets.get('short', '')
    if len(text.split()) > max_words and bullets.get('short'):
        text = bullets['short']
    if query:
        candidates = [candidate for candidate in bullets.values()
                      if candidate and len(candidate.split()) <= max_words]
        if candidates:
            best = max(candidates, key=lambda candidate: (
                vec.cosine(query, candidate), -len(candidate.split())))
            if vec.cosine(query, best) - vec.cosine(query, text) >= min_gain:
                text = best
    return text


# ---------------------------------------------------------------- assemble

def assemble(jd, m, target_pages=None):
    """Interpret truth/sections.json into a cv.json."""
    from .match import select_anchors
    prof = store.profile()
    by_id, recs = store.generation_anchors()
    spec = store.sections()
    bnd = store.boundaries()
    ladder = bnd['ownership_ladder']
    weights = spec.get('impact_weights', {})
    target_pages = int(target_pages or spec.get('default_pages', 3))
    output_language = (prof.get('output') or {}).get('language', 'en-US')

    identity = m['identity']
    primary = identity['primary']
    lane = spec.get('lanes', {}).get(primary, {})
    default_pages = str(spec.get('default_pages', 3))
    budget = spec.get('page_budgets', {}).get(
        str(target_pages), spec.get('page_budgets', {}).get(default_pages, {}))
    variant = budget.get('variant', 'std')
    scale = budget.get('role_scale', 1.0)
    sscale = budget.get('section_scale', 1.0)

    def externalize(text):
        """Apply the declared public-CV naming policy, never model inference."""
        return language.localize(disclosure.externalize(text, bnd), output_language)

    def claim_text(rec, preferred=None, max_words=34):
        """Choose only among approved variants; never compose claim prose.

        Governed sections pass an explicit variant and therefore stay stable.
        For a JD-matched claim, choose the shortest approved variant that best
        exposes the requirements it serves within the word limit.
        This prevents an evidence ID from counting as visible when its rendered
        short form has silently dropped the relevant tool or method.
        """
        bullets = rec.get('bullet') or {}
        explicit = preferred is not None
        preferred = preferred or variant
        query = ''
        req_numbers = usage.get(rec.get('id'), [])
        if not explicit and req_numbers:
            query = ' '.join(requirement_text.get(n, '') for n in req_numbers)
        gain = 0.0 if rec.get('id') in coverage_reserve else VARIANT_RELEVANCE_GAIN
        text = _claim_variant(bullets, preferred, max_words, query, gain)
        return externalize(text)

    # Budget scales with the corpus so growth in the truth layer does not starve
    # selection and silently remove high-impact evidence.
    picked, by_role = select_anchors(
        m, identity, budget=max(40, int(len(recs) * 0.6)))
    usage = m.get('anchor_usage', {})
    requirement_text = {r['n']: r.get('text', '')
                        for r in jd.get('requirements', [])}
    jd_terms = ' '.join(r['text'] for r in jd.get('requirements', [])).lower()

    # Reserve the strongest renderable evidence for every DIRECT requirement.
    # Also reserve an exact transferable/partial answer when the only remaining
    # gap is a named employer or platform. MATCH must never call a requirement
    # answered while a page cap silently removes the evidence that answered it.
    coverage_reserve = set()
    for requirement in m.get('requirements', []):
        exact_gap = (requirement.get('match') in ('TRANSFERABLE', 'PARTIAL')
                     and 'exact ' in str(requirement.get('note') or '').lower())
        if requirement.get('match') != 'DIRECT' and not exact_gap:
            continue
        if requirement.get('resolved_from'):
            continue
        for candidate in requirement.get('anchors', []):
            record = by_id.get(candidate.get('id'))
            if not record or record.get('render'):
                continue
            if record.get('type') in {
                    'anchor', 'skill', 'credential', 'education',
                    'publication', 'recognition'}:
                coverage_reserve.add(record['id'])
                break

    def cap(sid, default):
        n = lane.get('caps', {}).get(sid, default)
        return max(1, int(round(n * sscale))) if isinstance(n, int) else n

    def rank(items, sid):
        """items: list of (rec, serves). Returns impact-sorted recs."""
        jd_spec = bool(jd.get('requirements'))
        scored = []
        for r, sv in items:
            score = _impact(r, sv, primary, weights, ladder, jd_spec)
            if any(str(term).lower() in jd_terms
                   for term in r.get('display_priority_terms') or []):
                score += weights.get('headline_priority', 2)
            scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        return scored

    # ---- header -------------------------------------------------------
    loc = prof.get('location', {})
    wa = loc.get('work_authorisation', {})
    _blob = (jd.get('title', '') + ' ' + jd.get('company', '') + ' ' +
             ' '.join(r['text'] for r in jd.get('requirements', []))).lower()
    _city = f"{loc.get('city','')}, {loc.get('based_in','')}".strip(', ')
    _auth = wa.get('phrasing_default') or wa.get('phrasing_approved', '')
    _auth_first = False
    for rule in wa.get('display_rules') or []:
        if any(str(term).lower() in _blob for term in rule.get('terms') or []):
            _auth = rule.get('phrasing') or _auth
            _auth_first = bool(rule.get('authorisation_first'))
            break
    _head = [_auth, _city] if _auth_first else [_city, _auth]
    if any(term.lower() in _blob for term in prof.get('rank_display_terms', [])):
        rank_label = (prof.get('career') or {}).get('rank')
        if rank_label:
            _head.insert(0, rank_label)
    contact = _head + [prof['contact']['phone_primary'], prof['contact']['email']]
    pos_for_headline = next((a for a in recs if a.get('type') == 'positioning'
                             and primary in a.get('identity', [])), None)
    headline_cites = ([pos_for_headline['id']] + list(pos_for_headline.get('supports', []))) \
        if pos_for_headline else []
    headline = (prof.get('headlines') or {}).get(
        primary, smart_title(primary.replace('_', ' ')))
    for rule in prof.get('headline_rules') or []:
        if all(str(term).lower() in _blob for term in rule.get('terms_all') or []):
            headline = rule.get('headline') or headline
            break
    header = {'name': prof['name'].upper(),
              'headline': headline,
              'anchor': headline_cites[0] if headline_cites else None,
              'anchors': [a for a in headline_cites if a in by_id],
              'contact': [c for c in contact if c],
              'links': {k: v for k, v in (prof.get('links') or {}).items()
                        if v and not k.startswith('_')}}

    # ---- section builders --------------------------------------------
    built = {}

    def s_positioning(sec):
        pos = next((a for a in recs if a.get('type') == 'positioning'
                    and primary in a.get('identity', [])), None)
        if not pos:
            return []
        cites = [pos['id']] + [x for x in pos.get('supports', []) if x in by_id]
        serves = sorted({n for anchor_id in cites for n in usage.get(anchor_id, [])})
        query = ' '.join(requirement_text.get(n, '') for n in serves)
        preferred = sec.get('variant', 'short')
        txt = _claim_variant(
            pos.get('bullet') or {}, preferred, sec.get('max_words', 42),
            query=query, min_gain=VARIANT_RELEVANCE_GAIN / 2 if query else 1.0)
        txt = externalize(txt)
        return [{'text': txt.strip(), 'anchor': cites[0], 'anchors': cites,
                 '_serves': serves,
                 '_note': (f'JD-selected approved positioning variant from {cites[0]}'
                           if query else f'fixed identity positioning from {cites[0]}')}]

    def s_competency(sec):
        record = by_id.get(sec.get('anchor_id')) if sec.get('anchor_id') else next(
            (r for r in recs if r.get('type') == 'skill'
             and r.get('render') == 'competency_band'), {})
        kws = record.get('keywords', [])
        hit = [k for k in kws if k.lower() in jd_terms]
        rest = [k for k in kws if k not in hit]
        n = cap('competencies', sec.get('max', 14))
        return [{'text': externalize(' | '.join(smart_title(c) for c in (hit + rest)[:n])),
                 'anchor': record.get('id'),
                 '_serves': usage.get(record.get('id'), [])}] if record else []

    def s_bytype(sec, typ, sid, *, exclude_tiers=None, limit=None):
        """Candidates are the FULL pool of this type, not just JD-matched ones.

        Certifications, skills and recognition are sections a reader expects to
        be populated. Restricting them to anchors that happened to match a JD
        keyword can hide a professional credential simply because the advert
        never names it; the impact score should rank the wide pool instead.
        """
        exclude_tiers = set(exclude_tiers or [])
        pool = {a: usage.get(a, []) for a in picked
                if by_id[a].get('type') == typ and not by_id[a].get('render')
                and by_id[a].get('tier') not in exclude_tiers}
        for r in recs:
            if (r.get('type') != typ or r['id'] in pool or r.get('render')
                    or r.get('tier') in exclude_tiers):
                continue
            in_lane = primary in r.get('identity', []) or '*' in r.get('identity', [])
            # A professional certification is worth showing whatever lane the
            # CV is in. Other qualifications remain lane/JD conditional.
            # Other qualifications and coursework render only when the lane or
            # the JD calls for them; otherwise the section becomes an inventory.
            if in_lane or r.get('tier') == 'professional' or usage.get(r['id']):
                pool[r['id']] = []
        cands = [(by_id[a], sv) for a, sv in pool.items()]
        n = limit if limit is not None else cap(sid, sec.get('max', 4))
        out = []
        ranked = rank(cands, sid)
        protected_tiers = set(sec.get('protected_tiers') or [])
        ranked.sort(key=lambda pair: (
            0 if pair[1].get('tier') in protected_tiers else 1,
            0 if pair[1]['id'] in coverage_reserve else 1,
            -pair[0], pair[1]['id']))
        n = max(n, sum(r['id'] in coverage_reserve
                       or r.get('tier') in protected_tiers for _, r in ranked))
        for score, r in ranked[:n]:
            if score < sec.get('min_score', -99):
                continue
            txt = claim_text(r)
            if txt:
                cites = [r['id']] + [x for x in r.get('supports', []) if x in by_id]
                out.append({'text': txt, 'anchor': r['id'], 'anchors': cites,
                            '_serves': usage.get(r['id'], []),
                            '_score': round(score, 2),
                            '_protected': r.get('tier') in protected_tiers})
        return out

    def s_experience(sec):
        roles = [r for r in recs if r.get('type') == 'role'
                 and r.get('kind') not in ('umbrella', 'education_period')]
        roles.sort(key=lambda r: (r.get('period') or [''])[0], reverse=True)
        caps = sec.get('max_per_role', [6, 6, 5, 4, 4])
        exp = []
        # Roles are processed most-recent-first, so a multi-role anchor lands in
        # its newest role and the chronology fallback below cannot re-render it
        # further down. G6 caught SAFE-001 appearing twice when this was missing.
        rendered = set()
        redundant = {}
        for i, role in enumerate(roles):
            infos = by_role.get(role['id'], [])
            mins = sec.get('min_per_role', [4, 3, 3, 2, 2])
            floor = max(1, int(round(mins[min(i, len(mins) - 1)] * scale)))
            n = max(floor, int(round(caps[min(i, len(caps) - 1)] * scale)))
            # A governed highlight owns its claim once. Experience supplies
            # complementary role context, never a second telling.
            cands = [(inf['anchor'], inf['serves']) for inf in infos
                     if inf['anchor'].get('type') == 'anchor'
                     and inf['anchor'].get('placement', 'experience') == 'experience']

            # Rank the complete evidence pool for this role, not merely the
            # anchors retrieved by literal JD wording. Retrieval determines
            # relevance; it must not erase operational depth, lifecycle scope,
            # or a role-defining outcome before impact and diversity can judge
            # them. Multi-role anchors still have one deterministic home above.
            have = {a['id'] for a, _ in cands}
            for r in recs:
                if (r.get('type') != 'anchor' or r.get('render')
                        or r.get('placement', 'experience') != 'experience'
                        or r['id'] in have or r['id'] in rendered):
                    continue
                rid = r.get('role_id')
                rids = rid if isinstance(rid, list) else ([rid] if rid else [])
                if role['id'] not in rids or len(rids) != 1:
                    continue
                cands.append((r, usage.get(r['id'], [])))
            if not cands:
                # Every role must appear. A role selected out entirely leaves an
                # unexplained employment gap, which a recruiter reads as
                # something concealed -- far costlier than an off-lane bullet.
                # (ROLE-003 vanished here: its only selected item was a
                # credential, so the anchor-typed candidate list was empty.)
                own = [r for r in recs
                       if r.get('type') == 'anchor' and not r.get('render')
                       and r['id'] not in rendered
                       and role['id'] in ((r.get('role_id') if isinstance(r.get('role_id'), list)
                                           else [r.get('role_id')]) or [])]
                cands = [(a, []) for a in own]
            lane_core = (sec.get('core_by_lane') or {}).get(primary, {})
            core_ids = list((lane_core or sec.get('core_by_role') or {}).get(
                role['id'], []))
            core_order = {anchor_id: position
                          for position, anchor_id in enumerate(core_ids)}
            ranked_candidates = rank(cands, 'experience')
            ranked_candidates.sort(key=lambda pair: (
                0 if pair[1]['id'] in coverage_reserve else 1,
                0 if pair[1]['id'] in core_order else 1,
                core_order.get(pair[1]['id'], 10**9),
                -pair[0], pair[1]['id']))
            n = max(n, sum(a['id'] in coverage_reserve
                           for _, a in ranked_candidates))
            bullets = []
            chosen_txt = []
            for score, a in ranked_candidates:
                if len(bullets) >= n:
                    break
                if a['id'] in rendered:
                    continue
                txt = claim_text(a)
                if not txt:
                    continue
                # Greedy diversity: two bullets saying the same thing waste a
                # slot each. G6 only blocks near-identical text (0.85); this
                # catches conceptual overlap that still reads as padding.
                duplicate = max(
                    ((vec.cosine(txt, prev_txt), prev_id)
                     for prev_id, prev_txt in chosen_txt), default=(0.0, None))
                if duplicate[0] >= DIVERSITY_MAX:
                    redundant[a['id']] = {
                        'with': duplicate[1], 'cosine': round(duplicate[0], 3)}
                    continue
                chosen_txt.append((a['id'], txt))
                rendered.add(a['id'])
                srv = usage.get(a['id'], [])
                cites = [a['id']] + [x for x in a.get('supports', []) if x in by_id]
                bullets.append({'text': txt, 'anchor': a['id'], 'anchors': cites,
                                '_serves': srv,
                                '_score': round(score, 2),
                                '_reason': 'jd_match' if srv else 'lane_depth'})
            if not bullets:
                continue
            title = role['title'] + (f" — {role['subtitle']}" if role.get('subtitle') else '')
            exp.append({'title': externalize(title),
                        'org': externalize(role['org']), 'period': _period(role),
                        'framing': '',
                        'anchor': role['id'], 'text': externalize(role['title']),
                        'bullets': bullets})
        built['_redundant'] = redundant
        return exp

    def s_highlights(sec):
        """Render one explicit, chronological career story.

        Every ``placement: highlights`` record is mandatory for its identity.
        There is no JD ranking, fallback project pool or hidden promotion flag.
        Recognition or status may merge into its relevant stage while keeping
        an independent citation.
        """
        placed = [r for r in recs
                  if r.get('placement') == 'highlights' and not r.get('render')
                  and (primary in r.get('identity', []) or '*' in r.get('identity', []))]
        placed.sort(key=lambda r: (r.get('highlight_sequence', 10**9), r['id']))
        # The configuration integrity check guarantees this unscaled cap can
        # hold the whole governed story; page fitting must never squeeze it.
        n = lane.get('caps', {}).get('highlights', sec.get('max', len(placed) or 1))

        riders = {}
        for r in recs:
            d = str(r.get('render') or '')
            if d.startswith('merge:'):
                riders.setdefault(d.split(':', 1)[1], []).append(r)

        out = []
        for r in placed[:n]:
            txt = claim_text(r, preferred=sec.get('variant', 'short'),
                             max_words=sec.get('max_words', 26))
            if not txt:
                continue
            cites = [r['id']] + [x for x in r.get('supports', []) if x in by_id]
            for rider in riders.get(r['id'], []):
                add = externalize((rider.get('bullet') or {}).get('short', ''))
                if add:
                    if rider.get('merge_case') != 'preserve':
                        add = add[0].lower() + add[1:]
                    relation = rider.get('merge_relation', 'causal')
                    if relation == 'chronological':
                        txt = (txt.rstrip('.') + '; recognition during this period: '
                               + add)
                    else:
                        txt = txt.rstrip('.') + '; ' + add
                    cites.append(rider['id'])
            if sec.get('period_prefix'):
                dates = r.get('period') or []
                start = str(dates[0])[:4] if dates and dates[0] else ''
                end = (str(dates[1])[:4] if len(dates) > 1 and dates[1]
                       else 'Present' if start else '')
                period = f"{start}–{end}" if start else ''
                txt = f"{period} | {txt}" if period else txt
            txt = txt.rstrip('.') + '.'
            serves = sorted({n for anchor_id in cites for n in usage.get(anchor_id, [])})
            out.append({'text': txt, 'anchor': r['id'], 'anchors': cites,
                        '_serves': serves,
                        '_score': 1000 - r.get('highlight_sequence', 999)})
        if len(out) < sec.get('min_items', 1):
            return []
        return out

    def s_recency(sec, typ, sid):
        cands = [r for r in recs if r.get('type') == typ and not r.get('render')]
        if typ == 'publication':
            cands = [r for r in cands if r.get('status') == 'PUBLISHED']
        cands.sort(key=lambda r: (r.get('period') or [''])[0] or '', reverse=True)
        n = (len(cands) if sec.get('retention') == 'all_eligible'
             else cap(sid, sec.get('max', 4)))
        return [{'text': claim_text(r, preferred=sec.get('variant', 'short')),
                 'anchor': r['id'], '_serves': usage.get(r['id'], []),
                 '_protected': sec.get('retention') == 'all_eligible'}
                for r in cands[:n]]

    def s_credentials(sec):
        """Ranked credentials, plus one combined line for the grouped tiers."""
        gt = set(sec.get('group_tiers', []))
        grouped = [r for r in recs
                   if r.get('type') == 'credential' and r.get('tier') in gt
                   and not r.get('render')
                   and 'default OMIT' not in (r.get('boundary') or '')]
        group_limit = sec.get('group_limit', len(grouped))
        if group_limit < len(grouped):
            grouped = [r for _, r in rank(
                [(r, usage.get(r['id'], [])) for r in grouped], 'certifications')
            ][:group_limit]
        else:
            grouped.sort(key=lambda r: r['id'])
        group_count = min(sec.get('group_chunks', 1), len(grouped)) if grouped else 0
        total_slots = cap('certifications', sec.get('max', 4))
        # Reserve the reader-visible development groups before ranking the
        # higher-tier credentials, so the section cap remains real.
        main_slots = max(0, total_slots - group_count)
        main = s_bytype(sec, 'credential', 'certifications',
                        exclude_tiers=gt, limit=main_slots)
        if grouped:
            chunk_size = (len(grouped) + group_count - 1) // group_count
            prefixes = sec.get('group_prefixes') or [
                sec.get('group_prefix', 'Professional development')]
            for index in range(group_count):
                chunk = grouped[index * chunk_size:(index + 1) * chunk_size]
                if not chunk:
                    continue
                labels = [r.get('group_label') or
                          (r.get('bullet') or {}).get('short', r['id']) for r in chunk]
                prefix = prefixes[min(index, len(prefixes) - 1)]
                provider = sec.get('group_provider')
                if provider:
                    labels = [re.sub(rf'\s*/\s*{re.escape(provider)}\b', '', label)
                              for label in labels]
                    prefix += f" ({provider})"
                main.append({
                    'text': f"{prefix} — " + externalize('; '.join(labels)),
                    'anchor': chunk[0]['id'],
                    'anchors': [r['id'] for r in chunk],
                    '_serves': sorted({n for r in chunk for n in usage.get(r['id'], [])}),
                    '_score': 99.0,
                })
        return main

    HANDLERS = {
        'positioning':     s_positioning,
        'competency_band': s_competency,
        'skill':           lambda s: s_bytype(s, 'skill', 'skills'),
        'role_bullets':    s_experience,
        'highlight':       s_highlights,
        'publication':     lambda s: s_recency(s, 'publication', 'research'),
        'education':       lambda s: s_recency(s, 'education', 'education'),
        'credential':      s_credentials,
        'recognition':     lambda s: s_bytype(s, 'recognition', 'recognition'),
    }

    def included(sec):
        if sec['id'] in lane.get('drop', []):
            return False
        cond = sec.get('include_if')
        if not cond:
            return True
        if primary in cond.get('lane', []):
            return True
        if any(t in jd_terms for t in cond.get('jd_mentions', [])):
            return True
        return False

    by_sid = {s['id']: s for s in spec.get('sections', [])}
    order = lane.get('order') or [s['id'] for s in spec.get('sections', [])]
    order += [s['id'] for s in spec.get('sections', []) if s['id'] not in order]

    sections = []
    for sid in order:
        sec = by_sid.get(sid)
        if not sec or not included(sec):
            continue
        items = HANDLERS[sec['source']](sec)
        built[sid] = items
        if items:
            sections.append({'name': externalize(sec['name']),
                             'type': sec['type'], 'items': items})

    # ---- section boundaries --------------------------------------------
    # A section declaring `dedupe_against` may not repeat vocabulary that its
    # named sections already put on the page. CORE COMPETENCIES and TECHNICAL &
    # PROGRAMME SKILLS shared 7 of 14 terms; the band exists to widen ATS
    # coverage, not to say the page twice.
    from .vec import _stem as _st

    def _stems(txt):
        return {_st(w) for w in re.findall(r'[a-z]+', (txt or '').lower()) if len(w) > 2}

    for sec_spec in spec.get('sections', []):
        against = sec_spec.get('dedupe_against')
        if not against:
            continue
        tgt = next((s for s in sections if s['name'] == sec_spec['name']), None)
        if not tgt or tgt['type'] != 'band':
            continue
        elsewhere = set()
        for s in sections:
            sid = {x['name']: x['id'] for x in spec.get('sections', [])}.get(s['name'])
            if sid not in against:
                continue
            for it in s['items']:
                elsewhere |= _stems(it.get('text', ''))
                elsewhere |= _stems(it.get('title', ''))
                elsewhere |= _stems(it.get('frame', ''))
                for b in it.get('bullets', []):
                    elsewhere |= _stems(b.get('text', ''))
        for it in tgt['items']:
            kept = [term for term in it['text'].split(' | ')
                    if not (_stems(term) and _stems(term) <= elsewhere)]
            it['text'] = ' | '.join(kept)
            it['_deduped'] = True
        if sum(len(i['text'].split(' | ')) for i in tgt['items'] if i['text']) \
                < sec_spec.get('min_items', 1):
            sections = [s for s in sections if s is not tgt]

    # ---- auto-fit ------------------------------------------------------
    # A CV that spills four lines onto a third page is the worst layout there
    # is. Rather than hand-tuning caps per JD, trim the lowest-impact items
    # until the estimate fits the target -- the same ranking that chose them
    # decides what goes first, so trimming never removes the load-bearing
    # evidence. Roles keep their floor so nothing vanishes from the chronology.
    trimmed = []
    if sections:
        # Measure exactly what G8 and the renderer expose, including section,
        # role and header metadata. Those words are structural rather than
        # claims, but they still occupy physical page space.
        from . import gates as _g

        def words():
            probe = {'header': header, 'sections': sections, 'target_pages': target_pages}
            return sum(len(t.split()) for _, t, _, _ in _g._lines(probe))

        def experience_bullets():
            return sum(len(item.get('bullets', [])) for section in sections
                       if section.get('type') == 'experience'
                       for item in section.get('items', []))

        limit = int(target_pages * _g.WORDS_PER_PAGE)
        bullet_limit = int(target_pages * budget.get(
            'experience_bullets_per_page', 11))
        trimmed = []
        sid_of = {sec['name']: sec['id'] for sec in spec.get('sections', [])}

        def protected_for(section_id):
            section_spec = by_sid.get(section_id, {})
            return bool(section_spec.get('protected') or primary in
                        section_spec.get('protected_if_lane', []))

        guard = 0
        max_trim_steps = max(40, len(recs) * 2)
        while ((words() > limit or experience_bullets() > bullet_limit)
               and guard < max_trim_steps):
            guard += 1
            over_bullets = experience_bullets() > bullet_limit
            worst, where = None, None
            for s in sections:
                if s['type'] == 'experience':
                    for i, it in enumerate(s['items']):
                        mins = by_sid['experience'].get('min_per_role', [4, 3, 3, 2, 2])
                        fl = max(1, int(round(mins[min(i, len(mins) - 1)] * scale)))
                        if len(it['bullets']) <= fl:
                            continue
                        tr = by_sid.get('experience', {}).get('trim_rank', 5)
                        for b in it['bullets']:
                            if b.get('anchor') in coverage_reserve:
                                continue
                            sc = b.get('_score', 0) + tr * 1.5
                            if worst is None or sc < worst:
                                worst, where = sc, ('bullet', it, b)
                elif (not over_bullets
                      and s['type'] in ('list', 'plain') and len(s['items']) > 1
                      and not protected_for(sid_of.get(s['name']))
                      and len(s['items']) >
                          by_sid.get(sid_of.get(s['name']), {}).get('min_items', 1)):
                    # trim_rank orders which sections give way first, so a
                    # commendation is not sacrificed to keep a skills line.
                    tr = by_sid.get(sid_of.get(s['name']), {}).get('trim_rank', 5)
                    for it in s['items']:
                        if it.get('_protected'):
                            continue
                        item_anchors = {it.get('anchor')} | set(it.get('anchors') or [])
                        if item_anchors & coverage_reserve:
                            continue
                        sc = it.get('_score', 99.0) + tr * 1.5
                        if worst is None or sc < worst:
                            worst, where = sc, ('item', s, it)
            if where is None:
                break
            kind, holder, victim = where
            trimmed.append((victim.get('anchor', '?'),
                            round(victim.get('_score', 0), 2),
                            victim.get('text', '')[:70]))
            (holder['bullets'] if kind == 'bullet' else holder['items']).remove(victim)
        sections = [s for s in sections if s['items']]

    # ---- selection ledger -------------------------------------------------
    # A reviewer must be able to distinguish "not relevant" from "matched but
    # lost to impact/diversity/space". PREVIEW previously assigned the former
    # reason to every omission, including anchors that served several JD
    # requirements. The ledger is deterministic and travels with the release.
    used = set()
    for section in sections:
        for item in section.get('items', []):
            anchor = item.get('anchor')
            if anchor:
                used.add(anchor)
                # Grouped credentials, highlight supports and merged riders are
                # genuinely represented by one visible line and must all count
                # as used whatever the primary record type.
                used.update(item.get('anchors') or [])
            for bullet in item.get('bullets', []):
                if bullet.get('anchor'):
                    used.add(bullet['anchor'])
                used.update(bullet.get('anchors') or [])

    trimmed_ids = {row[0] for row in trimmed}
    redundant = built.get('_redundant', {})
    positioning_supports = set(pos_for_headline.get('supports', [])) \
        if pos_for_headline else set()
    threshold = (spec.get('selection_guardrails') or {}).get(
        'significant_impact_threshold', 8.0)
    omitted = []
    for record in recs:
        rid = record['id']
        if rid in used or record.get('type') in ('role', 'boundary', 'positioning'):
            continue
        reqs = sorted(set(usage.get(rid, [])))
        score = round(_impact(record, reqs, primary, weights, ladder,
                              bool(jd.get('requirements'))), 2)
        render_rule = record.get('render')
        if render_rule:
            code, reason = 'render_rule', f"controlled by render rule: {render_rule}"
        elif rid in redundant:
            info = redundant[rid]
            code = 'redundant'
            reason = (f"semantic duplicate of {info['with']} "
                      f"(cosine {info['cosine']:.3f})")
        elif rid in trimmed_ids:
            code, reason = 'page_trim', 'removed as the lowest-impact item at the measured page ceiling'
        elif reqs:
            code = 'matched_not_selected'
            reason = 'matched the JD but ranked below selected non-redundant evidence'
        elif (record.get('type') == 'publication'
              and record.get('status') == 'PUBLISHED'
              and included(by_sid.get('research', {}))):
            code = 'section_capacity'
            reason = 'eligible published paper exceeded the declared research-section capacity'
        elif record.get('priority') == 'headline' and (
                primary in record.get('identity', []) or rid in positioning_supports):
            code = 'headline_not_selected'
            reason = 'role-defining evidence ranked below selected non-redundant evidence'
        elif (primary in record.get('identity', [])
              or '*' in record.get('identity', [])):
            code = 'lane_depth_not_selected'
            reason = 'relevant lane depth ranked below selected evidence'
        else:
            code, reason = 'not_relevant', 'not selected for the chosen lane or JD'
        research_spec = by_sid.get('research', {})
        education_spec = by_sid.get('education', {})
        credential_spec = by_sid.get('certifications', {})
        protected = bool(
            (record.get('type') == 'publication'
             and record.get('status') == 'PUBLISHED'
             and research_spec.get('retention') == 'all_eligible'
             and included(research_spec))
            or (record.get('type') == 'education'
                and education_spec.get('retention') == 'all_eligible')
            or (record.get('type') == 'credential'
                and record.get('tier') in set(
                    credential_spec.get('protected_tiers') or []))
            or (record.get('placement') == 'highlights'
                and (primary in record.get('identity', [])
                     or '*' in record.get('identity', []))))
        significant = bool(
            protected
            or (record.get('type') == 'publication' and code == 'section_capacity')
            or (record.get('type') == 'anchor'
                and code not in ('redundant', 'render_rule')
                and ((record.get('priority') == 'headline'
                      and (rid in positioning_supports or bool(reqs)))
                     or (bool(reqs) and score >= threshold))))
        omitted.append({
            'id': rid, 'type': record.get('type'), 'impact': score,
            'requirements': reqs, 'reason_code': code, 'reason': reason,
            'significant': significant, 'protected': protected,
            'fact': record.get('fact', ''),
        })
    omitted.sort(key=lambda row: (not row['significant'], -row['impact'], row['id']))
    selection = {
        'selected_ids': sorted(used),
        'selected_count': len(used),
        'omitted': omitted,
        'significant_omissions': [row['id'] for row in omitted if row['significant']],
        'reason_counts': {
            code: sum(row['reason_code'] == code for row in omitted)
            for code in sorted({row['reason_code'] for row in omitted})
        },
    }

    # Corpus fit says evidence exists. Only document fit says this CV shows it.
    # Keep both so a reviewer can detect last-mile selection loss.
    from . import match as _match
    document = _match.document_coverage(m, used)
    m['document'] = document

    # Private, immutable application-context snapshot for any later outcome
    # review. It is not rendered in the CV, but prevents post-mortems from
    # borrowing a profile state that changed after submission.
    profile_context = {
        'based_in': (prof.get('location') or {}).get('based_in'),
        'city': (prof.get('location') or {}).get('city'),
        'work_authorisation': {
            key: value for key, value in
            ((prof.get('location') or {}).get('work_authorisation') or {}).items()
            if key in {'phrasing_default', 'phrasing_gcc', 'transferable',
                       'gcc_mobility', 'mobility', '_open_question'}
        },
        'languages': prof.get('languages') or {},
        'eligibility': prof.get('eligibility') or {},
        'availability_note': (prof.get('career') or {}).get('availability_note'),
    }

    return {
        '_trimmed': trimmed,
        '_selection': selection,
        'job': jd.get('_slug', ''), 'company': jd.get('company', ''),
        'role': jd.get('title', ''), 'identity': primary,
        'identity_ranked': identity.get('ranked', []),
        'target_pages': target_pages, 'variant': variant,
        'language': output_language,
        'generated': store.now(), 'header': header, 'sections': sections,
        'coverage': document.get('coverage'),
        'coverage_by_kind': document.get('coverage_by_kind', {}),
        '_profile_context': profile_context,
        '_inputs': store.generation_fingerprint(jd),
        '_status': 'MECHANICAL_DRAFT',
        '_spec': 'truth/sections.json',
    }
