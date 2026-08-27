#!/usr/bin/env python
"""Joblooper — JD in, defensible CV out, rejections that teach.

  jl init
  jl doctor
  jl ingest <file|-> --company X --title Y [--url U]
  jl plan   <job> [--identity NAME] [--pages N]
  jl present <job>                  # show every CV section in chat
  jl approve <job> --reviewer NAME --all-pass --user-signoff
  jl build  <job> [--no-pdf]
  jl artifacts <job>
  jl submit <job> --sent-file <approved-folder/CV.pdf> [--channel portal]
  jl response <file|-> [--job KEY]     # correlate an employer email
  jl outcome <job> --status rejected [--reason "..."] [--cat HARD_GATE]
  jl reason <job> [--cause CATEGORY --note "..."]
  jl ask    "<question>"
  jl verify <job>
  jl dashboard                         # local read-only application command view
  jl jobs | jl anchors [query] | jl sources | jl check | jl context

Every command is a thin shell over core/. If something misbehaves, the state it
acted on is a flat file you can open and read.
"""
import sys, os, argparse, re, json, csv, shutil, subprocess, tempfile

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='strict')
        except (OSError, ValueError):
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (store, vec, match, build, preview, gates, render, casefile,
                  integrity, release, learning, feedback, employer_response,
                  cover_letter, employer_review, preflight, truth_review,
                  dashboard as dashboard_ui)

FAIL_CATS = ['HARD_GATE', 'SENIORITY_MISMATCH', 'DOMAIN_TRANSLATION', 'ATS_KEYWORD',
             'EVIDENCE_DEPTH', 'NARRATIVE_COHERENCE', 'LOCATION_VISA', 'COMPENSATION',
             'TIMING_INTERNAL', 'NO_SIGNAL']


def say(*a):
    print(*a, flush=True)


def require_truth_integrity(action):
    context = store.truth_context()
    problems, _, _ = integrity.check_truth()
    if problems:
        raise SystemExit(f"{action} REFUSED — truth/configuration has "
                         f"{len(problems)} integrity error(s); run `jl check`")
    readiness = truth_review.readiness()
    if not readiness['ready']:
        raise SystemExit(
            f"{action} REFUSED — candidate truth is not currently approved: "
            + '; '.join(readiness['problems'])
            + "; run `jl truth audit`, resolve comments, then `jl onboard finalize`")
    return context


# ---------------------------------------------------------------- ingest

def cmd_init(args):
    """Create a blocked real workspace, or an explicit fictional demo."""
    target = store.DATA_ROOT
    anchor_file = os.path.join(target, 'truth', 'anchors.jsonl')
    if os.path.exists(anchor_file):
        release.write_dashboard()
        say(f"already initialized  {target}")
        say("  no files changed")
        return 0

    starter = store.code_p('examples', 'starter')
    if not os.path.isfile(os.path.join(starter, 'truth', 'anchors.jsonl')):
        raise SystemExit(f"Starter data is missing from {starter}")
    collisions = [name for name in ('truth', 'work', 'jobs', 'index')
                  if os.path.exists(os.path.join(target, name))]
    if collisions:
        raise SystemExit('INIT REFUSED — existing runtime path(s): ' + ', '.join(collisions))
    os.makedirs(target, exist_ok=True)
    if args.demo:
        for name in ('truth', 'index'):
            shutil.copytree(os.path.join(starter, name), os.path.join(target, name))
        shutil.copytree(os.path.join(starter, 'jobs'), os.path.join(target, 'work'))
        os.makedirs(os.path.join(target, 'jobs'), exist_ok=False)
    else:
        truth = os.path.join(target, 'truth')
        os.makedirs(truth, exist_ok=False)
        for filename in ('boundaries.json', 'aliases.json', 'sections.json'):
            shutil.copy2(os.path.join(starter, 'truth', filename),
                         os.path.join(truth, filename))
        # Demo identities, role IDs and negative evidence must never leak into
        # a real candidate configuration. Keep only schema mechanics that are
        # safe before the candidate's own review populates them.
        section_path = os.path.join(truth, 'sections.json')
        base_sections = store.read_json(section_path, {}) or {}
        for section in base_sections.get('sections') or []:
            if section.get('source') == 'role_bullets':
                section.pop('core_by_lane', None)
                section.pop('core_by_role', None)
            section.pop('protected_if_lane', None)
            if section.get('include_if'):
                section['include_if']['lane'] = []
        base_sections['lanes'] = {}
        store.write_json(section_path, base_sections)
        alias_path = os.path.join(truth, 'aliases.json')
        base_aliases = store.read_json(alias_path, {}) or {}
        base_aliases['groups'] = []
        base_aliases['boost_terms'] = {}
        store.write_json(alias_path, base_aliases)
        boundary_path = os.path.join(truth, 'boundaries.json')
        base_boundaries = store.read_json(boundary_path, {}) or {}
        base_boundaries['person_identity'] = {'excluded_domains': []}
        base_boundaries['forbidden_patterns'] = []
        base_boundaries['status_words'] = {}
        disclosure = base_boundaries.setdefault('disclosure', {})
        disclosure['external_aliases'] = []
        disclosure['restricted_patterns'] = [
            {'pattern': '(?i)\\b(classified|top secret|export[- ]controlled)\\b',
             'reason': 'Restricted content requires explicit candidate review.'}]
        store.write_json(boundary_path, base_boundaries)
        store.write_json(os.path.join(truth, 'profile.json'), {
            '_schema': 'joblooper.profile.v1',
            'ready_for_generation': False,
            '_onboarding': {
                'state': 'NEEDS_REVIEW',
                'instruction': 'Review candidate identity, sources and atomic facts before enabling generation.',
            },
            'name': '', 'contact': {}, 'location': {}, 'languages': {},
            'eligibility': {}, 'links': {}, 'career': {}, 'identities': {},
            'headlines': {},
            'identity_rule': 'Exactly one primary identity per tailored CV.',
        })
        for filename in ('anchors.jsonl', 'sources.jsonl', 'changelog.jsonl'):
            store.write_text(os.path.join(truth, filename), '')
        for name in ('index', 'work', 'jobs'):
            os.makedirs(os.path.join(target, name), exist_ok=False)
        for filename in ('application_events.jsonl', 'applications.jsonl'):
            store.write_text(os.path.join(target, 'index', filename), '')
    release.write_dashboard()
    say(f"initialized  {target}")
    if args.demo:
        say("  explicit DEMO mode: fictional starter profile and example job installed")
        say("  never use demo output for a real application")
    else:
        say("  empty real workspace created; generation is BLOCKED pending onboarding")
        say("  next: use Codex with $joblooper to review sources into atomic truth")


def cmd_doctor(args):
    """Report installation and data health without changing anything."""
    checks = []
    checks.append(('Python', sys.version_info >= (3, 10),
                   '.'.join(str(x) for x in sys.version_info[:3]) + ' (3.10+ required)'))
    checks.append(('Data directory', os.path.isdir(store.DATA_ROOT), store.DATA_ROOT))
    repo_class = store.read_repository_policy().get('classification')
    data_rule = ('governed private-Git data and writable' if repo_class == 'PERSONAL_PRIVATE'
                 else 'outside the installed public skill and writable')
    checks.append(('Data writable', os.path.isdir(store.DATA_ROOT) and os.access(store.DATA_ROOT, os.W_OK),
                   data_rule))
    checks.append(('Truth layer', os.path.isfile(store.p('truth', 'anchors.jsonl')),
                   store.p('truth', 'anchors.jsonl')))
    initialized = os.path.isfile(store.p('truth', 'anchors.jsonl'))
    if initialized:
        problems, warnings, stats = integrity.check_truth()
    else:
        problems, warnings, stats = [], [], {'records': 0}
    checks.append(('Truth integrity', not problems,
                   f"{stats['records']} records; {len(problems)} errors; {len(warnings)} warnings"))
    readiness = truth_review.readiness() if initialized else {
        'ready': False, 'problems': ['workspace not initialized'], 'audit_overdue': False}
    checks.append(('Candidate sign-off', readiness['ready'],
                   ('digest-bound and current' if readiness['ready'] else
                    '; '.join(readiness['problems']))))
    if readiness.get('audit_overdue'):
        checks.append(('Periodic truth audit', False,
                       f"review due {readiness.get('audit_due')}; run `jl truth audit`"))
    for name, ok, detail in checks:
        say(f"  [{'PASS' if ok else 'WARN':4}] {name:17} {detail}")
    pdf_ok, pdf_detail = render.pdf_capability()
    say(f"  [{'PASS' if pdf_ok else 'INFO':4}] PDF export        {pdf_detail}")
    blocking = [c for c in checks if not c[1]]
    if blocking:
        say("\nDoctor found a blocking setup problem.")
        if not os.path.isfile(store.p('truth', 'anchors.jsonl')):
            say("Run `python jl.py init` to create a blocked real workspace, or "
                "`python jl.py init --demo` for fictional testing.")
        return 1
    say("\nSystem is ready. Use `jl build --no-pdf` when PDF capability is unavailable.")
    return 0


def cmd_onboard(args):
    """Inspect or explicitly close candidate-ground-truth onboarding."""
    profile_path = store.p('truth', 'profile.json')
    profile = store.read_json(profile_path, {}) or {}
    _, anchors = store.anchors()
    sources = store.read_jsonl(store.p('truth', 'sources.jsonl'))
    problems, warnings, _ = integrity.check_truth()
    readiness = truth_review.readiness()
    if args.action == 'status':
        say(f"onboarding  {'READY' if readiness['ready'] else 'BLOCKED'}")
        say(f"  candidate  {profile.get('name') or '(not recorded)'}")
        say(f"  anchors    {len(anchors)}")
        say(f"  sources    {len(sources)}")
        say(f"  integrity  {len(problems)} error(s), {len(warnings)} warning(s)")
        for problem in readiness['problems']:
            say(f"  review     {problem}")
        return 0 if readiness['ready'] and not problems else 1

    if not args.confirm_reviewed:
        raise SystemExit(
            'ONBOARDING REFUSED — --confirm-reviewed is required after the user reviews '
            'identity, every broad-source disposition, atomic facts and boundaries')
    if not str(args.reviewer or '').strip():
        raise SystemExit('ONBOARDING REFUSED — --reviewer is required')
    if problems:
        raise SystemExit(
            f'ONBOARDING REFUSED — truth/configuration has {len(problems)} integrity error(s)')
    if not str(profile.get('name') or '').strip() or not anchors or not sources:
        raise SystemExit(
            'ONBOARDING REFUSED — candidate name, at least one atomic anchor and one '
            'registered source are required')
    pending = truth_review.open_items()
    if pending:
        raise SystemExit('ONBOARDING REFUSED — resolve open truth comments first: '
                         + ', '.join(item['id'] for item in pending))
    profile['ready_for_generation'] = True
    profile['_onboarding'] = {
        'state': 'REVIEWED', 'reviewer': str(args.reviewer).strip(),
        'reviewed_at': store.now(),
    }
    store.write_json(profile_path, profile)
    store.reset_context_cache()
    profile['_truth_approval'] = truth_review.approval_record(args.reviewer)
    store.write_json(profile_path, profile)
    store.reset_context_cache()
    store.log_change(
        'candidate onboarding',
        'Confirmed reviewed candidate identity, sources, atomic facts and boundaries.',
        'Enabled deterministic generation from the governed truth layer.',
        affected=['truth/profile.json', 'truth/anchors.jsonl',
                  'truth/sources.jsonl', 'truth/boundaries.json'])
    say('onboarding  READY')
    say(f"  reviewer   {profile['_onboarding']['reviewer']}")
    say(f"  truth      {profile['_truth_approval']['subject_sha256'][:12]} digest-bound")
    say(f"  audit due  {profile['_truth_approval']['next_audit_due']}")
    say('  next:      jl doctor')
    return 0


def cmd_truth(args):
    """Record candidate comments and audit the only generation authority."""
    if args.action == 'status':
        state = truth_review.readiness()
        say(f"truth      {'READY' if state['ready'] else 'NEEDS REVIEW'}")
        say(f"  digest    {state['current_subject_sha256']}")
        say(f"  comments  {len(state['open_comments'])} open")
        say(f"  audit due {state.get('audit_due') or 'not scheduled'}")
        for problem in state['problems']:
            say(f"  - {problem}")
        return 0 if state['ready'] else 1
    if args.action == 'comment':
        try:
            item = truth_review.record(args.scope, args.note, args.author, args.evidence)
        except ValueError as error:
            raise SystemExit(f'TRUTH COMMENT REFUSED — {error}')
        say(f"truth comment  {item['id']} · {item['scope']} · OPEN")
        say('  generation is blocked until the comment is resolved')
        return 0
    if args.action == 'resolve':
        try:
            item = truth_review.resolve(
                args.item_id, args.status, args.implementation, args.validation)
        except ValueError as error:
            raise SystemExit(f'TRUTH RESOLUTION REFUSED — {error}')
        say(f"truth comment  {item['id']} · {item['status']}")
        if item['status'] == 'ADOPTED':
            say('  candidate sign-off is invalidated; audit and re-finalize after truth changes')
        return 0
    report = truth_review.audit()
    out_json = store.p('index', 'TRUTH-AUDIT.json')
    out_md = store.p('index', 'TRUTH-AUDIT.md')
    store.write_json(out_json, report)
    store.write_text(out_md, truth_review.to_markdown(report))
    say(truth_review.to_markdown(report))
    say(f"\nfull audit: {os.path.abspath(out_md)}")
    return 1 if report['integrity_errors'] else 0


# ---------------------------------------------------------------- ingest

def cmd_ingest(args):
    raw = sys.stdin.read() if args.file == '-' else store.read_text(args.file)
    if not raw.strip():
        raise SystemExit('Empty JD text.')

    company = str(args.company or '').strip()
    title = str(args.title or '').strip()
    if not company or not title:
        raise SystemExit(
            'INGEST REFUSED — exact company and job title are required; do not infer '
            'identity fields from advert prose')

    # Short, stable keys are easier to navigate and discuss. Prefer the
    # employer's reference number from the URL; otherwise company + title is
    # sufficient. A suffix is added only for a genuinely different collision.
    reference = None
    if args.url:
        found = re.search(r'(?<!\d)(\d{6,})(?:[/?#-]|$)', args.url)
        reference = found.group(1) if found else None
    key = reference or store.slugify(title)
    base_slug = (f"{store.slugify(company)}--{key}")[:80]
    slug = base_slug
    d = store.job_dir(slug)
    if os.path.isdir(d):
        existing = store.read_text(os.path.join(d, 'jd.raw.md'))
        if existing == raw:
            say(f"already ingested  {slug} (identical JD; nothing overwritten)")
            return 0
        seq = 2
        while os.path.exists(store.job_dir(f"{base_slug}-{seq}")):
            seq += 1
        slug = f"{base_slug}-{seq}"
        d = store.job_dir(slug)
    os.makedirs(d, exist_ok=True)

    jd = match.parse_jd(raw, title=title, company=company, url=args.url,
                        job_reference=reference)
    jd['_slug'] = slug
    jd['raw_sha256'] = store.sha256_text(raw)
    store.write_json(os.path.join(d, 'jd.json'), jd)
    store.write_text(os.path.join(d, 'jd.raw.md'), raw)
    store.append_application_event({
        'event': 'JOB_INGESTED', 'app_id': slug, 'company': company, 'role': title,
        'jd_raw_sha256': jd['raw_sha256'], 'requirements': len(jd['requirements']),
    })
    release.write_dashboard()

    hard = sum(1 for r in jd['requirements'] if r['hard_gate'])
    say(f"ingested  {slug}")
    say(f"  {len(jd['requirements'])} requirements ({hard} hard-gate) from {jd['raw_chars']} chars")
    say(f"  next: jl plan {slug}")


# ---------------------------------------------------------------- plan

def cmd_preflight(args):
    """Ask material candidate questions before assembling either document."""
    require_truth_integrity('PREFLIGHT')
    slug = store.resolve_job(args.job)
    d = store.job_dir(slug)
    jd = store.read_json(os.path.join(d, 'jd.json')) or {}
    jd['_slug'] = slug
    try:
        identity = match.pick_identity(jd, override=args.identity)
    except ValueError as error:
        raise SystemExit(f'PREFLIGHT REFUSED — {error}')
    mapping = match.match_jd(jd, identity)
    rows = preflight.questions(jd, mapping, identity)
    report = preflight.to_markdown(jd, identity, rows)
    store.write_text(os.path.join(d, 'PRE-GENERATION-QUESTIONS.md'), report)
    say(report)
    if rows and not args.user_reviewed:
        say('Review these questions with the user before generation. Then rerun with '
            '--user-reviewed --reviewer <name> --note "<what was decided>".')
        return 1
    try:
        record = preflight.create(
            slug, jd, mapping, identity,
            reviewer=args.reviewer if args.user_reviewed else None,
            note=args.note if args.user_reviewed else None)
    except ValueError as error:
        raise SystemExit(f'PREFLIGHT REFUSED — {error}')
    say(f"preflight  {record['decision']} · {record['subject_sha256'][:12]}")
    say(f"  next: jl plan {slug}"
        + (f" --identity {args.identity}" if args.identity else ''))
    return 0

def cmd_plan(args):
    context = require_truth_integrity('PLAN')
    pages = args.pages or int(store.sections().get('default_pages', 3))
    slug = store.resolve_job(args.job)
    d = store.job_dir(slug)
    jd = store.read_json(os.path.join(d, 'jd.json'))
    if not jd:
        raise SystemExit(f"No jd.json in {d}. Run `jl ingest` first.")
    jd['_slug'] = slug

    try:
        ident = match.pick_identity(jd, override=args.identity)
    except ValueError as error:
        raise SystemExit(f"PLAN REFUSED — {error}")
    m = match.match_jd(jd, ident)
    preflight_record, preflight_errors, material_questions = preflight.validate(
        slug, jd, m, ident)
    if preflight_errors and not material_questions:
        preflight.create(slug, jd, m, ident)
        preflight_record, preflight_errors, _ = preflight.validate(slug, jd, m, ident)
    if preflight_errors:
        report = preflight.to_markdown(jd, ident, material_questions)
        store.write_text(os.path.join(d, 'PRE-GENERATION-QUESTIONS.md'), report)
        raise SystemExit(
            'PLAN REFUSED — ' + '; '.join(preflight_errors)
            + f"; run `jl preflight {slug}` and review its questions with the user")
    m['_preflight'] = {
        'subject_sha256': preflight_record['subject_sha256'],
        'decision': preflight_record['decision'],
        'reviewer': preflight_record['reviewer'],
    }
    m['learning_signals'] = learning.relevant_lessons(jd, exclude_slug=slug)
    m['positive_outcome_signals'] = learning.relevant_positive_outcomes(
        jd, exclude_slug=slug)
    m['_inputs'] = store.generation_fingerprint(jd)
    cv = build.assemble(jd, m, target_pages=pages)
    context_path = os.path.join(d, 'EMPLOYER-CONTEXT.json')
    employer_context = store.read_json(context_path, {}) or None
    try:
        letter = cover_letter.assemble(jd, m, cv)
        risk = employer_review.assess(
            jd, m, cv, employer_context,
            raw_text=store.read_text(os.path.join(d, 'jd.raw.md')))
    except ValueError as error:
        raise SystemExit(f"PLAN REFUSED — {error}")
    if store.truth_context()['truth_sha256'] != context['truth_sha256']:
        raise SystemExit('PLAN REFUSED — truth changed during planning; run the command again')

    try:
        retired = release.invalidate_unsubmitted_package(
            slug, 'a new deterministic plan superseded the approved unsubmitted package')
    except ValueError as error:
        raise SystemExit(f"PLAN REFUSED — {error}")

    store.write_json(os.path.join(d, 'match.json'), m)
    store.write_json(os.path.join(d, 'cv.json'), cv)
    store.write_json(os.path.join(d, 'cover-letter.json'), letter)
    store.write_json(os.path.join(d, 'employer-risk.json'), risk)
    store.write_text(os.path.join(d, 'EMPLOYER-RISK.md'),
                     employer_review.to_markdown(risk, employer_context))
    store.write_text(os.path.join(d, 'PREVIEW.md'), preview.render(jd, m, cv, slug))
    release.write_status(slug, 'PLAN')
    store.append_application_event({
        'event': 'PLAN_CREATED', 'app_id': slug,
        'plan_sha256': release.plan_digest(slug), 'inputs_sha256': m['_inputs']['sha256'],
        'truth_context_sha256': context['truth_sha256'], 'identity': ident['primary'],
        'coverage': cv['coverage'],
    })

    results, blocked = gates.run_all(cv, m)
    say(f"planned   {slug}")
    if retired:
        say("  removed   stale approved unsubmitted folder")
    say(f"  identity  {ident['primary']}"
        + ('  (override)' if ident['overridden'] else f"  (auto, {ident['confidence']:.2f})"))
    sp = m.get('spread', {})
    visible = m.get('document') or {}
    say(f"  evidence coverage  {cv['coverage']:.0%} local weighted heuristic  ·  "
        + '  '.join(f"{k[:4]} {v}"
                   for k, v in visible.get('spread', sp).items() if v))
    say(f"  employer  {risk['decision']} — {risk['decision_reason']}")
    if m['hard_gate_gaps']:
        say(f"  HARD GAPS {len(m['hard_gate_gaps'])}:")
        for g in m['hard_gate_gaps']:
            say(f"            #{g['n']} {g['text'][:80]}")
    say(gates.fmt(results))
    cut = cv.get('_trimmed') or []
    if cut:
        say(f"  TRIMMED to fit {pages} pages ({len(cut)} item(s), lowest impact first):")
        for a, sc, txt in cut:
            say(f"            {sc:6}  [{a}] {txt}")
    say(f"  audit:    {os.path.abspath(os.path.join(d, 'PREVIEW.md'))}")
    say(f"  then:     jl present {slug}" if not blocked
        else f"  BLOCKED:  fix {len(blocked)} gate failure(s) before build")


# ---------------------------------------------------------------- present

def cmd_present(args):
    """Print the exact CV and cover letter for chat review; render nothing."""
    slug = store.resolve_job(args.job)
    try:
        content, record = release.present(slug)
    except ValueError as e:
        raise SystemExit(f"PRESENTATION REFUSED — {e}")
    say(content)
    say("\n---")
    say(f"CHAT REVIEW  {record['content_sha256'][:12]} · "
        f"{record['document_count']} documents · {record['section_count']} CV sections")
    say(f"Employer-risk decision: {record['risk_decision']}")
    say("No DOCX or PDF has been created. Await explicit user sign-off on both documents.")
    say(f"After sign-off: jl approve {slug} --reviewer <name> --all-pass --user-signoff")


# ---------------------------------------------------------------- approve

def cmd_approve(args):
    """Record explicit human/model judgment against the exact current plan."""
    slug = store.resolve_job(args.job)
    judgments = {}
    if args.all_pass:
        judgments = {g: 'PASS' for g in release.MANUAL_GATES}
    for value in args.judgment or []:
        if '=' not in value:
            raise SystemExit("--judgment must be GATE=PASS")
        gate, result = (x.strip().upper() for x in value.split('=', 1))
        if gate not in release.MANUAL_GATES or result != 'PASS':
            raise SystemExit(f"invalid judgment {value!r}; gate must be one of "
                             f"{', '.join(release.MANUAL_GATES)} and result PASS")
        judgments[gate] = result
    try:
        record = release.approve(slug, args.reviewer, judgments, args.note or '',
                                 user_signoff=args.user_signoff)
    except ValueError as e:
        raise SystemExit(f"APPROVAL REFUSED — {e}")
    say(f"approved  {slug}")
    say(f"  reviewer  {record['reviewer']}")
    say(f"  plan      {record['plan_sha256'][:12]}")
    say(f"  folder    {os.path.abspath(store.approved_dir(slug))}")
    say(f"  next:     jl build {slug}")
    store.append_application_event({
        'event': 'PLAN_APPROVED', 'app_id': slug, 'reviewer': record['reviewer'],
        'plan_sha256': record['plan_sha256'], 'inputs_sha256': record['inputs_sha256'],
    })


# ---------------------------------------------------------------- feedback

def cmd_feedback(args):
    """Record or resolve user feedback without silently changing truth."""
    slug = store.resolve_job(args.job)
    try:
        # Validate first. A typo or incomplete resolution must never remove a
        # valid approved-but-unsubmitted package.
        if args.feedback_id:
            feedback.validate_resolution(
                slug, args.feedback_id, args.status,
                args.implementation, args.validation)
        else:
            feedback.validate_record(args.scope, args.note)
        retired = release.invalidate_unsubmitted_package(
            slug, 'user feedback invalidated the approved unsubmitted package')
        if args.feedback_id:
            item = feedback.resolve(
                slug, args.feedback_id, args.status,
                args.implementation, args.validation)
            say(f"resolved   {item['id']} · {item['status']}")
        else:
            item = feedback.record(
                slug, args.scope, args.note, args.author,
                plan_sha256=release.plan_digest(slug))
            say(f"recorded   {item['id']} · {item['scope']} · OPEN")
    except ValueError as e:
        raise SystemExit(f"FEEDBACK REFUSED — {e}")
    release.write_status(slug, 'PLAN')
    if retired:
        say("  removed   stale approved unsubmitted folder")
    say("  chat presentation and approval are now stale")
    say(f"  next: resolve feedback, re-plan if adopted, then `jl present {slug}`")


# ---------------------------------------------------------------- build

def cmd_build(args):
    require_truth_integrity('BUILD')
    slug = store.resolve_job(args.job)
    d = store.job_dir(slug)
    jd = store.read_json(os.path.join(d, 'jd.json'))
    cv = store.read_json(os.path.join(d, 'cv.json'))
    m = store.read_json(os.path.join(d, 'match.json'))
    letter = store.read_json(os.path.join(d, 'cover-letter.json'))
    risk = store.read_json(os.path.join(d, 'employer-risk.json'))
    if not jd or not cv or not m or not letter or not risk:
        raise SystemExit(f"Incomplete plan in {d}. Run `jl plan {slug}` first.")

    approval, approval_errors = release.validate_approval(slug)

    results, blocked = gates.run_all(cv, m)
    say(gates.fmt(results))
    # Deterministic truth, coverage and presentation failures are never
    # overridable. --force is reserved for a disclosed page-fit exception after
    # the exact content has passed every safety and approval gate.
    safety_blocks = ([f"{gid}_{name}: {summ}" for gid, name, lvl, summ, _ in blocked]
                     + approval_errors)
    if safety_blocks:
        say(f"\nBUILD REFUSED — {len(safety_blocks)} non-overridable safety failure(s).")
        for problem in safety_blocks:
            say(f"  - {problem}")
        return 1
    override_used = False

    # Build products live only in isolated staging until copied into the dated
    # folder. TemporaryDirectory guarantees cleanup even when rendering or
    # release creation raises unexpectedly.
    with tempfile.TemporaryDirectory(prefix='joblooper-build-') as staging:
        return _finish_build(
            args, slug, d, jd, cv, m, letter, risk, approval, results,
            override_used, staging)


def _finish_build(args, slug, d, jd, cv, m, letter, risk, approval, results,
                  override_used, staging):
    """Render and release a validated plan inside an auto-cleaned staging dir."""
    docx = os.path.join(staging, 'CV.docx')
    render.to_docx(cv, docx)
    letter_document = cover_letter.to_render_document(letter)
    letter_docx = os.path.join(staging, 'COVER-LETTER.docx')
    render.to_docx(letter_document, letter_docx)

    pdf = None
    letter_pdf = None
    pdf_note = None
    letter_pdf_note = None
    if not args.no_pdf:
        converted, converted_letter = render.to_pdfs([
            (docx, None), (letter_docx, None)])
        if isinstance(converted, str):
            pdf = converted
        else:
            pdf_note = converted[1]
        if isinstance(converted_letter, str):
            letter_pdf = converted_letter
        else:
            letter_pdf_note = converted_letter[1]

    pages = render.pdf_pages(pdf) if pdf else None
    target = cv.get('target_pages', 2)
    layout_problems = []
    if pages and pages > target:
        layout_problems.append(f"rendered {pages} pages; approved target is {target}")
    if pages:
        say(f"  [FIT  ] rendered {pages} page(s), target {target}")

    render_lvl, render_summary, render_details = gates.verify_rendered(docx, cv=cv, pdf_path=pdf)
    say(f"  [{render_lvl:5}] G9 RENDERED         {render_summary}")
    for x in render_details:
        say(f"           - {x}")
    if render_lvl == gates.BLOCK:
        say("\nBUILD REFUSED — rendered-file integrity failures are non-overridable.")
        for problem in render_details:
            say(f"  - {problem}")
        return 1
    letter_lvl, letter_summary, letter_details = gates.verify_rendered(
        letter_docx, cv=letter_document, pdf_path=letter_pdf)
    say(f"  [{letter_lvl:5}] G9 COVER LETTER     {letter_summary}")
    for x in letter_details:
        say(f"           - {x}")
    if letter_lvl == gates.BLOCK:
        say("\nBUILD REFUSED — rendered cover-letter integrity failures are non-overridable.")
        for problem in letter_details:
            say(f"  - {problem}")
        return 1
    letter_pages = render.pdf_pages(letter_pdf) if letter_pdf else None
    if letter_pages and letter_pages > 1:
        layout_problems.append(f"cover letter rendered {letter_pages} pages; target is 1")
    if layout_problems and not args.force:
        say("\nBUILD REFUSED — rendered output exceeds the approved page target.")
        for problem in layout_problems:
            say(f"  - {problem}")
        return 1
    if layout_problems and args.force:
        try:
            release.log_override(slug, 'build-layout', args.reason, layout_problems)
        except ValueError as e:
            raise SystemExit(f"BUILD REFUSED — {e}")
        override_used = True

    md = os.path.join(staging, 'CV.md')
    ats = os.path.join(staging, 'CV-ATS.txt')
    letter_md = os.path.join(staging, 'COVER-LETTER.md')
    letter_ats = os.path.join(staging, 'COVER-LETTER-ATS.txt')
    review_path = os.path.join(staging, 'EVIDENCE.md')
    audit_path = os.path.join(staging, 'GATE-AUDIT.csv')
    feedback_path = os.path.join(staging, 'FEEDBACK.json')
    store.write_text(md, render.to_markdown(cv))
    store.write_text(ats, render.to_ats_text(cv))
    store.write_text(letter_md, cover_letter.to_markdown(letter))
    store.write_text(letter_ats, render.to_ats_text(letter_document))
    store.write_text(review_path, preview.render(jd, m, cv, slug, phase='release'))
    store.write_json(feedback_path, {
        '_schema': 'joblooper.feedback-snapshot.v1',
        'app_id': slug, 'digest': feedback.digest(slug),
        'items': feedback.current(slug),
    })

    audit = []
    for i, (gid, name, lvl, summ, det) in enumerate(results, 1):
        audit.append({'gate_order': i, 'gate': f'{gid}_{name}', 'result': lvl,
                      'evidence_or_notes': summ, 'corrective_action': '; '.join(det)[:500]})
    audit.append({'gate_order': len(audit) + 1, 'gate': 'G9_RENDERED', 'result': render_lvl,
                  'evidence_or_notes': render_summary,
                  'corrective_action': '; '.join(render_details)[:500]})
    audit.append({'gate_order': len(audit) + 1, 'gate': 'G9_COVER_LETTER',
                  'result': letter_lvl, 'evidence_or_notes': letter_summary,
                  'corrective_action': '; '.join(letter_details)[:500]})
    audit.append({'gate_order': len(audit) + 1, 'gate': 'LAYOUT',
                  'result': (gates.BLOCK if layout_problems else
                             gates.PASS if pages else gates.WARN),
                  'evidence_or_notes': f'{pages or "unknown"} page(s), target {target}',
                  'corrective_action': '; '.join(layout_problems)})
    judgments = (approval or {}).get('judgments', {})
    for name in release.MANUAL_GATES:
        audit.append({'gate_order': len(audit) + 1, 'gate': name,
                      'result': judgments.get(name, 'FORCED' if args.force else 'MISSING'),
                      'evidence_or_notes': (approval or {}).get('note', ''),
                      'corrective_action': ''})
    with open(audit_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'gate_order', 'gate', 'result', 'evidence_or_notes', 'corrective_action'])
        writer.writeheader()
        writer.writerows(audit)

    artefacts = {
        'jd': os.path.join(d, 'jd.json'), 'jd_raw': os.path.join(d, 'jd.raw.md'),
        'match': os.path.join(d, 'match.json'),
        'cv': os.path.join(d, 'cv.json'), 'preview': review_path,
        'letter': os.path.join(d, 'cover-letter.json'),
        'risk': os.path.join(d, 'employer-risk.json'),
        'risk_markdown': os.path.join(d, 'EMPLOYER-RISK.md'),
        'employer_context': os.path.join(d, 'EMPLOYER-CONTEXT.json'),
        'approval': os.path.join(d, 'approval.json'), 'docx': docx, 'pdf': pdf,
        'markdown': md, 'ats': ats,
        'letter_docx': letter_docx, 'letter_pdf': letter_pdf,
        'letter_markdown': letter_md, 'letter_ats': letter_ats,
        'audit': audit_path,
        'presentation': os.path.join(d, release.PRESENTATION_NAME),
        'feedback': feedback_path,
        'oversight': os.path.join(d, 'OVERSIGHT.md'),
    }
    release_status = 'APPROVED_WITH_DISCLOSED_GAP' if override_used else 'APPROVED'
    release_dir, manifest = release.create_release(
        slug, artefacts, status=release_status,
        metadata={'layout': {
            'cv_pages': pages, 'cv_target_pages': target, 'cv_pdf_note': pdf_note,
            'cover_letter_pages': letter_pages, 'cover_letter_target_pages': 1,
            'cover_letter_pdf_note': letter_pdf_note,
        }})
    say(f"\nbuilt     {os.path.basename(docx)}")
    if pdf:
        say(f"          {os.path.basename(pdf)}")
    elif pdf_note:
        say(f"          PDF skipped: {pdf_note}")
    say(f"          {os.path.basename(letter_docx)}")
    if letter_pdf:
        say(f"          {os.path.basename(letter_pdf)}")
    elif letter_pdf_note:
        say(f"          cover-letter PDF skipped: {letter_pdf_note}")
    say(f"          approved application package [{release_status}]")
    say(f"          {os.path.abspath(release_dir)}")
    say(f"  open:    jl artifacts {slug}")
    say("  submit:  jl submit <job> --sent-file <this-folder/CV.pdf-or-CV.docx>")
    return 0


# ---------------------------------------------------------------- apply

def cmd_apply(args):
    slug = store.resolve_job(args.job)
    d = store.job_dir(slug)
    prior = next((a for a in store.applications() if a['app_id'] == slug), None)
    if prior:
        raise SystemExit('APPLY REFUSED - this application is already recorded as submitted')

    sent_file = getattr(args, 'sent_file', None)
    if not sent_file:
        raise SystemExit(
            'APPLY REFUSED - --sent-file is mandatory; select the exact approved CV.pdf or CV.docx')
    supplied_date = getattr(args, 'date', None)
    if supplied_date:
        import datetime
        try:
            applied_date = datetime.date.fromisoformat(supplied_date).isoformat()
        except ValueError:
            raise SystemExit('APPLY REFUSED - --date must use YYYY-MM-DD')
        if applied_date > store.today():
            raise SystemExit('APPLY REFUSED - submission date cannot be in the future')
    else:
        applied_date = None
    channel = getattr(args, 'channel', None)

    try:
        recorder = (release.record_confirmed_external_submission
                    if getattr(args, 'confirm_external', False)
                    else release.record_submission)
        release_dir, manifest, submission = recorder(
            slug, sent_file, cover_letter_file=getattr(args, 'cover_letter_file', None),
            channel=channel, applied_date=applied_date,
            screening_file=getattr(args, 'screening_file', None))
    except ValueError as error:
        raise SystemExit(f'APPLY REFUSED - {error}')

    files = manifest.get('files') or {}
    cv_info, match_info = files.get('cv'), files.get('match')
    if not cv_info or not match_info:
        raise SystemExit('APPLY REFUSED — package lacks cv/match snapshot')
    cv = store.read_json(os.path.join(release_dir, cv_info['file']))
    m = store.read_json(os.path.join(release_dir, match_info['file']))
    exact_sha = submission['sent_sha256']

    rec = {
        'app_id': slug,
        'company': cv.get('company'),
        'role': cv.get('role'),
        'applied': applied_date,
        'applied_date_status': 'recorded' if applied_date else 'not_provided',
        'recorded_at': store.now(),
        'channel': channel,
        'submission_mode': submission.get('mode', 'exact_approved_artefact'),
        'sent_file': submission.get('sent_file'),
        'sent_cover_letter': submission.get('sent_cover_letter'),
        'screening_evidence': submission.get('screening_evidence'),
        'identity': cv.get('identity'),
        'release_id': 'approved',
        'package_id': manifest.get('package_id'),
        'release_manifest_sha256': manifest['manifest_sha256'],
        'accepted_at': manifest.get('approved_at'),
        'accepted_by': (store.read_json(release.record_path(
            release_dir, 'APPROVAL.json'), {}) or {})
                       .get('reviewer'),
        'jd_sha256': (files.get('jd') or {}).get('sha256'),
        'cv_docx_sha256': (files.get('docx') or {}).get('sha256'),
        'cv_sha': (exact_sha or '')[:12],
        'cv_sha256': exact_sha,
        'coverage': cv.get('coverage'),
        'hard_gaps': [g['text'][:80] for g in (m or {}).get('hard_gate_gaps', [])],
        'status': 'applied',
        'responded': None,
        'hypotheses': [],
        'submission_integrity_exceptions':
            submission.get('unsent_package_integrity_exceptions', []),
        'test_record': False,
        'exclude_from_analytics': False,
    }
    apps = [a for a in store.applications() if a['app_id'] != slug]
    apps.append(rec)
    store.write_jsonl(store.p('index', 'applications.jsonl'), apps)
    store.write_json(os.path.join(d, 'outcome.json'), rec)
    store.append_application_event({
        'event': 'APPLICATION_RECORDED', 'app_id': slug, 'release_id': 'approved',
        'package_id': manifest.get('package_id'),
        'channel': channel, 'record': rec,
    })
    say(f"submitted {slug} · {rec['company']} · {rec['applied'] or 'date not provided'}")
    say(f"  folder      {os.path.abspath(release_dir)}")
    say(f"  exact file  {submission['sent_file']} · {submission['sent_sha256'][:12]}")
    if submission.get('sent_cover_letter'):
        say(f"  exact letter {submission['sent_cover_letter']} · "
            f"{submission['sent_cover_letter_sha256'][:12]}")


# ---------------------------------------------------------------- outcome

def cmd_outcome(args):
    slug = store.resolve_job(args.job)
    d = store.job_dir(slug)
    apps = store.applications()
    rec = next((a for a in apps if a['app_id'] == slug), None)
    if not rec:
        raise SystemExit(f"'{slug}' was never applied to. Run `jl apply {slug}` first.")
    if not learning._exact_submission(rec):
        raise SystemExit(
            'OUTCOME REFUSED — application record is not bound to an exact submitted package')
    if args.cat and args.status not in learning.NEGATIVE_OUTCOMES:
        raise SystemExit(
            'OUTCOME REFUSED — rejection hypotheses apply only to rejected or ghosted outcomes')

    rec['status'] = args.status
    rec['responded'] = args.date or None
    rec['responded_date_status'] = 'recorded' if args.date else 'not_provided'
    latency = getattr(args, 'latency', None)
    rec['response_latency'] = {
        'band': latency or 'unknown',
        'basis': 'user_reported' if latency else 'not_provided',
    }
    if rec.get('applied') and rec.get('responded'):
        import datetime
        try:
            a = datetime.date.fromisoformat(rec['applied'])
            b = datetime.date.fromisoformat(rec['responded'])
        except ValueError:
            raise SystemExit('OUTCOME REFUSED — dates must use YYYY-MM-DD')
        if b < a:
            raise SystemExit('OUTCOME REFUSED — response date cannot precede submission date')
        rec['days'] = (b - a).days
    if args.reason:
        rec['stated_reason'] = args.reason
    if (args.reason or '').strip().lower() in {'test', 'probe'} or \
            (args.note or '').strip().lower() in {'test', 'probe'}:
        rec['test_record'] = True
        rec['exclude_from_analytics'] = True

    store.write_jsonl(store.p('index', 'applications.jsonl'),
                      [a for a in apps if a['app_id'] != slug] + [rec])
    store.write_json(os.path.join(d, 'outcome.json'), rec)
    package = store.approved_dir(slug)
    if package:
        store.write_json(release.record_path(package, 'OUTCOME.json', create=True), rec)
        _, package_manifest = release.load_release(slug)
        release.write_status(slug, 'SUBMITTED', package_manifest)
    store.append_application_event({
        'event': 'OUTCOME', 'app_id': slug, 'status': args.status,
        'responded': rec.get('responded'), 'stated_reason': rec.get('stated_reason'),
        'response_latency': rec.get('response_latency'),
        'hypotheses': rec.get('hypotheses', []),
    })
    if args.cat and not rec.get('test_record'):
        learning.record_hypothesis(
            slug, args.cat, args.conf, args.note or args.reason or args.cat,
            args.author, args.evidence_for, args.evidence_against)

    say(f"outcome   {slug} -> {args.status}"
        + (f" after {rec['days']}d" if rec.get('days') is not None else ''))
    say('')
    say('  Context for the post-mortem:')
    say(f"    submitted package {rec.get('package_id') or rec.get('release_id')} · manifest "
        f"{str(rec.get('release_manifest_sha256') or '')[:12]}")
    say(f"    identity  {rec.get('identity')}   evidence coverage {rec.get('coverage')}")
    if rec.get('hard_gaps'):
        say(f"    hard gaps {len(rec['hard_gaps'])}")
        for g in rec['hard_gaps']:
            say(f"              - {g}")

    bm = vec.job_index()
    if bm:
        jd = store.read_json(os.path.join(d, 'jd.json')) or {}
        q = ' '.join([jd.get('title', '')] + [r['text'] for r in jd.get('requirements', [])])
        near = [(s, sc) for s, sc in bm.normed(q, top=6) if s != slug][:5]
        if near:
            say('')
            say('  Nearest past applications:')
            by = {a['app_id']: a for a in apps}
            for s, sc in near:
                o = by.get(s, {})
                say(f"    {sc:.2f}  {s[:52]:52} {o.get('status','not applied'):12}"
                    f" {o.get('identity','')}")
    say('')
    if args.status in learning.NEGATIVE_OUTCOMES:
        say(f"  Discuss and save reasoning: jl reason {slug} "
            f"--cause <{'|'.join(FAIL_CATS[:4])}|...> --note \"...\"")
    elif args.status in learning.POSITIVE_OUTCOMES:
        say('  This exact advancing outcome will surface on sufficiently similar future jobs.')
        say('  It records what advanced, not why the employer advanced it.')
    else:
        say('  Outcome recorded; no causal lesson was inferred.')


def cmd_reason(args):
    """Show, add or revise a rejection explanation with an audit trail."""
    slug = store.resolve_job(args.job)
    if not args.cause and not args.hypothesis_id:
        rows = learning.hypotheses(slug)
        say(f"reasoning  {slug}")
        if not rows:
            say("  no hypotheses recorded")
        for row in rows:
            say(f"  {row['id']} [{row['status']}] {row['cause']}  "
                f"confidence {row['confidence']:.0%}")
            say(f"       {row.get('summary', '')}")
            say(f"       {len(row.get('revisions') or [])} reasoning revision(s)")
            next_stage = learning.ROUND_STAGES[min(
                len(row.get('revisions') or []), len(learning.ROUND_STAGES) - 1)]
            say(f"       next pass: {next_stage}")
        say(f"\nFull evidence dossier: jl case {slug}")
        return 0
    if not args.hypothesis_id and not args.cause:
        raise SystemExit('REASON REFUSED — --cause is required for a new hypothesis')
    try:
        row = learning.record_hypothesis(
            slug, args.cause, args.confidence, args.note, args.author,
            args.evidence_for, args.evidence_against,
            hypothesis_id=args.hypothesis_id, status=args.status.upper(),
            company_context=args.company_context,
            profile_factors=args.profile_factor,
            other_factors=args.other_factor, unknowns=args.unknown)
    except ValueError as error:
        raise SystemExit(f"REASON REFUSED — {error}")
    say(f"reasoning  {slug}")
    say(f"  {row['id']} [{row['status']}] {row['cause']}  confidence {row['confidence']:.0%}")
    say(f"  saved revision {len(row['revisions'])}: {row['summary']}")
    if row['status'] in {'CONFIRMED', 'RETAINED_PLAUSIBLE'}:
        say("  retained as a future review question; ground truth was not changed")
    else:
        next_stage = learning.ROUND_STAGES[min(
            len(row['revisions']), len(learning.ROUND_STAGES) - 1)]
        say(f"  next reasoning pass: {next_stage}")
    package = store.approved_dir(slug)
    if package:
        _, package_manifest = release.load_release(slug)
        release.write_status(slug, 'SUBMITTED', package_manifest)
    say(f"  next: jl case {slug}")
    return 0


# ---------------------------------------------------------------- employer response

def cmd_response(args):
    """Ingest an employer response only when one exact sent CV can be proven."""
    raw = sys.stdin.read() if args.file == '-' else store.read_text(args.file)
    if not raw.strip():
        raise SystemExit('RESPONSE REFUSED — employer response is empty or unreadable')
    try:
        selected, response, duplicate = employer_response.ingest(
            raw, explicit_job=args.job, explicit_status=args.status,
            received=args.date)
    except ValueError as error:
        raise SystemExit(f'RESPONSE REFUSED — {error}')

    slug = selected['slug']
    manifest = selected['manifest']
    package_dir, _ = release.load_release(slug, 'submitted')
    files = manifest.get('files') or {}
    jd_file = (files.get('jd_raw') or files.get('jd') or {}).get('file')
    cv_file = ((manifest.get('submission') or {}).get('sent_file')
               or (files.get('pdf') or files.get('docx') or files.get('ats') or {}).get('file'))
    dossier = casefile.markdown(casefile.build(slug))
    dossier_path = os.path.join(store.job_dir(slug), 'CASE.md')
    store.write_text(dossier_path, dossier)
    package_case = release.record_path(store.approved_dir(slug), 'CASE.md', create=True)
    store.write_text(package_case, dossier)
    release.write_status(slug, 'SUBMITTED', manifest)

    say(f"{'duplicate' if duplicate else 'correlated'} response {response['response_id']} -> {slug}")
    say(f"  company   {selected['jd'].get('company')}")
    say(f"  role      {selected['jd'].get('title')}")
    say(f"  matched   {'; '.join(response['match_evidence'])}")
    say(f"  status    {response['status']}")
    say(f"  JD        {os.path.join(package_dir, jd_file) if jd_file else 'missing'}")
    say(f"  CV sent   {os.path.join(package_dir, cv_file) if cv_file else 'missing'}")
    say(f"  manifest  {response['submitted_manifest_sha256']}")
    say(f"  stated reason  {response.get('employer_stated_reason') or 'none explicitly stated'}")
    say(f"  dossier   {dossier_path}")
    say('')
    if response['status'] == 'rejected':
        say('No rejection cause was invented. Discuss hypotheses, evidence, counter-evidence and unknowns,')
        say(f"then save each revision with `jl reason {slug} ...`.")
    else:
        say('The advancing outcome is recorded against the exact package and will surface for similar jobs.')
        say('It is evidence of progression, not evidence of why the employer progressed it.')


def cmd_lessons(args):
    """Show confirmed, reusable lessons and the cases that support them."""
    rows = learning.confirmed_lessons()
    say('RETAINED REVIEW SIGNALS — hypotheses, never career truth')
    if not rows:
        say('  none')
        return 0
    for row in rows:
        revision = (row.get('revisions') or [{}])[-1]
        say(f"  {row['app_id']} · {row['id']} · {row['cause']} · "
            f"{row['confidence']:.0%} · {row.get('company')} · {row.get('role')}")
        say(f"    {row.get('summary', '')}")
        for label, key in [('company', 'company_context'), ('profile', 'profile_factors'),
                           ('other', 'other_factors'), ('unknown', 'unknowns')]:
            values = revision.get(key) or []
            if values:
                say(f"    {label}: " + '; '.join(values))


def cmd_metrics(args):
    """Show deterministic lifecycle KPIs without treating outcomes as causes."""
    apps = [row for row in store.applications()
            if not row.get('test_record') and not row.get('exclude_from_analytics')]
    outcomes = [row for row in apps if row.get('status') not in {None, 'applied'}]
    negative = [row for row in outcomes
                if row.get('status') in learning.NEGATIVE_OUTCOMES]
    positive = [row for row in outcomes
                if row.get('status') in learning.POSITIVE_OUTCOMES]
    exact = sum(learning._exact_submission(row) for row in apps)
    screening = sum(bool(row.get('screening_evidence')) for row in apps)
    response_dates = sum(bool(row.get('responded')) for row in outcomes)
    timing_bands = sum(
        (row.get('response_latency') or {}).get('band') not in {None, 'unknown'}
        for row in outcomes)
    immediate = sum(
        (row.get('response_latency') or {}).get('band') == 'under_24h'
        for row in outcomes)
    retained = len(learning.confirmed_lessons())

    def ratio(value, denominator):
        return f"{value}/{denominator} ({value / denominator:.0%})" if denominator else '0/0'

    say('APPLICATION LEARNING KPIs - descriptive, not hiring probabilities')
    say(f"  applications                 {len(apps)}")
    say(f"  exact submission correlation {ratio(exact, len(apps))}")
    say(f"  portal-answer capture        {ratio(screening, len(apps))}")
    say(f"  outcomes recorded            {len(outcomes)}")
    say(f"  exact response date          {ratio(response_dates, len(outcomes))}")
    say(f"  response timing band         {ratio(timing_bands, len(outcomes))}")
    say(f"  under-24-hour outcomes       {ratio(immediate, len(outcomes))}")
    say(f"  progressed/interview/offer   {ratio(len(positive), len(outcomes))}")
    say(f"  rejected/ghosted             {ratio(len(negative), len(outcomes))}")
    say(f"  retained review signals      {retained}")
    companies = {str(row.get('company') or '').strip().lower() for row in apps}
    if len(apps) < 10 or len(companies) < 3:
        say('')
        say('  CAUTION: sample is too small or employer-concentrated for broad causal conclusions.')
    if apps and screening < len(apps):
        say('  NEXT: capture portal answers with `submit --screening-file`.')
    if immediate:
        say('  NEXT: audit eligibility/knockout answers and direct-context gates before CV polishing.')
    return 0


def cmd_dashboard(args):
    """Launch or inspect the local, read-only lifecycle dashboard."""
    if args.snapshot:
        say(dashboard_ui.snapshot_json())
        return 0
    return dashboard_ui.serve(port=args.port, open_browser=not args.no_open)


# ---------------------------------------------------------------- case

def cmd_case(args):
    """Assemble the full dossier for one application.

    Everything needed to reason about a decision in one place: the advert, the
    exact document sent, what it answered, what was held back, what the advert
    signalled about local-hire policy and sponsorship, and the nearest past
    applications. Facts only -- the argument is for the conversation.
    """
    slug = store.resolve_job(args.job)
    c = casefile.build(slug)
    md = casefile.markdown(c)
    out = os.path.join(store.job_dir(slug), 'CASE.md')
    store.write_text(out, md)
    package = store.approved_dir(slug)
    if package:
        store.write_text(release.record_path(package, 'CASE.md', create=True), md)
        _, package_manifest = release.load_release(slug)
        state = ('SUBMITTED' if release.has_record_file(
            package, release.SUBMISSION_NAME) else 'APPROVED')
        release.write_status(slug, state, package_manifest)
    say(md if args.print_all else '\n'.join(md.splitlines()[:60]))
    say(f"\nfull dossier: {os.path.abspath(out)}")
    return 0


# ---------------------------------------------------------------- approved artefacts

def _release_artifact_path(release_dir, manifest, label):
    info = (manifest.get('files') or {}).get(label) or {}
    name = info.get('file')
    return os.path.abspath(os.path.join(release_dir, name)) if name else None


def cmd_artifacts(args):
    """Point the user at the exact approved artefact folder."""
    slug = store.resolve_job(args.job)
    manifest, errors = release.verify_release(slug)
    release_dir, _ = release.load_release(slug)
    if errors:
        say(f"ARTEFACTS UNAVAILABLE — {slug}")
        for problem in errors:
            say(f"  - {problem}")
        preview_path = os.path.abspath(os.path.join(store.job_dir(slug), 'PREVIEW.md'))
        if os.path.isfile(preview_path):
            say(f"  plan preview  {preview_path}")
        return 1

    match_path = _release_artifact_path(release_dir, manifest, 'match')
    mapping = store.read_json(match_path, {}) if match_path else {}
    approval_path = _release_artifact_path(release_dir, manifest, 'approval')
    approval = store.read_json(approval_path, {}) if approval_path else {}
    cv_path = _release_artifact_path(release_dir, manifest, 'docx')
    letter_path = _release_artifact_path(release_dir, manifest, 'letter_docx')
    preview_path = _release_artifact_path(release_dir, manifest, 'preview')
    ats_path = _release_artifact_path(release_dir, manifest, 'ats')
    audit_path = _release_artifact_path(release_dir, manifest, 'audit')
    pdf_path = _release_artifact_path(release_dir, manifest, 'pdf')
    letter_pdf_path = _release_artifact_path(release_dir, manifest, 'letter_pdf')
    risk_path = _release_artifact_path(release_dir, manifest, 'risk_markdown')
    folder = os.path.basename(release_dir)
    submission, submission_errors = release.verify_submission(slug)

    say(f"artifacts  {slug}")
    say(f"  package     {folder} · {manifest.get('package_id')} · hashes verified")
    say(f"  CV          {cv_path or '(DOCX not present)'}")
    if pdf_path:
        say(f"  PDF         {pdf_path}")
    say(f"  letter      {letter_path or '(DOCX not present)'}")
    if letter_pdf_path:
        say(f"  letter PDF  {letter_pdf_path}")
    say(f"  risk review {risk_path or '(risk review not present)'}")
    say(f"  evidence    {preview_path or '(preview not present)'}")
    say(f"  ATS text    {ats_path or '(ATS text not present)'}")
    say(f"  gate audit  {audit_path or '(audit not present)'}")
    context_sha = (mapping.get('_inputs') or {}).get('files', {}).get('truth_context')
    say(f"  context     verified {context_sha[:12]}" if context_sha else "  context     legacy/unknown")
    say(f"  reviewer    {approval.get('reviewer', 'unknown')}")
    approval = store.read_json(release.record_path(release_dir, 'APPROVAL.json'), {}) or approval
    say(f"  approved    {approval.get('approved_at', 'unknown')} by "
        f"{approval.get('reviewer', 'unknown')}")
    if submission_errors:
        say("  submission  not recorded")
    else:
        say(f"  submission  {submission.get('sent_file')} · "
            f"{submission.get('applied') or 'date not provided'}")

    document = mapping.get('document') or mapping
    coverage = document.get('coverage')
    if isinstance(coverage, (int, float)):
        by_kind = document.get('coverage_by_kind') or {}
        details = '  '.join(
            f"{name[:4]} {value:.0%}" for name, value in by_kind.items()
            if isinstance(value, (int, float)))
        say(f"  evidence coverage  {coverage:.1%} (local heuristic)"
            + (f"  ·  {details}" if details else ''))

    risks = [r for r in mapping.get('requirements', [])
             if r.get('match') not in ('DIRECT', 'BEHAVIOURAL')]
    mandatory = [r for r in risks if r.get('kind') == 'mandatory']
    if mandatory:
        say("  mandatory evidence risk:")
        for risk in mandatory:
            say(f"               [{risk.get('match')}] {risk.get('text')}")
    other = len(risks) - len(mandatory)
    if other:
        say(f"  other risks {other} — see the evidence preview for every requirement")
    pdf_note = ((manifest.get('layout') or {}).get('pdf_note'))
    if not pdf_path and pdf_note:
        say(f"  PDF         unavailable: {pdf_note}")
    elif not pdf_path:
        say("  PDF         unavailable; use the manifest-verified DOCX")

    say(f"\nFolder: {os.path.abspath(release_dir)}")
    if submission_errors:
        say("Record submission only with the exact file sent:")
        say(f"  jl submit {slug} --sent-file \"{pdf_path or cv_path}\"")
    return 0


def cmd_show(args):
    """Give Codex and the user one stable, shallow application lookup."""
    if not args.job:
        rows = [release.discover(slug) for slug in store.list_jobs()]
        if args.json_output:
            say(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        say('APPLICATIONS')
        if not rows:
            say('  none')
        for row in rows:
            say(f"  {row['state']:15} {row['app_id']}")
            say(f"    {row.get('company') or '?'} · {row.get('title') or '?'}")
            say(f"    {row.get('folder') or row['work_record']}")
        return 0
    slug = store.resolve_job(args.job)
    row = release.discover(slug)
    if args.json_output:
        say(json.dumps(row, ensure_ascii=False, indent=2))
        return 0
    say(f"application  {row['app_id']}")
    say(f"  employer   {row.get('company') or '(not recorded)'}")
    say(f"  role       {row.get('title') or '(not recorded)'}")
    say(f"  reference  {row.get('reference') or '(not recorded)'}")
    say(f"  state      {row['state']}")
    say(f"  folder     {row.get('folder') or '(not created; awaiting approval)'}")
    for name, item in row['artifacts'].items():
        say(f"  {name:18} {item['state']:15} {item['path']}")
    if row.get('official_url'):
        say(f"  JD URL     {row['official_url']}")
    for error in row['integrity_errors']:
        say(f"  DO NOT SUBMIT — {error}")
    if row['state'] == 'CHAT_REVIEW':
        say(f"  review in chat with: jl present {slug}")
    else:
        say(f"  open the preferred CV with: jl open {slug} cv")
    return 1 if row['state'] == 'INTEGRITY_ERROR' else 0


def _open_path(path):
    if os.name == 'nt':
        os.startfile(path)
        return 'os.startfile'
    command = 'open' if sys.platform == 'darwin' else 'xdg-open'
    if not shutil.which(command):
        raise ValueError(f'{command} is unavailable')
    subprocess.Popen([command, path], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return command


def cmd_open(args):
    """Open one verified artefact only after an explicit user command."""
    if args.job == 'dashboard':
        path = os.path.abspath(store.data_p('START-HERE.md'))
        state = 'VERIFIED' if os.path.isfile(path) else 'MISSING'
    else:
        slug = store.resolve_job(args.job)
        row = release.discover(slug)
        if args.kind == 'folder':
            path, state = row.get('folder'), 'VERIFIED'
        else:
            candidates = {
                'cv': ('cv_pdf', 'cv_docx'),
                'letter': ('cover_letter_pdf', 'cover_letter_docx'),
                'jd': ('jd',), 'status': ('status',), 'case': ('case',),
            }[args.kind]
            item = next((row['artifacts'].get(name) for name in candidates
                         if row['artifacts'].get(name)), None)
            path = item.get('path') if item else None
            state = item.get('state') if item else 'MISSING'
        if row['state'] == 'INTEGRITY_ERROR' and args.kind in {'cv', 'letter'}:
            path = row.get('folder')
            state = 'PACKAGE_INTEGRITY_ERROR'
    if not path or not os.path.exists(path):
        raise SystemExit(f'OPEN REFUSED — {args.kind} is not available')
    say(f"open  {path}")
    if state != 'VERIFIED':
        say(f"  {state}; opening the folder for inspection, not a sendable file")
    if args.print_only:
        return 0
    try:
        method = _open_path(path)
    except (OSError, ValueError) as error:
        say(f"  launcher unavailable: {error}")
        return 1
    say(f"  launched with {method}")
    return 0


def cmd_pdf(args):
    """Complete missing PDFs without changing an approved document plan."""
    slug = store.resolve_job(args.job)
    package, manifest = release.load_release(slug)
    _, errors = release.verify_release(slug)
    if errors:
        raise SystemExit('PDF REFUSED — ' + '; '.join(errors))
    if not package or not manifest:
        raise SystemExit('PDF REFUSED — approved package not found')
    files = manifest.get('files') or {}
    missing = [label for label in ('pdf', 'letter_pdf') if label not in files]
    if not missing:
        say('PDFs already exist and are manifest-verified')
        return 0
    cv = store.read_json(os.path.join(package, files['cv']['file']))
    letter = store.read_json(os.path.join(package, files['letter']['file']))
    letter_document = cover_letter.to_render_document(letter)
    documents = {
        'pdf': (os.path.join(package, files['docx']['file']), cv,
                int(cv.get('target_pages', 2))),
        'letter_pdf': (os.path.join(package, files['letter_docx']['file']),
                       letter_document, 1),
    }
    staging = tempfile.mkdtemp(prefix='joblooper-pdf-')
    rendered = {}
    pages = {}
    try:
        conversions = render.to_pdfs([
            (documents[label][0], os.path.join(staging, release.ARTEFACT_NAMES[label]))
            for label in missing])
        for label, converted in zip(missing, conversions):
            source, document, target_pages = documents[label]
            if not isinstance(converted, str):
                raise SystemExit(f'PDF UNAVAILABLE — {label}: {converted[1]}')
            level, summary, details = gates.verify_rendered(
                source, cv=document, pdf_path=converted)
            if level == gates.BLOCK:
                raise SystemExit('PDF REFUSED — ' + summary + ': ' + '; '.join(details))
            count = render.pdf_pages(converted)
            if count and count > target_pages:
                raise SystemExit(
                    f'PDF REFUSED — {label} rendered {count} pages; target is {target_pages}')
            rendered[label] = converted
            pages[label] = count
        package, manifest = release.attach_pdfs(slug, rendered, layout={
            'cv_pages': pages.get('pdf', (manifest.get('layout') or {}).get('cv_pages')),
            'cover_letter_pages': pages.get(
                'letter_pdf', (manifest.get('layout') or {}).get('cover_letter_pages')),
            'cv_pdf_note': None, 'cover_letter_pdf_note': None,
        })
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    say(f'PDFs completed and manifest-verified: {package}')
    return 0


def cmd_context(args):
    """Explain and materialise the exact ground-truth context used by commands."""
    if args.refresh:
        store.truth_context(force=True)
    context = require_truth_integrity('CONTEXT')
    stats = context['stats']
    say("ground-truth context READY")
    say(f"  fingerprint  {context['truth_sha256']}")
    say(f"  generation   {context.get('generation_truth_sha256', context['truth_sha256'])}")
    say(f"  records      {stats['records']} ({stats['active_records']} active)")
    say(f"  sources      {stats['sources']}")
    say(f"  decisions    {stats['changelog_entries']} changelog entries")
    say(f"  authority    {os.path.abspath(store.p('truth'))}")
    say(f"  read model   {os.path.abspath(store.p('index', 'truth_context.json'))}")
    say("  freshness    exact source hashes; automatic rebuild on truth change")
    say("\nDeterministic engine:")
    for item in context['oversight_contract']['deterministic']:
        say(f"  - {item}")
    say("Contextual reviewer (human or AI; never a fact source):")
    for item in context['oversight_contract']['contextual_oversight']:
        say(f"  - {item}")
    say("Reviewer constraint: may challenge or propose; may not invent or silently edit truth.")
    return 0


# ---------------------------------------------------------------- ask

def cmd_ask(args):
    q = ' '.join(args.question).lower()
    apps = [a for a in store.applications() if not a.get('exclude_from_analytics')]

    if not apps:
        say('No applications logged yet.')
        return

    if re.search(r'reject|fail|lost|why', q):
        rej = [a for a in apps if a.get('status') == 'rejected']
        say(f"{len(rej)} rejection(s) of {len(apps)} application(s)\n")
        from collections import Counter
        c = Counter((h.get('cause') or h.get('cat', 'NO_SIGNAL'))
                    for a in rej for h in a.get('hypotheses', []))
        for cat, n in c.most_common():
            say(f"  {n:3}x  {cat}")
        say('')
        for a in rej:
            top = max(a.get('hypotheses', [{}]),
                      key=lambda h: h.get('confidence', h.get('conf', 0)), default={})
            say(f"  {a['applied']}  {a['company'][:22]:22} {a.get('identity',''):18}"
                f" evidence-coverage {a.get('coverage','?')}  "
                f"{top.get('cause') or top.get('cat','—')}")
        return

    if re.search(r'identity|framing|which lane|best.*respon', q):
        from collections import defaultdict
        agg = defaultdict(lambda: [0, 0])
        for a in apps:
            agg[a.get('identity', '?')][0] += 1
            if a.get('status') in ('interview', 'offer', 'progressed'):
                agg[a.get('identity', '?')][1] += 1
        say('identity            sent  progressed  rate')
        for k, (n, p) in sorted(agg.items(), key=lambda x: -x[1][1] / max(x[1][0], 1)):
            say(f"  {k:18} {n:4}  {p:10}  {p/max(n,1):.0%}")
        return

    if re.search(r'keyword|missing|backlog|learn|skill gap', q):
        from collections import Counter
        c = Counter()
        for slug in store.list_jobs():
            mj = store.read_json(os.path.join(store.job_dir(slug), 'match.json'))
            for g in (mj or {}).get('gaps', []):
                for t in vec.tokens(g['text']):
                    c[t] += 1
        say('Terms recurring in UNCOVERED requirements — your market-derived backlog:\n')
        for t, n in c.most_common(25):
            if n >= 2:
                say(f"  {n:3}x  {t}")
        return

    # default: free-text search across everything logged
    say(f"Searching {len(apps)} application(s) for '{' '.join(args.question)}'\n")
    for a in apps:
        blob = json.dumps(a).lower()
        if any(t in blob for t in vec.tokens(q)):
            say(f"  {a['applied']}  {a['company']} · {a['role']}")
            say(f"    status {a.get('status')} · identity {a.get('identity')} · cv {a.get('cv_sha')}")
            say(f"    dir {os.path.abspath(store.job_dir(a['app_id']))}")


# ---------------------------------------------------------------- utility

def cmd_jobs(args):
    apps = {a['app_id']: a for a in store.applications()}
    for s in store.list_jobs():
        a = apps.get(s, {})
        if a.get('test_record'):
            a = {}
        jd = store.read_json(os.path.join(store.job_dir(s), 'jd.json')) or {}
        cv = store.read_json(os.path.join(store.job_dir(s), 'cv.json')) or {}
        job_dir = store.job_dir(s)
        artifact_dir = store.approved_dir(s)
        submitted = bool(artifact_dir and
                         release.has_record_file(artifact_dir, release.SUBMISSION_NAME))
        approved = bool(artifact_dir)
        integrity_errors = []
        if submitted:
            _, integrity_errors = release.verify_submission(s)
        elif approved and release.has_record_file(artifact_dir, release.MANIFEST_NAME):
            _, integrity_errors = release.verify_release(s)
        if integrity_errors:
            state = 'integrity-error'
        elif a.get('status'):
            state = a['status']
        elif submitted:
            state = 'submitted'
        elif approved:
            state = 'approved'
        else:
            status = store.read_text(os.path.join(job_dir, 'STATUS.md')).splitlines()
            state = status[0].lstrip('# ').lower() if status else 'planned'
        say(f"  {jd.get('company', '?')} · {jd.get('title', '?')}")
        say(f"    key   {s}")
        say(f"    state {state} · lane {cv.get('identity', '—')} · "
            f"evidence coverage {cv.get('coverage', '—')} (local heuristic)")
        if jd.get('url'):
            say(f"    JD    {jd['url']}")
        say(f"    work  {os.path.abspath(job_dir)}")
        if artifact_dir:
            say(f"    files {os.path.abspath(artifact_dir)}")
        if integrity_errors:
            say(f"    fix   jl verify {s}  ({'; '.join(integrity_errors)})")
        else:
            say(f"    use   jl artifacts {s}" if artifact_dir else
                f"    use   jl present {s}")


def cmd_anchors(args):
    by_id, recs = store.anchors()
    if args.query:
        bm, _ = vec.anchor_index()
        for aid, sc in bm.normed(' '.join(args.query), top=15):
            r = by_id[aid]
            say(f"  {sc:.2f}  [{aid:9}] {r.get('ownership','—'):12} {r.get('fact','')[:95]}")
    else:
        for r in recs:
            say(f"  [{r['id']:9}] {r.get('type','—'):12} {r.get('status','—'):11}"
                f" {(r.get('fact') or r.get('title') or '')[:80]}")
        say(f"\n  {len(recs)} anchors")


def cmd_check(args):
    """Integrity check on the truth layer itself."""
    problems, warnings, stats = integrity.check_truth()
    say(f"{stats['records']} records · {stats['sources']} registered sources · "
        f"{stats['changelog_entries']} changelog entries")
    if problems:
        say(f"\n{len(problems)} integrity problem(s):")
        for p_ in problems:
            say(f"  - {p_}")
    if warnings:
        say(f"\n{len(warnings)} provenance warning(s):")
        for warning in warnings[:20]:
            say(f"  - {warning}")
        if len(warnings) > 20:
            say(f"  - ...and {len(warnings) - 20} more")
    if problems:
        return 1
    say('\ntruth/configuration integrity OK')
    return 0


def cmd_sources(args):
    """Show whether broad evidence files were reconciled into ground truth."""
    rows = integrity.source_review_rows()
    say('SOURCE COVERAGE  archive is provenance; approved anchors are authority\n')
    for row in rows:
        marker = {'reviewed': 'OK', 'not_required': '--', 'missing': 'MISSING',
                  'stale': 'STALE'}[row['state']]
        say(f"  [{marker:7}] {row['id'] or '?':28} {row['kind'] or '?':18} "
            f"{row['anchor_refs']:3} anchor ref(s)")
        if row['broad'] and row.get('scope'):
            say(f"            reviewed {row.get('reviewed_at')} · {row['scope']}")
    unresolved = [row for row in rows if row['state'] in {'missing', 'stale'}]
    if unresolved:
        say(f"\n{len(unresolved)} broad source review(s) unresolved; planning is blocked.")
        return 1
    say('\nall broad narrative sources have current hash-bound coverage reviews')
    return 0


def cmd_verify(args):
    """Verify the current package manifest and every snapshotted file."""
    slug = store.resolve_job(args.job)
    manifest, errors = release.verify_release(slug)
    if errors:
        submission, submission_errors = release.verify_submission(slug)
        if (submission
                and submission.get('mode') == 'user_confirmed_external_submission'
                and not submission_errors):
            say(f"verified submission  {slug}")
            say(f"  package   {submission.get('package_id')}")
            say(f"  manifest  {submission.get('manifest_sha256')}")
            say(f"  sent CV   {submission.get('sent_file')} · "
                f"{submission.get('sent_sha256', '')[:12]}")
            if submission.get('sent_cover_letter'):
                say(f"  letter    {submission.get('sent_cover_letter')} · "
                    f"{submission.get('sent_cover_letter_sha256', '')[:12]}")
            say('  package   submission is exact; unsent-file exception remains disclosed')
            for problem in submission.get('unsent_package_integrity_exceptions', []):
                say(f"            - {problem}")
            return 0
        say(f"VERIFY FAILED — {slug}")
        for problem in errors:
            say(f"  - {problem}")
        return 1
    say(f"verified  {slug}")
    say(f"  package   {manifest.get('package_id', manifest['release_id'])}")
    say(f"  manifest  {manifest['manifest_sha256']}")
    say(f"  files     {len(manifest.get('files') or {})} exact artefact(s)")
    return 0


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(prog='jl', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data-dir', help='private runtime data directory (or JOBLOOPER_DATA_DIR)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('init')
    s.add_argument('--demo', action='store_true',
                   help='install fictional starter data explicitly; never for real applications')
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser('doctor'); s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser('onboard')
    s.add_argument('action', choices=('status', 'finalize'), default='status', nargs='?')
    s.add_argument('--reviewer')
    s.add_argument('--confirm-reviewed', action='store_true')
    s.set_defaults(fn=cmd_onboard)

    s = sub.add_parser('truth')
    s.add_argument('action', choices=('status', 'audit', 'comment', 'resolve'))
    s.add_argument('--scope', choices=sorted(x.lower() for x in truth_review.SCOPES))
    s.add_argument('--note'); s.add_argument('--author')
    s.add_argument('--evidence', action='append', default=[])
    s.add_argument('--id', dest='item_id')
    s.add_argument('--status', choices=('adopted', 'rejected'))
    s.add_argument('--implementation'); s.add_argument('--validation')
    s.set_defaults(fn=cmd_truth)

    s = sub.add_parser('ingest'); s.add_argument('file')
    s.add_argument('--company', required=True); s.add_argument('--title', required=True)
    s.add_argument('--url'); s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser('preflight'); s.add_argument('job'); s.add_argument('--identity')
    s.add_argument('--user-reviewed', action='store_true')
    s.add_argument('--reviewer'); s.add_argument('--note')
    s.set_defaults(fn=cmd_preflight)

    s = sub.add_parser('plan'); s.add_argument('job'); s.add_argument('--identity')
    s.add_argument('--pages', type=int, choices=(1, 2, 3), default=None,
                   help='page target; defaults to truth/sections.json default_pages')
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser('present'); s.add_argument('job'); s.set_defaults(fn=cmd_present)

    s = sub.add_parser('approve'); s.add_argument('job'); s.add_argument('--reviewer', required=True)
    s.add_argument('--all-pass', action='store_true')
    s.add_argument('--user-signoff', action='store_true',
                   help='assert the user explicitly signed off the exact chat presentation')
    s.add_argument('--judgment', action='append', default=[]); s.add_argument('--note')
    s.set_defaults(fn=cmd_approve)

    s = sub.add_parser('feedback'); s.add_argument('job')
    s.add_argument('--id', dest='feedback_id')
    s.add_argument('--scope', choices=sorted(x.lower() for x in feedback.SCOPES))
    s.add_argument('--note'); s.add_argument('--author', default='user')
    s.add_argument('--status', choices=['adopted', 'rejected'])
    s.add_argument('--implementation'); s.add_argument('--validation')
    s.set_defaults(fn=cmd_feedback)

    s = sub.add_parser('build'); s.add_argument('job')
    s.add_argument('--no-pdf', action='store_true'); s.add_argument('--force', action='store_true')
    s.add_argument('--reason')
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser('pdf'); s.add_argument('job'); s.set_defaults(fn=cmd_pdf)

    s = sub.add_parser('artifacts', aliases=['artefacts']); s.add_argument('job')
    s.set_defaults(fn=cmd_artifacts)

    s = sub.add_parser('show'); s.add_argument('job', nargs='?')
    s.add_argument('--json', dest='json_output', action='store_true')
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser('open'); s.add_argument('job')
    s.add_argument('kind', nargs='?', default='cv',
                   choices=('cv', 'letter', 'folder', 'jd', 'status', 'case'))
    s.add_argument('--print-only', action='store_true')
    s.set_defaults(fn=cmd_open)

    for command in ('submit', 'apply'):
        s = sub.add_parser(command); s.add_argument('job')
        s.add_argument('--channel')
        s.add_argument('--date', help='submission date in YYYY-MM-DD')
        s.add_argument('--sent-file',
                       required=True,
                       help='exact CV.pdf or CV.docx inside the approved job folder')
        s.add_argument('--cover-letter-file',
                       help='exact COVER-LETTER.pdf or COVER-LETTER.docx if it was submitted')
        s.add_argument(
            '--screening-file',
            help=('optional saved portal questionnaire/answers as PDF, text, JSON, HTML '
                  'or image; copied and hash-bound to the private application record'))
        s.add_argument(
            '--confirm-external', action='store_true',
            help=('retrospectively bind user-confirmed sent files that still match the '
                  'approved manifest when only other unsent employer-facing files changed'))
        s.set_defaults(fn=cmd_apply)

    s = sub.add_parser('outcome'); s.add_argument('job')
    s.add_argument('--status', required=True,
                   choices=['rejected', 'interview', 'offer', 'progressed', 'ghosted', 'withdrawn'])
    s.add_argument('--date'); s.add_argument('--reason'); s.add_argument('--cat', choices=FAIL_CATS)
    s.add_argument('--latency', choices=(
        'under_24h', '1_3d', '4_7d', '8_30d', 'over_30d', 'unknown'),
        help='user-reported response-time band when exact timestamps are unavailable')
    s.add_argument('--conf', type=float, default=0.5); s.add_argument('--note')
    s.add_argument('--author', default='user')
    s.add_argument('--evidence-for', action='append', default=[])
    s.add_argument('--evidence-against', action='append', default=[])
    s.set_defaults(fn=cmd_outcome)

    s = sub.add_parser('response'); s.add_argument('file')
    s.add_argument('--job', help='explicit application key when the email omits identifiers')
    s.add_argument('--status', choices=['rejected', 'interview', 'offer', 'progressed'])
    s.add_argument('--date', help='response date in YYYY-MM-DD')
    s.set_defaults(fn=cmd_response)

    s = sub.add_parser('reason'); s.add_argument('job')
    s.add_argument('--id', dest='hypothesis_id'); s.add_argument('--cause', choices=FAIL_CATS)
    s.add_argument('--confidence', type=float, default=0.5)
    s.add_argument('--status',
                   choices=['open', 'retained_plausible', 'confirmed', 'dismissed'],
                   default='open')
    s.add_argument('--note'); s.add_argument('--author', default='user')
    s.add_argument('--evidence-for', action='append', default=[])
    s.add_argument('--evidence-against', action='append', default=[])
    s.add_argument('--company-context', action='append', default=[])
    s.add_argument('--profile-factor', action='append', default=[])
    s.add_argument('--other-factor', action='append', default=[])
    s.add_argument('--unknown', action='append', default=[])
    s.set_defaults(fn=cmd_reason)

    s = sub.add_parser('lessons'); s.set_defaults(fn=cmd_lessons)
    s = sub.add_parser('metrics'); s.set_defaults(fn=cmd_metrics)
    s = sub.add_parser('dashboard')
    s.add_argument('--port', type=int, default=8765,
                   help='loopback port; use 0 to select a free port')
    s.add_argument('--no-open', action='store_true',
                   help='do not open the default browser automatically')
    s.add_argument('--snapshot', action='store_true',
                   help='print the deterministic dashboard JSON and exit')
    s.set_defaults(fn=cmd_dashboard)

    s = sub.add_parser('ask'); s.add_argument('question', nargs='+'); s.set_defaults(fn=cmd_ask)
    s = sub.add_parser('case'); s.add_argument('job')
    s.add_argument('--print-all', action='store_true'); s.set_defaults(fn=cmd_case)

    s = sub.add_parser('jobs'); s.set_defaults(fn=cmd_jobs)
    s = sub.add_parser('anchors'); s.add_argument('query', nargs='*'); s.set_defaults(fn=cmd_anchors)
    s = sub.add_parser('sources'); s.set_defaults(fn=cmd_sources)
    s = sub.add_parser('check'); s.set_defaults(fn=cmd_check)
    s = sub.add_parser('context'); s.add_argument('--refresh', action='store_true')
    s.set_defaults(fn=cmd_context)
    s = sub.add_parser('verify'); s.add_argument('job')
    s.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    if args.data_dir:
        store.configure(args.data_dir)
        vec.reset_caches()
    mutating = {
        'ingest', 'preflight', 'plan', 'present', 'approve', 'feedback', 'build', 'truth',
        'pdf', 'submit', 'apply', 'outcome', 'response', 'reason',
    }
    needs_lock = args.cmd in mutating or (
        args.cmd == 'onboard' and getattr(args, 'action', None) == 'finalize')
    if needs_lock:
        with store.writer_lock():
            result = args.fn(args)
    else:
        result = args.fn(args)
    sys.exit(result or 0)


if __name__ == '__main__':
    main()
