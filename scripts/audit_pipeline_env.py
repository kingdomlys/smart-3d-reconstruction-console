from __future__ import annotations

import shutil
import subprocess
import sys
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


def audit_colmap() -> dict[str, object]:
    colmap_path = shutil.which("colmap")
    rc, output = run_command(["conda", "run", "-n", "colmap_env", "python", "-c", "import shutil; print(shutil.which('colmap'))"])
    path_detail = output.strip() if output.strip() else colmap_path
    rc_help, help_output = run_command(["conda", "run", "-n", "colmap_env", "colmap", "--help"], timeout=30)
    return {
        "name": "COLMAP",
        "ok": rc_help == 0,
        "return_code": rc_help,
        "details": f"path={path_detail}\n{help_output}",
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
    audits = [audit_triposr(), audit_colmap(), audit_3dgs()]
    for item in audits:
        status = "OK" if item["ok"] else "NEEDS_ATTENTION"
        print(f"## {item['name']}: {status} (rc={item['return_code']})")
        print(item["details"] or "-")
        print()

    if not audits[0]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
