# Evidence Map — GE Aerospace AI Lead Developer

**Candidate: M. Umair Raza**  
**Target: AI Lead Developer — GE Aerospace, Warsaw**

This page is a compact technical evidence map for the role. It links the requirements in the vacancy to work that can be inspected or discussed in depth. It is not an attempt to relabel an 18-year aerospace career as 18 years of AI development; the relevant proposition is narrower and stronger:

> **Operational aerospace engineer + current applied-AI lead + hands-on AI/RAG/GenAI product work.**

## Why the profile is relevant

My current engineering work applies AI to real aerospace problems: computer vision, edge inference, autonomous systems, multimodal sensing, field validation, and AI-enabled software workflows. That sits on top of a career spent developing, integrating, testing, operating, and governing safety-critical aerospace systems.

The result is a profile that can work on the **AI solution lifecycle and the engineering context around it** — requirements, data, architecture, experimentation, deployment constraints, validation, failure modes, maintainability, and user workflow.

## Requirement → evidence

| GE Aerospace need | Direct evidence | Proof |
|---|---|---|
| **Develop and implement AI / ML solutions** | TIR-FOD / Clear Run: thermal/RGB detection, YOLO experimentation, edge inference, autonomous workflow integration | [Edge-AI case study](tir-fod-edge-ai.md) · [Dataset DOI](https://doi.org/10.5281/zenodo.22546586) |
| **Python and common AI/ML frameworks** | Python-based AI/RAG backends; YOLO/TensorRT experimentation; Python/FastAPI RAG implementation | [Lodestar case study](lodestar-rag.md) · [Edge-AI case study](tir-fod-edge-ai.md) |
| **Generative AI / prompt-driven applications** | Independent builder/reviewer GenAI workflow; prompt contracts, model fallback, structured verdicts, human sign-off | [Public Codex AR-L repo](https://github.com/razaumair2203-ux/codex-adversarial-review-lite) |
| **RAG applications** | Working retrieval pipeline with domain-aware chunking, embeddings, vector + lexical retrieval, fusion, reranking, citation grounding | [Lodestar case study](lodestar-rag.md) |
| **Vector databases / embeddings / semantic search** | BGE embeddings; PostgreSQL/Supabase `pgvector`; HNSW cosine index; semantic + full-text retrieval | [Lodestar case study](lodestar-rag.md) |
| **Model / API integration** | LLM-provider abstraction and CLI/model integrations in Lodestar / JobPilot / adversarial-review workflows | [Lodestar](lodestar-rag.md) · [Codex AR-L](adversarial-review-lite.md) |
| **Prototype → deployment** | Jetson Orin Nano + TensorRT runway-flight demonstrator with measured inference and end-to-end throughput | [Edge-AI case study](tir-fod-edge-ai.md) |
| **Testing / evaluation / monitoring mindset** | Leakage-aware dataset evaluation, repeated model runs, pipeline throughput measurement; adversarial code-review contracts and mutation checks | [TIR-FOD](tir-fod-edge-ai.md) · [Codex AR-L](adversarial-review-lite.md) |
| **Multimodal AI** | LWIR + RGB sensing and UAV-based perception workflow | [TIR-FOD](tir-fod-edge-ai.md) |
| **Responsible / secure AI** | Evidence-grounded retrieval, explicit source citations, no fabricated probability claims; privacy notice, no silent model edits, human approval | [Lodestar](lodestar-rag.md) · [Codex AR-L](adversarial-review-lite.md) · [Joblooper](joblooper.md) |
| **Agile / delivery discipline** | PMI-ACP + PMP; software-intensive aerospace delivery; current applied-R&D portfolio governance | CV / interview evidence; supporting public product work in [Joblooper](joblooper.md) |
| **Mentoring / technical leadership** | Leads multidisciplinary R&D portfolio and supervises advanced engineering/AI projects; previous engineering/software team leadership | CV / interview evidence |
| **Aerospace engineering context** | 18+ years across aircraft development, international OEM integration, operational flight-line support, PMO governance, and current applied AI | CV / interview evidence |

## Three projects to inspect first

### 1. Lodestar — RAG / retrieval engineering

This closes the most important “is the candidate actually hands-on with modern GenAI infrastructure?” question.

The implementation includes:

- legal-structure-aware chunking;
- local `sentence-transformers` / BGE embeddings;
- PostgreSQL/Supabase with `pgvector`;
- HNSW cosine vector search;
- PostgreSQL full-text search;
- hybrid retrieval with Reciprocal Rank Fusion;
- authority-aware reranking;
- structured citable retrieval objects;
- FastAPI backend and provider abstraction.

[Read the technical case study →](lodestar-rag.md)

### 2. TIR-FOD / Clear Run — operational aerospace edge AI

This answers a different question: can the candidate take AI outside a notebook?

Evidence includes:

- 3,499 original LWIR runway frames;
- 5,593 annotated objects across 23 classes;
- 29 YOLO training runs;
- leakage-aware evaluation;
- TensorRT deployment on NVIDIA Jetson Orin Nano;
- repeated flight-test means of 25.0 FPS inference and 15.6 FPS end-to-end;
- integration with sensing, communications, operator display, UAV operations, and broader autonomy work.

[Read the edge-AI case study →](tir-fod-edge-ai.md)

### 3. Codex Adversarial Review Lite — GenAI workflow engineering

This demonstrates that my GenAI work is not limited to “using ChatGPT.” The project wraps independent models in a controlled engineering workflow with scope contracts, preflight, test expectations, mutation checks, structured verdicts, report-before-fix behavior, and user approval.

[Inspect the public repository →](https://github.com/razaumair2203-ux/codex-adversarial-review-lite)

## Supporting public product

**Joblooper** shows the same design philosophy applied to an AI-assisted product: deterministic evidence boundaries, provenance, fail-closed validation, human sign-off, reproducible artifacts, and privacy-first local operation.

[Inspect Joblooper →](https://github.com/razaumair2203-ux/Pub-JobLooper)

## Published AI / computer-vision work

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD public thermal benchmark dataset v1.2** — [DOI](https://doi.org/10.5281/zenodo.22546586)

## Evidence boundary

I do **not** claim a long conventional career as a full-time software/ML engineer. I do claim direct current applied-AI leadership and hands-on AI product/retrieval work, backed by working repositories, public research artifacts, deployment measurements, and an aerospace career that supplies the operational context in which these systems must work.

Areas I would expect to discuss candidly in interview include enterprise cloud deployment depth and the difference between research/side-product environments and GE-scale production. Those are scaling-context questions, not substitutes for the implementation evidence above.

---

[Full Applied AI Portfolio](README.md) · [GitHub profile](https://github.com/razaumair2203-ux) · [LinkedIn](https://www.linkedin.com/in/mumairaza)
