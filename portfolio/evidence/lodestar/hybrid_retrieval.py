"""Sanitized representative source from Lodestar.

Hybrid lexical + vector retrieval with RRF fusion and authority-aware candidate lanes.
"""

from __future__ import annotations

from dataclasses import dataclass

_RRF_K = 60


@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    citation_label: str
    title: str
    source_type: str
    binding_weight: int
    section_label: str | None
    chunk_text: str
    is_non_precedent: bool
    score: float
    url: str | None = None


def _filter_clause(visa_class, criterion_tags) -> tuple[str, dict]:
    clause = ""
    params: dict = {}
    if visa_class:
        clause += " AND c.visa_class && %(visa_class)s"
        params["visa_class"] = list(visa_class)
    if criterion_tags:
        clause += " AND c.criterion_tags && %(criterion_tags)s"
        params["criterion_tags"] = list(criterion_tags)
    return clause, params


def _lexical(conn, query, k, visa_class, criterion_tags, max_weight=None) -> list[str]:
    clause, params = _filter_clause(visa_class, criterion_tags)
    weight_clause = ""
    if max_weight is not None:
        weight_clause = (
            " AND c.document_id IN "
            "(SELECT id FROM documents WHERE binding_weight <= %(mw)s)"
        )
        params["mw"] = max_weight
    params.update({"q": query, "k": k})
    rows = conn.execute(
        f"""
        SELECT c.id::text
        FROM chunks c
        WHERE c.tsv @@ websearch_to_tsquery('english', %(q)s){clause}{weight_clause}
        ORDER BY ts_rank(c.tsv, websearch_to_tsquery('english', %(q)s)) DESC
        LIMIT %(k)s
        """,
        params,
    ).fetchall()
    return [row[0] for row in rows]


def _vector(conn, query_vec, k, visa_class, criterion_tags, max_weight=None) -> list[str]:
    clause, params = _filter_clause(visa_class, criterion_tags)
    weight_clause = ""
    if max_weight is not None:
        weight_clause = (
            " AND c.document_id IN "
            "(SELECT id FROM documents WHERE binding_weight <= %(mw)s)"
        )
        params["mw"] = max_weight
    params.update({"vec": query_vec, "k": k})
    rows = conn.execute(
        f"""
        SELECT c.id::text
        FROM chunks c
        WHERE c.embedding IS NOT NULL{clause}{weight_clause}
        ORDER BY c.embedding <=> %(vec)s::vector
        LIMIT %(k)s
        """,
        params,
    ).fetchall()
    return [row[0] for row in rows]


def _rrf(*ranked_lists: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return scores


def hybrid_search(
    conn,
    provider,
    query: str,
    *,
    k: int = 10,
    pool: int = 30,
    visa_class: list[str] | None = None,
    criterion_tags: list[str] | None = None,
    reranker=None,
) -> list[RetrievalResult]:
    if reranker is None:
        from .rerank import authority_rerank
        reranker = authority_rerank

    query_vec = provider.embed_query(query)

    lexical_ids = _lexical(conn, query, pool, visa_class, criterion_tags)
    vector_ids = _vector(conn, query_vec, pool, visa_class, criterion_tags)

    # Dedicated high-authority lanes keep controlling sources in the candidate pool.
    lexical_authority = _lexical(
        conn, query, pool, visa_class, criterion_tags, max_weight=3
    )
    vector_authority = _vector(
        conn, query_vec, pool, visa_class, criterion_tags, max_weight=3
    )

    fused = _rrf(
        lexical_ids,
        vector_ids,
        lexical_authority,
        vector_authority,
    )
    if not fused:
        return []

    candidate_ids = sorted(
        fused,
        key=lambda cid: fused[cid],
        reverse=True,
    )[: max(k * 3, 20)]

    candidates = _hydrate(conn, candidate_ids, fused)
    return reranker(candidates)[:k]


def _hydrate(conn, ids: list[str], fused: dict[str, float]) -> list[RetrievalResult]:
    if not ids:
        return []

    rows = conn.execute(
        """
        SELECT c.id::text,
               c.document_id::text,
               d.citation_label,
               d.title,
               d.source_type,
               d.binding_weight,
               c.section_label,
               c.chunk_text,
               d.url
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.id = ANY(%(ids)s::uuid[])
        """,
        {"ids": ids},
    ).fetchall()

    by_id = {row[0]: row for row in rows}
    results: list[RetrievalResult] = []
    for chunk_id in ids:
        row = by_id.get(chunk_id)
        if not row:
            continue
        results.append(
            RetrievalResult(
                chunk_id=row[0],
                document_id=row[1],
                citation_label=row[2],
                title=row[3],
                source_type=row[4],
                binding_weight=row[5],
                section_label=row[6],
                chunk_text=row[7],
                is_non_precedent=row[4] == "aao_nonprecedent",
                score=fused[chunk_id],
                url=row[8],
            )
        )
    return results
