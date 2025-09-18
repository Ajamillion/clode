# Bagger-SPL

A focused loudspeaker enclosure co-design platform blending physics-based simulation, optimization, and modern developer tooling.

## Repository Status
- ✅ Architecture blueprint captured in [`docs/architecture.md`](docs/architecture.md)
- ✅ Delivery roadmap captured in [`docs/delivery-plan.md`](docs/delivery-plan.md)
- ✅ Frontend + mock backend scaffolding bootstrapped with pnpm workspaces
- ✅ Solver telemetry HUD with typed WebSocket protocol + GPU.js pressure renderer
- ✅ Analytical sealed + vented-box solvers with FastAPI endpoints (see [`spl_core`](python/spl_core) and [`services/gateway`](services/gateway))
- ✅ Alignment summary metrics (-3 dB bandwidth, velocity peaks) exposed alongside solver responses
- ✅ Suspension compliance curve helper and excursion headroom metrics for sealed + vented solvers
- ✅ JSON schema exports for solver request/response contracts (see [`spl_core/serialization.py`](python/spl_core/serialization.py))
- ✅ Solver schema catalog exposed via `/schemas/solvers` endpoints and a CLI export helper for typed client generation
- ✅ Python linting and type-checking automation wired into the pnpm workspace scripts
- ✅ FastAPI optimisation run API with SQLite-backed persistence and background solver tasks
- ✅ Run history API with status aggregates powering the Studio timeline panel and alignment toggles
- ✅ Monte Carlo tolerance analysis surfaced through new sealed/vented endpoints with qualitative risk ratings for manufacturing risk estimates
- ✅ Studio tolerance panel streaming Monte Carlo excursion/velocity risk snapshots from the gateway
- ✅ Measurement ingestion scaffolding with Klippel/REW parsers and FastAPI comparison endpoints for SPL/impedance deltas
- ✅ Studio measurement panel that previews uploads or synthesised traces and compares SPL/impedance deltas against solver predictions
- ✅ Measurement diagnostics that suggest level trims, leakage adjustments, and port retunes from solver/field deltas
- ✅ Measurement calibration helper that produces Bayesian posteriors for level trims, port scales, and leakage-Q corrections
- ✅ Calibration overrides that translate Bayesian posteriors into drive, port, and leakage adjustments across CLI, API, and Studio
- ✅ Measurement comparisons can automatically rerun solver predictions with the derived overrides, returning calibrated stats alongside the baseline fit
- ✅ Measurement panel overlays measured SPL against solver baselines and calibrated reruns so improvements are visible at a glance
- ✅ Measurement overlays now span SPL, phase, impedance magnitude, and THD with delta toggles to verify calibration impact at a glance
- ✅ Measurement stats now report Pearson SPL correlation so fit quality captures shape agreement alongside level error
- ✅ Measurement stats also surface SPL R² so reviewers see how much variance the prediction explains alongside correlation and bias
- ✅ Measurement stats now include SPL mean absolute error so reviewers get an intuitive average-delta gauge alongside RMSE
- ✅ Measurement stats expose the SPL 95th-percentile absolute error to spotlight worst-case deviations alongside average metrics
- ✅ Measurement stats also report the highest and lowest SPL deltas so reviewers see the most positive and negative excursions alongside the absolute worst-case value
- ✅ Measurement stats capture SPL delta standard deviation so reviewers can gauge typical spread alongside extrema-focused metrics
- ✅ Measurement comparison exports capture measured/predicted traces, deltas, and calibrated reruns as CSV snapshots for downstream analysis
- ✅ Measurement comparisons support fractional-octave smoothing across the CLI, gateway, and Studio controls so noisy traces can be tamed consistently
- ✅ GitHub Actions workflow that runs lint/type/test gates for Python + TypeScript workspaces and publishes Monte Carlo tolerance artefacts
- ✅ Hybrid solver prototype that blends the lumped models with interior pressure field
  previews, port compression metrics, and Mach tracking
- ✅ Hybrid simulation endpoint (`/simulate/hybrid`) returning multi-plane pressure
  snapshots with JSON Schemas for typed client integration
- ✅ Hybrid solver hotspot mapping that reports per-plane pressure coordinates and
  minimum port compression ratios for targeted damping and vent tuning analysis
- ✅ Configurable hybrid snapshot stride so lighter clients can down-sample interior
  field rasters without losing summary metrics
- ✅ Hybrid suspension creep model with API toggle and summary telemetry describing
  the low-frequency compliance gain and time constants
- ✅ Hybrid thermal network estimating coil/pole/basket temperature rise with thermal
  compression telemetry in solver responses and gateway payloads
- ✅ Hybrid port aeroacoustic heuristics estimating vortex shedding losses and jet
  noise SPL (referenced to the requested microphone distance) so chuffing risk is
  visible in solver traces and summaries
- ✅ Docker Compose orchestration for the gateway + Studio dev stack so the
  platform can spin up with a single command
- ✅ Playwright-guided Studio end-to-end coverage exercises the measurement
  panel and mock optimisation stack
- 🛠️ Extended FastAPI gateway, optimisation stack, and FEM/BEM solvers under development

Current roadmap snapshot: **M1 100 %**, **M2 100 %**, **M3 ≈92 %**, overall ≈73 % toward the v1.0 target.

## Prerequisites
- Node.js 20+
- pnpm 9+
- (optional) Python 3.11+ for upcoming gateway/simulation services

## Getting Started
1. Install dependencies
   ```bash
   pnpm install
   ```
2. (Optional) Install Python dev dependencies for lint/type/test workflows
   ```bash
   pip install -e .[dev]
   ```
3. In one terminal start the mock backend & WebSocket feed (includes the optimisation run API)
   ```bash
   pnpm --filter @motosub/dev-mocks dev
   ```
4. In another terminal launch the Studio web client
   ```bash
   pnpm --filter @motosub/web-ui dev
   ```
5. Open http://localhost:5173 to view the demo enclosure renderer streaming synthetic optimization telemetry.
   The optimisation HUD now records backend runs via `/api/opt/start` and polls `/api/opt/{id}` for convergence data.

   Monte Carlo tolerance sweeps are available via `POST /simulate/sealed/tolerances` and `/simulate/vented/tolerances` for quick manufacturing risk snapshots. The hybrid solver request now accepts a `snapshot_stride` field when you need to throttle how many interior pressure slices are captured.

### Docker Compose stack

Spin up the FastAPI gateway and Studio client together without installing local
dependencies:

```bash
docker compose up --build
```

The stack exposes the gateway at http://localhost:8000 (including the
`/health`, `/opt`, `/simulate`, and `/measurements` routes) and the Studio UI at
http://localhost:5173.  Solver runs persist inside the `gateway-data` named
volume so you can stop/restart the stack without losing iteration history.  The
Compose file targets local development, so rebuild the images (`docker compose
build`) after pulling upstream changes to the Python or TypeScript sources.

## Quality checks

Run the consolidated automation from the repo root:

```bash
pnpm lint        # eslint for the web workspace + ruff for python modules
pnpm typecheck   # tsconfig builds + mypy over python/services
pnpm test:e2e    # Playwright suite (runs Vite + mock API servers automatically)
pnpm py:test     # Python unit tests
pnpm py:tolerance # writes JSON reports into ./tolerance-snapshots
pnpm py:schemas  # writes solver request/response schemas into ./schema-exports
pnpm py:compare -- path/to/measurement.dat --alignment sealed
```

The tolerance helper accepts additional options (`--iterations`, `--seed`, `--vented-iterations`, etc.). Pass them after `--` when using the pnpm script, for example `pnpm py:tolerance -- --iterations 256`.

### End-to-end Studio tests

The Playwright suite lives under `packages/web-ui/tests` and uses the workspace
config in `packages/web-ui/playwright.config.ts` to boot the Vite dev server and
mock API automatically. Run it locally with:

```bash
pnpm test:e2e
```

Provide the `PLAYWRIGHT_BASE_URL` environment variable to target an already
running Studio instance and skip the web server bootstrap. Reports are written
to `packages/web-ui/playwright-report` by default; open them with
`pnpm --filter @motosub/web-ui test:e2e:report`.

## Workspace Layout
```
packages/
  web-ui/      # Vite + React Three Fiber Studio shell + live optimization HUD
  dev-mocks/   # Mock API + typed WebSocket server for local development
```

Additional services (gateway, simulation core, CLI) will be added following the blueprint in `docs/architecture.md`.

## Next Steps
- Close out the multi-resolution optimisation ladder by wiring differential evolution search and adjoint refinement into the persisted run workflow.
- Extend the measurement overlays to impedance, phase, and THD deltas while adding export hooks so calibrated reruns feed downstream tooling.
- Extend the FastAPI gateway with export/download and measurement upload endpoints, and surface the richer traces through Studio SPL/impedance charts.
- Wire the tolerance artefacts into dashboards (e.g. Grafana panels or Studio overlays) so CI snapshots drive proactive manufacturing risk monitoring.

## Python Simulation Core

The analytical sealed- and vented-box solvers live in the [`spl_core`](python/spl_core) package
and are exposed via a lightweight FastAPI gateway stub in
[`services/gateway`](services/gateway). Run the Python unit tests with:

```bash
python -m unittest discover -s python/tests
```

## Schema exports & API catalog

- Fetch solver request/response schemas directly from the gateway via `GET /schemas/solvers` or `GET /schemas/solvers/{alignment}`.
- Generate local JSON files for tooling by running `pnpm py:schemas`, which writes `catalog.json` plus per-solver request/response documents to `./schema-exports`.

Contributions and feedback are welcome as we grow Bagger-SPL toward an offline-first yet cloud-capable toolchain.

## Measurement comparison CLI

Use the new `compare_measurements.py` script to benchmark field measurements against the analytical solvers without spinning up the FastAPI gateway. Measurements exported from Klippel (`.dat`) and REW (`.mdat`) are detected automatically:

```bash
pnpm py:compare -- path/to/measurement.mdat --alignment vented --volume 62 --drive-voltage 2.83 \
  --stats-output ./stats.json --delta-output ./delta.json --diagnosis-output ./diagnosis.json --calibration-output ./calibration.json
```

The command prints a human-readable summary by default; pass `--json` for machine-readable output. Optional flags mirror the gateway defaults so Studio results and CLI analyses stay aligned, and the summary now calls out the SPL 95th-percentile absolute delta alongside RMSE/MAE/bias/correlation/R², the highest and lowest signed deltas, and worst-case error for a balanced sense of fit quality.

Add `--apply-overrides` to trigger a second solver run that applies the derived calibration overrides and reports the corrected SPL, phase, and impedance errors. When enabled you can capture the calibrated metrics via `--calibrated-stats-output`, `--calibrated-delta-output`, and `--calibrated-diagnosis-output` alongside the baseline results.

Diagnosis output highlights systematic biases: low/mid/high-band SPL offsets, suggested global level trims, tuning shifts with estimated port-length adjustments, leakage hints, and a note stack summarising the most actionable insights. Calibration payloads provide Bayesian posteriors with 95 % credible intervals for the recommended level trims, port length scaling, and leakage-Q multipliers.

Pass `--min-frequency` and/or `--max-frequency` to focus the analysis on a specific band—handy when measurements get noisy at the extremes or when you only care about the sub-bass window. The Studio measurement panel mirrors the behaviour with inline band controls so UI-driven comparisons stay aligned with the CLI outputs. Add `--smoothing-fraction <N>` to enable fractional-octave smoothing (1/N) across the SPL deltas; the Studio panel exposes the same selector so its overlays and summaries match the CLI output.

Once a comparison completes in Studio, use the **Export CSV** action to download a frequency-by-frequency snapshot that includes the measurement trace, solver prediction, delta overlays, and any calibrated rerun data. The export honours the active frequency band so downstream analysis tools stay aligned with the window you evaluated in the UI.
