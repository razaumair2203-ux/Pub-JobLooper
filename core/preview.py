"""PREVIEW.md -- the approval gate.

Everything the system intends to do, shown before a single document exists:
which identity was chosen and why, which requirements are answered by which
evidence, what was dropped and for what reason, and what is not covered at all.
"""
from . import store, gates

MARK = {'jd_match': '+', 'seniority_credibility': '*'}


def _omission_lines(cv):
    """Truthful, compact selection explanation; None means legacy plan."""
    ledger = (cv.get('_selection') or {}).get('omitted')
    if ledger is None:
        return None
    significant = [row for row in ledger if row.get('significant')]
    matched = [row for row in ledger
               if row.get('reason_code') in
               ('matched_not_selected', 'headline_not_selected')
               and not row.get('significant')]
    other = [row for row in ledger if row not in significant and row not in matched]
    lines = []
    for row in significant + matched:
        reqs = (f"; serves req#{', #'.join(str(n) for n in row.get('requirements', []))}"
                if row.get('requirements') else '')
        tag = ' **[MATERIAL]**' if row.get('significant') else ''
        lines.append(f"- [{row['id']}]{tag} impact {row['impact']:.2f}{reqs} - "
                     f"_{row['reason']}_")
    if other:
        counts = (cv.get('_selection') or {}).get('reason_counts') or {}
        summary = ', '.join(
            f"{name}={count}" for name, count in counts.items()
            if name not in ('matched_not_selected', 'headline_not_selected'))
        lines.append(f"- Other controlled omissions: {len(other)} ({summary})")
        for row in other[:8]:
            lines.append(f"  - [{row['id']}] {row['fact'][:80]}... - _{row['reason']}_")
        if len(other) > 8:
            lines.append(f"  - ...and {len(other)-8} lower-priority/control-rule items")
    return lines or ['- none']


def render(jd, m, cv, slug, phase='plan'):
    by_id, recs = store.anchors()
    section_contracts = {s.get('name'): s for s in store.sections().get('sections', [])}
    ident = m['identity']
    document = m.get('document') or {
        'coverage': m.get('coverage'),
        'coverage_by_kind': m.get('coverage_by_kind', {}),
        'covered': m.get('covered'),
        'total_material': m.get('total_material'),
        'spread': m.get('spread', {}),
        'requirements': [],
    }
    visible_by_number = {r.get('n'): r
                         for r in document.get('requirements', [])}
    o = []

    o.append(f"# PREVIEW — {cv.get('company') or '?'} · {cv.get('role') or '?'}")
    o.append('')
    o.append(f"`{slug}` · generated {cv['generated']}")
    o.append('')
    if phase == 'release':
        o.append('> Evidence map for the rendered package. Review the CV beside this file before accepting it for submission.')
    else:
        o.append('> Mechanical plan only; nothing has been rendered. Review evidence and omissions before approval.')
    o.append('')

    # ---- framing ------------------------------------------------------
    o.append('## FRAMING')
    o.append('')
    ranked = ' / '.join(f"{k.replace('_',' ')} {v:.2f}" for k, v in ident['ranked'][:4])
    o.append(f"**Primary identity:** `{ident['primary']}`"
             + ('  *(your override)*' if ident['overridden'] else ''))
    o.append('')
    o.append(f"JD scored: {ranked}")
    o.append('')
    o.append(f"**Headline:** {cv['header']['headline']}")
    o.append('')
    demoted = [k for k, _ in ident['ranked'][1:] if k != ident['primary']]
    o.append(f"Demoted to supporting evidence: {', '.join(x.replace('_',' ') for x in demoted)}")
    o.append('')
    o.append(f"► Override: `jl plan {slug} --identity <name>`")
    o.append('')

    # ---- hard gates ---------------------------------------------------
    hard = [r for r in m['requirements'] if r['hard_gate']]
    if hard:
        o.append('## HARD GATES')
        o.append('')
        for r in hard:
            visible = visible_by_number.get(r.get('n'), {})
            classification = visible.get('match', r['match'])
            icon = {'DIRECT': '[OK ]', 'TRANSFERABLE': '[~  ]',
                    'PARTIAL': '[?  ]', 'GAP': '[XX ]'}[classification]
            ids = ', '.join(visible.get('visible_anchors') or []) or '—'
            o.append(f"- `{icon}` **{classification}** · {r['text'][:110]}")
            o.append(f"      evidence: {ids} (best {r['best']:.2f})")
        o.append('')

    # ---- sections -----------------------------------------------------
    o.append('## WHAT GOES IN EACH SECTION')
    o.append('')
    used = set()
    for sec in cv['sections']:
        o.append(f"### {sec['name']}")
        o.append('')
        contract = section_contracts.get(sec['name'], {})
        if contract:
            o.append(f"_Rule: `{contract.get('tailoring')}` — {contract.get('purpose')}_")
            o.append('')
        if sec['type'] == 'experience':
            for item in sec['items']:
                o.append(f"**{item['title']}**  ·  _{item['org']} | {item['period']}_")
                o.append('')
                for b in item['bullets']:
                    used.add(b['anchor'])
                    serves = (', '.join(f"req#{n}" for n in b.get('_serves', []))
                              or 'seniority credibility')
                    o.append(f"  `{MARK.get(b.get('_reason'),'+')}` {b['text']}")
                    o.append(f"      └ [{b['anchor']}] → {serves}")
                o.append('')
        else:
            for item in sec['items']:
                anchor_ids = item.get('anchors') or [item.get('anchor')]
                anchor_ids = [anchor_id for anchor_id in anchor_ids if anchor_id]
                used.update(anchor_ids)
                note = item.get('_note')
                o.append(f"  `+` {item['text']}")
                citations = ', '.join(f'[{anchor_id}]' for anchor_id in anchor_ids) or '[unresolved]'
                o.append(f"      └ {citations}" + (f" · {note}" if note else ''))
            o.append('')

    # ---- dropped ------------------------------------------------------
    o.append('## DROPPED (available but not used)')
    o.append('')
    dropped = _omission_lines(cv)
    has_ledger = dropped is not None
    dropped = dropped or []
    for r in ([] if has_ledger else recs):
        if r['id'] in used or r.get('type') in ('role', 'boundary'):
            continue
        why = 'no JD requirement served'
        if r.get('render') == 'blocked_pending_validation':
            why = 'BLOCKED — metric unvalidated'
        elif r.get('render') == 'only_if_confirmed':
            why = 'BLOCKED — status unconfirmed'
        elif 'OMIT' in (r.get('boundary') or '').upper():
            why = 'boundary rule says omit for this role type'
        dropped.append(f"- [{r['id']}] {r.get('fact','')[:85]}… — _{why}_")
    o.extend(dropped if has_ledger else dropped[:20])
    if not has_ledger and len(dropped) > 20:
        o.append(f"- …and {len(dropped)-20} more")
    o.append('')

    # ---- coverage -----------------------------------------------------
    sp = document.get('spread', {})
    o.append(f"## CV-VISIBLE EVIDENCE COVERAGE — {document['coverage']:.0%} local whole-advert heuristic "
             f"({document['covered']}/{document['total_material']} evidence requirements DIRECT)")
    o.append('')
    kinds = document.get('coverage_by_kind') or {}
    o.append('  ' + ' · '.join(f"{k.upper()} {v:.0%}" for k, v in kinds.items()
                               if v is not None))
    o.append('')
    o.append('  ' + ' · '.join(f"{k} {v}" for k, v in sp.items() if v))
    o.append('')
    buckets = {}
    for r in m['requirements']:
        visible = visible_by_number.get(r.get('n'), {})
        buckets.setdefault(visible.get('match', r['match']), []).append(r)
    for cls in ('DIRECT', 'TRANSFERABLE', 'PARTIAL', 'GAP'):
        rs = buckets.get(cls, [])
        if not rs:
            continue
        o.append(f"**{cls}** ({len(rs)})")
        o.append('')
        for r in rs[:12]:
            tag = ' **[HARD GATE]**' if r['hard_gate'] else ''
            visible = visible_by_number.get(r.get('n'), {})
            ids = visible.get('visible_anchors') or []
            o.append(f"- #{r['n']}{tag} {r['text'][:100]}"
                     + (f"  → {', '.join(ids)}" if ids
                        else '  → **not visible in CV**'))
        if len(rs) > 12:
            o.append(f"- …and {len(rs)-12} more; all remain available in MATCH.json")
        o.append('')

    lessons = m.get('learning_signals') or []
    if lessons:
        o.append('## PRIOR LEARNING SIGNALS — contextual, not ground truth')
        o.append('')
        o.append('Confirmed review hypotheses from similar applications; use them to ask better questions, not to rewrite facts.')
        o.append('')
        for lesson in lessons:
            o.append(f"- {lesson['similarity']:.2f} similar · {lesson['company']} · "
                     f"**{lesson['cause']}** ({lesson['confidence']:.0%}) — {lesson['summary'][:120]}")
            revision = lesson.get('last_revision') or {}
            context = ((revision.get('company_context') or [])
                       + (revision.get('profile_factors') or [])
                       + (revision.get('other_factors') or []))
            if context:
                o.append('      context: ' + '; '.join(context)[:180])
            if revision.get('unknowns'):
                o.append('      still unknown: ' + '; '.join(revision['unknowns'])[:160])
        o.append('')

    # ---- gate results -------------------------------------------------
    results, blocked = gates.run_all(cv, m)
    o.append('## GUARDRAILS (dry run)')
    o.append('')
    o.append('```')
    o.append(gates.fmt(results))
    o.append('```')
    o.append('')
    if blocked:
        o.append(f"**{len(blocked)} BLOCKING failure(s) — `jl build` will refuse until fixed.**")
        o.append('')

    # ---- questions ----------------------------------------------------
    # A GAP means "no anchor records this", NOT "you have not done this". The
    # truth layer was built from a CV that under-described the work, so every
    # application surfaces facts that exist only in the subject's head. Asking
    # is how the system gets better; reporting a gap and moving on is how it
    # stays wrong. (2026-08-21: reported gaps for drawing acceptance, AGE and
    # investigation oversight, all of which turned out to be real experience.)
    unknown = [r for r in m['requirements']
               if r['match'] in ('GAP', 'PARTIAL') and r.get('resolved_from') is None]
    if unknown:
        o.append('## QUESTIONS FOR YOU — no anchor records these')
        o.append('')
        o.append('Each line is evidence the truth layer does not hold. If you have done it, '
                 'say so and it becomes an anchor for every future CV.')
        o.append('')
        for r in unknown[:14]:
            best = ', '.join(a['id'] for a in r['anchors'][:2]) or 'nothing close'
            o.append(f"- **#{r['n']} [{r['match']}]** {r['text'][:120]}")
            o.append(f"      closest evidence: {best} ({r['best']:.2f})"
                     + (f" · {r['note'][:70]}" if r.get('note') else ''))
        o.append('')

    # ---- flags --------------------------------------------------------
    o.append('## FLAGS')
    o.append('')
    flags = []
    for r in recs:
        if r.get('render') == 'blocked_pending_validation':
            flags.append(f"- `{r['id']}` available but blocked: {r.get('boundary','')[:120]}")
        if r.get('confidence', 1.0) < 0.85 and r['id'] in used:
            flags.append(f"- `{r['id']}` used at confidence {r.get('confidence')} — verify wording")
    prof = store.profile()
    for k, v in (prof.get('links') or {}).items():
        if not v and not k.startswith('_'):
            flags.append(f"- profile link `{k}` is empty — omitted from the document")

    # Profile-class notes (work authorisation, location, language) are raised
    # ONLY when the advert actually gates on them. Flagging work authorisation
    # on a JD that never mentions it is noise, and noise in this section trains
    # the reader to skip the flags that matter.
    if any(r.get('gate_type') == 'profile' for r in m.get('requirements', [])):
        wa = (prof.get('location') or {}).get('work_authorisation') or {}
        if wa.get('_open_question'):
            flags.append(f"- work authorisation is a stated requirement here — "
                         f"{wa['_open_question'][:150]}")
    if m['hard_gate_gaps']:
        flags.append(f"- **{len(m['hard_gate_gaps'])} hard-gate requirement(s) cannot be met.** "
                     "Decide whether to apply anyway.")
    o.extend(flags or ['- none'])
    o.append('')
    o.append('---')
    if phase == 'release':
        o.append('')
        o.append('**Approval provenance:** the complete CV was reviewed and approved in chat '
                 'before this document was rendered.')
        return '\n'.join(o)
    o.append('')
    o.append(f"**Present in chat:** `jl present {slug}` · after explicit user sign-off: "
             f"`jl approve {slug} --reviewer <name> --all-pass --user-signoff`, then `jl build {slug}`   ·   "
             f"**Re-frame:** `jl plan {slug} --identity <name>`   ·   "
             "**Correct facts:** update the truth record, run `jl check`, then plan again")
    return '\n'.join(o)
