# M. Umair Raza — Applied AI Engineering

**Applied AI Lead · Aerospace AI · RAG / Retrieval · Edge AI · GenAI Engineering**

I work where AI has to survive contact with real engineering systems: **data provenance, retrieval, integration, edge compute, evaluation, failure modes, human control and operational deployment**.

## Fast proof

| Evidence stream | Hard evidence | Inspect |
|---|---|---|
| **Grounded RAG / retrieval — Lodestar** | **209 docs / 2,945 embedded chunks** · **34** hand-checked grounding pairs · **2.9% top-5 retrieval error** · **53** backend tests · **17/17** stress cases · **12/12** concurrent full flows | [Case study + source evidence](portfolio/lodestar-rag.md) |
| **Aerospace edge AI — TIR-FOD / Clear Run** | **3,499** LWIR source frames · **5,593** objects · **23** classes · **29** training runs · **0.8603 ± 0.0017 mAP** best observed · **25.0 FPS inference / 15.6 FPS E2E** on Jetson/TensorRT | [Benchmark + deployment evidence](portfolio/tir-fod-edge-ai.md) |
| **GenAI control workflow — Codex AR-L** | Public multi-model review workflow: scope contracts, model fallback, mutation checks, structured verdicts, report-before-fix, human approval | [Public repo](https://github.com/razaumair2203-ux/codex-adversarial-review-lite) |
| **Governed AI product — Joblooper** | Public local-first product with evidence-backed generation, deterministic validation, traceability, approval and artifact integrity | [Public repo](https://github.com/razaumair2203-ux/Pub-JobLooper) |

## Inspect actual implementation

Lodestar representative code:

- [domain-aware chunking](portfolio/evidence/lodestar/legal_chunking.py)
- [BGE embedding provider](portfolio/evidence/lodestar/embedding_provider.py)
- [hybrid lexical/vector retrieval + RRF](portfolio/evidence/lodestar/hybrid_retrieval.py)
- [`pgvector` / HNSW / FTS schema](portfolio/evidence/lodestar/chunks_schema.sql)
- [grounding evaluation](portfolio/evidence/lodestar/grounding-eval.md)

TIR-FOD measured evidence:

- [benchmark / leakage / grouped-split / edge telemetry record](portfolio/evidence/tir-fod/README.md)
- [public dataset DOI](https://doi.org/10.5281/zenodo.22546586)

## Research

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD thermal benchmark v1.2** — [DOI](https://doi.org/10.5281/zenodo.22546586)

## Why my aerospace background matters

Before the current applied-AI work, my career covered aircraft development, operational AEW&C flight-line engineering, two years embedded inside an international fighter-aircraft design institute, and programme-level engineering across a 150+ aircraft fleet.

That is why my AI work emphasizes **requirements, interfaces, provenance, V&V, configuration, failure evidence and end-to-end performance** rather than only model output.

## GE Aerospace

For the GE AI Lead Developer role: [requirement → technical evidence dossier](portfolio/ge-aerospace-ai-lead-evidence.md)

For the complete portfolio: [full Applied AI portfolio](portfolio/README.md)

**GitHub:** [razaumair2203-ux](https://github.com/razaumair2203-ux) · **LinkedIn:** [M. Umair Raza](https://www.linkedin.com/in/mumairaza)
