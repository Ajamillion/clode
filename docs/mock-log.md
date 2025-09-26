# Development Mock Log

A consolidated catalog of the synthetic APIs and WebSocket feeds exposed by the
`@bagger/dev-mocks` server. Use this as a quick reference when wiring the
Studio client, integration tests, or CLI tooling against the local mocks.

_Last updated: 2025-09-19_

## HTTP endpoints

| Method | Path | Description | Sample payload |
| --- | --- | --- | --- |
| POST | `/api/opt/start` | Queue a synthetic optimisation run and receive the run record | `{ "id": "…", "status": "queued", "params": { … } }` |
| GET | `/api/opt/runs?limit=20&status=running` | Paginated optimisation run history filtered by status | `{ "runs": [{ "id": "…", "status": "running", "result": { "history": […] } }] }` |
| GET | `/api/opt/stats` | Aggregate run counts grouped by queue status | `{ "counts": { "queued": 1, "running": 2, … }, "total": 6 }` |
| GET | `/api/opt/{id}` | Retrieve the latest state for a specific run | `{ "id": "…", "status": "succeeded", "result": { "convergence": { … } } }` |
| GET | `/api/schemas/solvers` | List the sealed and vented solver schema summaries | `{ "solvers": { "sealed": { "request": { … } } } }` |
| GET | `/api/schemas/solvers/{alignment}` | Fetch the schema pair for the requested alignment | `{ "alignment": "sealed", "request": { … }, "response": { … } }` |
| POST | `/api/measurements/preview` | Generate a synthetic measurement preview when uploads are disabled | `{ "measurement": { "frequency_hz": […], "spl_db": […] } }` |
| POST | `/api/measurements/sealed/compare` | Compare a sealed-box prediction against a supplied measurement trace | `{ "summary": { … }, "prediction": { … }, "delta": { … }, "stats": { … } }` |
| POST | `/api/measurements/vented/compare` | Compare a vented-box prediction against a supplied measurement trace | `{ "summary": { … }, "prediction": { … }, "delta": { … }, "stats": { … } }` |
| GET | `/api/mock-log` | Return this catalog as JSON for programmatic access | `{ "version": "2025.09", "http": […], "websocket": […] }` |

## WebSocket broadcast events

All WebSocket messages are msgpack encoded. The mock server automatically
reconnects clients and replays updates for every connected socket.

| Type | Description | Key fields |
| --- | --- | --- |
| `ITERATION` | Per-iteration optimisation metrics emitted ~6 Hz | `iter`, `loss`, `gradNorm`, `topology`, `timestamp`, `metrics` |
| `TOPOLOGY_SWITCH` | Signals that the optimisation pivoted to a new topology | `from`, `to` |
| `CONSTRAINT_VIOLATION` | Highlights simulated manufacturing or physics constraint pressure | `constraint`, `severity`, `location` |
| `CONVERGENCE` | Final convergence summary once the synthetic run completes | `converged`, `finalLoss`, `iterations`, `cpuTime`, `solution` |

## Usage notes

- Start the server with `pnpm --filter @bagger/dev-mocks dev` (see the
  [`README`](../README.md#getting-started) for the full workflow).
- The mocks intentionally return slowly drifting metrics so charts and run
  histories visibly update during demos.
- The `/api/mock-log` endpoint mirrors this document to keep docs and runtime
  behaviour aligned. Use it in automated tests to assert endpoint availability
  without hard-coding the list.
