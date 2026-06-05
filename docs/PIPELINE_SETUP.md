# Pipeline Setup Guide

This project ships wrapper workers that can call real TripoSR, COLMAP, and 3DGS pipelines. You need to install those dependencies locally and set environment variables to enable them.

## 1) TripoSR

Required:
- A TripoSR inference entry point you can call from CLI.
- Optional: `rembg` for background removal.

Recommended setup:
1. Create a conda env for TripoSR.
2. Install TripoSR and its dependencies in that env.
3. Set environment variables for the backend:

Quick start (Windows PowerShell):
```
scripts/setup_triposr.ps1
```

```
TRIPOSR_PY=C:/path/to/triposr/env/python.exe
TRIPOSR_CMD=python backend/workers/triposr_infer.py
TRIPOSR_REPO=third_party/TripoSR
TRIPOSR_DEVICE=cuda:0
USE_REMBG=1
```

The backend will append `input_path` and `output_path` to `TRIPOSR_CMD`.

## 2) COLMAP

Required:
- COLMAP installed and accessible (either on PATH or via `COLMAP_BIN`).

Recommended setup:
1. Install COLMAP on the system (or in a dedicated conda env).
2. Set:

Quick start (Windows PowerShell):
```
scripts/setup_colmap.ps1
```

```
COLMAP_CMD=python backend/workers/colmap_pipeline.py
COLMAP_BIN=colmap
```

The wrapper creates `database.db` and outputs `cameras.txt`, `images.txt`, and `points3D.txt` under `data/tasks/{id}/interim/colmap/sparse`.

## 3) 3DGS

Required:
- A working 3DGS training script.

Recommended setup:
1. Install the 3DGS repo in its own env.
2. Set:

Quick start (Windows PowerShell):
```
scripts/setup_3dgs.ps1
```

```
DGS_CMD=python backend/workers/gsplat_pipeline.py
DGS_TRAIN_SCRIPT=path/to/train.py
```

The wrapper expects the training script to accept `--interim-dir`, `--output-dir`, and `--iterations`.

## 4) Environment file

Add these to `backend/.env` (see `backend/.env.example`).
