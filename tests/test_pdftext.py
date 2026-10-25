"""PDF extraction must prefer refusal over corrupting the truth layer."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import pdftext


def fake_pdf(path, text):
    payload = ("%PDF-1.4\n1 0 obj\nstream\nBT (" + text +
               ") Tj ET\nendstream\nendobj\n%%EOF").encode('latin-1')
    with open(path, 'wb') as stream:
        stream.write(payload)


def subset_font_pdf(path, words):
    """Two subset fonts, hex strings and kerned TJ arrays, as LibreOffice 24
    writes them. Both fonts number their glyphs from 01, so only a per-font
    CMap decodes the text; a merged table garbles it."""
    letters = sorted(set(''.join(words)))
    cmap = lambda shift: ('beginbfchar\n' + ''.join(
        f'<{i + 1:02X}> <{ord(c) + shift:04X}>\n' for i, c in enumerate(letters)) + 'endbfchar')
    code = {c: f'{i + 1:02X}' for i, c in enumerate(letters)}
    hexed = lambda w: '<' + ''.join(code[c] for c in w) + '>'
    runs = []
    for n, word in enumerate(words):
        font = 'F1' if n % 2 else 'F2'
        if font == 'F2':
            word = word.upper()
        split = max(1, len(word) // 2)
        runs.append(f'/{font} 9 Tf[{hexed(word[:split].lower())}-1{hexed(word[split:].lower())}-300]TJ')
    content = 'BT ' + ' '.join(runs) + ' ET'
    payload = (
        '%PDF-1.4\n'
        '1 0 obj << /Font << /F1 2 0 R /F2 3 0 R >> >> endobj\n'
        '2 0 obj << /Type /Font /ToUnicode 4 0 R >> endobj\n'
        '3 0 obj << /Type /Font /ToUnicode 5 0 R >> endobj\n'
        f'4 0 obj\nstream\n{cmap(0)}\nendstream\nendobj\n'
        f'5 0 obj\nstream\n{cmap(-32)}\nendstream\nendobj\n'
        f'6 0 obj\nstream\n{content}\nendstream\nendobj\n%%EOF')
    with open(path, 'wb') as stream:
        stream.write(payload.encode('latin-1'))


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-pdf-') as directory:
        clean = os.path.join(directory, 'clean.pdf')
        prose = ('the systems engineer led requirements and verification of the aircraft '
                 'with the customer and the supplier for acceptance and configuration ' * 5)
        fake_pdf(clean, prose)
        text, quality = pdftext.safe_extract(clean)
        checks.append(('readable embedded text is accepted',
                       bool(text) and quality['words'] >= 40))

        broken = os.path.join(directory, 'fragmented.pdf')
        fragments = (('the and of to in for with on this from ' * 3) +
                     ' '.join('ALEXMORGANENGINEERING' * 4))
        fake_pdf(broken, fragments)
        text, reason = pdftext.safe_extract(broken)
        checks.append(('letter-fragmented extraction is refused',
                       text is None and 'letter-fragmented' in reason))

        subset = os.path.join(directory, 'subset-fonts.pdf')
        words = ('the systems engineer led requirements and verification of the '
                 'aircraft with the customer for acceptance and configuration').split() * 4
        subset_font_pdf(subset, words)
        text, quality = pdftext.safe_extract(subset)
        checks.append(('hex strings in per-font subset CMaps decode to the words',
                       bool(text) and 'verification' in text.lower()
                       and 'requirements' in text.lower()))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} PDF extraction invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
