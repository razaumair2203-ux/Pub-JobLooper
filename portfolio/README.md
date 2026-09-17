# M. Umair Raza — Applied AI Engineering Portfolio

## AI systems for real aerospace and high-integrity workflows

I build and lead applied-AI systems where the model is only one part of the engineering problem: **data provenance, retrieval, edge compute, integration, validation, failure modes, human control and operational deployment all matter.**

My background is unusual for an AI role: 18+ years across military aircraft development, live operations, international OEM integration and programme governance, followed by current applied R&D in **computer vision, edge AI, autonomous systems, retrieval/RAG, GenAI workflows and AI-enabled engineering products**.

This page is intentionally evidence-first. Start with the numbers and code; use the career history only as context for why the systems are engineered this way.

> **GE Aerospace AI Lead Developer:** [open the requirement → evidence dossier](ge-aerospace-ai-lead-evidence.md)

---

# Proof before biography

| System | Measured / inspectable proof | What to open |
|---|---|---|
| **Lodestar — grounded RAG / evidence assessment** | **209 real docs / 2,945 embedded chunks** · **34** hand-checked grounding pairs · **2.9% top-5 retrieval error** · **53** backend tests · **17/17** stress cases · **12/12** concurrent full flows · BGE embeddings · `pgvector` / HNSW · PostgreSQL FTS · RRF · reranking | [Deep case study](lodestar-rag.md) · [actual sanitized source + eval evidence](evidence/lodestar/README.md) |
| **TIR-FOD / Clear Run — aerospace edge AI** | **3,499** source LWIR frames · **5,593** objects / **23** classes · **29** training runs · best observed **0.8603 ± 0.0017 mAP** · leakage experiment **+8.52 pp invalid uplift** · Jetson/TensorRT **25.0 FPS inference / 15.6 FPS E2E** · ~**17 W** | [Deep case study](tir-fod-edge-ai.md) · [benchmark + deployment evidence](evidence/tir-fod/README.md) · [public dataset](https://doi.org/10.5281/zenodo.22546586) |
| **Codex Adversarial Review Lite — agentic / GenAI workflow** | Public, installable workflow separating builder and reviewer models; scoped review contracts, model preflight/fallback, mutation hashes, structured verdicts, report-before-fix, human approval | [Public repository](https://github.com/razaumair2203-ux/codex-adversarial-review-lite) · [case study](adversarial-review-lite.md) |
| **Joblooper — governed AI product engineering** | Public local-first application with evidence-backed generation, deterministic guardrails, traceability, explicit approval, reproducible documents and hash-bound submission records | [Public repository](https://github.com/razaumair2203-ux/Pub-JobLooper) · [case study](joblooper.md) |

If you have **90 seconds**, open **Lodestar evidence** and **TIR-FOD evidence**. They answer the two most important questions:

1. **Can he build modern AI/RAG software beyond prompting?**
2. **Can he take ML out of a notebook and integrate it into an operational aerospace system?**

---

# 1 — Grounded RAG that can be interrogated technically

## Lodestar

A working private EB-2 NIW / EB-1A evidence-assessment product built around grounded retrieval rather than unconstrained LLM generation.

### Current engineering state

```text
primary sources
  -> provenance-preserving ingestion
  -> legal-structure-aware chunks
  -> local BGE passage embeddings (1024-d)
  -> PostgreSQL/Supabase
       |-- pgvector + HNSW cosine retrieval
       |-- generated tsvector + GIN lexical retrieval
  -> dedicated high-authority retrieval lanes
  -> Reciprocal Rank Fusion
  -> authority-aware reranking
  -> citable retrieval objects
  -> grounded assessment / UI
```

**Measured retrieval evidence:** 209 source documents, 2,945 chunks, 34 hand-checked query/expected-citation pairs, **2.9% top-5 retrieval error**.

The public evidence folder contains representative implementation code—not screenshots of a prompt:

- [structure-aware chunking](evidence/lodestar/legal_chunking.py)
- [embedding provider and BGE query/passage handling](evidence/lodestar/embedding_provider.py)
- [hybrid retrieval + RRF + authority lanes](evidence/lodestar/hybrid_retrieval.py)
- [`pgvector` / HNSW / full-text schema](evidence/lodestar/chunks_schema.sql)
- [grounding-evaluation record](evidence/lodestar/grounding-eval.md)

**Engineering judgement I can defend:** why domain structure beats fixed token windows; why vectors are a rebuildable cache; why query and passage embeddings differ for BGE; why RRF is preferable to fake score normalization; why retrieval quality must be evaluated separately from answer quality; why citation-critical control flow is explicit Python/SQL rather than hidden behind a large framework.

[Inspect Lodestar deeply →](lodestar-rag.md)

---

# 2 — ML moved into an aircraft / runway environment

## TIR-FOD / Clear Run

The project addresses low-light runway Foreign Object Debris using thermal/RGB sensing, AI detection and edge deployment, with the wider programme extending toward UAV/GCS/UGV autonomous retrieval.

### Experiment evidence

| Metric / experiment | Result |
|---|---:|
| Source LWIR frames | **3,499** |
| Annotated FOD objects | **5,593** |
| Classes | **23** |
| Training runs | **29** across YOLOv8 / YOLO11 / YOLO12 |
| Best observed detector | **YOLOv8n — 0.8603 ± 0.0017 mAP** |
| AP small / medium / large | **0.704 / 0.846 / 0.942** |
| Annotation F1, representative / difficult | **0.971 / 0.645** |
| Leakage experiment | **+8.52 percentage points invalid uplift** |
| Capture-group split | **0.8223 → 0.7410 mAP** |
| Stored derivative benefit | **+0.67 ± 0.83 points** |

The strongest result is not merely the best mAP: **source grouping and leakage changed apparent generalization dramatically**, which is exactly the kind of issue that separates field-oriented ML engineering from leaderboard-only experimentation.

### Edge evidence

```text
640x512 LWIR sensor
  -> UAV acquisition
  -> detector / preprocessing
  -> TensorRT
  -> NVIDIA Jetson Orin Nano
  -> detection + communications + operator display
  -> repeated runway-flight validation
```

- **25.0 FPS** TensorRT inference
- **15.6 FPS** complete pipeline
- approximately **17 W** compute + camera subsystem
- reported **55–70 °C** module temperature
- misses / false detections / classification errors retained as engineering evidence

[Inspect benchmark and deployment evidence →](evidence/tir-fod/README.md)  
[Public TIR-FOD dataset →](https://doi.org/10.5281/zenodo.22546586)

---

# 3 — GenAI engineering means controlling models, not just calling them

## Codex Adversarial Review Lite

**Claude builds. Codex audits.** The public project turns a second-model review into a repeatable engineering control plane.

The interesting part is not the prompt. It is the workflow around the models:

```text
builder change
  -> explicit review scope + test contract
  -> privacy/platform preflight
  -> independent reviewer model
  -> structured APPROVED / REVISE verdict
  -> mutation-state comparison
  -> builder validates findings
  -> human-readable report
  -> user decides whether fixes may proceed
```

Implemented controls include model fallback, platform-aware behavior, Git/dirty-file hash capture, reviewer non-mutation, test-spec and edge-case inputs, explicit finding dispositions, report-before-fix behavior and end-to-end self-test.

[Inspect the public repository →](https://github.com/razaumair2203-ux/codex-adversarial-review-lite)

---

# 4 — AI product architecture with deterministic guardrails

## Joblooper

Joblooper uses AI inside an evidence-governed application lifecycle rather than letting the model become the database, validator and decision-maker simultaneously.

```text
signed career truth
  -> exact job capture
  -> requirement/evidence mapping
  -> AI-assisted drafting
  -> deterministic validation
  -> human review/sign-off
  -> deterministic DOCX/PDF build
  -> hash-bound submission record
  -> outcome / learning record
```

The public repository demonstrates local-first architecture, structured provenance, fail-closed claim validation, stale-state invalidation, document generation, integrity checks and explicit human authority.

[Inspect Joblooper →](https://github.com/razaumair2203-ux/Pub-JobLooper)

---

# My technical ownership

I do not present myself as someone who only sponsors AI work. In the current portfolio I personally work at the level of:

- problem decomposition and system architecture;
- Python/backend implementation and review;
- chunking / retrieval / embedding / database design;
- AI/LLM workflow and provider integration;
- experiment design, evaluation logic and failure analysis;
- edge deployment requirements and systems integration;
- acceptance criteria, validation and release gates;
- technical mentoring and leadership across multidisciplinary teams.

At the same time, I have enough programme and operational background to understand why a technically impressive model can still fail as a deployed capability.

---

# Research evidence

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection** — IEEE ICoDT2 2025 — [DOI 10.1109/ICoDT269104.2025.11360736](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion** — IEEE ICoDT2 2025 — [DOI 10.1109/ICoDT269104.2025.11360694](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD thermal-infrared runway FOD benchmark, v1.2** — [DOI 10.5281/zenodo.22546586](https://doi.org/10.5281/zenodo.22546586)

---

# Why the aerospace background matters to AI

My previous work spans avionics development, live AEW&C flight-line operations, fighter-aircraft systems integration inside an international OEM, and programme-level engineering across a 150+ aircraft fleet. That background changes how I approach AI:

- requirements and interfaces are explicit;
- validation is separate from development;
- failure evidence is retained;
- configuration and provenance matter;
- performance is measured end-to-end;
- human authority is deliberate;
- deployment claims stop where the evidence stops.

That is the through-line across Lodestar, TIR-FOD, Adversarial Review and Joblooper.

---

# Technical interview: useful directions to challenge me

I would be comfortable being questioned on:

- chunking strategy and retrieval failure modes;
- BGE embeddings and vector-space migration;
- `pgvector`, HNSW, full-text search and hybrid retrieval;
- RRF and reranking trade-offs;
- grounding evaluation design;
- data leakage in UAV/video datasets;
- object-size effects on detector performance;
- TensorRT / Jetson deployment constraints;
- inference FPS vs complete-system throughput;
- human-in-the-loop GenAI controls;
- AI-assisted coding and how to validate work produced with coding agents;
- how systems engineering changes AI product architecture.

---

**Start here for GE Aerospace:** [AI Lead Developer evidence dossier](ge-aerospace-ai-lead-evidence.md)  
**GitHub:** [razaumair2203-ux](https://github.com/razaumair2203-ux)  
**LinkedIn:** [M. Umair Raza](https://www.linkedin.com/in/mumairaza)
