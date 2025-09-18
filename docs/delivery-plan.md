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
- Docker Compose dev stack (gateway + Studio) now available; Kubernetes manifests
  will extend it with nginx, solver workers, Postgres, Redis, Prometheus, and
  Grafana for production deployment.
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

## Progress Snapshot (Iteration 20)

- **Milestone M1 – Foundations:** 100 % complete. Repository scaffolding, sealed and vented solvers, FastAPI gateway, Studio HUD, consolidated lint/type/test scripts, and excursion reporting are all in place.
- **Milestone M2 – Optimisation Loop:** 100 % complete. Telemetry HUD groundwork, solver summaries, compliance curve synthesis, excursion headroom metrics, persisted optimisation runs, measurement ingestion scaffolding, tolerance sweeps, Studio tolerance + measurement panels, Bayesian calibration helpers, CI automation, and the schema catalog endpoints/CLI provide an end-to-end optimisation timeline backed by the gateway.
- **Milestone M3 – High-Fidelity Solvers:** ≈92 % complete. The reduced-order hybrid solver now layers vortex-shedding attenuation and jet-noise SPL estimation on top of the existing port compression heuristics, suspension creep toggle, thermal telemetry, multi-metric measurement overlays with correlation/MAE/R²/standard deviation/95th-percentile plus highest/lowest delta scoring, exportable comparison datasets, the docker-compose stack, and the Playwright Studio regression suite; remaining work focuses on FEM/BEM refinements and production hardening.
- **Overall programme:** ≈73 % toward the v1.0 roadmap ((1.0 + 1.0 + 0.92 + 0) ÷ 4 milestones).
- Latest iteration adds SPL delta standard deviation so Studio, the CLI, and the gateway can summarise typical fit spread alongside extrema-driven metrics while retaining the hybrid aeroacoustic heuristics for port noise assessment.
- Fractional-octave smoothing now spans the measurement CLI, FastAPI payloads, and Studio controls so noisy SPL traces can be compared using consistent 1/N-octave averaging across the toolchain.

## 4. Completion Strategy

### 4.1 Immediate Iteration Goals

1. **Simulation Core Expansion**
   - ✅ Extend `spl_core` with vented alignment support exposed via the gateway.
   - ✅ Add compliance-curve fitting and excursion limit estimation.
   - ✅ Add JSON schema export for solver inputs/outputs.
   - ✅ Introduce Monte Carlo tolerance sweeps for sealed and vented alignments with REST reporting.
   - ✅ Land measurement ingestion scaffolding (Klippel/REW parsers) feeding the tolerance and calibration loops.
   - ✅ Convert measurement heuristics into Bayesian calibration posteriors surfaced through the CLI, gateway, and Studio.
   - ✅ Automate calibration override reruns from the CLI so measurement comparisons can preview corrected solver fits.
2. **Gateway Evolution**
   - ✅ Replace optional FastAPI shim with concrete app, including async task manager and SQLite persistence.
   - ✅ Define WebSocket protocol aligning with Studio’s optimisation HUD.
   - ✅ Expose solver schema catalogs via REST endpoints and CLI exports so typed clients can stay in sync with `spl_core` contracts.
   - ✅ Introduce measurement upload endpoints wiring through to the simulation core ingestion queue.
3. **Studio Integration**
   - ✅ Render SPL/impedance plots from gateway responses with historical overlays.
   - ✅ Surface solver alignment metadata (Fc/Fb, excursion margins) in HUD with run history timeline and status chips.
   - ✅ Add tolerance visualisations (qualitative risk callouts driven by Monte Carlo sweeps) mirroring the new gateway outputs.
- ✅ Introduce a measurement comparison panel that previews uploads/synthetic traces, charts SPL/phase/impedance/THD overlays with solver deltas, and now exports the combined traces as CSV snapshots for downstream tooling.
4. **Tooling & QA**
   - ✅ Introduce `ruff` + `mypy` for Python lint/type checks and wire into root `pnpm` scripts.
   - ✅ Author GitHub Actions workflow running JS + Python unit suites and publishing Monte Carlo/tolerance snapshots as artefacts.
   - ✅ Provide a docker-compose stack that runs the FastAPI gateway and Studio UI together for local smoke tests.

### 4.2 Closing Milestone M2 – Optimisation Loop

- Finalise the coarse ➜ medium ➜ fine optimisation ladder by wiring differential evolution search to the existing run persistence layer and exposing adjoint/L-BFGS refinement metrics via the gateway.
- Ship measurement ingestion MVP so real-world SPL/impedance traces can be replayed against solver predictions, unlocking the Bayesian correction flow promised in the spec.
- Extend Studio to chart solver traces (SPL, impedance, excursion) and display constraint violation streaks, ensuring UX parity with the backend telemetry.
- Target completion: **Iteration 15** with parallel UI/backend pairing and automated regression tests for optimisation summaries.

### 4.3 Spinning up Milestone M3 – High-Fidelity Solvers

- Prototype the reduced-order FEM/BEM adaptor using analytical kernels as reference outputs; guard behind a feature flag so we can iterate without destabilising existing flows.
- Add nonlinear models (port compression, suspension creep) as optional modules in `spl_core`, emitting telemetry for Studio overlays.
- Introduce job affinity in the gateway so heavier FEM/BEM work can be queued separately from the fast analytical solvers.
- Target readiness: **Iterations 15–17**, delivering a demo-quality hybrid solver with automated comparison tests against baseline analytical results.

### 4.4 Preparing Milestone M4 – Platform Hardening

- Extend the docker-compose stack with additional services (Redis/worker pools) and package documented offline bundles with simplified solver/driver datasets.
- Layer observability (structured logs + Prometheus metrics) into the gateway and solver workers, wiring Grafana dashboards for runtime health.
- Implement licensing and feature-flag enforcement paths needed for pro/academic SKUs outlined in the main spec.
- Target readiness: **Iterations 18–20**, culminating in release-candidate documentation and installer assets.

### 4.5 Risk Radar

- **Data coverage for ML interpolation** – collect/curate driver datasets early; mitigation: begin ingestion tooling alongside measurement MVP to avoid blocking M3.
- **GPU.js performance ceilings** – benchmark pressure kernels on mid-tier hardware; mitigation: provide configurable quality tiers and fallbacks to CPU kernels.
- **Solver complexity creep** – maintain feature flags and regression tests to keep analytical path stable while FEM/BEM features mature.
- **CI resource constraints** – mock CUDA-dependent steps in CI and document how to enable full runs locally/on dedicated agents.

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
