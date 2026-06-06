from __future__ import annotations

import shutil
import subprocess
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, f"Timed out: {exc}"
    return result.returncode, "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def conda_python(env_name: str, code: str) -> tuple[int, str]:
    return run_command(["conda", "run", "-n", env_name, "python", "-c", code], timeout=120)


def audit_triposr() -> dict[str, object]:
    code = (
        "import torch, trimesh, numpy; "
        "print('torch=' + torch.__version__); "
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('torch_cuda=' + str(torch.version.cuda)); "
        "print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')); "
        "print('trimesh=' + trimesh.__version__); "
        "print('numpy=' + numpy.__version__)"
    )
    rc, output = conda_python("tripo_env", code)
    return {
        "name": "TripoSR",
        "ok": rc == 0 and "cuda=True" in output,
        "return_code": rc,
        "details": output,
    }


def audit_vggt() -> dict[str, object]:
    code = (
        "from pathlib import Path; "
        "import torch; "
        "repo=Path(r'E:/vscode/workspace/vggt'); "
        "checkpoint=repo/'model_pretrained_weight'/'model.pt'; "
        "runner=repo/'run_local_vggt_pointcloud.py'; "
        "preview=repo/'preview_ply_views.py'; "
        "print('torch=' + torch.__version__); "
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('torch_cuda=' + str(torch.version.cuda)); "
        "print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')); "
        "print('repo_exists=' + str(repo.exists())); "
        "print('runner_exists=' + str(runner.exists())); "
        "print('preview_exists=' + str(preview.exists())); "
        "print('checkpoint_exists=' + str(checkpoint.exists()))"
    )
    rc, output = conda_python("vggt", code)
    ok = (
        rc == 0
        and "cuda=True" in output
        and "runner_exists=True" in output
        and "preview_exists=True" in output
        and "checkpoint_exists=True" in output
    )
    return {
        "name": "VGGT",
        "ok": ok,
        "return_code": rc,
        "details": output,
    }


def audit_colmap() -> dict[str, object]:
    default_colmap = REPO_ROOT.parent / "colmap" / "colmap-x64-windows-cuda" / "bin" / "colmap.exe"
    colmap_path = Path(os.getenv("COLMAP_BIN", str(default_colmap))).resolve()
    if not colmap_path.exists():
        fallback = shutil.which("colmap")
        if fallback:
            colmap_path = Path(fallback)
    rc_help, help_output = run_command([str(colmap_path), "--help"], timeout=30)
    return {
        "name": "COLMAP",
        "ok": rc_help == 0,
        "return_code": rc_help,
        "details": f"path={colmap_path}\n{help_output}",
    }


def audit_3dgs() -> dict[str, object]:
    code = (
        "import importlib.util; "
        "print('torch_spec=' + str(importlib.util.find_spec('torch'))); "
        "print('diff_gaussian_rasterization_spec=' + str(importlib.util.find_spec('diff_gaussian_rasterization'))); "
        "print('simple_knn_spec=' + str(importlib.util.find_spec('simple_knn')))"
    )
    rc, output = conda_python("gs_env", code)
    ok = rc == 0 and "torch_spec=None" not in output and "diff_gaussian_rasterization_spec=None" not in output
    return {
        "name": "3DGS",
        "ok": ok,
        "return_code": rc,
        "details": output,
    }


def main() -> int:
    audits = [audit_triposr(), audit_vggt(), audit_colmap(), audit_3dgs()]
    for item in audits:
        status = "OK" if item["ok"] else "NEEDS_ATTENTION"
        print(f"## {item['name']}: {status} (rc={item['return_code']})")
        print(item["details"] or "-")
        print()

    if not audits[0]["ok"] or not audits[1]["ok"] or not audits[2]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
