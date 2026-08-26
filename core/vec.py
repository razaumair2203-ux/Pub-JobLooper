"""Retrieval: BM25 + alias expansion, plus cosine for duplicate detection.

Design note (read this before "upgrading" it to neural embeddings):
the corpus is ~72 anchors. The failure mode that actually costs recall here is
VOCABULARY, not semantics -- a JD says "line maintenance planning", the anchor
says "flight-line MRO". aliases.json closes that gap explicitly and auditably:
you can always answer "why did this bullet come back?".

An embedding backend can be dropped in behind `embed()` later without changing
any caller. Until then this is deterministic, dependency-free and ~2ms.
"""
import math, re
from collections import Counter
from . import store

_WORD = re.compile(r"[a-z0-9][a-z0-9&+.#/-]*")

_ALIAS_CACHE = None

# Weight of a query term absent from every anchor, in the coverage denominator.
UNKNOWN_TERM_WEIGHT = 0.35


def reset_caches():
    """Reload aliases after switching data roots or editing the synonym map."""
    global _ALIAS_CACHE
    _ALIAS_CACHE = None

def _alias_tables():
    """term -> set of group tags it belongs to. Built once."""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        al = store.aliases()
        term2groups, stop = {}, set(al.get('stopwords', []))
        for gi, group in enumerate(al.get('groups', [])):
            tag = f"~g{gi}"
            for term in group:
                low = term.lower()
                term2groups.setdefault(low, set()).add(tag)
                # Index the stemmed form as well, so a plural in the JD still
                # resolves to the group a singular anchor keyword registered.
                st = ' '.join(_stem(w) for w in low.split())
                if st != low:
                    term2groups.setdefault(st, set()).add(tag)
        _ALIAS_CACHE = (term2groups, stop, al)
    return _ALIAS_CACHE

def _stem(w):
    """Light suffix normalisation so singular and plural are one token.

    Without this "avionic" and "avionics" are unrelated strings: an advert
    asking for "extensive aircraft avionic experience" scored GAP against an
    18-year avionics career, because every anchor says "avionics". Same class of
    miss for drawing/drawings, regulation/regulations, activity/activities.

    Deliberately crude -- no linguistic stemmer, just the three suffixes that
    actually cost matches here. Aggressive stemming would collide unrelated
    terms, which is worse than missing a plural.
    """
    if len(w) > 4:
        if w.endswith('ies'):
            return w[:-3] + 'y'
        if w.endswith('sses') or w.endswith('ss'):
            return w
        if w.endswith('s'):
            return w[:-1]
    return w


def tokens(text):
    """Lowercase word tokens, stopwords removed, lightly stemmed."""
    _, stop, _ = _alias_tables()
    out = []
    for w in _WORD.findall((text or '').lower()):
        if w in stop or len(w) < 2:
            continue
        s = _stem(w)
        if s in stop:
            continue
        out.append(s)
    return out

def expand(text):
    """Tokens PLUS alias-group tags for every matched term or phrase.

    Phrase matching runs first (up to 4-grams) so 'line maintenance' resolves as
    a unit before its words are considered individually.
    """
    term2groups, stop, _ = _alias_tables()
    low = (text or '').lower()
    out = Counter(tokens(text))

    words = [_stem(w) for w in _WORD.findall(low)]
    raw = _WORD.findall(low)
    for n in (4, 3, 2):
        for i in range(len(words) - n + 1):
            for seq in (' '.join(words[i:i + n]), ' '.join(raw[i:i + n])):
                for tag in term2groups.get(seq, ()):
                    out[tag] += 2      # phrase hits weigh more than word hits
    for w in set(words) | set(raw):
        for tag in term2groups.get(w, ()):
            out[tag] += 1
    return out

# ---------------------------------------------------------------- BM25

class BM25:
    """Standard BM25 over alias-expanded token bags."""
    K1, B = 1.5, 0.75

    def __init__(self, docs):
        # docs: list of (id, text)
        self.ids = [d[0] for d in docs]
        self.bags = [expand(d[1]) for d in docs]
        self.lens = [sum(b.values()) or 1 for b in self.bags]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        self.df = Counter()
        for b in self.bags:
            self.df.update(b.keys())
        self.N = len(docs)

    def _idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query):
        q = expand(query) if isinstance(query, str) else query
        out = []
        for i, bag in enumerate(self.bags):
            s = 0.0
            for term, qf in q.items():
                f = bag.get(term, 0)
                if not f:
                    continue
                denom = f + self.K1 * (1 - self.B + self.B * self.lens[i] / self.avg)
                s += self._idf(term) * (f * (self.K1 + 1)) / denom * min(qf, 3)
            if s > 0:
                out.append((self.ids[i], s))
        out.sort(key=lambda x: -x[1])
        return out

    # BM25 saturation constant: raw scores above this are "strong" in absolute
    # terms. Calibrated so a solidly-matching aerospace bullet lands near 0.6-0.7
    # on the saturation component alone.
    SAT_K = 6.0
    # Coverage dominates the blend on purpose. A requirement can only be DIRECT
    # if the anchor actually contains its distinctive terms -- a high BM25 score
    # driven by one shared common word must not read as a match.
    W_SAT, W_COV = 0.35, 0.65

    def normed(self, query, top=None):
        """Absolute 0..1 relevance.

        Deliberately NOT rescaled against the query's own best hit: that makes
        the top result 1.0 for every query, however weak, which silently turns
        real gaps into apparent DIRECT matches. Instead this blends BM25
        saturation with IDF-weighted term coverage, so an unanswerable
        requirement scores low and surfaces as a GAP -- which is the point.
        """
        q = expand(query) if isinstance(query, str) else query
        # Terms the corpus has never seen are usually the employer's own nouns
        # (an employer, customer or department) or advert prose, not capability. At full weight
        # they dominate the denominator and drag genuine matches down: "liaison
        # with aircraft and equipment Engineering and Design Authorities" scored
        # 0.42 against two years embedded inside a design authority. Discounted,
        # not zeroed -- a JD of entirely unknown vocabulary should still score
        # low. Genuine product gaps (Falcon-X, CATIA) are caught separately and
        # explicitly by _unmatched_proper_nouns.
        qterms = {t: self._idf(t) * (1.0 if self.df.get(t, 0) else UNKNOWN_TERM_WEIGHT)
                  for t in q}
        tot = sum(qterms.values()) or 1.0

        out = []
        for i, bag in enumerate(self.bags):
            raw = 0.0
            for term, qf in q.items():
                f = bag.get(term, 0)
                if not f:
                    continue
                denom = f + self.K1 * (1 - self.B + self.B * self.lens[i] / self.avg)
                raw += self._idf(term) * (f * (self.K1 + 1)) / denom * min(qf, 3)
            if raw <= 0:
                continue
            cov = sum(w for t, w in qterms.items() if bag.get(t, 0)) / tot
            sat = raw / (raw + self.SAT_K)
            out.append((self.ids[i], round(self.W_SAT * sat + self.W_COV * cov, 4)))

        out.sort(key=lambda x: -x[1])
        return out[:top] if top else out

# ---------------------------------------------------------------- similarity

def cosine(a, b):
    """Cosine over alias-expanded token bags. Used by G6 duplicate detection."""
    va = expand(a) if isinstance(a, str) else a
    vb = expand(b) if isinstance(b, str) else b
    if not va or not vb:
        return 0.0
    common = set(va) & set(vb)
    num = sum(va[t] * vb[t] for t in common)
    da = math.sqrt(sum(v * v for v in va.values()))
    db = math.sqrt(sum(v * v for v in vb.values()))
    return round(num / (da * db), 4) if da and db else 0.0

def embed(text):
    """Backend seam. Returns the sparse expanded bag today; swap for a dense
    vector later and every caller keeps working."""
    return expand(text)


def record_surface(record):
    """The factual/searchable surface of one truth record."""
    bullet = record.get('bullet') or {}
    return ' '.join(filter(None, [
        record.get('fact', ''), record.get('title', ''), record.get('framing', ''),
        ' '.join(record.get('keywords') or []),
        ' '.join(str(v) for v in bullet.values()),
    ]))


def token_coverage(text, records):
    """Fraction of a claim's meaningful expanded tokens supported by records.

    Alias tags count, but ordinary word tokens remain in the denominator.  This
    catches an invented object hidden behind a legitimate verb: "led nuclear
    reactor integration" no longer passes merely because the anchor says "led
    integration".
    """
    query = expand(text)
    if not query:
        return 1.0
    evidence = Counter()
    for record in records:
        evidence.update(expand(record_surface(record)))
    # Alias tags are useful bridges, but counting every generated group token at
    # full weight can make one broad alias hide several unsupported nouns.
    total = 0.0
    hit = 0.0
    for term, freq in query.items():
        weight = (0.45 if term.startswith('~g') else 1.0) * min(freq, 2)
        total += weight
        if evidence.get(term):
            hit += weight
    return round(hit / total, 4) if total else 1.0

# ---------------------------------------------------------------- anchor index

def anchor_index():
    """BM25 over the searchable surface of every anchor: fact + keywords +
    bullet text. Role and pure-boundary records are excluded from matching."""
    by_id, recs = store.generation_anchors()
    docs = []
    for r in recs:
        # Positioning paragraphs are compositions made FROM evidence.  Letting
        # them retrieve as evidence is circular and inflates coverage.
        if r.get('type') in ('role', 'boundary', 'positioning'):
            continue
        surface = record_surface(r)
        docs.append((r['id'], surface))
    return BM25(docs), by_id

def job_index():
    """BM25 over past JDs -- powers 'what similar job did I lose before?'."""
    import os
    docs = []
    for slug in store.list_jobs():
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        if not jd:
            continue
        surface = ' '.join([jd.get('title', ''), jd.get('company', '')] +
                           [r['text'] for r in jd.get('requirements', [])])
        docs.append((slug, surface))
    return BM25(docs) if docs else None
