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
