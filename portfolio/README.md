# Applied AI & AI Engineering Portfolio — M. Umair Raza

> **For the GE Aerospace AI Lead Developer application:** [open the one-page requirement → evidence map](ge-aerospace-ai-lead-evidence.md).

**Aerospace engineer and applied-AI builder working at the intersection of operational aviation, computer vision, edge deployment, retrieval systems, GenAI workflows, and governed engineering delivery.**

This page is a recruiter-facing evidence layer. It is intentionally short: each project below shows the problem, architecture, measurable proof, my role, and what can be inspected publicly. Sensitive military programme material and private product repositories are not exposed.

## 90-second proof

| Project | What it proves | Technical evidence | Public proof |
|---|---|---|---|
| **Lodestar — grounded RAG / evidence assessment** | RAG architecture, embeddings, chunking, vector search, hybrid retrieval, grounded LLM workflows | Python/FastAPI, structure-aware chunking, BGE embeddings, PostgreSQL/Supabase + pgvector, HNSW cosine index, full-text search, Reciprocal Rank Fusion, authority-aware reranking, citation-grounded output | [Case study](lodestar-rag.md) — codebase private; architecture and implementation evidence summarized safely |
| **TIR-FOD / Clear Run — edge AI for runway safety** | Applied computer vision, multimodal sensing, experimental discipline, edge deployment | 3,499 LWIR source frames, 5,593 annotated objects, 23 classes; 29 YOLO training runs; TensorRT on Jetson Orin Nano; 25.0 FPS inference / 15.6 FPS end-to-end in repeated flight tests | [Case study](tir-fod-edge-ai.md) · [Public dataset DOI](https://doi.org/10.5281/zenodo.22546586) |
| **Codex Adversarial Review Lite** | GenAI/agentic workflow engineering, evaluation, safety controls, human-in-the-loop | Independent builder/reviewer agents, model fallback, test-spec contracts, mutation checks, structured verdicts, report-before-fix flow | [Case study](adversarial-review-lite.md) · [Public repository](https://github.com/razaumair2203-ux/codex-adversarial-review-lite) |
| **Joblooper** | AI-assisted product engineering, traceability, privacy, deterministic validation and release gates | Local-first workflow, evidence-backed generation, provenance, fail-closed validation, review/sign-off gates, reproducible DOCX/PDF output | [Case study](joblooper.md) · [Public repository](https://github.com/razaumair2203-ux/Pub-JobLooper) |

## What connects the projects

The common pattern is **AI applied to consequential engineering workflows rather than isolated demos**:

1. Start with a real operational or business problem.
2. Turn the problem into explicit requirements, data/evidence structures, interfaces, and measurable acceptance criteria.
3. Prototype quickly, but keep validation and traceability separate from the model itself.
4. Measure failure modes as deliberately as headline performance.
5. Deploy only as far as the evidence supports; keep human approval where risk requires it.

That approach comes from an aerospace background spanning aircraft development, flight-line operations, international OEM integration, programme governance, and current applied R&D.

## Selected technical evidence

**Computer vision / edge AI**

- Thermal/RGB object detection and edge deployment for runway Foreign Object Debris detection.
- YOLOv8 / YOLO11 / YOLO12 comparative experimentation with frozen source-grouped evaluation splits.
- TensorRT deployment on NVIDIA Jetson Orin Nano with flight-test performance logging.
- Published work on low-latency multi-stream object-detection architectures and adversarial robustness.

**RAG / retrieval / GenAI**

- Legal-structure-aware deterministic chunking rather than blind fixed token windows.
- Embedding-provider abstraction with model/dimension provenance.
- PostgreSQL/Supabase retrieval plane with `pgvector`, HNSW cosine search, generated full-text search indexes, and metadata filters.
- Hybrid lexical + vector retrieval fused with Reciprocal Rank Fusion and post-retrieval authority-aware reranking.
- Grounded outputs where retrieved evidence is retained as a citable object rather than collapsed into untraceable prompt text.
- Prompt-driven multi-agent review workflows with independent model roles, test contracts, mutation checks, and human sign-off.

**Engineering delivery**

- Python, FastAPI, PostgreSQL/Supabase, Git/GitHub, TypeScript/Next.js, Playwright, containers, CI-style checks and local deployment workflows.
- Applied R&D governance across AI/ML, autonomous systems, sensors, embedded systems, radar/RF, and avionics projects.
- GPU/HPC research environment supporting AI, simulation and engineering workloads.

## Selected publications

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection**, IEEE ICoDT2 2025 — DOI: [10.1109/ICoDT269104.2025.11360736](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion**, IEEE ICoDT2 2025 — DOI: [10.1109/ICoDT269104.2025.11360694](https://doi.org/10.1109/ICoDT269104.2025.11360694)
- **TIR-FOD: thermal-infrared runway FOD benchmark**, public dataset v1.2 — DOI: [10.5281/zenodo.22546586](https://doi.org/10.5281/zenodo.22546586); manuscript/revision work remains in progress.

## How to review this portfolio

If you have only **90 seconds**, read the four project rows above and open **Lodestar** plus **TIR-FOD / Clear Run**. Together they show the two sides of my current AI work: grounded GenAI/RAG software and operational aerospace AI deployed at the edge.

If you are conducting a **technical interview**, use the case-study pages. Each states architecture choices, validation evidence, known limitations, and what I would change next. I prefer discussing trade-offs and failure modes over presenting a technology list.

---

GitHub: [razaumair2203-ux](https://github.com/razaumair2203-ux)  
LinkedIn: [M. Umair Raza](https://www.linkedin.com/in/mumairaza)
