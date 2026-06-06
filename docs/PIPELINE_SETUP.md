# Pipeline Setup Guide

This project currently enables TripoSR and VGGT. COLMAP and 3DGS wrappers remain in the repository for follow-up development, but they are not registered in the runtime pipeline list until their real paths are stable.

## 1) TripoSR

Required:
- A TripoSR inference entry point you can call from CLI.
- Optional: `rembg` for background removal.
- CUDA-capable PyTorch in the TripoSR environment.

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

If `TRIPOSR_CMD` is not set, the TripoSR pipeline defaults to the in-repository wrapper:

```
python backend/workers/triposr_infer.py
```

For local placeholder-only smoke tests, set:

```
TRIPOSR_ALLOW_PLACEHOLDER=1
```

Windows notes:

- `torchmcubes` may fail to build without Visual Studio C++ build tools. The project provides a local compatibility module at `backend/compat/torchmcubes.py`, and `backend/workers/triposr_infer.py` injects it through `PYTHONPATH`.
- `trimesh==4.0.5` is not compatible with NumPy 2.x for GLB export. Use `numpy<2` in `tripo_env`.

Verified smoke command:

```
conda run -n tripo_env python scripts/smoke_triposr_real.py
```

Verified control-plane smoke command:

```
$env:TRIPOSR_PY="E:/conda/workspace/envs/tripo_env/python.exe"
.\.venv\Scripts\python.exe scripts\smoke_triposr_control_plane_real.py
```

This runs the FastAPI control-plane queue in the backend environment while executing real TripoSR inference in `tripo_env` through `TRIPOSR_PY`. It verifies that a task reaches `Completed` and writes a non-empty `output.glb` through the same worker path used by the app.

## 2) VGGT

VGGT is the default multi-image route. The backend runs the control-plane worker in `.venv`, then delegates model inference to the Python executable configured by `VGGT_PY`.

Required:
- A working VGGT checkout.
- Local VGGT checkpoint weights.
- CUDA-capable PyTorch in the `vggt` conda environment.

Verified local command:

```
conda run -n vggt python run_local_vggt_pointcloud.py --image_folder examples\kitchen\images --checkpoint model_pretrained_weight\model.pt --output_dir outputs\local_vggt_pointcloud --max_images 3 --conf_percentile 70 --source depth
```

Preview generation command:

```
conda run -n vggt python preview_ply_views.py outputs\local_vggt_pointcloud\pointcloud_depth_3imgs_p70.ply
```

Backend environment variables:

```
MULTI_IMAGE_PIPELINE=vggt
VGGT_PY=E:/conda/workspace/envs/vggt/python.exe
VGGT_REPO=E:/vscode/workspace/vggt
VGGT_CHECKPOINT=E:/vscode/workspace/vggt/model_pretrained_weight/model.pt
VGGT_MAX_IMAGES=3
VGGT_CONF_PERCENTILE=70
VGGT_SOURCE=depth
VGGT_PREPROCESS_MODE=crop
VGGT_PREVIEW=1
```

Control-plane real smoke command:

```
.\.venv\Scripts\python.exe scripts\smoke_vggt_control_plane_real.py
```

The smoke creates a temporary task, copies three kitchen images from the VGGT checkout, runs the same queue path used by the app, and verifies a real `.ply`, `predictions.npz`, and three preview `.png` files.

## 3) Disabled Follow-Up Pipelines

COLMAP and 3DGS are temporarily disabled in `backend/pipelines/registry.py`. They should stay hidden from `/api/pipelines` and unreachable from task routing while validating the currently implemented TripoSR and VGGT paths.

### COLMAP

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

The intended pipeline creates `database.db` and outputs `cameras.txt`, `images.txt`, and `points3D.txt` under `data/tasks/{id}/interim/colmap/sparse`.

### 3DGS

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

The wrapper expects the training script to accept `--interim-dir`, `--output-dir`, and `--iterations`. The intended output targets are:

- `point_cloud.ply`
- `scene.splat`

## 4) Multi-image route selection

By default, multi-image uploads run VGGT and complete with `.ply`, `.npz`, and preview `.png` outputs.

`MULTI_IMAGE_PIPELINE=vggt` is currently the only supported runtime value.

## 5) Repository setup

After cloning the repository, initialize third-party dependencies:

```
git submodule update --init --recursive
```

## 6) Environment file

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

## 7) Pipeline extension point

New reconstruction or inference methods should be added under `backend/pipelines/{method}/pipeline.py` and registered in `backend/pipelines/registry.py`.

Each pipeline implements:

- `supports(image_count, mode)`
- `run(context)`

The shared worker entry point is:

```
python backend/workers/run_pipeline.py --pipeline triposr --task-id demo --input-dir ... --interim-dir ... --output-dir ... --logs-path ...
```

## 8) Environment audit

Use this local audit before running real pipeline tests:

```
.\.venv\Scripts\python.exe scripts/audit_pipeline_env.py
```

The audit reports TripoSR, VGGT, COLMAP, and 3DGS environment status. TripoSR and VGGT are expected to have CUDA-capable PyTorch. COLMAP and 3DGS remain useful as environment diagnostics, but they are not enabled runtime pipelines yet.
