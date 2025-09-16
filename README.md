# Bagger-SPL

A focused loudspeaker enclosure co-design platform blending physics-based simulation, optimization, and modern developer tooling.

## Repository Status
- ✅ Architecture blueprint captured in [`docs/architecture.md`](docs/architecture.md)
- ✅ Delivery roadmap captured in [`docs/delivery-plan.md`](docs/delivery-plan.md)
- ✅ Frontend + mock backend scaffolding bootstrapped with pnpm workspaces
- ✅ Solver telemetry HUD with typed WebSocket protocol + GPU.js pressure renderer
- ✅ Analytical sealed + vented-box solvers with FastAPI endpoints (see [`spl_core`](python/spl_core) and [`services/gateway`](services/gateway))
- ✅ Alignment summary metrics (-3 dB bandwidth, velocity peaks) exposed alongside solver responses
- ✅ JSON schema exports for solver request/response contracts (see [`spl_core/serialization.py`](python/spl_core/serialization.py))
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
2. In one terminal start the mock backend & WebSocket feed
   ```bash
   pnpm --filter @motosub/dev-mocks dev
   ```
3. In another terminal launch the Studio web client
   ```bash
   pnpm --filter @motosub/web-ui dev
   ```
4. Open http://localhost:5173 to view the demo enclosure renderer streaming synthetic optimization telemetry.

## Workspace Layout
```
packages/
  web-ui/      # Vite + React Three Fiber Studio shell + live optimization HUD
  dev-mocks/   # Mock API + typed WebSocket server for local development
```

Additional services (gateway, simulation core, CLI) will be added following the blueprint in `docs/architecture.md`.

## Next Steps
- Grow the Python simulation core beyond first-order alignments (excursion limits, tolerance analysis)
- Promote the FastAPI gateway stub into a production-ready service with persistence and WebSocket telemetry
- Expand the Studio telemetry panels (SPL, impedance, constraint ledger)
- Wire Playwright/Vitest automation once backend contracts stabilize

## Python Simulation Core

The analytical sealed- and vented-box solvers live in the [`spl_core`](python/spl_core) package
and are exposed via a lightweight FastAPI gateway stub in
[`services/gateway`](services/gateway). Run the Python unit tests with:

```bash
python -m unittest discover -s python/tests
```

Contributions and feedback are welcome as we grow Bagger-SPL toward an offline-first yet cloud-capable toolchain.
