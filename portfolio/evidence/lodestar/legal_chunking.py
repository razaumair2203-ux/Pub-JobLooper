"""Sanitized representative source from Lodestar.

Structure-aware chunkers for each legal source type.
Deterministic, regex-driven splitting on legal structure; structure first, size second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_index: int
    chunk_text: str
    section_label: str | None = None
    visa_class: list[str] | None = None
    criterion_tags: list[str] | None = None


_SOFT_MAX = 1600
_MIN = 60

_PAREN_MARKER = re.compile(r"(?m)^[ \t]*(\([0-9a-zA-Z]{1,4}\))[ \t]*")
_HEADING_MARKER = re.compile(
    r"(?m)^[ \t]*("
    r"[IVXLC]{1,5}\.|"
    r"[A-Z]\.|"
    r"[0-9]{1,3}\.(?=\s)|"
    r"Chapter\s+\d+|"
    r"Part\s+[A-Z]\b|"
    r"[0-9]+\s+USCIS-PM\s+[A-Z]\.\d+"
    r")"
)


def _split_at_markers(text: str, marker: re.Pattern[str]) -> list[tuple[str | None, str]]:
    matches = list(marker.finditer(text))
    if not matches:
        return [(None, text)]

    pairs: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if len(preamble) >= _MIN:
        pairs.append((None, preamble))

    for i, match in enumerate(matches):
        label = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            pairs.append((label, body))
    return pairs


def _part_label(label: str | None, part: int) -> str | None:
    return f"part {part}" if label is None else f"{label} (cont. {part})"


def _enforce_size(pairs: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for label, body in pairs:
        if len(body) <= _SOFT_MAX:
            out.append((label, body))
            continue

        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        buf = ""
        part = 1
        for para in paras:
            if buf and len(buf) + len(para) + 2 > _SOFT_MAX:
                out.append((_part_label(label, part), buf))
                part += 1
                buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf:
            out.append((_part_label(label, part) if part > 1 else label, buf))
    return out


def _to_chunks(
    pairs: list[tuple[str | None, str]],
    *,
    visa_class: list[str] | None = None,
    criterion_tags: list[str] | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for idx, (label, body) in enumerate(pairs):
        if not body:
            continue
        if label is None and len(body) < _MIN:
            continue
        chunks.append(
            Chunk(
                chunk_index=idx,
                chunk_text=body,
                section_label=label,
                visa_class=list(visa_class or []),
                criterion_tags=list(criterion_tags or []),
            )
        )
    return chunks


def chunk_statute(text: str, **kwargs) -> list[Chunk]:
    return _to_chunks(_enforce_size(_split_at_markers(text, _PAREN_MARKER)), **kwargs)


def chunk_cfr(text: str, **kwargs) -> list[Chunk]:
    return _to_chunks(_enforce_size(_split_at_markers(text, _PAREN_MARKER)), **kwargs)


def chunk_policy_manual(text: str, **kwargs) -> list[Chunk]:
    return _to_chunks(_enforce_size(_split_at_markers(text, _HEADING_MARKER)), **kwargs)


def chunk_decision(text: str, **kwargs) -> list[Chunk]:
    return _to_chunks(_enforce_size(_split_at_markers(text, _HEADING_MARKER)), **kwargs)


def chunk_generic(text: str, **kwargs) -> list[Chunk]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pairs = _enforce_size([(None, "\n\n".join(paras))]) if paras else []
    return _to_chunks(pairs, **kwargs)
