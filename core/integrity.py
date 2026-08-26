"""Truth/configuration integrity checks.

These checks validate the evidence contract itself.  Output gates cannot rescue a
record whose fact, render text, source state, or references are internally
inconsistent.
"""
import collections
import datetime
import os
import re

from . import store, vec


RECORD_TYPES = {
    'anchor', 'boundary', 'credential', 'education', 'positioning',
    'publication', 'recognition', 'role', 'skill',
}
STATUSES = {'APPROVED', 'CONTROLLED', 'IN_PROGRESS', 'PUBLISHED', 'SUPPORTED', 'VERIFIED'}
TIERS = {'professional', 'qualification', 'coursework', 'training'}
RETENTION_POLICIES = {'all_eligible', 'ranked'}
SECTION_SOURCES = {
    'competency_band', 'credential', 'education', 'highlight', 'positioning',
    'publication', 'recognition', 'role_bullets', 'skill',
}
TAILORING_MODES = {
    'all_verified', 'governed_identity_story', 'identity_positioning',
    'jd_complement', 'jd_ranked', 'jd_reserved_then_lane_core',
    'lane_or_jd', 'professional_plus_lane_or_jd',
}
SOURCE_TAILORING = {
    'competency_band': {'jd_complement'},
    'credential': {'professional_plus_lane_or_jd'},
    'education': {'all_verified'},
    'highlight': {'governed_identity_story'},
    'positioning': {'identity_positioning'},
    'publication': {'lane_or_jd'},
    'recognition': {'jd_ranked'},
    'role_bullets': {'jd_reserved_then_lane_core'},
    'skill': {'jd_ranked'},
}
BROAD_SOURCE_KINDS = {
    'canonical_cv', 'evidence_register', 'career_history', 'historical_cv',
    'signed_reference', 'reference_letter',
}
RENDER_VALUES = {
    'blocked_pending_validation', 'competency_band', 'header_only', 'never',
    'only_if_asked', 'only_if_confirmed', 'summary_only', 'superseded',
    'supporting_only',
}
DATE = re.compile(r'^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$')


def _ref_values(rec, field):
    value = rec.get(field) or []
    return value if isinstance(value, list) else [value]


def _source_registry():
    rows = store.sources()
    return {r.get('id'): r for r in rows if r.get('id')}, rows


def source_review_rows():
    """Report one-time coverage review and current anchor use per source.

    Broad narrative sources can contain several career claims. A file hash
    proves only that the reviewed file did not change. ``coverage_review`` is a
    reviewer attestation; v2 reviews additionally enumerate claim
    dispositions. Neither mechanism independently proves that a source is true.
    """
    _, recs = store.anchors()
    use = collections.Counter()
    for record in recs:
        for ref in record.get('evidence_refs') or []:
            if isinstance(ref, dict) and ref.get('source_id'):
                use[ref['source_id']] += 1
    rows = []
    for source in store.sources():
        review = source.get('coverage_review') or {}
        broad = source.get('kind') in BROAD_SOURCE_KINDS
        expected = str(source.get('sha256') or '').lower()
        reviewed = str(review.get('reviewed_sha256') or '').lower()
        state = 'not_required'
        if broad:
            if review.get('status') != 'reviewed':
                state = 'missing'
            elif not expected or reviewed != expected:
                state = 'stale'
            else:
                state = 'reviewed'
        rows.append({
            'id': source.get('id'), 'kind': source.get('kind'), 'broad': broad,
            'state': state, 'anchor_refs': use[source.get('id')],
            'reviewed_at': review.get('reviewed_at'),
            'scope': review.get('scope', ''),
        })
    return rows


def check_truth():
    """Return ``(errors, warnings, stats)`` for all generation inputs."""
    by_id, recs = store.anchors()
    profile = store.profile()
    boundaries = store.boundaries()
    sections = store.sections()
    sources, source_rows = _source_registry()
    changes = {x.get('entry_id') for x in store.changelog()}
    errors, warnings = [], []

    ids = [r.get('id') for r in recs]
    for rid, n in collections.Counter(ids).items():
        if not rid:
            errors.append('record without id')
        elif n > 1:
            errors.append(f"{rid}: duplicate id ({n} records)")

    ladder = boundaries.get('ownership_ladder') or []
    identities = set((profile.get('identities') or {}).keys()) | {'*'}
    headlines = profile.get('headlines') or {}
    for identity in sorted(identities - {'*'}):
        if not str(headlines.get(identity, '')).strip():
            errors.append(f"profile: identity {identity!r} has no controlled headline")
    for language, assessment in (profile.get('languages') or {}).items():
        if not isinstance(assessment, dict) or assessment.get('classification') not in {
                'DIRECT', 'PARTIAL', 'GAP'} or not assessment.get('note'):
            errors.append(f"profile: language assessment {language!r} is incomplete")
    work_auth = ((profile.get('location') or {}).get('work_authorisation') or {})
    for field in ('display_rules', 'requirement_rules'):
        for n, rule in enumerate(work_auth.get(field) or [], 1):
            if not isinstance(rule, dict) or not rule.get('terms'):
                errors.append(f"profile: {field}[{n}] needs non-empty terms")
            if field == 'display_rules' and not rule.get('phrasing'):
                errors.append(f"profile: {field}[{n}] needs phrasing")
            if field == 'requirement_rules' and (
                    rule.get('classification') not in {'DIRECT', 'PARTIAL', 'GAP'}
                    or not rule.get('note')):
                errors.append(f"profile: {field}[{n}] needs classification and note")
    seen_evidence_numbers = collections.defaultdict(list)
    anchor_edges = collections.defaultdict(set)
    terminal_evidence = set()

    def register_evidence_refs(rid, refs, status):
        if not refs:
            if status in {'VERIFIED', 'PUBLISHED'}:
                warnings.append(
                    f"{rid}: legacy free-text evidence; add evidence_refs for machine verification")
            return
        if not isinstance(refs, list):
            errors.append(f"{rid}: evidence_refs must be a list")
            return
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f"{rid}: malformed evidence reference {ref!r}")
                continue
            keys = [k for k in ('source_id', 'anchor_id', 'change_id') if ref.get(k)]
            if len(keys) != 1:
                errors.append(f"{rid}: evidence reference needs exactly one of "
                              "source_id, anchor_id or change_id")
                continue
            key = keys[0]
            value = ref[key]
            if key == 'source_id' and value not in sources:
                errors.append(f"{rid}: unknown evidence source {value!r}")
            elif key == 'anchor_id' and value not in by_id:
                errors.append(f"{rid}: unknown evidence anchor {value!r}")
            elif key == 'change_id' and value not in changes:
                errors.append(f"{rid}: unknown evidence change {value!r}")
            elif key == 'anchor_id':
                anchor_edges[rid].add(value)
            else:
                terminal_evidence.add(rid)

    for r in recs:
        rid = r.get('id') or '?'
        typ = r.get('type')
        if typ not in RECORD_TYPES:
            errors.append(f"{rid}: unknown type {typ!r}")
        if r.get('status') not in STATUSES:
            errors.append(f"{rid}: unknown or missing status {r.get('status')!r}")
        if r.get('ownership') and r.get('ownership') not in ladder:
            errors.append(f"{rid}: unknown ownership {r.get('ownership')!r}")
        for n, constraint in enumerate(r.get('claim_caps') or [], 1):
            if (not isinstance(constraint, dict)
                    or not str(constraint.get('pattern') or '').strip()
                    or constraint.get('max') not in ladder):
                errors.append(f"{rid}: claim_caps[{n}] needs pattern and valid max ownership")
        if typ not in {'role', 'boundary'} and (
                not isinstance(r.get('identity'), list) or not r.get('identity')):
            errors.append(f"{rid}: identity must be a non-empty list")
        elif isinstance(r.get('identity'), list):
            unknown = set(r['identity']) - identities
            if unknown:
                errors.append(f"{rid}: unknown identity {sorted(unknown)}")

        conf = r.get('confidence')
        if conf is not None and (not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
            errors.append(f"{rid}: confidence must be between 0 and 1")

        directive = r.get('render')
        if directive and directive not in RENDER_VALUES and not str(directive).startswith('merge:'):
            errors.append(f"{rid}: unknown render directive {directive!r}")
        if str(directive).startswith('merge:'):
            target = str(directive).split(':', 1)[1]
            if target not in by_id:
                errors.append(f"{rid}: merge target {target!r} does not exist")
            if r.get('merge_relation') not in {None, 'causal', 'chronological'}:
                errors.append(f"{rid}: merge_relation must be causal or chronological")

        register_evidence_refs(rid, r.get('evidence_refs'), r.get('status'))

        for field in ('role_id', 'supports'):
            for ref in _ref_values(r, field):
                if ref and ref not in by_id:
                    errors.append(f"{rid}: {field} reference {ref!r} does not exist")

        period = r.get('period')
        if period is not None:
            if not isinstance(period, list) or len(period) != 2:
                errors.append(f"{rid}: period must be [start, end]")
            else:
                start, end = period
                if start and not DATE.match(str(start)):
                    errors.append(f"{rid}: invalid period start {start!r}")
                if end and not DATE.match(str(end)):
                    errors.append(f"{rid}: invalid period end {end!r}")
                if start and end and str(start) > str(end):
                    errors.append(f"{rid}: period starts after it ends")

        if typ == 'role':
            for field in ('title', 'org', 'period'):
                if not r.get(field):
                    errors.append(f"{rid}: role missing {field}")
            continue
        if typ == 'boundary':
            continue

        if not r.get('fact'):
            errors.append(f"{rid}: missing fact")
        bullets = r.get('bullet') or {}
        for variant in ('short', 'std', 'long'):
            if not bullets.get(variant):
                errors.append(f"{rid}: missing bullet.{variant}")
        if not r.get('evidence') and not r.get('evidence_refs'):
            errors.append(f"{rid}: no evidence citation")

        # Atomic experience facts must still mean the same thing after
        # re-voicing.  Positioning and skill composites intentionally summarise
        # several records and are checked through their supports instead.
        if typ in {'anchor', 'credential', 'education', 'publication', 'recognition'} \
                and r.get('fact') and bullets:
            best = max((vec.cosine(r['fact'], text) for text in bullets.values()), default=0)
            if best < 0.10:
                errors.append(f"{rid}: fact and bullet variants are semantically disconnected ({best:.2f})")

        for m in r.get('metrics') or []:
            if not isinstance(m, dict) or not str(m.get('n', '')).strip():
                errors.append(f"{rid}: malformed metric {m!r}")
            if str(m.get('status', '')).upper() == 'UNVALIDATED' \
                    and directive != 'blocked_pending_validation':
                errors.append(f"{rid}: unvalidated metric is renderable")

        if r.get('tier') and r.get('tier') not in TIERS:
            errors.append(f"{rid}: unknown credential tier {r.get('tier')!r}")
        provenance = (r.get('evidence') or '') + ' ' + (r.get('boundary') or '')
        if r.get('status') in {'APPROVED', 'VERIFIED', 'PUBLISHED', 'SUPPORTED'} \
                and re.search(r'\b(?:UNCONFIRMED|UNVALIDATED|PENDING REVIEW)\b', provenance):
            errors.append(f"{rid}: authoritative record still declares unresolved provenance")
        elif r.get('status') in {'VERIFIED', 'PUBLISHED'} and re.search(
                r'\b(confirm|not yet|pending)\b', provenance, re.I):
            warnings.append(f"{rid}: verified/published record still contains unresolved language")

        evidence = r.get('evidence') or ''
        for number in re.finditer(r'\b\d{7,}\b', evidence):
            # Changelog dates in IDs (UCC-20260819-001) are provenance, not
            # certificate/credential numbers shared across records.
            if evidence[max(0, number.start() - 4):number.start()] == 'UCC-':
                continue
            seen_evidence_numbers[number.group(0)].append(rid)

    # Every authoritative claim must terminate at a registered source or
    # reviewed change; anchor-to-anchor citation cycles are not provenance.
    visiting = set()
    memo = {}

    def reaches_terminal(rid, trail):
        if rid in memo:
            return memo[rid]
        if rid in visiting:
            cycle = trail[trail.index(rid):] + [rid] if rid in trail else trail + [rid]
            errors.append('evidence-reference cycle: ' + ' -> '.join(cycle))
            return False
        if rid in terminal_evidence:
            memo[rid] = True
            return True
        visiting.add(rid)
        result = any(reaches_terminal(child, trail + [rid])
                     for child in anchor_edges.get(rid, ()))
        visiting.discard(rid)
        memo[rid] = result
        return result

    for record in recs:
        if record.get('status') in {'APPROVED', 'VERIFIED', 'PUBLISHED', 'SUPPORTED'} \
                and record.get('evidence_refs') \
                and not reaches_terminal(record['id'], []):
            errors.append(f"{record['id']}: evidence references have no acyclic path "
                          "to a registered source or reviewed change")

    for number, owners in seen_evidence_numbers.items():
        creds = [x for x in owners if by_id.get(x, {}).get('type') == 'credential']
        if len(set(creds)) > 1:
            warnings.append(f"evidence identifier {number} is shared by credentials {sorted(set(creds))}")

    source_ids = [r.get('id') for r in source_rows]
    for sid, n in collections.Counter(source_ids).items():
        if sid and n > 1:
            errors.append(f"source {sid}: duplicate id")
    for sid, src in sources.items():
        path = src.get('path')
        expected = src.get('sha256')
        if path:
            full = path if os.path.isabs(path) else os.path.join(store.DATA_ROOT, path)
            if not os.path.exists(full):
                warnings.append(f"source {sid}: file not present at {path}")
            elif expected and store.sha256_file(full).lower() != str(expected).lower():
                errors.append(f"source {sid}: SHA-256 mismatch for {path}")

        if src.get('kind') in BROAD_SOURCE_KINDS:
            review = src.get('coverage_review')
            if not isinstance(review, dict) or review.get('status') != 'reviewed':
                errors.append(
                    f"source {sid}: broad narrative source needs a completed coverage_review")
                continue
            if not expected or str(review.get('reviewed_sha256') or '').lower() \
                    != str(expected).lower():
                errors.append(
                    f"source {sid}: coverage review is stale or lacks the registered source hash")
            if not DATE.match(str(review.get('reviewed_at') or '')):
                errors.append(f"source {sid}: coverage_review needs reviewed_at YYYY-MM-DD")
            if not str(review.get('scope') or '').strip():
                errors.append(f"source {sid}: coverage_review needs an explicit review scope")
            dispositions = review.get('claim_dispositions')
            if str(review.get('reviewed_at') or '') >= '2026-08-26':
                if not isinstance(dispositions, list) or not dispositions:
                    errors.append(
                        f"source {sid}: new broad-source review needs claim_dispositions")
                elif any(not isinstance(item, dict)
                         or item.get('disposition') not in {
                             'ADOPTED', 'DUPLICATE', 'REJECTED', 'UNRESOLVED'}
                         or not str(item.get('claim') or '').strip()
                         for item in dispositions):
                    errors.append(f"source {sid}: malformed claim_dispositions")

    section_rows = sections.get('sections') or []
    section_ids = [s.get('id') for s in section_rows]
    for sid, n in collections.Counter(section_ids).items():
        if not sid or n > 1:
            errors.append(f"sections: invalid or duplicate id {sid!r}")
    for s in section_rows:
        sid = s.get('id') or '?'
        if not s.get('purpose'):
            errors.append(f"section {sid}: missing purpose")
        if s.get('source') not in SECTION_SOURCES:
            errors.append(f"section {sid}: unknown source {s.get('source')!r}")
        if s.get('tailoring') not in TAILORING_MODES:
            errors.append(f"section {sid}: unknown tailoring contract "
                          f"{s.get('tailoring')!r}")
        elif s.get('tailoring') not in SOURCE_TAILORING.get(s.get('source'), set()):
            errors.append(f"section {sid}: tailoring {s.get('tailoring')!r} is invalid "
                          f"for source {s.get('source')!r}")
        if s.get('min_items', 0) > s.get('max', 10**9):
            errors.append(f"section {sid}: min_items exceeds max")
        if s.get('retention') and s.get('retention') not in RETENTION_POLICIES:
            errors.append(f"section {sid}: unknown retention policy {s.get('retention')!r}")
        unknown_tiers = set(s.get('protected_tiers') or []) - TIERS
        if unknown_tiers:
            errors.append(f"section {sid}: unknown protected credential tier(s) "
                          f"{sorted(unknown_tiers)}")
        for dep in s.get('dedupe_against') or []:
            if dep not in section_ids:
                errors.append(f"section {sid}: unknown dedupe target {dep!r}")
        unknown_protected_lanes = set(s.get('protected_if_lane') or []) - identities
        if unknown_protected_lanes:
            errors.append(
                f"section {sid}: unknown protected lane(s) {sorted(unknown_protected_lanes)}")
        if s.get('source') == 'role_bullets':
            core_maps = [('default', s.get('core_by_role') or {})]
            for lane_name, lane_map in (s.get('core_by_lane') or {}).items():
                if lane_name not in identities:
                    errors.append(f"section {sid}: unknown core lane {lane_name!r}")
                if not isinstance(lane_map, dict):
                    errors.append(f"section {sid}: core lane {lane_name!r} must be an object")
                    continue
                core_maps.append((lane_name, lane_map))
            for lane_name, core_map in core_maps:
                for role_id, record_ids in core_map.items():
                    if role_id not in by_id or by_id[role_id].get('type') != 'role':
                        errors.append(
                            f"section {sid}: unknown {lane_name} core role {role_id!r}")
                    if not isinstance(record_ids, list) or len(record_ids) != len(set(record_ids)):
                        errors.append(
                            f"section {sid}: {lane_name} core records for {role_id} must be a unique list")
                        continue
                    for record_id in record_ids:
                        record = by_id.get(record_id)
                        role_refs = _ref_values(record or {}, 'role_id')
                        if not record or record.get('type') != 'anchor' or role_id not in role_refs:
                            errors.append(
                                f"section {sid}: {lane_name} core record {record_id!r} "
                                f"does not belong to {role_id}")

        if s.get('source') == 'positioning':
            for field in ('min_words', 'max_words', 'min_sentences', 'max_sentences'):
                if not isinstance(s.get(field), int) or s[field] <= 0:
                    errors.append(f"section {sid}: {field} must be a positive integer")
            if (isinstance(s.get('min_words'), int)
                    and isinstance(s.get('max_words'), int)
                    and s['min_words'] > s['max_words']):
                errors.append(f"section {sid}: min_words exceeds max_words")
            if (isinstance(s.get('min_sentences'), int)
                    and isinstance(s.get('max_sentences'), int)
                    and s['min_sentences'] > s['max_sentences']):
                errors.append(f"section {sid}: min_sentences exceeds max_sentences")

    known_lanes = identities - {'*'}
    for lane_name, lane in (sections.get('lanes') or {}).items():
        if lane_name not in known_lanes:
            errors.append(f"sections: unknown lane {lane_name!r}")
        if not isinstance(lane, dict):
            errors.append(f"sections: lane {lane_name!r} must be an object")
            continue
        order = lane.get('order') or []
        if not isinstance(order, list) or len(order) != len(set(order)):
            errors.append(f"sections: lane {lane_name!r} order must be a unique list")
        for section_id in order:
            if section_id not in section_ids:
                errors.append(f"sections: lane {lane_name!r} orders unknown section "
                              f"{section_id!r}")
        drop = lane.get('drop') or []
        if not isinstance(drop, list) or len(drop) != len(set(drop)):
            errors.append(f"sections: lane {lane_name!r} drop must be a unique list")
        for section_id in drop:
            if section_id not in section_ids:
                errors.append(f"sections: lane {lane_name!r} drops unknown section "
                              f"{section_id!r}")
        caps = lane.get('caps') or {}
        if not isinstance(caps, dict):
            errors.append(f"sections: lane {lane_name!r} caps must be an object")
            continue
        for section_id, value in caps.items():
            if section_id not in section_ids:
                errors.append(f"sections: lane {lane_name!r} caps unknown section "
                              f"{section_id!r}")
            if not isinstance(value, int) or value <= 0:
                errors.append(f"sections: lane {lane_name!r} cap for {section_id!r} "
                              "must be a positive integer")

    disclosure = boundaries.get('disclosure') or {}
    if disclosure.get('output_mode') not in {None, 'named', 'generic_defence'}:
        errors.append('boundaries: disclosure.output_mode is invalid')
    for n, rule in enumerate(disclosure.get('external_aliases') or [], 1):
        if not isinstance(rule, dict) or not rule.get('pattern') or 'replacement' not in rule:
            errors.append(f'boundaries: external_aliases[{n}] needs pattern and replacement')
            continue
        try:
            re.compile(rule['pattern'])
        except re.error as error:
            errors.append(f'boundaries: external_aliases[{n}] invalid regex: {error}')

    highlight_section = next((s for s in section_rows if s.get('source') == 'highlight'), {})
    highlight_records = [r for r in recs if r.get('placement') == 'highlights']
    for record in highlight_records:
        sequence = record.get('highlight_sequence')
        if not isinstance(sequence, int) or sequence <= 0:
            errors.append(f"{record['id']}: highlight_sequence must be a positive integer")
    for identity in sorted(identities - {'*'}):
        featured = [r['id'] for r in recs
                    if r.get('placement') == 'highlights'
                    and (identity in r.get('identity', []) or '*' in r.get('identity', []))]
        lane_cap = ((sections.get('lanes') or {}).get(identity, {}).get('caps') or {}).get(
            highlight_section.get('id'), highlight_section.get('max', 0))
        if featured and (not isinstance(lane_cap, int) or lane_cap < len(featured)):
            errors.append(
                f"highlights: {identity} cap {lane_cap!r} cannot hold records {featured}")

    page_budgets = sections.get('page_budgets') or {}
    default_pages = sections.get('default_pages')
    if not isinstance(default_pages, int) or default_pages <= 0:
        errors.append('sections: default_pages must be a positive integer')
    elif str(default_pages) not in page_budgets:
        errors.append(f'sections: default_pages {default_pages} has no page budget')
    for pages, budget in page_budgets.items():
        try:
            page_count = int(pages)
        except (TypeError, ValueError):
            errors.append(f'sections: invalid page budget key {pages!r}')
            continue
        if page_count <= 0 or not isinstance(budget, dict):
            errors.append(f'sections: page budget {pages!r} must be a positive-page object')
            continue
        if budget.get('variant') not in {'short', 'std', 'long'}:
            errors.append(f'sections: page budget {pages} has invalid variant')
        for field in ('role_scale', 'section_scale'):
            value = budget.get(field)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f'sections: page budget {pages} needs positive {field}')
        bullet_cap = budget.get('experience_bullets_per_page')
        if not isinstance(bullet_cap, int) or bullet_cap <= 0:
            errors.append(
                f'sections: page budget {pages} needs positive experience_bullets_per_page')

    selection = sections.get('selection_guardrails') or {}
    fill = selection.get('minimum_fill_ratio')
    if not isinstance(fill, (int, float)) or not 0 < fill <= 1:
        errors.append('sections: selection_guardrails.minimum_fill_ratio must be in (0, 1]')
    impact = selection.get('significant_impact_threshold')
    if not isinstance(impact, (int, float)) or impact < 0:
        errors.append(
            'sections: selection_guardrails.significant_impact_threshold must be non-negative')

    stats = {
        'records': len(recs), 'sources': len(sources),
        'changelog_entries': len(store.changelog()),
        'checked_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    return errors, sorted(set(warnings)), stats
