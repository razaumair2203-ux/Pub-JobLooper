"""Output invariants for the CV pipeline.

test_gates.py proves the guardrails refuse bad claims. It says nothing about
what a good CV must CONTAIN. Typical regressions include a professional
credential silently deleted, an achievement ranked out, a qualification
lane-filtered away, or a whole role disappearing and leaving an employment gap.

Every one was found by eye, after the document was built. Each fix was correct
and none of them stopped the next change re-breaking something else -- which is
the definition of patching.

These assert what must be TRUE OF THE BUILT DOCUMENT, so a weighting change
that quietly drops a credential fails here instead of reaching a recruiter.

    python tests/test_pipeline.py            (exit 1 on any failure)
"""
import sys, os, json, re, glob, tempfile

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'examples', 'starter')
os.environ.setdefault('JOBLOOPER_DATA_DIR', FIXTURE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import (build, cover_letter, employer_review, gates, language, match,
                  preview, render, store)

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    return ok


def build_cv(slug, pages=3, identity=None):
    d = store.job_dir(slug)
    jd = store.read_json(os.path.join(d, 'jd.json'))
    jd['_slug'] = slug
    ident = match.pick_identity(jd, override=identity)
    m = match.match_jd(jd, ident)
    return jd, m, build.assemble(jd, m, target_pages=pages)


def rendered(cv):
    """(all anchor ids on the page, bullet anchor ids, plain text)."""
    ids, bullets = [], []
    for s in cv['sections']:
        for it in s['items']:
            if it.get('anchor'):
                ids.append(it['anchor'])
            for b in it.get('bullets', []):
                ids.append(b['anchor'])
                bullets.append(b['anchor'])
    return ids, bullets, render.to_ats_text(cv)


def main():
    by_id, recs = store.anchors()
    jobs = store.list_jobs()
    if not jobs:
        print('  no jobs to test against — run `jl ingest` first')
        return 0
    slug = jobs[-1]
    jd, m, cv = build_cv(slug)
    ids, bullets, text = rendered(cv)
    idset = set(ids)

    check('configured output language is carried into the CV',
          cv.get('language') == (store.profile().get('output') or {}).get(
              'language', 'en-US'))
    check('configured US spelling is deterministic',
          language.localize('Modernisation programme recognised organisationally',
                            'en-US') ==
          'Modernization program recognized organizationally')
    check('section labels use the configured output language',
          all('PROGRAMME' not in section.get('name', '') for section in cv['sections']))

    check('configured default page policy is authoritative',
          build.assemble(jd, m)['target_pages'] ==
          store.sections().get('default_pages'))

    # --- chronology: a missing role reads as a concealed gap ---------------
    roles = [r for r in recs if r.get('type') == 'role'
             and r.get('kind') not in ('umbrella', 'education_period')]
    shown = {i['anchor'] for s in cv['sections'] if s['type'] == 'experience'
             for i in s['items']}
    missing_roles = [r['id'] for r in roles if r['id'] not in shown]
    check('every role appears (no employment gap)', not missing_roles, ', '.join(missing_roles))

    # --- professional credentials are never optional -----------------------
    prof = [r['id'] for r in recs if r.get('tier') == 'professional' and not r.get('render')]
    lost = [p for p in prof if p not in idset]
    check('every professional credential renders', not lost, ', '.join(lost))

    # --- every DIRECT classification must survive the last mile -------------
    direct = [r for r in m['requirements'] if r.get('match') == 'DIRECT']
    invisible = [str(r['n']) for r in direct
                  if r.get('anchors') and not any(a['id'] in idset for a in r['anchors'])]
    check('every DIRECT requirement has visible evidence',
          not invisible, ', '.join(invisible))

    # --- render directives are honoured ------------------------------------
    leaked = [a for a in bullets if by_id.get(a, {}).get('render')]
    check('no render-directive anchor appears as a bullet', not leaked, ', '.join(leaked))

    # --- nothing renders twice ---------------------------------------------
    dupes = sorted({a for a in bullets if bullets.count(a) > 1})
    check('no anchor renders twice', not dupes, ', '.join(dupes))

    # --- tailored credentials are a selection, not the master inventory ----
    cited = set()
    for s in cv['sections']:
        for it in s['items']:
            if it.get('anchor'):
                cited.add(it['anchor'])
            cited.update(it.get('anchors') or [])
    shown_creds = [c for c in cited if by_id.get(c, {}).get('type') == 'credential']
    spec = store.read_json(store.p('truth', 'sections.json'), {})
    default_cap = next(s['max'] for s in spec['sections'] if s['id'] == 'certifications')
    cap = spec.get('lanes', {}).get(cv['identity'], {}).get('caps', {}).get(
        'certifications', default_cap)
    check('credential selection respects the lane cap', len(shown_creds) <= cap,
          f'{len(shown_creds)} > {cap}')
    irrelevant = [c for c in shown_creds if by_id[c].get('tier') != 'professional'
                  and cv['identity'] not in by_id[c].get('identity', [])
                  and '*' not in by_id[c].get('identity', [])
                  and not m.get('anchor_usage', {}).get(c)]
    check('non-professional credentials are lane/JD relevant', not irrelevant,
          ', '.join(irrelevant))

    grouped_coursework = [i for s in cv['sections']
                          if s['name'] == 'CERTIFICATIONS'
                          for i in s['items'] if 'CRED-008' in (i.get('anchors') or [])]
    check('verified coursework survives as one compact cited line',
          len(grouped_coursework) == 1)

    check('role-depth evidence reaches impact selection without literal JD retrieval',
          'MRO-002' in bullets and not m.get('anchor_usage', {}).get('MRO-002'))

    # --- the governed career story is chronological, complete and unique ----
    featured = [r['id'] for r in recs if r.get('placement') == 'highlights'
                and (cv['identity'] in r.get('identity', [])
                     or '*' in r.get('identity', []))]
    highlight_section = next(s for s in cv['sections']
                             if s['name'] == 'CAREER HIGHLIGHTS & RECOGNITION')
    highlight_ids = [i.get('anchor') for i in highlight_section['items']]
    expected_ids = [r['id'] for r in sorted(
        (r for r in recs if r['id'] in featured),
        key=lambda r: (r['highlight_sequence'], r['id']))]
    check('every governed career highlight is preserved in sequence',
          highlight_ids == expected_ids, f'{highlight_ids} != {expected_ids}')
    check('career highlights do not repeat in role bullets',
           not (set(featured) & set(bullets)),
           ', '.join(sorted(set(featured) & set(bullets))))

    positioning_supports = set(next(
        (r.get('supports', []) for r in recs
         if r.get('type') == 'positioning'
         and cv['identity'] in r.get('identity', [])), []))
    unjustified_significant = [row['id'] for row in
        cv.get('_selection', {}).get('omitted', [])
        if row.get('significant') and not row.get('requirements')
        and row['id'] not in positioning_supports]
    check('significant omissions are tied to the JD or positioning evidence',
          not unjustified_significant, ', '.join(unjustified_significant))

    supported_item = highlight_section['items'][0]
    original_anchors = supported_item.get('anchors')
    supported_item['anchors'] = [supported_item['anchor'], 'SYS-001']
    evidence_map = preview.render(jd, m, cv, slug)
    supported_item['anchors'] = original_anchors
    check('review map exposes every supporting highlight citation',
          f"[{supported_item['anchor']}], [SYS-001]" in evidence_map)

    check('external output replaces governed platform aliases',
          'Falcon-R' not in text and 'Orion-X' not in text)

    exp_spec = next(s for s in spec['sections'] if s['id'] == 'experience')
    role_caps = exp_spec['max_per_role']
    experience = next(s for s in cv['sections'] if s['type'] == 'experience')
    over_role_cap = [item['anchor'] for n, item in enumerate(experience['items'])
                     if len(item['bullets']) > role_caps[min(n, len(role_caps) - 1)]]
    check('role descriptions stay within complementary evidence caps',
          not over_role_cap, ', '.join(over_role_cap))
    core_map = (exp_spec.get('core_by_lane') or {}).get(cv['identity'], {})
    out_of_order = []
    for item in experience['items']:
        expected = [anchor_id for anchor_id in core_map.get(item['anchor'], [])
                    if anchor_id in {b['anchor'] for b in item['bullets']}]
        actual = [b['anchor'] for b in item['bullets'][:len(expected)]]
        if actual != expected:
            out_of_order.append(f"{item['anchor']}:{actual}!={expected}")
    check('governed role evidence renders in its declared order',
          not out_of_order, '; '.join(out_of_order))

    # --- readability: a bullet past ~34 words is skipped, not read ----------
    # G8 had been reporting "17 bullet(s) over 34 words" on every build as a
    # WARN, and nobody read it. Page count must change the NUMBER of bullets,
    # never their length.
    longb = []
    for s in cv['sections']:
        if s['type'] != 'experience':
            continue
        for it in s['items']:
            for b in it['bullets']:
                if len(b['text'].split()) > 34:
                    longb.append(f"{b['anchor']}:{len(b['text'].split())}w")
    check('no rendered bullet exceeds 34 words', not longb, ', '.join(longb[:6]))

    # --- education is complete ---------------------------------------------
    edu = [r['id'] for r in recs if r.get('type') == 'education' and not r.get('render')]
    lost_e = [e for e in edu if e not in idset]
    check('every degree renders', not lost_e, ', '.join(lost_e))

    # --- recognition stays attached to the stage it validates --------------
    merged_rec = [r['id'] for r in recs if r.get('type') == 'recognition'
                  and str(r.get('render') or '').startswith('merge:')]
    check('merged recognition remains independently cited',
          set(merged_rec) <= cited,
          ', '.join(sorted(set(merged_rec) - cited)))

    # --- publications ------------------------------------------------------
    pubs = [r['id'] for r in recs if r.get('type') == 'publication'
            and r.get('status') == 'PUBLISHED' and not r.get('render')]
    shown_p = [p for p in pubs if p in idset]
    jd_blob = ' '.join(r['text'] for r in jd.get('requirements', [])).lower()
    research_relevant = cv['identity'] in (
        'systems_engineer', 'rd_technical_lead', 'analyst_governance') or any(
        x in jd_blob for x in ('research', 'publication', 'academic', 'phd', 'patent'))
    expected_publications = len(pubs) if research_relevant else 0
    check('every eligible publication survives protected retention',
          len(shown_p) == expected_publications,
          f'{len(shown_p)} shown; expected {expected_publications} of {len(pubs)}')

    # --- every hard gate is assessed ---------------------------------------
    unassessed = [r['n'] for r in m['requirements']
                  if r.get('hard_gate') and not r.get('match')]
    check('every hard gate is assessed', not unassessed, str(unassessed))

    # --- summary is present and anchored -----------------------------------
    summ = next((s for s in cv['sections'] if s['name'] == 'PROFESSIONAL SUMMARY'), None)
    ok_s = bool(summ and summ['items'] and
                by_id.get(summ['items'][0]['anchor'], {}).get('type') == 'positioning')
    check('summary renders from a positioning anchor', ok_s)
    summary_spec = next(s for s in spec['sections'] if s['id'] == 'summary')
    summary_text = summ['items'][0]['text']
    check('summary obeys the configured one-paragraph word contract',
          summary_spec['min_words'] <= len(summary_text.split()) <= summary_spec['max_words'])
    original_summary = summ['items'][0]['text']
    summ['items'][0]['text'] = 'Systems engineer.'
    summary_details = gates.g8_document(cv)[2]
    summ['items'][0]['text'] = original_summary
    check('undersized summary is blocked by the document gate',
          any('professional summary is' in detail and 'contract is' in detail
              for detail in summary_details))

    chosen_variant = build._claim_variant({
        'short': 'Engineering tools',
        'std': 'Engineering drawings — AutoCAD and CATIA',
        'long': 'Engineering drawings and controlled design evidence — AutoCAD and CATIA',
    }, 'short', 12, 'AutoCAD CATIA engineering drawings')
    check('JD selection chooses an approved variant that exposes served terms',
          chosen_variant == 'Engineering drawings — AutoCAD and CATIA')
    guarded_variant = build._claim_variant({
        'short': 'Engineering tools',
        'std': 'Engineering drawings — AutoCAD and CATIA',
        'long': 'Engineering drawings and controlled design evidence — AutoCAD and CATIA',
    }, 'short', 12, 'AutoCAD CATIA engineering drawings', min_gain=1.0)
    check('richer wording is rejected when its relevance gain is immaterial',
          guarded_variant == 'Engineering tools')
    check('controlled link labels preserve professional brand capitalisation',
          render._display_link('linkedin', 'linkedin.com/in/example').startswith('LinkedIn:')
          and render._display_link('github', 'github.com/example').startswith('GitHub:'))

    # --- cover letter reuses only already-governed CV evidence -------------
    letter = cover_letter.assemble(jd, m, cv)
    check('cover letter validates against the exact CV and JD',
          not cover_letter.validate(letter, jd, cv))
    with tempfile.TemporaryDirectory(prefix='joblooper-docx-stable-') as rendered_dir:
        first = os.path.join(rendered_dir, 'first.docx')
        second = os.path.join(rendered_dir, 'second.docx')
        render.to_docx(cv, first)
        render.to_docx(cv, second)
        check('identical CV input produces byte-identical DOCX output',
              store.sha256_file(first) == store.sha256_file(second))
    visible_source_texts = {
        source
        for paragraph in letter['paragraphs']
        for source in paragraph.get('source_texts', [])
    }
    check('cover letter has no independent candidate-fact stream',
          bool(visible_source_texts)
          and all(source in render.to_markdown(cv) for source in visible_source_texts))
    check('cover letter action fragments are grammatical first-person prose',
          all(not re.search(r'\. (Led|Mentors|Acted|Managed|Leads)\b',
                            paragraph['text'])
              for paragraph in letter['paragraphs']))

    # --- rejection-risk review must earn a CV change -----------------------
    risk = employer_review.assess(jd, m, cv)
    check('risk review leaves a fully selected evidence plan unchanged',
          risk['decision'] == 'LEAVE_AS_IS'
          and not risk['improvement_candidates'])
    check('risk semantics separate JD priority from prediction confidence',
          risk['_schema'] == employer_review.RISK_SCHEMA
          and all(row.get('requirement_label') in {
              'HARD GATE', 'REQUIRED', 'RESPONSIBILITY', 'PREFERRED'}
                  for row in risk['risks'])
          and all('confidence' not in row and 'cv_addressable' not in row
                  for row in risk['risks'])
          and all('counterevidence_anchor_ids' not in row
                  for row in risk['leading_objections']))
    invalid_context = {
        '_schema': employer_review.CONTEXT_SCHEMA,
        'job_url': jd.get('url'), 'researched_at': '2026-01-01',
        'sources': [{'kind': 'exact_job', 'url': jd.get('url'),
                     'observation': 'Exact fictional job captured.'}],
        'findings': [{'basis': 'INFERRED', 'confidence': 'LOW',
                      'risk': 'Speculative risk', 'anchor_ids': ['UNKNOWN']}],
        'cv_decision': 'REPLAN', 'decision_reason': 'Decorative change',
        'proposed_changes': [],
    }
    check('unsupported employer context cannot trigger decorative replanning',
          bool(employer_review.validate_context(invalid_context, jd, set(by_id))))

    # --- traceability of every line ----------------------------------------
    orphan = [a for a in ids if a not in by_id]
    check('every rendered line cites a live anchor', not orphan, ', '.join(orphan))

    education_item = next(i for s in cv['sections'] if s['name'] == 'EDUCATION'
                          for i in s['items'] if i.get('anchor') == 'EDU-001')
    original_education = education_item['text']
    education_item['text'] = 'Bachelor of Engineering — Example University | 2014'
    education_details = gates.g8_document(cv)[2]
    education_item['text'] = original_education
    check('an education period cannot close chronology unless its years are visible',
          any('education chronology for ROLE-002' in detail
              for detail in education_details))

    # --- lane switching actually changes the document ----------------------
    _, _, cv2 = build_cv(slug, identity='mro_sustainment')
    ids2, _, _ = rendered(cv2)
    check('a different lane produces a different document',
          set(ids2) != idset, f'{len(set(ids2) ^ idset)} anchors differ')

    # --- one-page build still holds the invariants -------------------------
    _, _, cv1 = build_cv(slug, pages=1)
    ids1, b1, _ = rendered(cv1)
    shown1 = {i['anchor'] for s in cv1['sections'] if s['type'] == 'experience'
              for i in s['items']}
    check('one-page build still shows every role',
          all(r['id'] in shown1 for r in roles),
          ', '.join(r['id'] for r in roles if r['id'] not in shown1))
    check('one-page build renders no anchor twice',
          len(b1) == len(set(b1)))

    # --- report ------------------------------------------------------------
    w = max(len(n) for n, _, _ in RESULTS)
    fails = 0
    print()
    for name, ok, detail in RESULTS:
        if not ok:
            fails += 1
        print(f"  {'ok ' if ok else 'FAIL'}  {name:{w}}" + (f'   {detail}' if detail and not ok else ''))
    print(f"\n  {len(RESULTS) - fails}/{len(RESULTS)} invariants hold"
          + (f', {fails} FAILED' if fails else '') + f'   (job: {slug})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
