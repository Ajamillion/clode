# Bagger-SPL Delivery Plan (v0.2)

This document consolidates the multi-LLM build proposal into an actionable
roadmap for the Bagger-SPL platform. It aligns the architecture blueprint with
concrete implementation workstreams so the team can execute incrementally while
preserving the long-term vision.

## 1. Program Pillars

1. **Large-signal interpolation engine** – Dual-stage manifold → Gaussian
   Process stack for synthesising driver behaviour with physics regularisation
   (monotonic BL, symmetric Kms, causal inductance, and thermal modelling).
2. **Hybrid acoustic solver core** – Coupled FEM/BEM formulation with
   GMRES-based Helmholtz solver, nonlinear extensions (port compression,
   suspension creep, thermal coupling, cone breakup), and optional transient
   simulation.
3. **Convergence acceleration** – Multi-resolution optimisation ladder
   (differential evolution → adjoint trust-region → interior-point) with
   manufacturing constraints and telemetry hooks.
4. **Validation loop** – Measurement ingestion (Klippel/REW), Bayesian model
   updating, tolerance stack Monte Carlo, and systematic error correction.
5. **Advanced topologies** – Metamaterial resonators and hybrid active/passive
   cancellation modules as opt-in enhancements beyond the core sealed/ported
   families.
6. **Cloud & offline runtime** – Distributed compute (AWS/GCP), caching, and
   full offline subset with simplified solver for field deployments.
7. **Safety and performance** – Thermal/structural guardrails, vibration
   survivability checks, and benchmark dashboards tracking SPL error,
   optimisation throughput, and resource usage.

## 2. Workstream Breakdown

### 2.1 ML Driver Synthesiser
- Implement UMAP+kNN coarse search followed by physics-informed Gaussian
  Processes per curve (BL, Kms, Le, thermal network).
- Enforce regularisers (monotonicity, symmetry, causality) and reciprocity
  projection.
- Deliver evaluation harness targeting the stated RMSE goals for SPL, THD, and
  compression across the holdout dataset.

### 2.2 Acoustic Solver Core
- Establish the FEM interior / FMM-BEM exterior coupling with PML boundaries
  and mortar interface constraints.
- Provide steady-state Helmholtz solve via GMRES + physics preconditioner and
  transient Newmark-β integrator with adaptive timestep.
- Layer in nonlinearities: port compression, suspension creep, thermal-acoustic
  coupling, cone breakup modal overlay.

### 2.3 Optimisation System
- Realise the multi-resolution workflow (coarse differential evolution,
  medium trust-region adjoint, fine interior-point) with constraint ledger from
  manufacturing rules.
- Capture convergence history, gradient norms, and topology switches for UI and
  analytics consumers.

### 2.4 Validation & Feedback
- Build measurement ingestion for Klippel `.dat` and REW `.mdat` files,
  producing delta fields (SPL, phase, impedance, THD).
- Apply Bayesian updating to adjust solver priors; flag systematic errors and
  derive correction factors (port end correction, damping multipliers, etc.).
- Encode production tolerances (material thickness, cutting precision, driver
  variation) and support Monte Carlo runs with 95% confidence reporting.

### 2.5 Advanced Topology Modules
- Metamaterial resonator designer for embedding Helmholtz arrays.
- Hybrid active cancellation module to place small drivers at pressure nodes
  with IIR filter synthesis.

### 2.6 Runtime & Infrastructure
- Docker Compose + Kubernetes manifests for production deployment (nginx,
  gateway, solver workers, Postgres, Redis, Prometheus, Grafana).
- Offline cache bundle for common drivers/topologies with simplified solver and
  iteration cap.

### 2.7 Safety & Benchmarks
- Thermal protection heuristics (coil, adhesive, magnet, port heating) with
  mitigation recommendations.
- Structural vibration verification using ISO 16750-3 profile and modal stress
  analysis.
- Continuous benchmarking dataset capturing SPL/phase error, optimisation time,
  mesh generation, export latency, and memory footprint.

## 3. Execution Milestones

| Milestone | Target | Key Outcomes |
|-----------|--------|--------------|
| **M1 – Foundations** | Month 1 | pnpm/pyproject scaffolding, sealed-box analytical solver (delivered in `spl_core`), FastAPI gateway stub, Studio shell with mock telemetry, unit tests + CI bootstrap. |
| **M2 – Optimisation Loop** | Month 3 | Differential-evolution coarse search, trust-region refinement, typed WebSocket telemetry, SPL/impedance panels in Studio, measurement ingestion prototype. |
| **M3 – High-Fidelity Solvers** | Month 6 | FEM/BEM coupling prototype, nonlinear extensions, Monte Carlo tolerance engine, Playwright + pytest integration tests, Docker Compose deployment. |
| **M4 – Platform Hardening** | Month 9 | Cloud orchestration, offline cache packaging, metamaterial/active modules behind feature flags, observability dashboards, documentation for v1.0 release. |

## Progress Snapshot (Iteration 9)

- **Milestone M1 – Foundations:** 100 % complete. Repository scaffolding, sealed and vented solvers, FastAPI gateway, Studio HUD, consolidated lint/type/test scripts, and excursion reporting are all in place.
- **Milestone M2 – Optimisation Loop:** ~60 % complete. Telemetry HUD groundwork, solver summaries, compliance curve synthesis, excursion headroom metrics, and the new persisted optimisation run API with background solver tasks wire optimisation state cleanly into the frontend and gateway.
- **Overall programme:** ≈40 % toward the v1.0 roadmap ((1.0 + 0.6 + 0 + 0) ÷ 4 milestones).
- Latest iteration introduced the run persistence layer, background task execution, and run-history REST endpoints alongside the existing suspension/excursion instrumentation, unlocking history-aware optimisation flows for downstream services.

## 4. Near-Term Backlog (Next Iterations)

1. **Simulation Core Expansion**
   - ✅ Extend `spl_core` with vented alignment support exposed via the gateway.
   - ✅ Add compliance-curve fitting and excursion limit estimation.
   - ✅ Add JSON schema export for solver inputs/outputs.
2. **Gateway Evolution**
   - ✅ Replace optional FastAPI shim with concrete app, including async task
     manager and SQLite persistence.
   - Define WebSocket protocol aligning with Studio’s optimisation HUD.
3. **Studio Integration**
   - Render SPL/impedance plots from gateway responses.
   - Surface solver alignment metadata (Fc, Qtc, excursion margins) in HUD.
4. **Tooling & QA**
   - ✅ Introduce `ruff` + `mypy` for Python lint/type checks and wire into root
     `pnpm` scripts.
   - Author GitHub Actions workflow running JS + Python unit suites.

## 5. Reference Benchmarks & Targets

Current prototype targets retain the previous spec goals:

```
SPL prediction error   < 0.6 dB (20–200 Hz)
THD error              < 2.1 % at Xmax / 100 Hz
Compression error      < 1.8 dB at rated power / 60 s
Phase error            < 3° (40–140 Hz)
Optimisation runtime   < 60 s end-to-end
Mesh generation        < 5 s per refinement step
Export generation      < 10 s for DXF/STL bundles
```

The dataset currently tracks 47 validation builds with average SPL error of
0.9 dB and phase error of 4.1°. Closing the loop with measurement ingestion and
Bayesian correction is expected to reach the stated launch metrics.

---

This plan provides the connective tissue between the long-form specification
and the concrete code landing in the repository. Each iteration should update
this document with progress notes, risk adjustments, and refined targets.
