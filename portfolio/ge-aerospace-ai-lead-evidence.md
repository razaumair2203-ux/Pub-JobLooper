# Evidence Map — GE Aerospace AI Lead Developer

**Candidate: M. Umair Raza**  
**Target: AI Lead Developer — GE Aerospace, Warsaw**

> **Operational aerospace engineer + current applied-AI lead + hands-on AI/RAG/GenAI product work.**

## What I bring to this role

- **Applied AI in aerospace:** computer vision, edge inference, autonomous systems, multimodal sensing, field validation, and AI-enabled engineering workflows.
- **Modern AI application engineering:** RAG, embeddings, vector search, hybrid retrieval, grounded generation, prompt-driven workflows, APIs, databases, and human-in-the-loop controls.
- **Operational engineering depth:** 18+ years developing, integrating, testing, operating, and governing safety-critical aerospace systems — useful when an AI prototype has to become a dependable engineering capability.

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

A working AI application built around grounded retrieval rather than an unverified chatbot response.

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

AI moved from dataset and model experiments into an onboard sensing and inference chain.

Evidence includes:

- 3,499 original LWIR runway frames;
- 5,593 annotated objects across 23 classes;
- 29 YOLO training runs;
- leakage-aware evaluation;
- TensorRT deployment on NVIDIA Jetson Orin Nano;
- repeated flight-test means of **25.0 FPS inference** and **15.6 FPS end-to-end**;
- integration with sensing, communications, operator display, UAV operations, and broader autonomy work.

[Read the edge-AI case study →](tir-fod-edge-ai.md)

### 3. Codex Adversarial Review Lite — GenAI workflow engineering

A public AI engineering tool that wraps independent models in a controlled workflow with scope contracts, preflight, test expectations, mutation checks, structured verdicts, report-before-fix behavior, and human approval.

[Inspect the public repository →](https://github.com/razaumair2203-ux/codex-adversarial-review-lite)

## Supporting public product

**Joblooper** applies the same engineering philosophy to an AI-assisted product: deterministic evidence boundaries, provenance, fail-closed validation, human sign-off, reproducible artifacts, and privacy-first local operation.

[Inspect Joblooper →](https://github.com/razaumair2203-ux/Pub-JobLooper)

## Published AI / computer-vision work

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion** — IEEE ICoDT2 2025 — [DOI](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD public thermal benchmark dataset v1.2** — [DOI](https://doi.org/10.5281/zenodo.22546586)

## Evidence boundary

This page distinguishes direct current AI evidence from the broader aerospace career behind it. Unsupported experience is intentionally omitted; private repositories and sensitive programme material remain private, while public code, publications, datasets, architecture decisions, and measured deployment results are exposed wherever possible.

---

[Full Applied AI Portfolio](README.md) · [GitHub profile](https://github.com/razaumair2203-ux) · [LinkedIn](https://www.linkedin.com/in/mumairaza)
