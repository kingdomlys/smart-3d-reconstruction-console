from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db


def write_fake_vggt_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "model_pretrained_weight").mkdir(parents=True, exist_ok=True)
    (repo_root / "model_pretrained_weight" / "model.pt").write_text("fake checkpoint", encoding="utf-8")
    (repo_root / "run_local_vggt_pointcloud.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import argparse",
                "from pathlib import Path",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--image_folder', required=True)",
                "parser.add_argument('--checkpoint', required=True)",
                "parser.add_argument('--output_dir', required=True)",
                "parser.add_argument('--max_images', default='3')",
                "parser.add_argument('--conf_percentile', default='70')",
                "parser.add_argument('--source', default='depth')",
                "parser.add_argument('--preprocess_mode', default='crop')",
                "args = parser.parse_args()",
                "output_dir = Path(args.output_dir)",
                "output_dir.mkdir(parents=True, exist_ok=True)",
                "ply = output_dir / f'pointcloud_{args.source}_{args.max_images}imgs_p{args.conf_percentile}.ply'",
                "ply.write_text('\\n'.join([",
                "    'ply',",
                "    'format ascii 1.0',",
                "    'element vertex 3',",
                "    'property float x',",
                "    'property float y',",
                "    'property float z',",
                "    'property uchar red',",
                "    'property uchar green',",
                "    'property uchar blue',",
                "    'end_header',",
                "    '0 0 0 255 0 0',",
                "    '1 0 0 0 255 0',",
                "    '0 1 0 0 0 255',",
                "]) + '\\n', encoding='ascii')",
                "(output_dir / 'predictions.npz').write_bytes(b'fake npz')",
                "print(f'PLY: {ply}')",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "preview_ply_views.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import argparse",
                "from pathlib import Path",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('ply')",
                "parser.add_argument('--output_dir', default=None)",
                "args = parser.parse_args()",
                "ply = Path(args.ply)",
                "output_dir = Path(args.output_dir) if args.output_dir else ply.parent",
                "output_dir.mkdir(parents=True, exist_ok=True)",
                "for name in ('front_xy', 'side_zy', 'top_xz'):",
                "    path = output_dir / f'{ply.stem}_{name}.png'",
                "    path.write_bytes(b'fake png')",
                "    print(path)",
            ]
        ),
        encoding="utf-8",
    )


async def main_async() -> None:
    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"
        fake_repo = tmp_root / "fake_vggt"
        write_fake_vggt_repo(fake_repo)

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["VGGT_REPO"] = str(fake_repo)
        os.environ["VGGT_CHECKPOINT"] = str(fake_repo / "model_pretrained_weight" / "model.pt")
        os.environ["VGGT_PY"] = sys.executable
        os.environ["VGGT_MAX_IMAGES"] = "3"
        os.environ["VGGT_CONF_PERCENTILE"] = "70"
        os.environ["VGGT_SOURCE"] = "depth"
        os.environ["VGGT_PREVIEW"] = "1"
        os.environ["MULTI_IMAGE_PIPELINE"] = "vggt"
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-vggt-route"
        db.create_task(task_id, mode="fast", image_count=3)
        dirs = storage_module.ensure_task_dirs(task_id)
        for index in range(3):
            (Path(dirs["inputs_dir"]) / f"{index:02d}.png").write_bytes(b"fake image")

        worker_task = asyncio.create_task(task_worker())
        try:
            await TASK_QUEUE.enqueue(task_id)
            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=30)

            task = db.get_task(task_id)
            assert task and task["status"] == "Completed", task
            output_path = Path(task["output_path"])
            assert output_path.suffix.lower() == ".ply", output_path
            assert output_path.exists(), output_path

            outputs = storage_module.list_output_files(task_id)
            output_types = {item["type"] for item in outputs}
            assert {"ply", "npz", "png"}.issubset(output_types), outputs
            assert sum(1 for item in outputs if item["type"] == "png") == 3, outputs

            logs = storage_module.read_task_log(task_id)
            assert "[vggt]" in logs
            assert "Task completed" in logs
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("vggt route smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
