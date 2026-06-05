# Pipeline Setup Guide

This project ships in-repository pipeline implementations for TripoSR, COLMAP, and 3DGS. The control plane runs them through `backend/workers/run_pipeline.py`, and each pipeline can call third-party code through environment variables when the real CUDA dependencies are installed.

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

The backend will append `input_path` and `output_path` to `TRIPOSR_CMD`. This command is called from `backend/pipelines/triposr/pipeline.py`.

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

The pipeline creates `database.db` and outputs `cameras.txt`, `images.txt`, and `points3D.txt` under `data/tasks/{id}/interim/colmap/sparse`.

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

The in-repository pipeline currently standardizes two output targets for multi-image tasks:

- `point_cloud.ply`
- `scene.splat`

## 4) Repository setup

After cloning the repository, initialize third-party dependencies:

```
git submodule update --init --recursive
```

## 5) Environment file

Add these to `backend/.env` (see `backend/.env.example`).

Key local settings:

```
TASKS_ROOT=./data/tasks
MAX_UPLOAD_FILES=8
MAX_IMAGE_PIXELS=2073600
MAX_IMAGE_LONG_EDGE=1920
```

`TASKS_ROOT` may be absolute or relative to the repository root. It controls where generated task artifacts are stored. The backend validates that this directory is writable on startup.

Upload validation currently accepts `.png`, `.jpg`, `.jpeg`, and `.webp` images. A task can upload at most 8 images, and each image must fit within the 1080p limit.

## 6) Pipeline extension point

New reconstruction or inference methods should be added under `backend/pipelines/{method}/pipeline.py` and registered in `backend/pipelines/registry.py`.

Each pipeline implements:

- `supports(image_count, mode)`
- `run(context)`

The shared worker entry point is:

```
python backend/workers/run_pipeline.py --pipeline triposr --task-id demo --input-dir ... --interim-dir ... --output-dir ... --logs-path ...
```
