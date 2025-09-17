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
- ✅ Monte Carlo tolerance analysis surfaced through new sealed/vented endpoints for manufacturing risk estimates
- ✅ Studio tolerance panel streaming Monte Carlo excursion/velocity risk snapshots from the gateway
- ✅ Measurement ingestion scaffolding with Klippel/REW parsers and FastAPI comparison endpoints for SPL/impedance deltas
- ✅ Studio measurement panel that previews uploads or synthesised traces and compares SPL/impedance deltas against solver predictions
- ✅ Measurement diagnostics that suggest level trims, leakage adjustments, and port retunes from solver/field deltas
- ✅ Measurement calibration helper that produces Bayesian posteriors for level trims, port scales, and leakage-Q corrections
- ✅ Calibration overrides that translate Bayesian posteriors into drive, port, and leakage adjustments across CLI, API, and Studio
- ✅ GitHub Actions workflow that runs lint/type/test gates for Python + TypeScript workspaces and publishes Monte Carlo tolerance artefacts
- 🛠️ Extended FastAPI gateway, optimisation stack, and FEM/BEM solvers under development

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

   Monte Carlo tolerance sweeps are available via `POST /simulate/sealed/tolerances` and `/simulate/vented/tolerances` for quick manufacturing risk snapshots.

## Quality checks

Run the consolidated automation from the repo root:

```bash
pnpm lint        # eslint for the web workspace + ruff for python modules
pnpm typecheck   # tsconfig builds + mypy over python/services
pnpm py:test     # Python unit tests
pnpm py:tolerance # writes JSON reports into ./tolerance-snapshots
pnpm py:schemas  # writes solver request/response schemas into ./schema-exports
pnpm py:compare -- path/to/measurement.dat --alignment sealed
```

The tolerance helper accepts additional options (`--iterations`, `--seed`, `--vented-iterations`, etc.). Pass them after `--` when using the pnpm script, for example `pnpm py:tolerance -- --iterations 256`.

## Workspace Layout
```
packages/
  web-ui/      # Vite + React Three Fiber Studio shell + live optimization HUD
  dev-mocks/   # Mock API + typed WebSocket server for local development
```

Additional services (gateway, simulation core, CLI) will be added following the blueprint in `docs/architecture.md`.

## Next Steps
- Close out the multi-resolution optimisation ladder by wiring differential evolution search and adjoint refinement into the persisted run workflow.
- Automate reruns leveraging the calibration overrides so measurement comparisons can trigger corrected solver batches without manual tweaking.
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

The command prints a human-readable summary by default; pass `--json` for machine-readable output. Optional flags mirror the gateway defaults so Studio results and CLI analyses stay aligned.

Diagnosis output highlights systematic biases: low/mid/high-band SPL offsets, suggested global level trims, tuning shifts with estimated port-length adjustments, leakage hints, and a note stack summarising the most actionable insights. Calibration payloads provide Bayesian posteriors with 95 % credible intervals for the recommended level trims, port length scaling, and leakage-Q multipliers.
