# Lodestar Grounding Evaluation

This is the current retrieval-grounding result from the working private Lodestar build.

| Date | Hand-checked query / expected-citation pairs | Retrieval depth | Error rate | Corpus |
|---|---:|---:|---:|---:|
| 2026-07-10 | **34** | top-5 | **2.9%** | **209 docs / 2,945 chunks** |

## What this measures

For each hand-checked query, the expected authority/citation is known in advance. Retrieval succeeds when an accepted source marker appears within the top-5 result set.

This measures **retrieval grounding**, not legal correctness, LLM answer quality, user success, or immigration outcome probability.

## Examples from the frozen evaluation set

These are representative entries from the actual 34-pair evaluation file:

| Query | Accepted source marker(s) |
|---|---|
| `lesser nationally or internationally recognized prizes or awards for excellence` | `(h)(3)(i)` / `(i)` |
| `membership in associations requiring outstanding achievements judged by experts` | `(h)(3)(ii)` / `(ii)` |
| `two step analysis count the criteria then final merits determination` | `Kazarian` / `F.2` |
| `proposed endeavor has substantial merit and national importance` | `Dhanasar` / `F.5` |
| `on balance beneficial to waive the job offer and labor certification requirements` | `Dhanasar` / `F.5` |
| `endeavor described too vaguely to assess national importance` | `AAO Non-Precedent` / `F.5` / `Dhanasar` |

The complete private set is append-only in practice: failing pairs are not removed to improve the headline metric.

## Pipeline under test

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

## Why it matters

A RAG pipeline can produce polished prose while retrieving the wrong evidence. Lodestar therefore evaluates retrieval quality independently from downstream generation.

The current **2.9% top-5 error** corresponds to the frozen 34-pair set and current 209-document / 2,945-chunk corpus. It is not generalized beyond that measured configuration.

## Additional test state from the same build

- **53** backend/Python tests green.
- **17 / 17** stress and abuse cases pass.
- **3 / 3** Playwright browser end-to-end flows pass.
- **12 / 12** concurrent full flows passed after hardening connection pooling, batching, embedder warm-up/locking, UUID validation and lexical fallback.

## Next evaluation work

The current result is useful but intentionally not presented as sufficient production evaluation. Next additions should include:

- a larger frozen relevance set;
- Recall@K across multiple retrieval depths;
- MRR / nDCG where graded relevance is available;
- latency percentiles for lexical/vector/fusion/rerank stages;
- failure slicing by authority type and criterion;
- regression gating on chunker/model/index changes;
- separate LLM grounded-answer evaluation.

[Implementation evidence](README.md) · [AI portfolio](../../README.md)
