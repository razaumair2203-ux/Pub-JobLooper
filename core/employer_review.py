"""Bounded pre-approval rejection-risk and CV-value assessment.

This is not a rejection predictor.  It surfaces explicit JD risks and decides
whether the current evidence selection has a demonstrated, truthful improvement
available.  Optional online context remains contextual oversight and can never
become candidate ground truth.
"""
import re

from . import store


CONTEXT_SCHEMA = 'joblooper.employer-context.v1'
DECISIONS = {'LEAVE_AS_IS', 'REPLAN'}
CONFIDENCE = {'HIGH', 'MEDIUM', 'LOW'}
BASES = {'OBSERVED', 'INFERRED'}


def validate_context(context, jd, active_ids):
    if not context:
        return []
    problems = []
    if context.get('_schema') != CONTEXT_SCHEMA:
        problems.append(f'employer context schema must be {CONTEXT_SCHEMA}')
    if context.get('job_url') != jd.get('url'):
        problems.append('employer context is not bound to the exact captured JD URL')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(context.get('researched_at') or '')):
        problems.append('employer context requires researched_at YYYY-MM-DD')
    sources = context.get('sources') or []
    if not 1 <= len(sources) <= 5:
        problems.append('employer context requires one to five sources')
    if sources and not any(source.get('kind') == 'exact_job' for source in sources):
        problems.append('employer context must include the exact job as a source')
    for source in sources:
        if not str(source.get('url') or '').startswith('http'):
            problems.append('every employer-context source requires an HTTP(S) URL')
        if not str(source.get('observation') or '').strip():
            problems.append('every employer-context source requires a concise observation')
    findings = context.get('findings') or []
    if len(findings) > 8:
        problems.append('employer context is capped at eight material findings')
    for finding in findings:
        if finding.get('basis') not in BASES:
            problems.append('every finding must declare OBSERVED or INFERRED basis')
        if finding.get('confidence') not in CONFIDENCE:
            problems.append('every finding must declare HIGH, MEDIUM or LOW confidence')
        unknown = [anchor for anchor in finding.get('anchor_ids') or []
                   if anchor not in active_ids]
        if unknown:
            problems.append('employer context cites unknown anchor(s): ' + ', '.join(unknown))
    decision = context.get('cv_decision')
    if decision not in DECISIONS:
        problems.append('employer context cv_decision must be LEAVE_AS_IS or REPLAN')
    if decision == 'REPLAN' and not context.get('proposed_changes'):
        problems.append('REPLAN requires at least one evidence-bound proposed change')
    for change in context.get('proposed_changes') or []:
        anchors = change.get('anchor_ids') or []
        if not anchors:
            problems.append('each proposed change requires existing anchor_ids')
        unknown = [anchor for anchor in anchors if anchor not in active_ids]
        if unknown:
            problems.append('proposed change cites unknown anchor(s): ' + ', '.join(unknown))
    return sorted(set(problems))


def assess(jd, m, cv, context=None, raw_text=''):
    """Return explicit risks and a non-decorative CV action decision."""
    by_id, _ = store.generation_anchors()
    context_errors = validate_context(context, jd, set(by_id))
    if context_errors:
        raise ValueError('invalid employer context: ' + '; '.join(context_errors))

    document = m.get('document') or {}
    visible = {row.get('n'): row for row in document.get('requirements', [])}
    risks = []
    for requirement in m.get('requirements', []):
        rendered = visible.get(requirement.get('n'), requirement)
        classification = rendered.get('match') or requirement.get('match')
        if classification not in {'GAP', 'PARTIAL', 'TRANSFERABLE'}:
            continue
        confidence = 'HIGH' if requirement.get('hard_gate') else (
            'MEDIUM' if classification in {'GAP', 'PARTIAL'} else 'LOW')
        risks.append({
            'requirement_number': requirement.get('n'),
            'classification': classification,
            'confidence': confidence,
            'text': requirement.get('text'),
            'note': requirement.get('note') or '',
            'visible_anchors': rendered.get('visible_anchors') or [],
            'cv_addressable': classification != 'GAP' and bool(
                rendered.get('visible_anchors')),
        })

    raw = ' '.join(str(value or '') for value in (
        raw_text, jd.get('summary'), jd.get('raw_text'), jd.get('title')))
    constraints = []
    checks = (
        ('GOVERNMENT_OR_CUSTOMER_APPROVAL', r'government.{0,30}customer approvals?|customer approvals?'),
        ('SECURITY_OR_EXPORT_CONTROL', r'security clearance|export control'),
        ('NATIONALITY_LIMITATION', r'national only|nationality restriction|saudi national only'),
    )
    for code, pattern in checks:
        if re.search(pattern, raw, re.I):
            constraints.append({'code': code, 'confidence': 'HIGH',
                                'basis': 'explicit captured JD language'})

    # A CV edit is warranted only when selection lost evidence that would
    # improve the visible classification.  Existing partials caused by missing
    # employer/platform truth are not fixable by rearranging prose.
    selected = set((cv.get('_selection') or {}).get('selected_ids') or [])
    improvements = []
    for requirement in m.get('requirements', []):
        rendered = visible.get(requirement.get('n'), {})
        corpus_class = requirement.get('match')
        visible_class = rendered.get('match', corpus_class)
        rank = {'DIRECT': 3, 'TRANSFERABLE': 2, 'PARTIAL': 1, 'GAP': 0}
        if rank.get(visible_class, 0) >= rank.get(corpus_class, 0):
            continue
        omitted = [candidate.get('id') for candidate in requirement.get('anchors', [])
                   if candidate.get('id') in by_id and candidate.get('id') not in selected]
        if omitted:
            improvements.append({
                'requirement_number': requirement.get('n'),
                'current': visible_class, 'available': corpus_class,
                'anchor_ids': omitted[:2],
                'reason': 'verified matched evidence was lost during CV selection',
            })

    leading_objections = []
    for risk in sorted(risks, key=lambda row: (
            {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}.get(row['confidence'], 3),
            {'GAP': 0, 'PARTIAL': 1, 'TRANSFERABLE': 2}.get(
                row['classification'], 3), row['requirement_number']))[:5]:
        leading_objections.append({
            'requirement_number': risk['requirement_number'],
            'objection': risk['text'], 'support': risk['confidence'],
            'classification': risk['classification'],
            'counterevidence_anchor_ids': risk.get('visible_anchors') or [],
            'cv_addressable': risk.get('cv_addressable', False),
            'unknown': ('The employer’s screening weight and applicant competition are '
                        'not observable from the advert.'),
        })

    contextual_decision = (context or {}).get('cv_decision')
    if improvements:
        decision = 'REPLAN'
        reason = 'Verified evidence can improve at least one visible requirement classification.'
    elif contextual_decision == 'REPLAN':
        decision = 'REPLAN'
        reason = str(context.get('decision_reason') or '').strip()
    else:
        decision = 'LEAVE_AS_IS'
        reason = ('No verified omitted evidence would improve the current requirement '
                  'classification; remaining risks require new truth or external eligibility.')

    return {
        '_schema': 'joblooper.employer-risk.v1',
        'job': jd.get('_slug'), 'company': jd.get('company'), 'role': jd.get('title'),
        'generated': store.now(), 'decision': decision, 'decision_reason': reason,
        'risks': risks, 'external_constraints': constraints,
        'leading_objections': leading_objections,
        'improvement_candidates': improvements,
        'online_context': {
            'present': bool(context),
            'sha256': (store.sha256_text(store.canonical_json(context)) if context else None),
            'finding_count': len((context or {}).get('findings') or []),
            'decision': contextual_decision,
        },
        'confidence_boundary': (
            'Confidence describes support for a screening factor, not the probability '
            'that this employer will reject the application.'),
        'cv_sha256': store.sha256_text(store.canonical_json(cv)),
    }


def validate(report, jd, cv, context=None):
    problems = []
    if report.get('company') != jd.get('company') or report.get('role') != jd.get('title'):
        problems.append('risk review belongs to a different JD')
    if report.get('cv_sha256') != store.sha256_text(store.canonical_json(cv)):
        problems.append('risk review is stale relative to the CV plan')
    expected_context = store.sha256_text(store.canonical_json(context)) if context else None
    if (report.get('online_context') or {}).get('sha256') != expected_context:
        problems.append('risk review is stale relative to employer context')
    if report.get('decision') not in DECISIONS:
        problems.append('risk review has no valid CV decision')
    return problems


def to_markdown(report, context=None):
    out = [f"# EMPLOYER RISK & VALUE DECISION — {report.get('company')} · {report.get('role')}", '',
           f"**CV decision:** `{report.get('decision')}`", '',
           report.get('decision_reason', ''), '',
           '> This is a screening-risk assessment, not a prediction of rejection.', '']
    if report.get('risks'):
        out += ['## JD-EVIDENCED RISKS', '']
        for risk in report['risks']:
            note = f" — {risk['note']}" if risk.get('note') else ''
            out.append(f"- **{risk['confidence']} · {risk['classification']}** · "
                       f"#{risk['requirement_number']} {risk['text']}{note}")
        out.append('')
    if report.get('external_constraints'):
        out += ['## EXPLICIT EXTERNAL CONSTRAINTS', '']
        for item in report['external_constraints']:
            out.append(f"- **{item['confidence']}** · {item['code']} — {item['basis']}")
        out.append('')
    out += ['## WHY THIS APPLICATION COULD STILL BE SCREENED OUT', '']
    if report.get('leading_objections'):
        for item in report['leading_objections']:
            anchors = ', '.join(item.get('counterevidence_anchor_ids') or []) or 'none visible'
            action = ('CV-addressable' if item.get('cv_addressable') else
                      'requires new truth or is externally constrained')
            out.append(f"- **{item['support']} · {item['classification']}** · "
                       f"#{item['requirement_number']} {item['objection']} — {action}; "
                       f"counterevidence: {anchors}")
    else:
        out.append('- No adverse JD-to-evidence classification is visible. Competition, '
                   'screening preferences and internal candidates remain unknowable.')
    out += ['', '> These are evidence-bounded objections, not predicted rejection causes.', '']
    if context:
        out += ['## OFFICIAL EMPLOYER CONTEXT', '']
        for finding in context.get('findings') or []:
            out.append(f"- **{finding['confidence']} · {finding['basis']}** — {finding['risk']}")
        out += ['', 'Sources:']
        for source in context.get('sources') or []:
            out.append(f"- [{source.get('title') or source['kind']}]({source['url']}) — "
                       f"{source['observation']}")
        out.append('')
    out += ['## CHANGE THRESHOLD', '',
            '- Change the CV only when verified evidence can improve visible fit or correct an error.',
            '- Leave it unchanged when the remaining risk is employer-specific experience, eligibility or speculation.',
            '- Online findings may guide emphasis; they never become candidate ground truth.', '']
    return '\n'.join(out)
