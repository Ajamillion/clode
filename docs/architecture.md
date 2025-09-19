# Bagger-SPL Platform Architecture (v1)

## 1. Vision & Objectives
- Deliver production-ready bass enclosure co-design combining loudspeaker physics with user-friendly workflows.
- Prioritize maintainability and incremental delivery over speculative scope while preserving extensibility for advanced research features.
- Ensure every service can run on a single developer workstation first, then scale out to optional cloud accelerators.

_Progress snapshot:_ M1 and M2 remain complete while M3 now closes at 100 % after adding piston directivity traces with directivity index telemetry—now surfaced in the Studio spectra overlay, augmented with -6 dB beamwidth summaries, and exportable via a standalone hybrid directivity CLI—on top of the earlier SPL correlation/MAE/R²/P95/median absolute deviation metrics, keeping the overall roadmap about 75 % toward v1.0.

## 2. Guiding Design Principles
1. **Single source of truth for physics** – a well-tested core simulation/optimization library that both the CLI and UI consume.
2. **Incremental fidelity** – start with analytical + reduced-order models, progressively unlock FEM/BEM refinements when hardware is available.
3. **Observable by default** – instrument solvers and services with structured logs and metrics from day one.
4. **Offline-first** – every workflow must run with bundled datasets and simplified solvers without network access.
5. **Composable interfaces** – prefer gRPC/JSON schemas and typed client SDKs to glue components together with minimal duplication.

## 3. System Overview
```
+----------------+        +-------------------+        +-----------------+
|  Studio (Web)  | <--->  |  Design Gateway   | <----> |  Simulation Core |
|  & CLI (Node)  |        |  (FastAPI + WS)   |        |  (Python/NumPy)  |
+----------------+        +-------------------+        +-----------------+
         |                         |                             |
         v                         v                             v
  Local Cache (TS)      Artifact Store (SQLite)        Optional GPU kernels
         |                         |                             |
         +-------------------> Telemetry Sink <------------------+
```
- **Studio UI**: Vite/React canvas for topology visualization, solver control, and result dashboards.
- **CLI**: Node-based automation front end sharing the same SDK as the UI for parity and scripting.
- **Design Gateway**: FastAPI app exposing REST + WebSocket endpoints, orchestrating solver jobs, handling caching, and publishing progress events.
 - **Design Gateway**: FastAPI app exposing REST + WebSocket endpoints, orchestrating solver jobs, handling caching, and publishing progress events with persisted run history + statistics.
- **Simulation Core**: Python package encapsulating loudspeaker models, reduced-order acoustic solvers, and multi-resolution optimizers with optional GPU acceleration (CuPy) when available.
- **Local Cache & Artifact Store**: SQLite + msgpack bundles storing driver data, run histories, and exported geometries to support offline usage.
- **Telemetry Sink**: Structured logs + metrics (OpenTelemetry/Prometheus) enabling performance tracking even in single-node mode.

## 4. Component Breakdown

### 4.1 Core Physics Library (`python/spl_core`)
- **Modules**:
  - `drivers`: TS parameter ingestion, validation, interpolation (kNN + GP-lite) plus suspension compliance curve synthesis and excursion utilities.
  - `mechanics`: Suspension/BL curve estimators with physics-informed regularization (progressively migrating out of `drivers`).
  - `acoustics`: Reduced-order box/port solver (sealed + vented alignments landed with excursion headroom metrics) plus the new hybrid pressure-field prototype that previews FEM/BEM outputs (interior pressure slices, hotspot coordinate mapping, port compression heuristics, Mach tracking, configurable snapshot stride, suspension creep modelling, lightweight thermal network for coil/pole/basket heating and thermal compression telemetry, aeroacoustic heuristics for vortex shedding loss + jet-noise SPL estimates referenced to the caller's microphone distance, and piston directivity traces with directivity index telemetry now piped through the Studio HUD) without heavy numerical dependencies.
  - `optimization`: Multi-resolution optimizer (differential evolution ➜ L-BFGS) with constraint ledger.
  - `validation`: Monte Carlo tolerance analysis (initial sealed/vented sweep landed) and reciprocity/thermal sanity checks.
  - `measurements`: Klippel/REW ingestion, trace alignment, heuristic diagnosis (level trims, leakage hints, port retunes), and measurement-vs-simulation delta statistics exposed through both the FastAPI endpoints and a standalone CLI, now powering multi-metric overlays (SPL, phase, impedance magnitude, THD) with solver delta toggles, Pearson SPL correlation, SPL mean absolute error, SPL R² scoring, SPL delta standard deviation, SPL median absolute deviation, SPL 95th-percentile absolute error, highest/lowest signed SPL deltas, and CSV exports for measured/predicted/calibrated traces inside Studio.
  - `calibration`: Bayesian updates that transform measurement diagnoses into posterior level trims, port-length scales, and leakage-Q multipliers with credible intervals for automated solver correction.
  - `serialization`: JSON schema exports for solver requests/responses used by gateway + clients.
- **API Surface**: Plain Python classes exported through pydantic models; zero global state.

### 4.2 Simulation Gateway (`services/gateway`)
- FastAPI app that:
  - Exposes REST endpoints for job submission, driver queries, schema catalogs, and aggregation (`/opt/runs`, `/opt/stats`, `/schemas/solvers`).
  - Returns alignment summaries (Fc/Qtc, Fb, -3 dB edges, velocity peaks) alongside solver traces.
  - Streams hybrid solver responses via `/simulate/hybrid`, returning multi-plane pressure slices with per-plane maxima/means and hotspot coordinates for Studio overlays, and allows callers to throttle snapshot density via the `snapshot_stride` request field or disable the suspension creep model per run.
  - Offers Monte Carlo tolerance endpoints to summarise manufacturing risk (excursion, port velocity) with qualitative risk ratings directly from the gateway.
  - Provides measurement preview + comparison endpoints that parse Klippel `.dat` / REW `.mdat` uploads and report SPL/impedance deltas against solver predictions, returning both heuristic diagnoses and calibration posteriors with optional frequency-band gating for targeted fits.
  - Hosts WebSocket streams for live optimization telemetry (iterations, constraint hits, topology swaps).
  - Manages run lifecycle (start, pause, resume, cancel) with async tasks.
  - Persists run inputs/outputs in SQLite via a lightweight `RunStore` with status counts + filters.
  - Uses dependency-injected `spl_core` instances for testability and alignment heuristics (sealed/vented) based on optimisation preferences.

### 4.3 Client SDK (`packages/sdk`)
- Generated TypeScript + Python clients sharing OpenAPI schema.
- Provides strongly-typed calls, WebSocket helpers with auto-reconnect, and offline fallbacks.

### 4.4 Studio Web App (`apps/studio`)
- Vite + React + Zustand for state management.
- Three.js-based enclosure viewer fed by gateway mesh snapshots.
- Uses TanStack Query for API calls, Msgpack WebSocket stream for telemetry.
- Pluggable data panels (SPL curve, impedance, tolerance risk snapshots) plus optimisation HUD with alignment toggles and run history timeline fed by persisted run APIs.

### 4.5 CLI (`apps/cli`)
- Node-based CLI (ts-node / bun) bundling the SDK.
- Commands: `init`, `optimize`, `export`, `validate`, `cache sync`.
- Shares configuration with Studio via `.bagger/config.yaml`.

### 4.6 Tooling & Infrastructure
- **Data packages**: `data/driver-db.msgpack`, `data/topologies/*.json` shipped with installer.
- **Testing**: Pytest for `spl_core`, Vitest/Playwright for Studio, smoke tests for CLI.
- **Build**: `uv` for Python deps, `pnpm` workspaces for JS/TS; `make` orchestrates.
- **Packaging**: Docker images with a docker-compose dev stack, alongside Python wheels and npm packages for direct installs.
- **Command-line utilities**: Measurement comparison, solver schema export, tolerance snapshot generation, and the hybrid directivity exporter for off-axis studies outside the gateway (now capturing -6 dB beamwidth statistics alongside directivity index traces).
- **Observability**: Structured logging (loguru), metrics via `prometheus-client`, OpenTelemetry export toggled by env var.

## 5. Deployment Modes
1. **Solo Developer** (default)
   - FastAPI gateway + simulation core run locally.
   - SQLite + local cache only.
   - Studio served via `pnpm dev` proxying to FastAPI.
2. **Team Server / Local Compose** (optional)
   - `docker compose up` launches the FastAPI gateway and Studio UI containers with sensible defaults.
   - SQLite run history lives in a named volume so state survives restarts; future revisions can add Redis/Postgres as they land.
3. **Cloud Burst** (future)
   - Reuse same FastAPI container with autoscaling compute pods.
   - Feature flag to offload heavy simulations to GPU nodes.

## 6. Incremental Delivery Plan
| Milestone | Scope | Key Deliverables |
|-----------|-------|------------------|
| M1 – Foundations | Establish repo layout, scaffolding, driver dataset ingestion, sealed-box solver, CLI `optimize` command. | Working FastAPI gateway, Studio skeleton showing SPL curve, automated tests + CI. |
| M2 – Optimization Loop | Implement multi-resolution optimizer, telemetry streaming, topology visualizer, tolerance analysis. | End-to-end run on bundled dataset with convergence dashboard. |
| M3 – Advanced Fidelity | Introduce ported enclosures, thermal model hooks, GPU acceleration toggle, artifact exports (DXF/STL). | Extended analytics, offline caching improvements. |
| M4 – Integration & Hardening | Add Monte Carlo validation, measurement feedback importer, packaging/installers, observability dashboards. | Release candidate for v1.0. |

## 7. Technology Summary
- **Languages**: Python 3.11+, TypeScript 5+
- **Frontend**: Vite, React 18, Three.js, Zustand, TanStack Query, ECharts (for plots)
- **Backend**: FastAPI, SQLModel/SQLite, Uvicorn, Redis (optional)
- **Simulation**: NumPy/SciPy, CuPy (optional), scikit-learn-lite (e.g., `umap-learn`), custom optimization routines.
- **Transport**: REST (JSON) for control plane, Msgpack over WebSocket for telemetry.
- **Build/Test**: pnpm, uv, pytest, Ruff, mypy, Vitest, Playwright, GitHub Actions CI.
- **Packaging**: Python wheels via `uv build`, npm packages, optional Docker Compose definitions.

## 8. Next Steps Toward Development
1. ✅ Scaffold initial repository structure with `packages/web-ui` and `packages/dev-mocks`; continue fleshing out apps, services, python libs, and data.
2. ✅ Land initial FastAPI gateway stub backed by the analytical sealed-box solver housed in `spl_core`.
3. ✅ Provide unit tests validating sealed-box alignment (Fc/Qtc, SPL/impedance shape).
4. Define shared configuration schema (`bagger.config.jsonschema`) and auto-generate TS/Python types.
5. ✅ Wire Studio SPL plot + WebSocket telemetry using mocked backend and expose persisted run history in the UI.
6. ✅ Set up CI pipeline executing lint/type/test on both Python and TypeScript stacks, publishing tolerance artefacts for downstream dashboards.
7. ✅ Ship docker-compose orchestration for the gateway + Studio dev stack so the platform spins up with one command.
8. ✅ Land Playwright-driven Studio regression coverage for the Studio workflow, wiring the mock optimisation stack into automated checks.
9. ✅ Expand hybrid solver fidelity with piston directivity, aeroacoustic heuristics, and richer snapshot validation to close the high-fidelity milestone.

This architecture keeps the platform approachable for a small team while preserving clear pathways to high-fidelity simulation and cloud-scale deployments when needed.
