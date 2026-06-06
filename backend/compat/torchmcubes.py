from __future__ import annotations

import numpy as np
import torch
from skimage import measure


def marching_cubes(level: torch.Tensor, threshold: float) -> tuple[torch.Tensor, torch.Tensor]:
    volume = level.detach().cpu().numpy().astype(np.float32)
    vertices, faces, _, _ = measure.marching_cubes(volume, level=threshold)
    vertices_tensor = torch.from_numpy(vertices.astype(np.float32))
    faces_tensor = torch.from_numpy(faces.astype(np.int64))
    return vertices_tensor, faces_tensor
