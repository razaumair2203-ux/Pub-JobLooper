"""Flat-file store. JSONL + JSON only, stdlib only, no database.

Everything here is deliberately boring: if this module is deleted, every file it
touches is still readable in Notepad and greppable from the shell.
"""
import contextlib, copy, json, os, hashlib, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PERSONAL_PRIVATE repositories keep governed data beside the engine so the
# private Git history is authoritative. Sanitized PUBLIC_SKILL mirrors keep
# user data in the home directory, outside the installed skill. An explicit
# environment/CLI override always wins.
_ENV_DATA = 'JOBLOOPER_DATA_DIR'
_DATA_DIRS = {'truth', 'work', 'jobs', 'index', 'archive', 'audits', 'imports'}


def _default_data_root():
    configured = os.environ.get(_ENV_DATA)
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    policy = read_repository_policy()
    if policy.get('classification') == 'PUBLIC_SKILL':
        return os.path.join(os.path.expanduser('~'), '.joblooper')
    legacy = os.path.join(ROOT, 'truth', 'anchors.jsonl')
    current = os.path.join(ROOT, '.joblooper', 'truth', 'anchors.jsonl')
    if os.path.exists(legacy) and os.path.exists(current):
        raise RuntimeError(
            'ambiguous runtime layout: both root truth/ and .joblooper/truth exist; '
            'set JOBLOOPER_DATA_DIR explicitly and migrate deliberately')
    return ROOT if os.path.exists(legacy) else os.path.join(ROOT, '.joblooper')


def read_repository_policy():
    """Read the code-repository classification without depending on data IO."""
    path = os.path.join(ROOT, 'repo-policy.json')
    try:
        with open(path, encoding='utf-8') as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


DATA_ROOT = _default_data_root()
_TRUTH_CONTEXT_CACHE = None
_TRUTH_CONTEXT_FILES = (
    'truth/profile.json', 'truth/anchors.jsonl', 'truth/boundaries.json',
    'truth/aliases.json', 'truth/sections.json', 'truth/sources.jsonl',
    'truth/changelog.jsonl',
)
_ENGINE_CONTEXT_FILES = (
    'jl.py', 'core/store.py', 'core/integrity.py', 'core/match.py',
    'core/vec.py', 'core/build.py', 'core/gates.py', 'core/preview.py',
    'core/render.py', 'core/disclosure.py', 'core/learning.py',
    'core/release.py', 'core/feedback.py', 'core/employer_response.py',
    'core/casefile.py', 'core/cover_letter.py', 'core/employer_review.py',
    'core/truth_review.py', 'core/preflight.py',
    'core/language.py', 'core/pdftext.py',
)

OVERSIGHT_CONTRACT = {
    'authoritative': [
        'truth/profile.json', 'truth/anchors.jsonl', 'truth/boundaries.json',
        'truth/aliases.json', 'truth/sections.json', 'truth/sources.jsonl',
        'truth/changelog.jsonl',
    ],
    'deterministic': [
        'truth loading and freshness', 'source/reference integrity',
        'JD parsing and identity eligibility', 'retrieval and requirement matching',
        'CV assembly from approved variants', 'automated gates G1-G9',
        'cover-letter assembly from evidence already visible in the CV',
        'JD-evidenced rejection-risk review and non-decorative change decision',
        'approval freshness, rendering parity and release hashes',
        'employer-response correlation to one verified submitted JD/CV package',
    ],
    'contextual_oversight': [
        'relevance and role fit', 'specificity and translation quality',
        'cross-document contradiction review', 'deletion and bloat judgment',
        'ATS terminology review after evidence review', 'hostile recruiter review',
        'bounded official-source employer context when it can change a decision',
        'record, classify and resolve user feedback before renewed sign-off',
    ],
    'reviewer_must_not': [
        'invent or silently edit facts, metrics, dates, credentials or ownership',
        'treat the derived context snapshot as a new evidence source',
        'approve a claim without its exact truth-record citations',
        'hide a hard gate, mandatory risk or named-platform gap',
        'treat feedback as career truth or silently auto-apply it',
        'guess which application an ambiguous employer response belongs to',
    ],
}


def configure(data_root):
    """Point the process at another runtime data directory.

    Tests and multi-profile users use this instead of mutating repository files.
    Call it before loading anchors or aliases.
    """
    global DATA_ROOT, _TRUTH_CONTEXT_CACHE
    DATA_ROOT = os.path.abspath(os.path.expanduser(str(data_root)))
    _TRUTH_CONTEXT_CACHE = None
    return DATA_ROOT

def p(*parts):
    base = DATA_ROOT if parts and parts[0] in _DATA_DIRS else ROOT
    return os.path.join(base, *parts)


def code_p(*parts):
    return os.path.join(ROOT, *parts)


def data_p(*parts):
    return os.path.join(DATA_ROOT, *parts)

# ---------------------------------------------------------------- io

def read_jsonl(path):
    """Yield dicts from a .jsonl file. Blank lines and # comments are skipped.
    A malformed line raises with its line number so debugging is one glance."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{os.path.basename(path)} line {i}: {e}") from None
    return out

def append_jsonl(path, obj):
    """Append one complete audit event and force it to stable storage."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

def write_jsonl(path, objs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for o in objs:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    os.replace(tmp, path)

def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def read_text(path, default=''):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return f.read()


def canonical_json(obj):
    """Stable JSON used for freshness checks and release manifests."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256_text(text):
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


@contextlib.contextmanager
def writer_lock():
    """Allow one mutating Joblooper CLI process per data root."""
    lock_dir = data_p('index')
    os.makedirs(lock_dir, exist_ok=True)
    path = os.path.join(lock_dir, '.writer.lock')
    stream = open(path, 'a+b')
    try:
        if os.path.getsize(path) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as error:
            raise ValueError(
                f'another Joblooper write is active for {DATA_ROOT}') from error
        yield
    finally:
        try:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        stream.close()


def generation_fingerprint(jd=None):
    """Hash every input capable of changing a planned CV.

    The changelog is intentionally excluded: it records why truth changed, but
    does not itself change generated content. Engine files are included so an
    approval cannot survive a selection, matching, gate or rendering-code
    change made after the reviewer saw the plan.
    """
    context = truth_context()
    inputs = {rel: context['source_hashes'].get(rel) for rel in _TRUTH_CONTEXT_FILES
              if rel != 'truth/changelog.jsonl'}
    style = p('templates', 'style.json')
    inputs['templates/style.json'] = sha256_file(style) if os.path.exists(style) else None
    for rel in _ENGINE_CONTEXT_FILES:
        path = code_p(*rel.split('/'))
        inputs[f'engine/{rel}'] = sha256_file(path) if os.path.exists(path) else None
    inputs['truth_context'] = context.get(
        'generation_truth_sha256', context['truth_sha256'])
    if jd is not None:
        inputs['jd'] = sha256_text(canonical_json(jd))
    return {'files': inputs, 'sha256': sha256_text(canonical_json(inputs))}


def truth_approval_subject():
    """Hash the generation authority without hashing its approval receipt.

    ``profile.json`` contains both candidate facts and the approval metadata.
    The latter must be excluded or signing the digest would immediately change
    it. The append-only changelog records decisions but is not generation
    authority, so it is excluded for the same reason it is excluded from the
    generation fingerprint.
    """
    hashes = _truth_source_hashes()
    profile = copy.deepcopy(read_json(p('truth', 'profile.json'), {}) or {})
    for field in ('ready_for_generation', '_onboarding', '_truth_approval'):
        profile.pop(field, None)
    hashes['truth/profile.json'] = sha256_text(canonical_json(profile))
    hashes.pop('truth/changelog.jsonl', None)
    return {
        'files': hashes,
        'sha256': sha256_text(canonical_json(hashes)),
    }


def truth_approval_status():
    """Return a fail-closed assessment of candidate truth sign-off."""
    profile_value = read_json(p('truth', 'profile.json'), {}) or {}
    approval = profile_value.get('_truth_approval') or {}
    current = truth_approval_subject()
    problems = []
    if profile_value.get('ready_for_generation') is not True:
        problems.append('candidate truth is marked NEEDS_REVIEW')
    if not approval:
        problems.append('candidate truth has no digest-bound approval')
    elif approval.get('subject_sha256') != current['sha256']:
        problems.append('candidate truth changed after its last approval')
    return {
        'ready': not problems,
        'problems': problems,
        'approval': approval,
        'current_subject_sha256': current['sha256'],
        'current_files': current['files'],
    }

# ---------------------------------------------------------------- truth layer

def _truth_source_state():
    """Content state, not mtime state; preserved timestamps cannot fool cache."""
    state = {}
    for rel in _TRUTH_CONTEXT_FILES:
        path = p(*rel.split('/'))
        try:
            state[rel] = sha256_file(path)
        except OSError:
            state[rel] = None
    return state


def _truth_source_hashes():
    return {
        rel: sha256_file(p(*rel.split('/'))) if os.path.exists(p(*rel.split('/'))) else None
        for rel in _TRUTH_CONTEXT_FILES
    }


def _read_truth_file(rel):
    path = p(*rel.split('/'))
    return read_jsonl(path) if rel.endswith('.jsonl') else read_json(path, {})


def _compile_truth_context(source_hashes):
    """Build the private derived read model from authoritative truth files."""
    content = {rel: _read_truth_file(rel) for rel in _TRUTH_CONTEXT_FILES}
    if _truth_source_hashes() != source_hashes:
        raise RuntimeError('truth changed while its context was being built; retry the command')

    records = content['truth/anchors.jsonl'] or []
    active = [r for r in records if r.get('render') != 'superseded']
    by_identity = {}
    for record in active:
        for identity in record.get('identity') or []:
            by_identity.setdefault(identity, []).append(record.get('id'))
    context = {
        '_schema': 'joblooper.truth-context.v1',
        'built_at': now(),
        'truth_sha256': sha256_text(canonical_json(source_hashes)),
        'generation_truth_sha256': sha256_text(canonical_json({
            rel: digest for rel, digest in source_hashes.items()
            if rel != 'truth/changelog.jsonl'})),
        'source_hashes': source_hashes,
        'authority': {
            'source_of_truth': 'truth/* files listed in oversight_contract.authoritative',
            'derived_cache': 'index/truth_context.json',
            'rule': 'cache is discarded whenever any authoritative file hash changes',
        },
        'oversight_contract': OVERSIGHT_CONTRACT,
        'stats': {
            'records': len(records),
            'active_records': len(active),
            'sources': len(content['truth/sources.jsonl'] or []),
            'changelog_entries': len(content['truth/changelog.jsonl'] or []),
        },
        'profile': content['truth/profile.json'] or {},
        'records': records,
        'boundaries': content['truth/boundaries.json'] or {},
        'aliases': content['truth/aliases.json'] or {},
        'sections': content['truth/sections.json'] or {},
        'sources': content['truth/sources.jsonl'] or [],
        'changelog': content['truth/changelog.jsonl'] or [],
        'indices': {
            'record_ids': [r.get('id') for r in records],
            'active_record_ids': [r.get('id') for r in active],
            'record_ids_by_identity': by_identity,
        },
    }
    write_json(p('index', 'truth_context.json'), context)
    return context


def truth_context(force=False):
    """Return one coherent, fingerprinted read model for every truth consumer.

    The snapshot is a cache, never authority. Each new process verifies exact
    source hashes; repeated reads in that process use a cheap file-state check.
    """
    global _TRUTH_CONTEXT_CACHE
    state = _truth_source_state()
    if not force and _TRUTH_CONTEXT_CACHE \
            and _TRUTH_CONTEXT_CACHE.get('_source_state') == state:
        return _TRUTH_CONTEXT_CACHE['context']

    hashes = _truth_source_hashes()
    path = p('index', 'truth_context.json')
    cached = None if force else read_json(path)
    if not cached or cached.get('source_hashes') != hashes:
        cached = _compile_truth_context(hashes)
    _TRUTH_CONTEXT_CACHE = {'_source_state': state, 'context': cached}
    return cached


def reset_context_cache():
    global _TRUTH_CONTEXT_CACHE
    _TRUTH_CONTEXT_CACHE = None

def anchors():
    """All anchor records, keyed by id, plus the ordered list."""
    recs = truth_context()['records']
    return {r['id']: r for r in recs}, recs


def generation_anchors():
    """Active records available to generation; superseded rows remain audit-only."""
    context = truth_context()
    active = set(context['indices']['active_record_ids'])
    recs = [r for r in context['records'] if r.get('id') in active]
    return {r['id']: r for r in recs}, recs

def profile():
    return truth_context()['profile']

def boundaries():
    return truth_context()['boundaries']

def aliases():
    return truth_context()['aliases']


def sections():
    return truth_context()['sections']


def sources():
    return truth_context()['sources']

def changelog():
    return truth_context()['changelog']


def log_change(scope, instruction, effect, status='APPROVED',
               affected=None, supersedes=None, conflict='NONE'):
    """Append-only. Never overwrite, never delete. This is the audit spine."""
    entry = {
        'entry_id': f"UCC-{today().replace('-','')}-{len(changelog())+1:03d}",
        'timestamp': now(),
        'status': status,
        'scope': scope,
        'affected_files': affected or [],
        'user_instruction': instruction,
        'effect': effect,
        'supersedes': supersedes or [],
        'conflict_state': conflict,
    }
    append_jsonl(p('truth', 'changelog.jsonl'), entry)
    reset_context_cache()
    return entry

# ---------------------------------------------------------------- jobs

def job_dir(slug):
    """Internal working record for one stable application id.

    New records live under ``work/``.  The legacy ``jobs/<app_id>`` fallback
    keeps old/private data and the fictional starter usable until migrated.
    Human-facing approved folders are resolved separately through case_registry.
    """
    work = p('work', slug)
    legacy = p('jobs', slug)
    if os.path.isdir(work):
        return work
    if os.path.isdir(legacy) and slug not in {
            os.path.basename(item.get('artifact_dir', ''))
            for item in case_registry().values()}:
        return legacy
    return work


def approved_dir(slug):
    row = case_registry().get(slug) or {}
    rel = row.get('artifact_dir')
    return data_p(*rel.split('/')) if rel else None


def case_registry():
    data = read_json(p('index', 'cases.json'), {}) or {}
    return data.get('cases', {}) if isinstance(data, dict) else {}


def _write_case_registry(cases):
    write_json(p('index', 'cases.json'), {
        '_schema': 'joblooper.case-registry.v1', 'cases': cases,
    })


def _safe_display_part(value, label):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '-', str(value or ''))
    text = re.sub(r'\s+', ' ', text).strip(' .')
    if not text:
        raise ValueError(f'{label} is missing; cannot create an approved folder')
    return text


def approved_folder_name(jd, approved_at):
    date = str(approved_at or '')[:10]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('approval timestamp has no valid YYYY-MM-DD date')
    company = _safe_display_part(jd.get('company'), 'company')
    title = _safe_display_part(jd.get('title'), 'job title')
    reference = str(jd.get('job_reference') or '').strip()
    if not reference:
        source_hash = str(jd.get('raw_sha256') or '')[:8]
        if not source_hash:
            source_hash = sha256_text(canonical_json(jd))[:8]
        reference = 'NOT-RECORDED-' + source_hash
    reference = _safe_display_part(reference, 'job reference')
    return f'{date}__{company}__{title}__ref-{reference}'


def create_approved_case(slug, approved_at, plan_sha256):
    """Create the one human-facing folder after exact chat approval."""
    cases = case_registry()
    if slug in cases:
        row = cases[slug]
        if row.get('plan_sha256') != plan_sha256:
            raise ValueError('an approved folder exists for a different plan')
        path = approved_dir(slug)
        if not path or not os.path.isdir(path):
            raise ValueError('case registry points to a missing approved folder')
        return path, row
    d = job_dir(slug)
    jd = read_json(os.path.join(d, 'jd.json'), {}) or {}
    folder = approved_folder_name(jd, approved_at)
    rel = f'jobs/{folder}'
    target = data_p('jobs', folder)
    if len(os.path.abspath(target)) > 230:
        raise ValueError('approved folder path is too long; shorten the recorded job title explicitly')
    if os.path.exists(target):
        raise ValueError('approved folder path already exists for an unregistered case')
    os.makedirs(target, exist_ok=False)
    row = {
        'app_id': slug, 'artifact_dir': rel, 'approved_at': approved_at,
        'plan_sha256': plan_sha256, 'company': jd.get('company'),
        'title': jd.get('title'), 'job_reference': jd.get('job_reference'),
    }
    cases[slug] = row
    try:
        _write_case_registry(cases)
    except Exception:
        try:
            os.rmdir(target)
        except OSError:
            pass
        raise
    return target, row


def remove_approved_case(slug):
    cases = case_registry()
    row = cases.pop(slug, None)
    if row is not None:
        _write_case_registry(cases)
    return row

def list_jobs():
    names = set()
    work = p('work')
    if os.path.isdir(work):
        names.update(x for x in os.listdir(work)
                     if os.path.isdir(os.path.join(work, x)))
    registered_folders = {
        os.path.basename(item.get('artifact_dir', ''))
        for item in case_registry().values()
    }
    legacy = p('jobs')
    if os.path.isdir(legacy):
        names.update(x for x in os.listdir(legacy)
                     if os.path.isdir(os.path.join(legacy, x))
                     and x not in registered_folders)
    return sorted(names)

def slugify(*parts):
    s = '__'.join(str(x) for x in parts if x)
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return re.sub(r'-{2,}', '-', s)

def resolve_job(name):
    """Accept a full slug, a unique prefix, or a fuzzy fragment."""
    jobs = list_jobs()
    if name in jobs:
        return name
    hits = [j for j in jobs if name.lower() in j.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"No job matches '{name}'. Known: {', '.join(jobs) or '(none)'}")
    raise SystemExit(f"'{name}' is ambiguous: {', '.join(hits)}")

# ---------------------------------------------------------------- misc

def today():
    return datetime.date.today().isoformat()

def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]

def applications():
    """Materialised latest state, retained for simple queries and compatibility."""
    return read_jsonl(p('index', 'applications.jsonl'))


def application_events():
    return read_jsonl(p('index', 'application_events.jsonl'))


def append_application_event(event):
    event = {'event_id': f"APP-{now()}-{len(application_events()) + 1:04d}",
             'timestamp': now(), **event}
    append_jsonl(p('index', 'application_events.jsonl'), event)
    return event
