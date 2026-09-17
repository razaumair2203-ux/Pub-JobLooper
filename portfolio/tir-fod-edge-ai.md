# Case Study — TIR-FOD / Clear Run: Edge AI for Runway Safety

## Problem

Detect runway Foreign Object Debris (FOD) under low-light / night conditions and move beyond a lab-only detector toward an operational sensing pipeline that can run onboard a UAV.

The broader programme combines thermal/RGB sensing, AI detection, geolocation, ground-control coordination, and autonomous retrieval concepts. This case study focuses on the **AI / computer-vision / edge-deployment evidence**.

## My role

I lead/supervise the applied R&D programme and its systems integration: problem framing, project architecture, dataset/test strategy, model evaluation direction, edge-deployment requirements, verification logic, field-validation planning, and technical review across the UAV / sensing / compute / operator workflow.

## Evidence baseline

- **3,499 original LWIR runway frames**.
- **5,593 annotated FOD objects** across **23 classes**.
- Public archival release expands to **29,243 images** including stored derivatives; derivatives are not treated as independent acquisitions.
- **29 model-training runs** across YOLOv8, YOLO11, and YOLO12 configurations with frozen source-grouped train/validation/test partitions.
- Independent annotation-quality checks on selected difficult and representative imagery.
- TensorRT detector deployed on **NVIDIA Jetson Orin Nano** with a 640×512 LWIR stream.
- Repeated flight-test averages: **25.0 FPS inference** and **15.6 FPS end-to-end** for the complete inspection pipeline.
- Compute-and-camera subsystem measured around **17 W** in the reported demonstration configuration.

Public dataset: [TIR-FOD v1.2 — DOI 10.5281/zenodo.22546586](https://doi.org/10.5281/zenodo.22546586)

## Architecture

```mermaid
flowchart LR
    A[LWIR / RGB sensors] --> B[UAV acquisition]
    B --> C[Pre-processing / source grouping]
    C --> D[YOLO detector family]
    D --> E[TensorRT edge inference]
    E --> F[Jetson Orin Nano]
    F --> G[Detection / geolocation output]
    G --> H[Ground-control display / tasking]
    H --> I[Field-validation and failure logging]
```

## Engineering choices that matter

### 1. Evaluation leakage was treated as an engineering risk

The programme explicitly tests source similarity and partitioning rather than assuming random image splitting is representative. Allowing related derivatives of held-out sources into training created a large invalid performance uplift in controlled analysis, showing why leakage-aware evaluation matters for fielded vision systems.

### 2. Small-object performance is treated separately

Runway FOD is often small in image space. Reporting only an aggregate mAP can hide the operationally difficult regime, so the work tracks size-resolved performance and treats small-object generalization as an explicit next-step risk.

### 3. Deployment is measured end-to-end

The useful number is not only model inference speed. The programme distinguishes detector inference from the complete sensing/compute/communications/operator pipeline, which is why both **25.0 FPS inference** and **15.6 FPS end-to-end** are reported.

### 4. The system is not presented as certified autonomy

The current evidence demonstrates a research baseline and integrated sensing/edge-AI flight capability. It does **not** claim certified autonomous runway-clearance performance. Cross-airport validation, false-alarm characterization, latency/power/thermal logging, retrieval integration, and safety evidence remain separate engineering gates.

## Related work

- **Low-Latency Architectures for Real-Time Multi-Stream Object Detection**, IEEE ICoDT2 2025 — [DOI 10.1109/ICoDT269104.2025.11360736](https://doi.org/10.1109/ICoDT269104.2025.11360736)
- **TK-Patch: Universal Top-K Adversarial Patches for Cross-Model Person Evasion**, IEEE ICoDT2 2025 — [DOI 10.1109/ICoDT269104.2025.11360694](https://doi.org/10.1109/ICoDT269104.2025.11360694)

These publications support two adjacent parts of the same engineering mindset: low-latency multi-stream perception and robustness against adversarial/model-transfer failure modes.

## What this project proves for an AI engineering role

**Applied ML:** dataset design, training experiments, model comparison, error analysis, evaluation discipline.

**Multimodal / edge AI:** thermal/RGB sensing, Jetson/TensorRT deployment, real-time constraints, field integration.

**Production thinking:** performance is assessed across the whole pipeline, not only offline model accuracy.

**Aerospace context:** the AI problem originates in an operational aviation-safety need and is integrated with sensing, communications, autonomy, operator workflow, and validation constraints.

## Next engineering steps

- Cross-airport / cross-condition validation.
- Formal false-alarm and miss-rate characterization by operational scenario.
- Checkpoint-specific latency, power, and thermal telemetry.
- Better small-object detection and calibration analysis.
- Automated model-regression reporting across dataset and deployment changes.
- Complete UAV-to-UGV handoff and retrieval validation with defensible system KPIs.

That progression is deliberate: prototype → measured edge deployment → controlled field validation → operational evidence.
