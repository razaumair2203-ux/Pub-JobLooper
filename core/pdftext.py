"""PDF text extraction that refuses what it cannot vouch for.

Ported from the jobpilot-local design (D13). The naive approach -- pulling
literal strings out of content streams -- yields mojibake for anything Chrome or
Word produced, because those embed subset fonts whose byte codes are glyph
indices rather than characters ("Alex Morgan" becomes "$OH[0RUJDQ"). So each
font's /ToUnicode CMap is resolved first.

Where that is impossible -- scans, exotic encodings -- the extracted text is
quality-gated and the read is REFUSED rather than returned as garbage.

    A corrupt career knowledge base is worse than an empty one.

This module exists because the original misc sweep had no PDF support at all,
and two signed recommendation letters holding the most quantified evidence in
the corpus were silently invisible to it.
"""
import re, zlib

# Words common enough that their absence from a page of English prose means the
# decode failed, not that the document is unusual.
_COMMON = {'the', 'and', 'of', 'to', 'in', 'for', 'a', 'is', 'was', 'with',
           'on', 'as', 'at', 'his', 'her', 'has', 'have', 'that', 'this', 'from'}


def _streams(data):
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', data, re.S):
        raw = m.group(1)
        try:
            yield zlib.decompress(raw)
        except Exception:
            yield raw


def _cmaps(data):
    """Map font byte codes to unicode via every /ToUnicode CMap in the file."""
    table = {}
    for s in _streams(data):
        if b'beginbfchar' not in s and b'beginbfrange' not in s:
            continue
        txt = s.decode('latin-1', 'replace')
        for blk in re.findall(r'beginbfchar(.*?)endbfchar', txt, re.S):
            for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
                try:
                    table[int(src, 16)] = ''.join(
                        chr(int(dst[i:i + 4], 16)) for i in range(0, len(dst), 4))
                except ValueError:
                    pass
        for blk in re.findall(r'beginbfrange(.*?)endbfrange', txt, re.S):
            for lo, hi, dst in re.findall(
                    r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
                try:
                    a, b, d = int(lo, 16), int(hi, 16), int(dst, 16)
                    for i in range(a, min(b, a + 512) + 1):
                        table[i] = chr(d + (i - a))
                except ValueError:
                    pass
    return table


_ESCAPES = {b'\\n': b' ', b'\\r': b' ', b'\\t': b' '}


def _clean(piece):
    for k, v in _ESCAPES.items():
        piece = piece.replace(k, v)
    return re.sub(rb'\\([()\\])', rb'\1', piece)


def _decode_literal(piece, cmap, mode):
    """mode: 'raw' | 'cmap1' | 'cmap2'.

    A PDF names a font per text run; this reader does not track resource
    dictionaries, so it cannot know which font's CMap applies. Applying a
    merged CMap to text that was already correct CORRUPTS it -- the
    recommendation letters decoded to "enJrS o E ClM M E NaAq" that way. So all
    three decodings are produced for the whole document and the one that
    actually reads as English wins.
    """
    piece = _clean(piece)
    if mode == 'raw' or not cmap:
        return piece.decode('latin-1', 'replace')
    if mode == 'cmap1':
        return ''.join(cmap.get(b, chr(b)) for b in piece)
    pairs = [piece[i] << 8 | piece[i + 1] for i in range(0, len(piece) - 1, 2)]
    return ''.join(cmap.get(c, '') for c in pairs)


def _score(text):
    """How much this looks like real English prose.

    Single-character tokens are excluded: they inflate the score for both
    mojibake ("b:±  -, b° %bad°mnuba8") and letter-spaced extractions
    ("A C a r e e r i n A e r o s p a c e"), neither of which is usable text.
    A Coursera certificate scored 0.04 on stray "a" and "i" hits and passed a
    0.02 threshold while being pure garbage.
    """
    words = [w for w in re.findall(r"[A-Za-z']+", text.lower()) if len(w) > 1]
    if len(words) < 20:
        return 0.0
    hits = sum(1 for w in words if w in _COMMON)
    return hits / len(words)


def extract(path, min_words=40, min_common=0.05, min_space_ratio=0.05,
            max_single_letter_ratio=0.30):
    """Return (text, quality) or raise ValueError if the read cannot be trusted.

    quality is a dict of the measured signals, so a refusal can say why.
    """
    data = open(path, 'rb').read()
    cmap = _cmaps(data)
    literals = []
    for s in _streams(data):
        if b'Tj' not in s and b'TJ' not in s:
            continue
        literals.append([t.group(0)[1:-1]
                         for t in re.finditer(rb'\((?:\\.|[^\\()])*\)', s)])

    def build(mode):
        out = []
        for parts in literals:
            line = re.sub(r'\s+', ' ',
                          ' '.join(_decode_literal(p, cmap, mode) for p in parts)).strip()
            if len(line) > 3:
                out.append(line)
        return '\n'.join(out)

    candidates = [(build(m), m) for m in (('raw', 'cmap1', 'cmap2') if cmap else ('raw',))]
    text, mode = max(candidates, key=lambda c: (_score(c[0]), len(c[0])))

    words = re.findall(r"[A-Za-z']+", text)
    alpha_words = re.findall(r'[A-Za-z]+', text)
    single_letter_ratio = (sum(len(w) == 1 for w in alpha_words) /
                           max(len(alpha_words), 1))
    short_fragment_ratio = (sum(len(w) <= 2 for w in alpha_words) /
                            max(len(alpha_words), 1))
    quality = {
        'chars': len(text),
        'words': len(words),
        'common_word_ratio': round(_score(text), 3),
        'space_ratio': round(text.count(' ') / max(len(text), 1), 3),
        'single_letter_ratio': round(single_letter_ratio, 3),
        'short_fragment_ratio': round(short_fragment_ratio, 3),
        'has_cmap': bool(cmap),
        'decode_mode': mode,
    }
    if quality['words'] < min_words:
        raise ValueError(f"too little text recovered ({quality['words']} words) — "
                         f"likely a scan. Paste the text instead. {quality}")
    if quality['common_word_ratio'] < min_common:
        raise ValueError(f"decoded text does not look like prose "
                         f"(common-word ratio {quality['common_word_ratio']}) — "
                         f"font encoding could not be resolved. Paste the text instead. {quality}")
    if quality['space_ratio'] < min_space_ratio:
        raise ValueError(f"word boundaries missing (space ratio {quality['space_ratio']}) — "
                         f"refusing rather than importing garbage. {quality}")
    if quality['single_letter_ratio'] > max_single_letter_ratio \
            or quality['short_fragment_ratio'] > 0.70:
        raise ValueError(f"text is letter-fragmented rather than readable prose "
                         f"(single-letter ratio {quality['single_letter_ratio']}) — "
                         f"refusing rather than importing garbage. {quality}")
    return text, quality


def safe_extract(path):
    """Extract, or return (None, reason). Never returns untrustworthy text."""
    try:
        return extract(path)
    except Exception as e:
        return None, str(e)
