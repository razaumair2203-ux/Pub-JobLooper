# Case Study — Joblooper: Evidence-Governed AI-Assisted Application System

## Problem

Generic AI résumé tools optimize wording but often blur the boundary between supported evidence and invented claims. The engineering problem here was to build a system that can still use AI for job analysis and document refinement while **failing closed when evidence is missing, stale, contradictory, or unapproved**.

Public repository: [Pub-JobLooper](https://github.com/razaumair2203-ux/Pub-JobLooper)

## Core architecture

```mermaid
flowchart LR
    A[Signed career truth] --> B[Exact job capture]
    B --> C[Requirement-to-evidence mapping]
    C --> D[Preflight gaps / cautions]
    D --> E[Evidence-backed draft]
    E --> F[AI-assisted refinement]
    F --> G[Deterministic validation]
    G --> H[Human review / sign-off]
    H --> I[Deterministic DOCX/PDF build]
    I --> J[Hash-bound submission record]
    J --> K[Outcome / learning record]
```

## Engineering principles

### 1. The model is not the source of truth

Candidate facts live in a structured, reviewed career knowledge base. The system can use AI to reason about relevance and wording, but a generated claim cannot become valid merely because a model produced it.

### 2. Generation is traceable

The system keeps atomic career anchors, provenance, approved wording, chronology, metrics, disclosure boundaries, and change history. Output is built from those governed facts rather than from an unconstrained chat history.

### 3. Hard gates stay deterministic

Examples include:

- unsupported ownership/status;
- metrics absent from cited evidence;
- duplicate or omitted governed evidence;
- stale job-description or truth inputs;
- prohibited disclosure;
- approval/build state mismatches;
- malformed or tampered deliverables.

When an absolute gate fails, the workflow stops instead of asking the LLM to “decide” whether it is close enough.

### 4. Human approval is part of the architecture

The workflow separates drafting, review, approval, build, submission, and outcome capture. AI can assist reasoning, but the candidate explicitly approves the final evidence and employer-facing document.

### 5. Reproducibility matters

Approved output is rendered deterministically into DOCX/PDF, checked against approved text, packaged with its evidence/audit record, and tied to the exact submitted files by hash.

## Technical implementation themes

- Python-based local application with minimal runtime dependencies.
- Local-first storage and privacy boundary.
- Optional Codex integration for reasoning about a captured job.
- Exact input capture instead of relying on summaries.
- Structured JSON/JSONL evidence records and append-only decision history.
- Deterministic validation before build/release.
- DOCX/PDF generation and content verification.
- Browser dashboard backed by the same deterministic engine rather than a separate opaque scoring layer.
- Testable state transitions and explicit stale-state invalidation.

## What this project proves for an AI engineering role

**AI product architecture:** the model is integrated as one component inside a larger application lifecycle rather than treated as the application itself.

**Evaluation and guardrails:** claims, metrics, chronology, ownership verbs, and requirement coverage are validated outside the LLM.

**Human-in-the-loop design:** the product knows which decisions belong to the user and which can be automated safely.

**Responsible AI:** no opaque hiring-probability score, no auto-application, no fabricated evidence, and no silent escalation of user claims.

**Production discipline:** installation, diagnostics, deterministic build, artifact integrity, error states, state recovery, and traceable output are first-class requirements.

## Why this matters to enterprise AI

Most enterprise AI applications are not “a model plus a prompt.” They are controlled workflows where data provenance, permissions, validation, auditability, user approval, and recovery behavior matter as much as generation quality.

Joblooper is a deliberately constrained example of that architecture.

## Known limitations / next steps

- Broaden provider abstraction while preserving the same deterministic evidence boundary.
- Add formal evaluation sets for requirement-to-evidence retrieval and wording regressions.
- Strengthen telemetry around generation/review latency and error classes without compromising local-first privacy.
- Continue separating deterministic controls from probabilistic reasoning as features expand.
