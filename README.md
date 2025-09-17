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
- ✅ Python linting and type-checking automation wired into the pnpm workspace scripts
- ✅ FastAPI optimisation run API with SQLite-backed persistence and background solver tasks
- ✅ Run history API with status aggregates powering the Studio timeline panel and alignment toggles
- ✅ Monte Carlo tolerance analysis surfaced through new sealed/vented endpoints for manufacturing risk estimates
- ✅ Studio tolerance panel streaming Monte Carlo excursion/velocity risk snapshots from the gateway
- ✅ Measurement ingestion scaffolding with Klippel/REW parsers and FastAPI comparison endpoints for SPL/impedance deltas
- ✅ Studio measurement panel that previews uploads or synthesised traces and compares SPL/impedance deltas against solver predictions
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
- Extend the measurement ingestion scaffolding into Bayesian calibration so the new comparison panel can close the solver feedback loop automatically.
- Extend the FastAPI gateway with export/download and measurement upload endpoints, and surface the richer traces through Studio SPL/impedance charts.
- Wire the tolerance artefacts into dashboards (e.g. Grafana panels or Studio overlays) so CI snapshots drive proactive manufacturing risk monitoring.

## Python Simulation Core

The analytical sealed- and vented-box solvers live in the [`spl_core`](python/spl_core) package
and are exposed via a lightweight FastAPI gateway stub in
[`services/gateway`](services/gateway). Run the Python unit tests with:

```bash
python -m unittest discover -s python/tests
```

Contributions and feedback are welcome as we grow Bagger-SPL toward an offline-first yet cloud-capable toolchain.
