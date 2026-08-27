"""Assemble everything about one application into a single reviewable dossier.

Built for the moment a decision arrives. A rejection is only informative if you
can put the advert, the exact document that was sent, what it answered, what it
left out, and the surrounding context side by side. Reconstructing that from
memory weeks later is where the learning loop usually dies.

Deliberately assembles FACTS and leaves the reasoning to the conversation. It
will not guess why a decision went the way it did -- it lays out what is
knowable so the two of us can argue about it from the same evidence.
"""
import os, re
from . import store, vec, render, release, gates

# Signals an advert gives about who it is really open to. These are read from
# the employer's own words, never inferred about a person.
_LOCALISATION = re.compile(
    r'\b(saudi(s|z)ation|emirati(s|z)ation|omani(s|z)ation|qatari(s|z)ation|'
    r'bahraini(s|z)ation|kuwaiti(s|z)ation|nationali(s|z)ation programme|'
    r'national (capability|talent|development)|local (content|hire|talent)|'
    r'preference will be given|nationals? only|citizens? only)\b', re.I)
_SPONSORSHIP = re.compile(
    r'\b(visa sponsorship|sponsor(ship)? (is )?(available|provided|offered)|'
    r'expatriate|expat|relocation (package|assistance|support)|'
    r'work permit will be|no sponsorship|unable to sponsor)\b', re.I)
_CLEARANCE = re.compile(
    r'\b(security clearance|SC clearance|DV clearance|baseline personnel|'
    r'export control|ITAR|EAR|official sensitive|government approval)\b', re.I)


def context_signals(raw):
    """What the advert itself says about openness, sponsorship and clearance."""
    def hits(pat):
        return sorted({m.group(0).strip() for m in pat.finditer(raw or '')})
    return {
        'localisation': hits(_LOCALISATION),
        'sponsorship': hits(_SPONSORSHIP),
        'clearance_or_export': hits(_CLEARANCE),
    }


def build(slug):
    """Return the full dossier as a dict."""
    d = store.job_dir(slug)
    app = next((a for a in store.applications() if a['app_id'] == slug), None)
    snapshot_errors = []
    release_id = (app or {}).get('release_id')
    release_dir, manifest = release.load_release(slug) if app else (None, None)

    def snapshot_json(label, fallback):
        info = ((manifest or {}).get('files') or {}).get(label)
        if release_dir and info:
            return store.read_json(os.path.join(release_dir, info['file'])) or {}
        return store.read_json(os.path.join(d, fallback)) or {}

    def snapshot_text(label, fallback):
        info = ((manifest or {}).get('files') or {}).get(label)
        if release_dir and info:
            return store.read_text(os.path.join(release_dir, info['file']))
        return store.read_text(os.path.join(d, fallback))

    jd = snapshot_json('jd', 'jd.json')
    m = snapshot_json('match', 'match.json')
    cv = snapshot_json('cv', 'cv.json')
    letter = snapshot_json('letter', 'cover-letter.json')
    risk = snapshot_json('risk', 'employer-risk.json')
    raw = snapshot_text('jd_raw', 'jd.raw.md')
    if app:
        _, snapshot_errors = release.verify_submission(slug)
    by_id, recs = store.anchors()
    release_files = []
    submission = (store.read_json(release.record_path(release_dir, release.SUBMISSION_NAME), {})
                  if release_dir else {}) or {}
    for label, info in ((manifest or {}).get('files') or {}).items():
        release_files.append({
            'label': label, 'file': info.get('file'), 'sha256': info.get('sha256'),
            'bytes': info.get('bytes'),
            'sent': info.get('file') in {
                submission.get('sent_file'), submission.get('sent_cover_letter')},
        })
    correlated_ids = {slug, *(jd.get('_legacy_slugs') or [])}
    events = [e for e in store.application_events()
              if e.get('app_id') in correlated_ids]
    responses = store.read_jsonl(os.path.join(d, 'responses.jsonl'))

    used = set((cv.get('_selection') or {}).get('selected_ids') or [])
    lines = []
    for line in gates._line_records(cv, {gates.CLAIM, gates.HEADLINE}):
        used.update(line['ids'])
        lines.append((line['section'], ','.join(line['ids']), line['text'],
                      line['serves']))

    omitted = [r for r in recs
               if r.get('type') in ('anchor', 'credential', 'publication', 'recognition', 'skill')
               and r['id'] not in used and not r.get('render')]

    # Nearest past applications, so a pattern can be seen rather than guessed.
    bm = vec.job_index()
    near = []
    if bm:
        q = ' '.join([jd.get('title', '')] + [r['text'] for r in jd.get('requirements', [])])
        by_app = {a['app_id']: a for a in store.applications()}
        for s2, sc in bm.normed(q, top=8):
            if s2 == slug:
                continue
            o = by_app.get(s2, {})
            near.append({'slug': s2, 'similarity': sc, 'status': o.get('status', 'not applied'),
                         'identity': o.get('identity'), 'company': o.get('company'),
                         'hypotheses': o.get('hypotheses', [])})
        near = near[:5]

    return {
        'slug': slug, 'company': cv.get('company'), 'role': cv.get('role'),
        'url': jd.get('url'), 'applied': (app or {}).get('applied'),
        'responded': (app or {}).get('responded'), 'status': (app or {}).get('status', 'not applied'),
        'days': (app or {}).get('days'),
        'response_latency': (app or {}).get('response_latency') or {},
        'channel': (app or {}).get('channel'),
        'cv_sha': (app or {}).get('cv_sha'),
        'sent_file': (app or {}).get('sent_file') or submission.get('sent_file'),
        'sent_cover_letter': ((app or {}).get('sent_cover_letter')
                              or submission.get('sent_cover_letter')),
        'screening_evidence': ((app or {}).get('screening_evidence')
                               or submission.get('screening_evidence')),
        'submission_mode': (app or {}).get('submission_mode'),
        'release_id': release_id, 'release_manifest': manifest,
        'release_files': release_files, 'snapshot_errors': snapshot_errors,
        'events': events,
        'employer_responses': responses,
        'profile_context': cv.get('_profile_context') or {},
        'identity': cv.get('identity'), 'identity_ranked': cv.get('identity_ranked', []),
        'coverage': m.get('coverage'), 'spread': m.get('spread', {}),
        'requirements': m.get('requirements', []),
        'employer_risk_decision': risk.get('decision'),
        'employer_risk_reason': risk.get('decision_reason'),
        'cover_letter_words': len(' '.join(
            paragraph.get('text', '') for paragraph in letter.get('paragraphs', [])
        ).split()) if letter else 0,
        'hard_gates': [r for r in m.get('requirements', []) if r.get('hard_gate')],
        'gaps': m.get('gaps', []),
        'behavioural': m.get('n_behavioural'),
        'lines': lines, 'omitted': omitted,
        'signals': context_signals(raw),
        'near': near,
        'stated_reason': (app or {}).get('stated_reason'),
        'hypotheses': (app or {}).get('hypotheses', []),
        'ats_text_words': len(render.to_ats_text(cv).split()) if cv else 0,
    }


def markdown(c):
    o = [f"# CASE FILE — {c['company']} · {c['role']}", '',
         f"`{c['slug']}`", '']
    o += ['## DECISION TIMELINE', '',
          f"- status    : **{c['status']}**",
          f"- applied   : {c['applied'] or '(date not provided)'}   "
          f"channel: {c['channel'] or '(not provided)'}",
          f"- responded : {c['responded']}" + (f"  ({c['days']} days)" if c['days'] is not None else ''),
          f"- latency   : {(c.get('response_latency') or {}).get('band', 'unknown')} "
          f"({(c.get('response_latency') or {}).get('basis', 'not provided')})",
          f"- CV sent   : `{c['sent_file'] or 'package content not separately identified'}` · "
          f"SHA `{c['cv_sha']}` · package `{c.get('release_id') or 'legacy/unknown'}` · "
          f"{c['ats_text_words']} words extracted",
          f"- letter sent: `{c['sent_cover_letter'] or 'not recorded as submitted'}` · "
          f"{c['cover_letter_words']} words in approved snapshot",
          f"- portal answers: `{(c.get('screening_evidence') or {}).get('file', 'not captured')}`",
          f"- advert    : {c['url'] or '(not recorded)'}", '']
    if c.get('employer_risk_decision'):
        o += [f"- pre-application risk decision: **{c['employer_risk_decision']}** — "
              f"{c.get('employer_risk_reason') or '(reason not recorded)'}", '']
    if c.get('snapshot_errors'):
        o += ['> **Snapshot warning:** ' + '; '.join(c['snapshot_errors']), '']
    if c['stated_reason']:
        o += [f"- their words: *\"{c['stated_reason']}\"*", '']

    if c.get('release_manifest'):
        manifest = c['release_manifest']
        o += ['## EXACT SUBMISSION ARTIFACTS', '',
              f"Package **{manifest.get('package_id', manifest.get('release_id'))}** · manifest `{manifest.get('manifest_sha256')}`", '',
              '| purpose | file | SHA-256 |', '|---|---|---|']
        for item in c['release_files']:
            purpose = item['label'] + (' **(sent)**' if item.get('sent') else '')
            o.append(f"| {purpose} | `{item['file']}` | `{item['sha256']}` |")
        o.append('')

    if c.get('events'):
        o += ['## CASE EVENT TIMELINE', '']
        for event in c['events']:
            o.append(f"- {event.get('timestamp')} · **{event.get('event')}**"
                     + (f" · {event.get('status')}" if event.get('status') else ''))
        o.append('')

    if c.get('employer_responses'):
        o += ['## EMPLOYER RESPONSE CORRELATION', '',
              '_Deterministic identifiers and the immutable submitted package; no inferred cause._', '']
        for response in c['employer_responses']:
            o.append(f"- **{response.get('response_id')}** · {response.get('received')} · "
                     f"{response.get('status')} · raw SHA-256 `{response.get('raw_sha256')}`")
            o.append('  - matched by: ' + '; '.join(response.get('match_evidence') or []))
            o.append(f"  - submitted manifest: `{response.get('submitted_manifest_sha256')}`")
            o.append('  - employer-stated reason: '
                     + (response.get('employer_stated_reason') or '_none explicitly stated_'))
        o.append('')

    o += ['## WHAT THE ADVERT SIGNALLED', '',
          '_Read from the employer\'s own wording, not inferred about you._', '']
    sig = c['signals']
    for k, label in [('localisation', 'Local-hire / nationalisation policy'),
                     ('sponsorship', 'Sponsorship / expatriate posture'),
                     ('clearance_or_export', 'Clearance or export control')]:
        o.append(f"- **{label}**: " + (', '.join(f'`{x}`' for x in sig[k]) if sig[k] else '_no signal_'))
    o.append('')

    profile = c.get('profile_context') or {}
    o += ['## PROFILE CONTEXT AT SUBMISSION', '',
          '_Snapshotted with the submitted CV; later profile changes are not borrowed._', '',
          f"- Based in: {profile.get('city') or profile.get('based_in') or '_not recorded_'}"]
    work_auth = profile.get('work_authorisation') or {}
    o.append('- Work authorisation / mobility: '
             + (work_auth.get('phrasing_gcc') or work_auth.get('phrasing_default')
                or '_not recorded_'))
    if profile.get('availability_note'):
        o.append('- Availability: ' + profile['availability_note'])
    for language, assessment in (profile.get('languages') or {}).items():
        o.append(f"- Language · {language}: {assessment.get('classification')} — "
                 f"{assessment.get('note', '')}")
    for name, assessment in (profile.get('eligibility') or {}).items():
        o.append(f"- Eligibility · {name.replace('_', ' ')}: "
                 f"{assessment.get('classification')} — {assessment.get('note', '')}")
    o.append('')

    o += [f"## LOCAL EVIDENCE COVERAGE AT SUBMISSION — {c['coverage']:.0%} weighted heuristic" if c['coverage'] is not None
          else '## FIT AS ASSESSED AT THE TIME', '',
          '  ' + ' · '.join(f'{k} {v}' for k, v in c['spread'].items() if v),
          f"  lane chosen: `{c['identity']}`",
          f"  behavioural requirements excluded from scoring: {c['behavioural']}", '']

    if c['hard_gates']:
        o += ['### Hard gates', '']
        for r in c['hard_gates']:
            o.append(f"- **{r['match']}** — {r['text'][:120]}")
            if r.get('note'):
                o.append(f"      {r['note'][:110]}")
        o.append('')
    if c['gaps']:
        o += ['### Not answered', '']
        for g in c['gaps']:
            o.append(f"- {g['text'][:120]}")
        o.append('')

    o += ['## WHAT WAS ACTUALLY SENT', '']
    sec = None
    for s, a, t, srv in c['lines']:
        if s != sec:
            o += ['', f"**{s}**", '']
            sec = s
        served = ', '.join(f'req#{n}' for n in srv) or '—'
        o.append(f"- [{a}] {t[:150]}")
        o.append(f"      serves: {served}")
    o.append('')

    o += [f"## HELD BACK ({len(c['omitted'])} anchors available and not used)", '']
    for r in c['omitted'][:25]:
        o.append(f"- [{r['id']}] {(r.get('fact') or '')[:110]}")
    if len(c['omitted']) > 25:
        o.append(f"- …and {len(c['omitted']) - 25} more")
    o.append('')

    if c['near']:
        o += ['## NEAREST PAST APPLICATIONS', '']
        for n in c['near']:
            h = ((n['hypotheses'][0].get('cause') or n['hypotheses'][0].get('cat'))
                 if n['hypotheses'] else '—')
            o.append(f"- {n['similarity']:.2f}  {n['company'] or n['slug'][:40]:28} "
                     f"{n['status']:12} lane={n['identity']} top-cause={h}")
        o.append('')

    if c['hypotheses']:
        o += ['## REJECTION HYPOTHESES — versioned, not facts', '']
        for n, hypothesis in enumerate(c['hypotheses'], 1):
            hid = hypothesis.get('id', f"legacy-{n}")
            cause = hypothesis.get('cause') or hypothesis.get('cat', 'NO_SIGNAL')
            confidence = hypothesis.get('confidence', hypothesis.get('conf', 0.5))
            status = hypothesis.get('status', 'OPEN')
            summary = hypothesis.get('summary', hypothesis.get('note', ''))
            o.append(f"### {hid} · {cause} · {status} · {confidence:.0%}")
            o.append('')
            o.append(summary or '_No reasoning note recorded._')
            o.append('')
            for revision in hypothesis.get('revisions') or []:
                o.append(f"- round {revision.get('round', '?')} · "
                         f"{revision.get('stage', 'LEGACY')} · "
                         f"{revision.get('at')} · {revision.get('author')} · "
                         f"{revision.get('confidence', 0):.0%}: {revision.get('note', '')}")
                if revision.get('evidence_for'):
                    o.append('  - supports: ' + '; '.join(revision['evidence_for']))
                if revision.get('evidence_against'):
                    o.append('  - challenges: ' + '; '.join(revision['evidence_against']))
                if revision.get('company_context'):
                    o.append('  - company context: ' + '; '.join(revision['company_context']))
                if revision.get('profile_factors'):
                    o.append('  - profile factors: ' + '; '.join(revision['profile_factors']))
                if revision.get('other_factors'):
                    o.append('  - other factors: ' + '; '.join(revision['other_factors']))
                if revision.get('unknowns'):
                    o.append('  - unresolved unknowns: ' + '; '.join(revision['unknowns']))
            o.append('')

    o += ['## QUESTIONS TO REASON THROUGH', '',
          'The dossier states facts. These are the things worth arguing about:', '',
          '1. Did the decision turn on a stated requirement, or on something the advert never named?',
          '2. Which held-back anchor, if any, would have changed the answer?',
          '3. Was the lane right? A different framing ranks different evidence.',
          '4. Do the advert signals above (local-hire policy, sponsorship, clearance) explain more',
          '   than the CV content does?',
          '5. Does this match a pattern in the nearest past applications, or is it a one-off?', '']
    return '\n'.join(o)
