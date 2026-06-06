# Pipeline Setup Guide

This project currently enables TripoSR, VGGT, and COLMAP. 3DGS remains in the repository for follow-up development, but it is not registered in the runtime pipeline list until its real training path is stable.

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

VGGT is the default multi-image route and can also be selected for single-image reconstruction. The backend runs the control-plane worker in `.venv`, then delegates model inference to the Python executable configured by `VGGT_PY`.

Required:
- A working VGGT checkout.
- Local VGGT checkpoint weights.
- CUDA-capable PyTorch in the `vggt` conda environment.

Verified local command:

```
conda run -n vggt python run_local_vggt_pointcloud.py --image_folder examples\kitchen\images --checkpoint model_pretrained_weight\model.pt --output_dir outputs\local_vggt_pointcloud --max_images 16 --conf_percentile 70 --source depth
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
VGGT_MAX_IMAGES=16
VGGT_CONF_PERCENTILE=70
VGGT_SOURCE=depth
VGGT_PREPROCESS_MODE=crop
VGGT_PREVIEW=1
```

Control-plane real smoke command:

```
.\.venv\Scripts\python.exe scripts\smoke_vggt_control_plane_real.py
```

The smoke creates a temporary task, copies sixteen kitchen images from the VGGT checkout, runs the same queue path used by the app, and verifies a real `.ply`, `predictions.npz`, and three preview `.png` files.

## 3) COLMAP

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
COLMAP_BIN=E:/vscode/workspace/colmap/colmap-x64-windows-cuda/bin/colmap.exe
```

The `COLMAP Sparse` pipeline runs feature extraction, exhaustive matching, sparse mapping, and text model conversion. It writes the working artifacts under `data/tasks/{id}/interim/colmap` and exposes these outputs for download:

- `colmap/sparse.ply`
- `colmap/database.db`
- `colmap/summary.json`
- `colmap/sparse_txt/cameras.txt`
- `colmap/sparse_txt/images.txt`
- `colmap/sparse_txt/points3D.txt`
- raw sparse `.bin` model files under `colmap/sparse`

`colmap/sparse.ply` is the previewable sparse point cloud exported from the mapper output and is used as the primary task output for `COLMAP Sparse`.

The optional `COLMAP Dense` pipeline is registered separately as `colmap_dense`. It keeps the sparse route intact, then continues with COLMAP image undistortion, PatchMatch stereo, and stereo fusion. Its primary preview output is:

- `colmap_dense/dense/fused.ply`

It also exposes the sparse intermediate outputs under `colmap_dense/`, including `colmap_dense/sparse.ply`, `colmap_dense/summary.json`, and `colmap_dense/sparse_txt/*.txt`.

Sparse reconstruction keeps only triangulated feature tracks that COLMAP can match across views. A sparse PLY can therefore look dispersed or incomplete even when COLMAP succeeded. Dense reconstruction is the later multi-view-stereo stage that estimates many more surface points and writes `fused.ply`.

COLMAP requires images from the same static scene or object with enough overlap, stable lighting, visible texture, and moderate viewpoint changes. If images are unrelated, too sparse, blurred, reflective, mostly background, or taken from very large viewpoint jumps, sparse reconstruction can fail with `no_initial_pair` or `bad_initial_pair`. In that case, COLMAP ran correctly but could not initialize geometry from the inputs.

COLMAP upload budget defaults are designed for an 8 GB VRAM target:

```
COLMAP_MAX_UPLOAD_FILES=32
COLMAP_MAX_TOTAL_IMAGE_PIXELS=29491200
COLMAP_MAX_IMAGE_PIXELS=2073600
COLMAP_MAX_IMAGE_LONG_EDGE=1920
COLMAP_TARGET_VRAM_GB=8
```

The default total-pixel budget is `32 * 1280 * 720`, so 32 small images are accepted while 32 full 1080p images are rejected unless the budget is explicitly raised. COLMAP memory use also depends on detected features, image texture, GPU SIFT settings, and exhaustive matching pairs, so `COLMAP_MAX_NUM_FEATURES` remains an important cap.

Dense defaults are more conservative because PatchMatch stereo uses more GPU memory than sparse feature extraction:

```
COLMAP_DENSE_MAX_UPLOAD_FILES=16
COLMAP_DENSE_MAX_TOTAL_IMAGE_PIXELS=14745600
COLMAP_DENSE_MAX_IMAGE_PIXELS=2073600
COLMAP_DENSE_MAX_IMAGE_LONG_EDGE=1920
COLMAP_DENSE_TARGET_VRAM_GB=8
COLMAP_DENSE_MAX_IMAGE_SIZE=1600
COLMAP_DENSE_GEOM_CONSISTENCY=1
COLMAP_DENSE_FUSION_INPUT_TYPE=geometric
```

`COLMAP_DENSE_MAX_IMAGE_SIZE` is passed to `image_undistorter --max_image_size` and is the main quality/memory knob for dense reconstruction.

Tunable defaults:

```
COLMAP_MAX_NUM_FEATURES=16384
COLMAP_ESTIMATE_AFFINE_SHAPE=1
COLMAP_DOMAIN_SIZE_POOLING=1
COLMAP_INIT_MIN_NUM_INLIERS=15
COLMAP_INIT_MAX_ERROR=12
COLMAP_INIT_MIN_TRI_ANGLE=1
COLMAP_ABS_POSE_MIN_NUM_INLIERS=8
COLMAP_ABS_POSE_MAX_ERROR=24
```

Control-plane real smoke command:

```
.\.venv\Scripts\python.exe scripts\smoke_colmap_control_plane_real.py
```

To run COLMAP instead of VGGT for a multi-image task, set:

```
MULTI_IMAGE_PIPELINE=colmap
```

The frontend can also explicitly select `COLMAP Sparse` or `COLMAP Dense` per task. The default multi-image route remains VGGT.

## 4) Disabled Follow-Up Pipeline

3DGS is temporarily disabled in `backend/pipelines/registry.py`. It should stay hidden from `/api/pipelines` and unreachable from task routing while its real training path is still pending.

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

## 5) Multi-image route selection

By default, single-image uploads run TripoSR and multi-image uploads run VGGT. The frontend can override the default with a compatible pipeline choice:

Supported runtime values:

- `vggt`
- `colmap`
- `colmap_dense`

Compatibility:

- TripoSR: single image
- VGGT: one or more images
- COLMAP Sparse: multiple images
- COLMAP Dense: multiple images

## 6) Repository setup

After cloning the repository, initialize third-party dependencies:

```
git submodule update --init --recursive
```

## 7) Environment file

Add these to `backend/.env` (see `backend/.env.example`).

Key local settings:

```
TASKS_ROOT=./data/tasks
MAX_UPLOAD_FILES=16
MAX_IMAGE_PIXELS=2073600
MAX_IMAGE_LONG_EDGE=1920
COLMAP_MAX_UPLOAD_FILES=32
COLMAP_MAX_TOTAL_IMAGE_PIXELS=29491200
COLMAP_DENSE_MAX_UPLOAD_FILES=16
COLMAP_DENSE_MAX_TOTAL_IMAGE_PIXELS=14745600
COLMAP_DENSE_MAX_IMAGE_SIZE=1600
```

`TASKS_ROOT` may be absolute or relative to the repository root. It controls where generated task artifacts are stored. The backend validates that this directory is writable on startup.

Upload validation currently accepts `.png`, `.jpg`, `.jpeg`, and `.webp` images. Default multi-image VGGT tasks can upload at most 16 images. Explicit COLMAP Sparse tasks can upload up to 32 images, while COLMAP Dense defaults to 16 images; both COLMAP routes must also fit their total-pixel budgets.

## 8) Pipeline extension point

New reconstruction or inference methods should be added under `backend/pipelines/{method}/pipeline.py` and registered in `backend/pipelines/registry.py`.

Each pipeline implements:

- `supports(image_count, mode)`
- `run(context)`

The shared worker entry point is:

```
python backend/workers/run_pipeline.py --pipeline triposr --task-id demo --input-dir ... --interim-dir ... --output-dir ... --logs-path ...
```

## 9) Environment audit

Use this local audit before running real pipeline tests:

```
.\.venv\Scripts\python.exe scripts/audit_pipeline_env.py
```

The audit reports TripoSR, VGGT, COLMAP, and 3DGS environment status. TripoSR and VGGT are expected to have CUDA-capable PyTorch. COLMAP is expected to run from the local CUDA Windows build. 3DGS remains useful as an environment diagnostic, but it is not an enabled runtime pipeline yet.
