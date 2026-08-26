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

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} PDF extraction invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
