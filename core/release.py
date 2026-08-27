"""Chat approval, immutable human-facing artefacts, and application events."""
import os
import re
import shutil

from . import (cover_letter, employer_review, feedback, gates, integrity, render,
               preflight, store, truth_review)


MANUAL_GATES = (
    'RELEVANCE_FIT', 'SPECIFICITY', 'CONTRADICTION',
    'DELETION_BLOAT', 'ATS_LAST', 'HOSTILE_REVIEW',
)

ARTEFACT_NAMES = {
    'docx': 'CV.docx', 'pdf': 'CV.pdf', 'markdown': 'CV.md',
    'ats': 'CV-ATS.txt', 'preview': 'EVIDENCE.md', 'audit': 'GATE-AUDIT.csv',
    'jd_raw': 'JOB-DESCRIPTION.md', 'jd': 'JD.json', 'match': 'MATCH.json',
    'cv': 'CV.json', 'approval': 'APPROVAL.json',
    'presentation': 'PRESENTATION.json', 'feedback': 'FEEDBACK.json',
    'oversight': 'OVERSIGHT.md', 'letter': 'COVER-LETTER.json',
    'letter_docx': 'COVER-LETTER.docx', 'letter_pdf': 'COVER-LETTER.pdf',
    'letter_markdown': 'COVER-LETTER.md', 'letter_ats': 'COVER-LETTER-ATS.txt',
    'risk': 'EMPLOYER-RISK.json', 'risk_markdown': 'EMPLOYER-RISK.md',
    'employer_context': 'EMPLOYER-CONTEXT.json',
}

MANIFEST_NAME = 'MANIFEST.json'
PRESENTATION_NAME = 'presentation.json'
SUBMISSION_NAME = 'SUBMISSION.json'
RECORD_DIR_NAME = 'APPLICATION-RECORD'
EMPLOYER_FACING_LABELS = {'docx', 'pdf', 'letter_docx', 'letter_pdf'}
REQUIRED_RELEASE_LABELS = {
    'jd', 'jd_raw', 'match', 'cv', 'preview', 'letter', 'risk',
    'risk_markdown', 'approval', 'presentation', 'feedback', 'audit',
    'docx', 'markdown', 'ats', 'letter_docx', 'letter_markdown', 'letter_ats',
}


def record_dir(package, create=False):
    """Return the one-level application record, with legacy-root fallback."""
    nested = os.path.join(package, RECORD_DIR_NAME)
    # A migrated/legacy package may keep its authoritative manifest at the
    # package root. Creating a later CASE/STATUS file must never create a
    # nested directory that shadows that manifest and breaks correlation.
    root_manifest = os.path.join(package, MANIFEST_NAME)
    nested_manifest = os.path.join(nested, MANIFEST_NAME)
    if os.path.isfile(root_manifest) and not os.path.isfile(nested_manifest):
        return package
    if os.path.isdir(nested) or create:
        if create:
            os.makedirs(nested, exist_ok=True)
        return nested
    return package


def record_path(package, filename, create=False):
    return os.path.join(record_dir(package, create=create), filename)


def has_record_file(package, filename):
    return bool(package and os.path.isfile(record_path(package, filename)))


def _manifest_target(package, label, source):
    filename = ARTEFACT_NAMES.get(label, os.path.basename(source))
    base = package if label in EMPLOYER_FACING_LABELS else record_dir(package, create=True)
    return os.path.join(base, filename)


def invalidate_unsubmitted_package(slug, reason):
    """Remove an approved-but-unsubmitted folder when its source plan changes."""
    out = store.approved_dir(slug)
    if not out or not os.path.isdir(out):
        return None
    d = os.path.abspath(store.DATA_ROOT)
    out = os.path.abspath(out)
    if os.path.commonpath([d, out]) != d:
        raise ValueError('refused to invalidate an approved folder outside private data')
    if has_record_file(out, SUBMISSION_NAME):
        raise ValueError('submitted application artefacts are immutable')
    manifest = store.read_json(record_path(out, MANIFEST_NAME), {}) or {}
    event = {
        'event': 'STALE_APPROVED_FOLDER_REMOVED', 'app_id': slug,
        'package_id': manifest.get('package_id'),
        'reason': str(reason or 'generation inputs changed').strip(),
    }
    try:
        shutil.rmtree(out)
    except OSError as error:
        raise ValueError(
            f'could not remove stale approved folder; close any open artifact: {error}') from error
    store.remove_approved_case(slug)
    work = store.job_dir(slug)
    store.append_jsonl(os.path.join(work, 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    store.append_application_event(event)
    write_dashboard()
    return event


def write_status(slug, state, manifest=None):
    """Write internal status before approval, or package status afterwards."""
    work = store.job_dir(slug)
    package = store.approved_dir(slug)
    target = record_dir(package, create=True) if package else work
    jd = store.read_json(os.path.join(work, 'jd.json'), {}) or {}
    state = state.upper()
    url = str(jd.get('url') or '').strip()
    lines = [f'# {state}', '',
             f"**Company:** {jd.get('company', '(not recorded)')}  ",
             f"**Role:** {jd.get('title', '(not recorded)')}  ",
             f"**Application key:** `{slug}`  ",
             (f"**Official advert:** [{url}]({url})" if url
              else '**Official advert:** (not recorded; do not infer)'), '']
    if package:
        lines += ['## ARTEFACTS', '']
        nested = os.path.abspath(target) != os.path.abspath(package)
        for label, filename, employer_facing in (
                ('CV (PDF)', 'CV.pdf', True), ('CV (DOCX)', 'CV.docx', True),
                ('Cover letter (PDF)', 'COVER-LETTER.pdf', True),
                ('Cover letter (DOCX)', 'COVER-LETTER.docx', True),
                ('CV source', 'CV.md', False), ('ATS text', 'CV-ATS.txt', False),
                ('Cover letter source', 'COVER-LETTER.md', False),
                ('Employer risk review', 'EMPLOYER-RISK.md', False),
                ('Captured JD', 'JOB-DESCRIPTION.md', False),
                ('Structured JD', 'JD.json', False),
                ('Evidence map', 'EVIDENCE.md', False),
                ('Gate audit', 'GATE-AUDIT.csv', False),
                ('Approval', 'APPROVAL.json', False),
                ('Manifest', MANIFEST_NAME, False),
                ('Submission', SUBMISSION_NAME, False),
                ('Employer responses', 'RESPONSES.jsonl', False),
                ('Outcome', 'OUTCOME.json', False),
                ('Case dossier', 'CASE.md', False),
                ('Reasoning history', 'REASONING.jsonl', False)):
            path = os.path.join(package if employer_facing else target, filename)
            if os.path.isfile(path):
                href = f'../{filename}' if employer_facing and nested else filename
                lines.append(f'- {label}: [{filename}]({href})')
        if (not os.path.isfile(os.path.join(target, 'EVIDENCE.md'))
                and os.path.isfile(os.path.join(target, 'REVIEW.md'))):
            lines.append('- Evidence map (legacy filename): [REVIEW.md](REVIEW.md)')
        submission = store.read_json(os.path.join(target, SUBMISSION_NAME), {}) or {}
        if submission:
            sent = submission.get('sent_file')
            sent_href = f'../{sent}' if nested else sent
            lines += ['', f"**Exact submitted artefact:** [{sent}]({sent_href})  ",
                      f"**Applied date:** {submission.get('applied') or '(not provided)'}  ",
                      f"**Channel:** {submission.get('channel') or '(not provided)'}"]
            sent_letter = submission.get('sent_cover_letter')
            if sent_letter:
                letter_href = f'../{sent_letter}' if nested else sent_letter
                lines.insert(-2, f"**Exact submitted cover letter:** [{sent_letter}]({letter_href})  ")
        elif state == 'APPROVED':
            lines += ['', 'The CV and cover letter were approved in chat. Generated artefacts in this folder are the '
                      'approved application package; record submission with the exact sent file.']
        lines.append('')
    else:
        lines += ['## CHAT REVIEW', '',
                  '- Captured JD: [jd.raw.md](jd.raw.md)',
                  '- Structured JD: [jd.json](jd.json)']
        if os.path.isfile(os.path.join(work, 'PREVIEW.md')):
            lines.append('- Internal evidence plan: [PREVIEW.md](PREVIEW.md)')
        lines += ['', ('The complete CV and cover letter were presented in chat. Await explicit approval; '
                       'no job artefact folder or employer-facing document exists yet.'
                       if state == 'PRESENTED' else
                       'Run `jl present <job>` and show the complete CV and cover letter in chat.'), '']
    if manifest:
        lines += [f"Package: `{manifest.get('package_id', '?')}`  ",
                  f"Manifest: `{manifest.get('manifest_sha256', '')}`", '']
    if state == 'SUBMITTED':
        lines += ['This folder contains the immutable submitted application record.', '']
    store.write_text(os.path.join(target, 'STATUS.md'), '\n'.join(lines))
    write_dashboard()


def write_dashboard():
    """Write one shallow private entry point with approved folders first."""
    repo_class = store.read_repository_policy().get('classification')
    data_note = (
        'This personal repository keeps governed candidate evidence and application '
        'records in private Git. Never publish this history.'
        if repo_class == 'PERSONAL_PRIVATE' else
        'Runtime candidate evidence and application records live outside the installed '
        'public skill and must not be committed to its repository.')
    lines = [
        '# START HERE', '',
        'This private page is the navigation entry point. ' + data_note, '',
        '## APPLICATION FOLDERS', '',
    ]
    registry = store.case_registry()
    if not registry:
        lines += ['- No approved application folders.', '']
    for slug, row in sorted(registry.items(), key=lambda item: item[1].get('artifact_dir', '')):
        work = store.job_dir(slug)
        jd = store.read_json(os.path.join(work, 'jd.json'), {}) or {}
        package = store.approved_dir(slug)
        folder = os.path.basename(str(row.get('artifact_dir') or '').replace('/', os.sep))
        _, package_errors = verify_release(slug) if package else (None, [])
        submission_exact = False
        if package and has_record_file(package, SUBMISSION_NAME):
            receipt, receipt_errors = verify_submission(slug)
            submission_exact = bool(receipt) and not receipt_errors
        state = ('SUBMITTED - UNSENT FILE EXCEPTION DISCLOSED'
                 if package_errors and submission_exact else
                 'INTEGRITY ERROR' if package_errors else
                 'SUBMITTED' if package and has_record_file(package, SUBMISSION_NAME)
                 else 'APPROVED')
        rel = f"jobs/{folder}"
        rec = record_dir(package) if package else None
        rec_rel = (f"{rel}/{RECORD_DIR_NAME}"
                   if package and os.path.abspath(rec) != os.path.abspath(package)
                   else rel)
        lines += [f"### {folder}", '', f"**State:** {state}  ",
                  f"**Application key:** `{slug}`", '']
        url = str(jd.get('url') or '').strip()
        if url:
            lines.append(f"- [Open the official advert]({url})")
        else:
            lines.append('- Official advert: not recorded; no URL inferred')
        if package:
            for label, filename in (
                ('Open the CV (PDF)', 'CV.pdf'), ('Open the CV (DOCX)', 'CV.docx'),
                ('Open the cover letter (PDF)', 'COVER-LETTER.pdf'),
                ('Open the cover letter (DOCX)', 'COVER-LETTER.docx')):
                if os.path.isfile(os.path.join(package, filename)):
                    lines.append(f"- [{label}]({rel}/{filename})")
            for label, filename in (
                    ('Read the employer risk review', 'EMPLOYER-RISK.md'),
                    ('Open the captured JD', 'JOB-DESCRIPTION.md'),
                    ('Read the evidence map', 'EVIDENCE.md'),
                    ('Read ATS text', 'CV-ATS.txt'),
                    ('Verify the package manifest', MANIFEST_NAME)):
                if os.path.isfile(os.path.join(rec, filename)):
                    lines.append(f"- [{label}]({rec_rel}/{filename})")
            if (not os.path.isfile(os.path.join(rec, 'EVIDENCE.md'))
                    and os.path.isfile(os.path.join(rec, 'REVIEW.md'))):
                lines.append(f"- [Read the evidence map (legacy filename)]({rec_rel}/REVIEW.md)")
            if os.path.isfile(os.path.join(rec, 'CASE.md')):
                lines.append(f"- [Open the application case file]({rec_rel}/CASE.md)")
            lines.append(f"- [Status and all links]({rec_rel}/STATUS.md)")
        lines.append('')

    pending = [slug for slug in store.list_jobs() if slug not in registry]
    lines += ['## IN CHAT REVIEW', '']
    if not pending:
        lines += ['- None.', '']
    for slug in pending:
        work = store.job_dir(slug)
        jd = store.read_json(os.path.join(work, 'jd.json'), {}) or {}
        lines += [f"- **{jd.get('company', '?')} - {jd.get('title', '?')}**  ",
                  f"  Key: `{slug}`  ",
                  f"  Show complete CV and cover letter: `python jl.py present {slug}`", '']

    if os.path.isfile(store.data_p('OPEN-QUESTIONS.md')):
        lines += [
            '## OPEN DECISIONS', '',
            '- [Review unresolved candidate-data questions](OPEN-QUESTIONS.md)', '',
        ]

    lines += [
        '## PRIVATE FOLDER MAP', '',
        '- `truth/` - authoritative candidate facts, wording boundaries and source registry.',
        '- `work/` - internal plans awaiting chat approval; not a user artefact location.',
        '- `jobs/` - one dated, human-readable folder per approved application; only the sendable CV and cover letter are at its root.',
        f'- `jobs/<application>/{RECORD_DIR_NAME}/` - JD, evidence, gates, hashes, approval, submission, responses and reasoning.',
        '- `index/` - generated application/event lookup data; do not edit by hand.',
        '- `archive/` - private source documents and retired material; generation uses only records registered in `truth/`.',
        '',
        'The reusable public engine is outside this private folder: `core/`, '
        '`templates/`, `examples/`, `tests/`, `tools/`, and `jl.py`.',
        '',
    ]
    store.write_text(store.data_p('START-HERE.md'), '\n'.join(lines))


def _job_files(slug):
    d = store.job_dir(slug)
    return d, {
        'jd': store.read_json(os.path.join(d, 'jd.json')),
        'match': store.read_json(os.path.join(d, 'match.json')),
        'cv': store.read_json(os.path.join(d, 'cv.json')),
        'letter': store.read_json(os.path.join(d, 'cover-letter.json')),
        'risk': store.read_json(os.path.join(d, 'employer-risk.json')),
        'employer_context': store.read_json(os.path.join(d, 'EMPLOYER-CONTEXT.json')),
        'preview': store.read_text(os.path.join(d, 'PREVIEW.md')),
    }


def plan_digest(slug):
    _, files = _job_files(slug)
    return store.sha256_text(store.canonical_json(files))


def presentation_content(slug):
    """Return both documents and the exact internal decision packet."""
    _, files = _job_files(slug)
    if not files.get('cv') or not files.get('letter'):
        raise ValueError('no current CV and cover-letter plan; run `jl plan` first')
    omissions = (files['cv'].get('_selection') or {}).get('omitted') or []
    material = [row for row in omissions if row.get('significant') or row.get('protected')]
    omission_lines = ['## MATERIAL OMISSION DISCLOSURE', '']
    if not material:
        omission_lines.append('- None. All protected inventory is visible.')
    else:
        for row in material:
            label = 'PROTECTED' if row.get('protected') else 'MATERIAL'
            omission_lines.append(
                f"- **{label}** · `{row.get('id')}` · {row.get('reason')}")
    other = len(omissions) - len(material)
    omission_lines += ['', f'- Other controlled, non-material omissions: {other}',
                       '- Any factual change requires governed truth review; employer research '
                       'cannot fill a candidate-evidence gap.', '']
    return ('# DOCUMENT 1 — CV\n\n' + render.to_markdown(files['cv']).strip()
            + '\n\n---\n\n# DOCUMENT 2 — COVER LETTER\n\n'
            + cover_letter.to_markdown(files['letter']).strip()
            + '\n\n---\n\n# INTERNAL SIGN-OFF PACKET — NOT EMPLOYER-FACING\n\n'
            + employer_review.to_markdown(
                files['risk'], files.get('employer_context')).strip()
            + '\n\n' + '\n'.join(omission_lines).strip())


def present(slug):
    """Bind a chat-ready application-bundle presentation to the current plan."""
    d, files = _job_files(slug)
    required = ('jd', 'match', 'cv', 'letter', 'risk', 'preview')
    missing = [key for key in required if not files.get(key)]
    if missing:
        raise ValueError('cannot present; missing plan artefact(s): ' + ', '.join(missing))
    letter_errors = cover_letter.validate(files['letter'], files['jd'], files['cv'])
    risk_errors = employer_review.validate(
        files['risk'], files['jd'], files['cv'], files.get('employer_context'))
    if letter_errors or risk_errors:
        raise ValueError('; '.join(letter_errors + risk_errors))
    if files['risk'].get('decision') == 'REPLAN':
        raise ValueError('employer-risk review found a verified CV improvement; re-plan before presentation')
    preflight_record, preflight_errors, _ = preflight.validate(
        slug, files['jd'], files['match'], files['match'].get('identity') or {})
    expected_preflight = (files['match'].get('_preflight') or {}).get('subject_sha256')
    if preflight_errors or preflight_record.get('subject_sha256') != expected_preflight:
        raise ValueError('pre-generation review is missing or stale')
    content = presentation_content(slug)
    omissions = (files['cv'].get('_selection') or {}).get('omitted') or []
    material = [row for row in omissions if row.get('significant') or row.get('protected')]
    record = {
        '_schema': 'joblooper.presentation.v2',
        'presented_at': store.now(), 'channel': 'CHAT',
        'plan_sha256': plan_digest(slug),
        'content_sha256': store.sha256_text(content),
        'feedback_sha256': feedback.digest(slug),
        'section_count': len([s for s in files['cv'].get('sections', []) if s.get('items')]),
        'document_count': 2,
        'risk_decision': files['risk'].get('decision'),
        'risk_sha256': store.sha256_text(store.canonical_json(files['risk'])),
        'material_omissions': [row.get('id') for row in material],
    }
    store.write_json(os.path.join(d, PRESENTATION_NAME), record)
    write_status(slug, 'PRESENTED')
    store.append_application_event({
        'event': 'APPLICATION_BUNDLE_PRESENTED_IN_CHAT', 'app_id': slug,
        'plan_sha256': record['plan_sha256'],
        'content_sha256': record['content_sha256'],
        'feedback_sha256': record['feedback_sha256'],
    })
    return content, record


def validate_presentation(slug):
    d = store.job_dir(slug)
    record = store.read_json(os.path.join(d, PRESENTATION_NAME))
    if not record or record.get('channel') != 'CHAT':
        return None, ['complete CV and cover letter have not been presented in chat']
    errors = []
    if record.get('plan_sha256') != plan_digest(slug):
        errors.append('chat presentation is stale: plan artefacts changed')
    content = presentation_content(slug)
    if record.get('content_sha256') != store.sha256_text(content):
        errors.append('chat presentation is stale: presented CV content changed')
    if record.get('feedback_sha256') != feedback.digest(slug):
        errors.append('chat presentation is stale: user feedback changed')
    return record, errors


def approve(slug, reviewer, judgments, note='', user_signoff=False):
    if not reviewer or not str(reviewer).strip():
        raise ValueError('reviewer must be a non-empty name')
    truth_errors, _, _ = integrity.check_truth()
    if truth_errors:
        raise ValueError(f"truth/configuration has {len(truth_errors)} integrity error(s)")
    readiness = truth_review.readiness()
    if not readiness['ready']:
        raise ValueError('candidate truth is not currently approved: '
                         + '; '.join(readiness['problems']))
    d, files = _job_files(slug)
    required = ('jd', 'match', 'cv', 'letter', 'risk', 'preview')
    missing = [key for key in required if not files.get(key)]
    if missing:
        raise ValueError(f"cannot approve; missing plan artefact(s): {', '.join(missing)}")
    absent = [g for g in MANUAL_GATES if judgments.get(g) != 'PASS']
    if absent:
        raise ValueError('every judgment gate must be explicitly PASS: ' + ', '.join(absent))
    if user_signoff is not True:
        raise ValueError('explicit user sign-off is required after the complete chat presentation')
    presentation, presentation_errors = validate_presentation(slug)
    if presentation_errors:
        raise ValueError('; '.join(presentation_errors))
    pending_feedback = feedback.open_items(slug)
    if pending_feedback:
        raise ValueError('unresolved user feedback: ' + ', '.join(x['id'] for x in pending_feedback))
    _, deterministic_blocks = gates.run_all(files['cv'], files['match'])
    if deterministic_blocks:
        labels = ', '.join(f'{gid}_{name}' for gid, name, *_ in deterministic_blocks)
        raise ValueError('deterministic plan gates block approval: ' + labels)
    current = store.generation_fingerprint(files['jd'])
    planned = (files['cv'].get('_inputs') or {}).get('sha256')
    if planned != current['sha256']:
        raise ValueError('plan is stale: JD/truth/configuration changed; run `jl plan` again')
    record = {
        '_schema': 'joblooper.approval.v3',
        'decision': 'APPROVED', 'approved_at': store.now(),
        'reviewer': str(reviewer).strip(), 'note': note,
        'user_signoff': True,
        'presentation_sha256': presentation['content_sha256'],
        'feedback_sha256': feedback.digest(slug),
        'judgments': {g: judgments[g] for g in MANUAL_GATES},
        'plan_sha256': plan_digest(slug),
        'inputs_sha256': current['sha256'],
        'selection_summary': {
            'selected_count': (files['cv'].get('_selection') or {}).get('selected_count'),
            'significant_omissions':
                (files['cv'].get('_selection') or {}).get('significant_omissions', []),
        },
    }
    package, case = store.create_approved_case(
        slug, record['approved_at'], record['plan_sha256'])
    record['artifact_folder'] = case['artifact_dir']
    store.write_json(os.path.join(d, 'approval.json'), record)
    store.write_json(record_path(package, ARTEFACT_NAMES['approval'], create=True), record)
    write_status(slug, 'APPROVED')
    return record


def validate_approval(slug):
    d, files = _job_files(slug)
    approval = store.read_json(os.path.join(d, 'approval.json'))
    errors = []
    if not approval or approval.get('decision') != 'APPROVED':
        return None, ['no explicit approval for the current plan']
    readiness = truth_review.readiness()
    if not readiness['ready']:
        errors.append('candidate truth is not currently approved: '
                      + '; '.join(readiness['problems']))
    presentation, presentation_errors = validate_presentation(slug)
    errors.extend(presentation_errors)
    if approval.get('user_signoff') is not True:
        errors.append('approval has no explicit user sign-off')
    if presentation and approval.get('presentation_sha256') != presentation.get('content_sha256'):
        errors.append('approval is not bound to the current chat presentation')
    if approval.get('feedback_sha256') != feedback.digest(slug):
        errors.append('approval is stale: user feedback changed')
    pending_feedback = feedback.open_items(slug)
    if pending_feedback:
        errors.append('unresolved user feedback: ' + ', '.join(x['id'] for x in pending_feedback))
    if approval.get('plan_sha256') != plan_digest(slug):
        errors.append('approval is stale: plan artefacts changed')
    if (not files['jd'] or not files['match'] or not files['cv']
            or not files['letter'] or not files['risk']):
        errors.append('plan is incomplete')
    else:
        errors.extend(cover_letter.validate(files['letter'], files['jd'], files['cv']))
        errors.extend(employer_review.validate(
            files['risk'], files['jd'], files['cv'], files.get('employer_context')))
        if files['risk'].get('decision') == 'REPLAN':
            errors.append('employer-risk review requires a revised plan')
        preflight_record, preflight_errors, _ = preflight.validate(
            slug, files['jd'], files['match'], files['match'].get('identity') or {})
        errors.extend(preflight_errors)
        if preflight_record.get('subject_sha256') != (
                (files['match'].get('_preflight') or {}).get('subject_sha256')):
            errors.append('plan is not bound to the current pre-generation review')
        current = store.generation_fingerprint(files['jd'])
        if approval.get('inputs_sha256') != current['sha256']:
            errors.append('approval is stale: JD/truth/configuration changed')
        if (files['cv'].get('_inputs') or {}).get('sha256') != current['sha256']:
            errors.append('cv.json is stale relative to generation inputs')
        if (files['match'].get('_inputs') or {}).get('sha256') != current['sha256']:
            errors.append('match.json is stale relative to generation inputs')
    missing = [g for g in MANUAL_GATES
               if (approval.get('judgments') or {}).get(g) != 'PASS']
    if missing:
        errors.append('manual gates not passed: ' + ', '.join(missing))
    return approval, errors


def log_override(slug, command, reason, blocked):
    if not reason or len(reason.strip()) < 8:
        raise ValueError('--force requires --reason with at least 8 characters')
    event = {
        'event': 'FORCE_OVERRIDE', 'job': slug, 'command': command,
        'reason': reason.strip(), 'blocked': list(blocked or []),
    }
    store.append_jsonl(os.path.join(store.job_dir(slug), 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    return event


def create_release(slug, artefacts, status='APPROVED', metadata=None):
    """Populate the folder created by chat approval with one immutable package."""
    approval, approval_errors = validate_approval(slug)
    if approval_errors:
        raise ValueError('approval is not current: ' + '; '.join(approval_errors))
    out = store.approved_dir(slug)
    if not out or not os.path.isdir(out):
        raise ValueError('approved application folder is missing')
    if has_record_file(out, SUBMISSION_NAME):
        raise ValueError('submitted application artefacts are immutable')
    if has_record_file(out, MANIFEST_NAME):
        raise ValueError('approved artefact package already exists; change the plan and re-approve')

    missing = sorted(
        label for label in REQUIRED_RELEASE_LABELS
        if not artefacts.get(label) or not os.path.isfile(artefacts[label]))
    if missing:
        raise ValueError('release artefact set is incomplete: ' + ', '.join(missing))

    digest = plan_digest(slug)
    stamp = re.sub(r'[^0-9]', '', approval['approved_at'])[:14]
    package_id = f"{stamp}-{digest[:12]}"
    copied = {}
    created = []
    try:
        for label, path in artefacts.items():
            if not path or not os.path.exists(path):
                continue
            target = _manifest_target(out, label, path)
            same_path = os.path.abspath(path) == os.path.abspath(target)
            if not same_path and os.path.exists(target):
                if store.sha256_file(path) != store.sha256_file(target):
                    raise ValueError(f'release target already exists with different content: {label}')
            elif not same_path:
                shutil.copy2(path, target)
                created.append(target)
            copied[label] = {
                'file': os.path.relpath(target, out).replace('\\', '/'),
                'sha256': store.sha256_file(target),
                'bytes': os.path.getsize(target),
            }
    except Exception:
        for target in reversed(created):
            try:
                os.remove(target)
            except OSError:
                pass
        raise
    manifest = {
        '_schema': 'joblooper.package.v2',
        'release_id': 'approved', 'package': os.path.basename(out),
        'job': slug, 'status': status, 'package_id': package_id,
        'created_at': store.now(), 'approved_at': approval['approved_at'],
        'plan_sha256': digest, 'files': copied,
        'required_labels': sorted(REQUIRED_RELEASE_LABELS),
        **(metadata or {}),
    }
    manifest['manifest_sha256'] = store.sha256_text(store.canonical_json(manifest))
    store.write_json(record_path(out, MANIFEST_NAME, create=True), manifest)
    event = {
        'event': 'APPROVED_ARTEFACTS_BUILT', 'app_id': slug,
        'package_id': package_id, 'status': status,
        'artifact_folder': os.path.basename(out),
        'manifest_sha256': manifest['manifest_sha256'],
    }
    work = store.job_dir(slug)
    store.append_jsonl(os.path.join(work, 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    store.append_application_event(event)
    write_status(slug, 'APPROVED', manifest)
    return out, manifest


def load_release(slug, release_id=None):
    """Resolve the one approved/submitted human folder for an application."""
    path = store.approved_dir(slug)
    if not path or not os.path.isdir(path):
        return None, None
    requested = str(release_id or '').lower()
    if requested == 'submitted' and not has_record_file(path, SUBMISSION_NAME):
        return None, None
    manifest = store.read_json(record_path(path, MANIFEST_NAME))
    return path, manifest


def verify_release(slug, release_id=None):
    path, manifest = load_release(slug, release_id)
    if not path or not manifest:
        return None, ['approved artefact package not found']
    errors = []
    if manifest.get('job') != slug:
        errors.append('package manifest belongs to a different application')
    recorded = manifest.get('manifest_sha256')
    unsigned = {key: value for key, value in manifest.items()
                if key != 'manifest_sha256'}
    if recorded != store.sha256_text(store.canonical_json(unsigned)):
        errors.append('package manifest digest mismatch')
    required = set(manifest.get('required_labels') or [])
    missing = sorted(required - set(manifest.get('files') or {}))
    if missing:
        errors.append('package manifest is incomplete: ' + ', '.join(missing))
    for label, info in (manifest.get('files') or {}).items():
        target = os.path.join(path, info.get('file', ''))
        if not os.path.isfile(target):
            errors.append(f'{label}: file missing')
        elif store.sha256_file(target) != info.get('sha256'):
            errors.append(f'{label}: file digest mismatch')
    return manifest, errors


def discover(slug):
    """Resolve human-facing paths even when package integrity needs attention.

    Discovery and trust are separate: a digest mismatch blocks submission but
    must not hide where the user can inspect the affected file.
    """
    work = store.job_dir(slug)
    jd = store.read_json(os.path.join(work, 'jd.json'), {}) or {}
    package, manifest = load_release(slug)
    manifest = manifest or {}
    _, package_errors = verify_release(slug) if package else (None, [])
    external_submission_exact = False
    if package and has_record_file(package, SUBMISSION_NAME):
        receipt, receipt_errors = verify_submission(slug)
        external_submission_exact = (
            bool(receipt)
            and receipt.get('mode') == 'user_confirmed_external_submission'
            and not receipt_errors)
    artifacts = {}
    labels = {
        'cv_pdf': 'pdf', 'cv_docx': 'docx',
        'cover_letter_pdf': 'letter_pdf', 'cover_letter_docx': 'letter_docx',
        'jd': 'jd_raw', 'status': None, 'case': None,
    }
    for public_name, label in labels.items():
        if not package:
            continue
        if label:
            info = (manifest.get('files') or {}).get(label) or {}
            relative = info.get('file')
        else:
            filename = 'STATUS.md' if public_name == 'status' else 'CASE.md'
            path = record_path(package, filename)
            relative = os.path.relpath(path, package).replace('\\', '/') \
                if os.path.isfile(path) else None
            info = {'file': relative}
        if not relative:
            continue
        path = os.path.abspath(os.path.join(package, relative))
        state = 'MISSING'
        if os.path.isfile(path):
            expected = info.get('sha256')
            state = ('VERIFIED' if not expected or store.sha256_file(path) == expected
                     else 'DIGEST_MISMATCH')
        artifacts[public_name] = {'path': path, 'state': state}
    if not package:
        state = 'CHAT_REVIEW'
    elif package_errors and not external_submission_exact:
        state = 'INTEGRITY_ERROR'
    elif package_errors and external_submission_exact:
        state = 'SUBMITTED_WITH_UNSENT_EXCEPTION'
    elif has_record_file(package, SUBMISSION_NAME):
        state = 'SUBMITTED'
    else:
        state = 'APPROVED'
    return {
        '_schema': 'joblooper.discovery.v1', 'app_id': slug,
        'company': jd.get('company'), 'title': jd.get('title'),
        'reference': jd.get('job_reference'), 'official_url': jd.get('url'),
        'state': state, 'folder': os.path.abspath(package) if package else None,
        'work_record': os.path.abspath(work), 'artifacts': artifacts,
        'integrity_errors': package_errors,
    }


def attach_pdfs(slug, pdfs, layout=None):
    """Add verified render derivatives to an approved, unsubmitted package."""
    package, manifest = load_release(slug)
    _, errors = verify_release(slug)
    if errors:
        raise ValueError('approved package integrity failed: ' + '; '.join(errors))
    if has_record_file(package, SUBMISSION_NAME):
        raise ValueError('submitted application artefacts are immutable')
    expected_names = {'pdf': 'CV.pdf', 'letter_pdf': 'COVER-LETTER.pdf'}
    additions = {}
    for label, source in pdfs.items():
        if label not in expected_names or not source:
            continue
        if not os.path.isfile(source):
            raise ValueError(f'{label}: rendered PDF is missing')
        with open(source, 'rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise ValueError(f'{label}: rendered file has no PDF signature')
        target = os.path.join(package, expected_names[label])
        existing = (manifest.get('files') or {}).get(label)
        if existing:
            if (os.path.isfile(target)
                    and store.sha256_file(target) == existing.get('sha256')):
                continue
            raise ValueError(f'{label}: manifest already records a different PDF')
        shutil.copy2(source, target)
        additions[label] = {
            'file': os.path.basename(target), 'sha256': store.sha256_file(target),
            'bytes': os.path.getsize(target),
        }
    if not additions:
        raise ValueError('no missing PDF artefacts were supplied')
    manifest['files'].update(additions)
    manifest['pdf_completed_at'] = store.now()
    if layout:
        manifest['layout'] = {**(manifest.get('layout') or {}), **layout}
    unsigned = {key: value for key, value in manifest.items()
                if key != 'manifest_sha256'}
    manifest['manifest_sha256'] = store.sha256_text(store.canonical_json(unsigned))
    store.write_json(record_path(package, MANIFEST_NAME), manifest)
    event = {
        'event': 'APPROVED_PDFS_COMPLETED', 'app_id': slug,
        'package_id': manifest.get('package_id'),
        'manifest_sha256': manifest['manifest_sha256'],
        'files': sorted(additions),
    }
    store.append_jsonl(os.path.join(store.job_dir(slug), 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    store.append_application_event(event)
    write_status(slug, 'APPROVED', manifest)
    return package, manifest


def _capture_screening_evidence(package, screening_file):
    """Copy an optional portal-answer export into the private application record."""
    if not screening_file:
        return None
    source = os.path.abspath(screening_file)
    if not os.path.isfile(source):
        raise ValueError('the screening-answer evidence file does not exist')
    extension = os.path.splitext(source)[1].lower()
    allowed = {'.pdf', '.txt', '.md', '.json', '.html', '.png', '.jpg', '.jpeg', '.webp'}
    if extension not in allowed:
        raise ValueError(
            'screening-answer evidence must be PDF, text, JSON, HTML or an image')
    target = record_path(package, 'SCREENING-ANSWERS' + extension, create=True)
    if os.path.abspath(target) != source:
        if os.path.exists(target):
            raise ValueError('screening-answer evidence is already present')
        shutil.copy2(source, target)
    return {
        'file': os.path.relpath(target, package).replace('\\', '/'),
        'sha256': store.sha256_file(target),
        'bytes': os.path.getsize(target),
        'basis': 'user-supplied exact portal-answer evidence',
    }


def record_submission(slug, sent_file, cover_letter_file=None, channel=None,
                      applied_date=None, screening_file=None):
    """Record the exact sent CV and optional cover letter without moving the folder."""
    package, manifest = load_release(slug)
    verified, errors = verify_release(slug)
    if errors:
        raise ValueError('approved package integrity failed: ' + '; '.join(errors))
    if has_record_file(package, SUBMISSION_NAME):
        raise ValueError('submission is already recorded')
    if not sent_file:
        raise ValueError('--sent-file is required; the system will not guess which CV was sent')
    exact = os.path.abspath(sent_file)
    package_abs = os.path.abspath(package)
    if not os.path.isfile(exact):
        raise ValueError('the exact sent artefact does not exist')
    if os.path.commonpath([package_abs, exact]) != package_abs:
        raise ValueError('the exact sent artefact must be inside this approved job folder')
    sent_name = os.path.relpath(exact, package_abs).replace('\\', '/')
    if '/' in sent_name or sent_name not in {'CV.pdf', 'CV.docx'}:
        raise ValueError('the exact sent artefact must be CV.pdf or CV.docx')
    sent_sha = store.sha256_file(exact)
    expected = next((info.get('sha256') for info in (manifest.get('files') or {}).values()
                     if info.get('file') == sent_name), None)
    if not expected or expected != sent_sha:
        raise ValueError('the exact sent artefact is not the manifest-verified approved CV')
    letter_name = None
    letter_sha = None
    if cover_letter_file:
        letter_exact = os.path.abspath(cover_letter_file)
        if not os.path.isfile(letter_exact):
            raise ValueError('the exact sent cover letter does not exist')
        if os.path.commonpath([package_abs, letter_exact]) != package_abs:
            raise ValueError('the exact sent cover letter must be inside this approved job folder')
        letter_name = os.path.relpath(letter_exact, package_abs).replace('\\', '/')
        if '/' in letter_name or letter_name not in {
                'COVER-LETTER.pdf', 'COVER-LETTER.docx'}:
            raise ValueError('the exact sent cover letter must be COVER-LETTER.pdf or COVER-LETTER.docx')
        letter_sha = store.sha256_file(letter_exact)
        letter_expected = next((
            info.get('sha256') for info in (manifest.get('files') or {}).values()
            if info.get('file') == letter_name), None)
        if not letter_expected or letter_expected != letter_sha:
            raise ValueError('the exact sent cover letter is not manifest-verified')
    screening = _capture_screening_evidence(package, screening_file)
    receipt = {
        '_schema': 'joblooper.submission.v2', 'app_id': slug,
        'package_id': verified['package_id'],
        'manifest_sha256': verified['manifest_sha256'],
        'sent_file': sent_name, 'sent_sha256': sent_sha,
        'sent_cover_letter': letter_name,
        'sent_cover_letter_sha256': letter_sha,
        'screening_evidence': screening,
        'applied': applied_date, 'channel': channel, 'recorded_at': store.now(),
    }
    store.write_json(record_path(package, SUBMISSION_NAME, create=True), receipt)
    event = {'event': 'SUBMITTED', 'artifact_folder': os.path.basename(package), **receipt}
    work = store.job_dir(slug)
    store.append_jsonl(os.path.join(work, 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    store.append_application_event(event)
    write_status(slug, 'SUBMITTED', manifest)
    return package, manifest, receipt


def _confirmed_submission_file(package, manifest, supplied, allowed):
    """Validate one explicitly selected file against its immutable manifest entry."""
    if not supplied:
        raise ValueError('the exact sent artefact is required')
    exact = os.path.abspath(supplied)
    package_abs = os.path.abspath(package)
    if not os.path.isfile(exact):
        raise ValueError('the exact sent artefact does not exist')
    if os.path.commonpath([package_abs, exact]) != package_abs:
        raise ValueError('the exact sent artefact must be inside this approved job folder')
    relative = os.path.relpath(exact, package_abs).replace('\\', '/')
    label = allowed.get(relative)
    if not label:
        raise ValueError('the selected file is not an allowed CV or cover-letter artefact')
    info = (manifest.get('files') or {}).get(label) or {}
    digest = store.sha256_file(exact)
    if info.get('file') != relative or info.get('sha256') != digest:
        raise ValueError('the selected sent artefact does not match its approved manifest entry')
    return relative, label, digest


def record_confirmed_external_submission(slug, sent_file, cover_letter_file=None,
                                         channel=None, applied_date=None,
                                         screening_file=None):
    """Bind a user-confirmed sent file when an unsent package file later changed.

    This is intentionally narrower than repairing or reapproving the package.
    Every selected sent file must still match the original approved manifest;
    only integrity errors on *other employer-facing files* are tolerated and
    preserved on the receipt.
    """
    package, manifest = load_release(slug)
    if not package or not manifest:
        raise ValueError('approved artefact package not found')
    if has_record_file(package, SUBMISSION_NAME):
        raise ValueError('submission is already recorded')

    sent_name, sent_label, sent_sha = _confirmed_submission_file(
        package, manifest, sent_file, {'CV.pdf': 'pdf', 'CV.docx': 'docx'})
    letter_name = letter_label = letter_sha = None
    if cover_letter_file:
        letter_name, letter_label, letter_sha = _confirmed_submission_file(
            package, manifest, cover_letter_file,
            {'COVER-LETTER.pdf': 'letter_pdf',
             'COVER-LETTER.docx': 'letter_docx'})

    verified_manifest, package_errors = verify_release(slug)
    selected = {sent_label, letter_label} - {None}
    allowed_unsent = EMPLOYER_FACING_LABELS - selected
    critical = []
    for error in package_errors:
        label = error.split(':', 1)[0]
        if label not in allowed_unsent:
            critical.append(error)
    if critical:
        raise ValueError(
            'external confirmation refused; application evidence or a selected '
            'sent file is not intact: ' + '; '.join(critical))

    screening = _capture_screening_evidence(package, screening_file)
    receipt = {
        '_schema': 'joblooper.submission.v3', 'app_id': slug,
        'mode': 'user_confirmed_external_submission',
        'package_id': manifest.get('package_id'),
        'manifest_sha256': manifest.get('manifest_sha256'),
        'sent_file': sent_name, 'sent_sha256': sent_sha,
        'sent_cover_letter': letter_name,
        'sent_cover_letter_sha256': letter_sha,
        'screening_evidence': screening,
        'applied': applied_date, 'channel': channel, 'recorded_at': store.now(),
        'confirmation_basis': 'selected sent files match the approved manifest',
        'unsent_package_integrity_exceptions': list(package_errors),
    }
    store.write_json(record_path(package, SUBMISSION_NAME, create=True), receipt)
    event = {'event': 'EXTERNAL_SUBMISSION_CONFIRMED',
             'artifact_folder': os.path.basename(package), **receipt}
    work = store.job_dir(slug)
    store.append_jsonl(os.path.join(work, 'release_events.jsonl'),
                       {'timestamp': store.now(), **event})
    store.append_application_event(event)
    write_status(slug, 'SUBMITTED', verified_manifest or manifest)
    return package, manifest, receipt


def verify_submission(slug):
    """Verify the approved package and its exact sent-file receipt."""
    package, manifest = load_release(slug)
    if not package or not manifest:
        return None, ['approved artefact package not found']
    receipt = store.read_json(record_path(package, SUBMISSION_NAME), {}) or {}
    if not receipt:
        return None, ['submission receipt not found']
    if receipt.get('mode') == 'user_confirmed_external_submission':
        problems = []
        if manifest.get('job') != slug:
            problems.append('package manifest belongs to a different application')
        unsigned = {key: value for key, value in manifest.items()
                    if key != 'manifest_sha256'}
        if manifest.get('manifest_sha256') != store.sha256_text(
                store.canonical_json(unsigned)):
            problems.append('package manifest digest mismatch')
        if receipt.get('app_id') != slug:
            problems.append('submission receipt belongs to a different application')
        if receipt.get('manifest_sha256') != manifest.get('manifest_sha256'):
            problems.append('submission receipt does not match the package manifest')
        _, current_package_errors = verify_release(slug)
        selected_labels = set()
        for label, info in (manifest.get('files') or {}).items():
            if info.get('file') in {
                    receipt.get('sent_file'), receipt.get('sent_cover_letter')}:
                selected_labels.add(label)
        tolerated_unsent = EMPLOYER_FACING_LABELS - selected_labels
        recorded_exceptions = set(
            receipt.get('unsent_package_integrity_exceptions') or [])
        for error in current_package_errors:
            label = error.split(':', 1)[0]
            if label not in tolerated_unsent:
                problems.append(error)
            elif error not in recorded_exceptions:
                problems.append('new unsent package integrity exception: ' + error)
        try:
            sent_name, _, sent_sha = _confirmed_submission_file(
                package, manifest, os.path.join(package, receipt.get('sent_file', '')),
                {'CV.pdf': 'pdf', 'CV.docx': 'docx'})
            if sent_name != receipt.get('sent_file') or sent_sha != receipt.get('sent_sha256'):
                problems.append('exact submitted CV digest mismatch')
        except ValueError as error:
            problems.append(str(error))
        letter_name = receipt.get('sent_cover_letter')
        if letter_name:
            try:
                confirmed_name, _, letter_sha = _confirmed_submission_file(
                    package, manifest, os.path.join(package, letter_name),
                    {'COVER-LETTER.pdf': 'letter_pdf',
                     'COVER-LETTER.docx': 'letter_docx'})
                if (confirmed_name != letter_name
                        or letter_sha != receipt.get('sent_cover_letter_sha256')):
                    problems.append('exact submitted cover letter digest mismatch')
            except ValueError as error:
                problems.append(str(error))
        screening = receipt.get('screening_evidence')
        if screening:
            screening_path = os.path.join(package, screening.get('file', ''))
            if not os.path.isfile(screening_path):
                problems.append('screening-answer evidence is missing')
            elif store.sha256_file(screening_path) != screening.get('sha256'):
                problems.append('screening-answer evidence digest mismatch')
        return receipt, problems

    manifest, errors = verify_release(slug)
    if errors:
        return None, errors
    problems = []
    if receipt.get('app_id') != slug:
        problems.append('submission receipt belongs to a different application')
    if receipt.get('manifest_sha256') != manifest.get('manifest_sha256'):
        problems.append('submission receipt does not match the package manifest')
    sent = os.path.join(package, receipt.get('sent_file', ''))
    if not os.path.isfile(sent):
        problems.append('exact submitted CV is missing')
    elif store.sha256_file(sent) != receipt.get('sent_sha256'):
        problems.append('exact submitted CV digest mismatch')
    letter_name = receipt.get('sent_cover_letter')
    if letter_name:
        sent_letter = os.path.join(package, letter_name)
        if not os.path.isfile(sent_letter):
            problems.append('exact submitted cover letter is missing')
        elif store.sha256_file(sent_letter) != receipt.get('sent_cover_letter_sha256'):
            problems.append('exact submitted cover letter digest mismatch')
    screening = receipt.get('screening_evidence')
    if screening:
        screening_path = os.path.join(package, screening.get('file', ''))
        if not os.path.isfile(screening_path):
            problems.append('screening-answer evidence is missing')
        elif store.sha256_file(screening_path) != screening.get('sha256'):
            problems.append('screening-answer evidence digest mismatch')
    return receipt, problems
