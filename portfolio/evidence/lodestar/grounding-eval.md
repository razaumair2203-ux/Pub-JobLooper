# Lodestar Grounding Evaluation

This is the current retrieval-grounding result from the working private Lodestar build.

| Date | Hand-checked query / expected-citation pairs | Retrieval depth | Error rate | Corpus |
|---|---:|---:|---:|---:|
| 2026-07-10 | **34** | top-5 | **2.9%** | **209 docs / 2,945 chunks** |

## What this measures

For each hand-checked query, the expected authority/citation is known in advance. The retrieval pipeline is then tested on whether the expected source appears within the top-5 result set.

This measures **retrieval grounding**, not legal correctness, LLM answer quality, user success, or immigration outcome probability.

## Why it matters

A RAG pipeline can produce polished text while retrieving the wrong evidence. Lodestar therefore treats retrieval quality as a separate engineering concern from downstream generation.

Current pipeline under test:

```text
query
  -> BGE query embedding
  -> semantic pgvector retrieval
  -> PostgreSQL full-text retrieval
  -> high-authority semantic + lexical lanes
  -> Reciprocal Rank Fusion
  -> authority-aware reranking
  -> top-k citable chunks
```

## Additional test state from the same build

- **53** backend/Python tests green.
- **17 / 17** stress and abuse cases pass.
- **3 / 3** Playwright browser end-to-end flows pass.
- **12 / 12** concurrent full flows passed after hardening connection pooling, batching, embedder warm-up/locking, UUID validation and lexical fallback.

## Next evaluation work

The current result is useful but intentionally not presented as sufficient production evaluation. Next additions should include:

- Recall@K across a larger frozen test set;
- MRR / nDCG where graded relevance is available;
- latency percentiles for lexical/vector/fusion/rerank stages;
- failure slicing by authority type and criterion;
- regression gating on chunker/model/index changes;
- separate LLM grounded-answer evaluation.

[Implementation evidence](README.md) · [AI portfolio](../../README.md)
