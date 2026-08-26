"""Deterministic output-language preferences.

Ground truth keeps the wording recorded by its sources.  Presentation applies
only explicitly configured, auditable spelling substitutions; it never asks a
model to rewrite prose or infer a dialect.
"""
import re


_EN_US = {
    'modernisation': 'modernization',
    'modernised': 'modernized',
    'modernising': 'modernizing',
    'organisation': 'organization',
    'organisations': 'organizations',
    'organisational': 'organizational',
    'organisationally': 'organizationally',
    'programme': 'program',
    'programmes': 'programs',
    'finalise': 'finalize',
    'finalised': 'finalized',
    'finalises': 'finalizes',
    'finalising': 'finalizing',
    'recognise': 'recognize',
    'recognised': 'recognized',
    'recognises': 'recognizes',
    'recognising': 'recognizing',
}


def _preserve_case(source, replacement):
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def localize(text, language='en-US'):
    """Apply the configured presentation language without changing facts."""
    if not text or str(language).lower() not in {'en-us', 'en_us'}:
        return text
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, _EN_US)) + r')\b', re.I)
    return pattern.sub(
        lambda match: _preserve_case(match.group(0), _EN_US[match.group(0).lower()]),
        text,
    )
