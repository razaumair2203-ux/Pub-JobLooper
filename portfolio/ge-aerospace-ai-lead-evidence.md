# GE Aerospace AI Lead Developer — Technical Evidence Dossier

**Candidate:** M. Umair Raza  
**Target role:** AI Lead Developer — GE Aerospace, Warsaw

## Core proposition

**Operational aerospace engineer + current applied-AI lead + hands-on RAG/GenAI/edge-AI engineering.**

The value is not that I can list AI frameworks. It is that I already work across the lifecycle GE describes: **real problem → requirements → data / retrieval architecture → prototype → evaluation → integration → deployment constraints → validation → maintainable engineering workflow**.

My current AI work sits on top of 18+ years of aerospace engineering, including aircraft development, operational flight-line support, international OEM integration and programme governance. That gives me direct context for where AI systems fail when they leave a notebook and enter a real engineering environment.

---

# 60-second proof

| GE requirement | Evidence already implemented | Inspectable proof |
|---|---|---|
| **AI / ML solution development** | Thermal/RGB runway perception, repeated YOLO experimentation, TensorRT edge deployment | [TIR-FOD / Clear Run](tir-fod-edge-ai.md) |
| **Python / AI application development** | FastAPI backend, retrieval/embedding services, explicit SQL, evaluation logic | [Lodestar code evidence](evidence/lodestar/README.md) |
| **RAG applications** | Structure-aware ingestion, BGE embeddings, pgvector, full-text search, RRF, reranking, citable grounding | [Lodestar code evidence](evidence/lodestar/README.md) |
| **Embeddings / vector DB / semantic search** | 1024-d BGE vectors, PostgreSQL/Supabase pgvector, HNSW cosine index, hybrid retrieval | [Schema + embedding provider](evidence/lodestar/README.md) |
| **Testing / evaluation** | 34-pair grounding eval at **2.9% top-5 error**; 53 backend tests; 17/17 stress cases; 3/3 Playwright E2E | [Grounding eval](evidence/lodestar/grounding-eval.md) |
| **Prototype → deployment** | Jetson Orin Nano + TensorRT runway-flight demonstrator, **25.0 FPS inference / 15.6 FPS end-to-end** | [Edge-AI evidence](evidence/tir-fod/README.md) |
| **Multimodal AI** | LWIR + RGB sensing, UAV perception and wider autonomous workflow | [TIR-FOD / Clear Run](tir-fod-edge-ai.md) |
| **GenAI / prompt-driven workflows** | Independent builder/reviewer model workflow with scope contract, model fallback, mutation checks, structured verdict and human approval | [Public Codex AR-L repo](https://github.com/razaumair2203-ux/codex-adversarial-review-lite) |
| **Responsible / secure AI** | Citable retrieval objects, source hierarchy, no invented probability claims, explicit human approval, privacy boundaries | [Lodestar](lodestar-rag.md) · [Joblooper](joblooper.md) · [Codex AR-L](adversarial-review-lite.md) |
| **Agile delivery / technical leadership** | PMP + PMI-ACP; current multidisciplinary R&D portfolio; previous engineering/software/programme leadership | CV + interview evidence |
| **Aerospace context** | Development, integration, live operations, fleet programmes, applied R&D | CV + research portfolio |

---

# Evidence stream 1 — RAG / retrieval engineering

## Lodestar

A working evidence-assessment application built around grounded retrieval and controlled downstream reasoning.

### Current measured state

- **209 real source documents**
- **2,945 embedded chunks**
- **34 hand-checked query / expected-citation pairs**
- **2.9% top-5 retrieval error**
- **53 backend tests green**
- **17 / 17 stress and abuse cases pass**
- **3 / 3 Playwright browser flows pass**
- **12 / 12 concurrent full flows pass** after hardening

### Retrieval stack

```text
primary source ingestion
  -> domain-structure-aware chunking
  -> local BGE passage embeddings
  -> PostgreSQL/Supabase
       |-- pgvector + HNSW cosine
       |-- tsvector + GIN full-text retrieval
  -> semantic + lexical retrieval
  -> high-authority retrieval lanes
  -> Reciprocal Rank Fusion
  -> authority-aware reranking
  -> structured citable chunks
  -> grounded assessment
```

### Actual source that can be inspected

- [legal-structure-aware chunking](evidence/lodestar/legal_chunking.py)
- [embedding provider / BGE query-passage handling](evidence/lodestar/embedding_provider.py)
- [hybrid lexical + vector retrieval / RRF](evidence/lodestar/hybrid_retrieval.py)
- [Postgres / pgvector / HNSW schema](evidence/lodestar/chunks_schema.sql)
- [grounding evaluation](evidence/lodestar/grounding-eval.md)

This is the strongest evidence that my GenAI/RAG work goes beyond using a hosted chat interface.

### Real failures already encountered and fixed

The private build recorded issues including excessive remote DB handshakes, embedder initialization races, unnecessary heavyweight model initialization on unembedded corpora, invalid path IDs reaching SQL and ANN query-cast issues. The system was changed in response: pooled connections, batched writes, embedder locking/warm-up, lexical fallback, UUID validation and query fixes.

That is the type of engineering lifecycle I would expect to continue in a GE product environment: prototype, observe failure, instrument, harden, retest.

[Deep Lodestar case study →](lodestar-rag.md)

---

# Evidence stream 2 — applied ML / edge AI in aerospace

## TIR-FOD / Clear Run

A runway-safety perception programme using LWIR/RGB sensing, computer vision and onboard edge inference, with the wider system extending toward autonomous UAV/GCS/UGV retrieval.

### Dataset / evaluation evidence

| Evidence | Result |
|---|---:|
| Source LWIR frames | **3,499** |
| Annotated FOD objects | **5,593** |
| Classes | **23** |
| Training runs | **29** |
| Best observed detector | **YOLOv8n — 0.8603 ± 0.0017 mAP** |
| AP small / medium / large | **0.704 / 0.846 / 0.942** |
| Annotation F1 representative / difficult | **0.971 / 0.645** |
| Leakage experiment | **+8.52 pp invalid uplift** |
| Capture-group effect | **0.8223 → 0.7410 mAP** |

The leakage and source-grouping experiments are important because they show I am not treating model performance as a single leaderboard number. The work explicitly asks whether the evaluation itself is lying.

### Deployment evidence

- **NVIDIA Jetson Orin Nano**
- **TensorRT**
- **640 × 512 LWIR** stream
- repeated runway-flight testing
- **25.0 FPS** detector inference
- **15.6 FPS** full inspection pipeline
- approximately **17 W** compute + camera subsystem
- reported **55–70 °C** module temperature

The measured gap between inference FPS and complete-pipeline FPS is exactly the kind of integration reality that matters when moving ML into engineering operations.

[Measured edge-AI evidence →](evidence/tir-fod/README.md)  
[Public dataset →](https://doi.org/10.5281/zenodo.22546586)

---

# Evidence stream 3 — GenAI workflow / agent control

## Codex Adversarial Review Lite

Public repository: [codex-adversarial-review-lite](https://github.com/razaumair2203-ux/codex-adversarial-review-lite)

The project turns “ask another model to review my code” into an engineered workflow:

```text
builder
  -> scoped review contract
  -> test expectations / edge cases
  -> privacy + platform preflight
  -> independent reviewer model
  -> structured verdict
  -> repository mutation check
  -> builder validates findings
  -> report before any fix
  -> human approval
```

Controls include model preflight and fallback, Git/dirty-file hashes, reviewer non-mutation, explicit finding disposition, platform-aware behavior and a self-test path.

This maps directly to the GE requirement for prompt-driven / GenAI applications plus responsible implementation and maintainability.

[Case study →](adversarial-review-lite.md)

---

# Evidence stream 4 — AI product engineering / guardrails

## Joblooper

Public repository: [Pub-JobLooper](https://github.com/razaumair2203-ux/Pub-JobLooper)

Joblooper is a local-first AI-assisted application system where the LLM is not allowed to become the source of truth. Candidate facts are governed separately, claims are evidence-backed, hard release gates remain deterministic, human approval is explicit, and employer-facing artifacts are reproducibly generated and hash-bound to the submission record.

That demonstrates a broader engineering principle I would bring to GE: **probabilistic models inside deterministic application boundaries**.

[Case study →](joblooper.md)

---

# Published AI / computer-vision research

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD thermal-infrared runway FOD benchmark v1.2** — [Dataset DOI](https://doi.org/10.5281/zenodo.22546586)

These support three different technical areas relevant to the role: **low-latency perception architecture, robustness/adversarial behavior, and real aerospace dataset/deployment engineering**.

---

# Why the operational aerospace background is an AI advantage

I have worked on systems that had to be integrated, qualified, operated, maintained and sustained—not just demonstrated. That background affects how I build AI products now:

- requirements are explicit;
- interfaces are treated as engineering objects;
- datasets and sources need provenance;
- development evidence and validation evidence remain separate;
- performance is measured end-to-end;
- failure modes are recorded instead of hidden;
- configuration and versioning matter;
- human authority is intentional;
- deployment claims stop where the evidence stops.

For GE Aerospace, that is the connection I would emphasize: **AI implementation capability plus an aerospace engineer’s instinct for dependable systems.**

---

# Technical ownership

My contribution is not limited to programme sponsorship. Across the projects above I work directly in:

- architecture and requirements decomposition;
- Python/backend implementation and review;
- database/retrieval design;
- chunking, embeddings and search behavior;
- GenAI provider/model workflow design;
- experiment and evaluation strategy;
- edge-AI requirements and integration;
- acceptance criteria, test logic and release gates;
- technical mentoring and multidisciplinary delivery.

I also know the boundary between work I personally implement, work I technically lead/review, and work performed by students/team members. That distinction is maintained in the CV and can be discussed explicitly in interview.

---

# Where I would expect the hardest interview questions

A serious technical review should challenge me on:

- RAG evaluation beyond “looks relevant”;
- chunking and retrieval failure modes;
- `pgvector` / HNSW / lexical retrieval trade-offs;
- RRF and reranking design;
- embedding-model migration and provenance;
- API/backend failure behavior and observability;
- data leakage and grouped validation in image/video datasets;
- small-object detection;
- TensorRT / Jetson deployment constraints;
- GenAI workflow safety and hallucination control;
- enterprise cloud / scaling differences between current projects and GE-scale deployment.

The portfolio is designed so those questions can be grounded in actual work rather than résumé keywords.

---

[Full Applied AI portfolio](README.md) · [GitHub profile](https://github.com/razaumair2203-ux) · [LinkedIn](https://www.linkedin.com/in/mumairaza)
