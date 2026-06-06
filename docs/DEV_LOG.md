# Development Log

## 2026-05-26
- Phase 1 verified: API upload endpoint, SQLite tasks table, and WebSocket queue skeleton.
- Added health check route and richer validation errors for task creation.
- Added per-task logs.txt writing and worker progress logging.
- Phase 2 wiring: TripoSR placeholder worker and subprocess invocation for single-image tasks.
- Added structured worker progress events and multi-image COLMAP+3DGS placeholder routing.
- Added image-only upload validation to avoid non-image task failures.
- Added COLMAP/3DGS command hooks and safe output download endpoint.
- Added React + Vite + R3F frontend scaffold with upload + preview flow.
- Added task listing API and frontend recent task selector.
- Added pipeline setup guide and local wrapper scripts for COLMAP/3DGS.
- Added setup scripts for TripoSR/COLMAP/3DGS and third_party placeholders.
- Added TripoSR CLI wrapper for run.py integration.

## 2026-06-06
- Verified Milestone 0/1 smoke checks: upload validation, pipeline registry, and unified worker entry.
- Added task log API, output list API, per-output download API, and retry API for local task debugging.
- Added startup recovery that marks leftover Pending/Running tasks as Interrupted after server restart.
- Added frontend task observability: error display, logs panel, multi-output download list, and retry action.
- Added task observability smoke coverage for log reading, output listing, path traversal rejection, and interrupted task marking.
- Verification: backend API, upload validation, pipeline registry, worker entry, and task observability smoke checks passed in `.venv`.
- Added unified frontend preview selection from `/outputs`, GLB/PLY preview routing, PLY point-cloud rendering, and preview failure fallback.
- Added output asset smoke coverage for `.glb`, `.ply`, and `.splat` output discovery.
- Added frontend dependency lockfile and ignored local `node_modules`/`dist` artifacts.
- Verification: backend API, upload validation, pipeline registry, worker entry, task observability, output asset smoke checks, and frontend `npm run build` passed.
- Current environment note: `npm audit` reports 2 moderate dev-server advisories through Vite/esbuild; production dependency audit with `--omit=dev` is clean, and the available fix requires a breaking Vite upgrade.
- Added task cancellation for Pending/Running jobs, including API cancellation, worker cancel checks, running subprocess termination, retry protection during cancellation cleanup, and frontend cancel action.
- Added cancellation smoke coverage for active task termination and API conflict behavior.
- Verification: backend API, upload validation, pipeline registry, worker entry, task observability, output asset, task cancel smoke checks, and frontend `npm run build` passed.
- Added pipeline diagnostics API and frontend System panel for task root, upload limits, pipeline readiness, configured environment variables, output types, and dependency paths.
- Added diagnostics smoke coverage to verify pipeline registration and avoid leaking environment variable values.
- Verification: backend API, pipeline diagnostics, upload validation, pipeline registry, worker entry, task observability, output asset, task cancel smoke checks, and frontend `npm run build` passed.
