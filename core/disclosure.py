"""Deterministic external naming derived only from declared boundary policy."""
import re

from . import store


def externalize(text, boundaries=None):
    """Return the approved external form of text; make no inferred substitutions."""
    value = str(text or '')
    disclosure = (boundaries or store.boundaries()).get('disclosure') or {}
    if disclosure.get('output_mode') != 'generic_defence':
        return value
    for rule in disclosure.get('external_aliases') or []:
        value = re.sub(rule['pattern'], rule['replacement'], value)
    return re.sub(r'\s{2,}', ' ', value).strip()
