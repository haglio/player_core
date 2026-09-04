"""Builds the .rhcache files the reader tests read.

The clip player only ever reads this format -- Evolver and Origenerator write
the real ones into the clips folder -- so the writer is fixture code and lives
here, next to the tests that need one.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


def write_rhcache(
    frames: list[np.ndarray],
    output_path: Path,
    *,
    source_name: str = "",
    quality: int = 95,
    lossless: bool = False,
) -> None:
    if not frames:
        raise ValueError("frames list is empty")

    height, width = frames[0].shape[:2]
    meta = {
        "width": width,
        "height": height,
        "frame_count": len(frames),
        "source": source_name,
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("meta.json", json.dumps(meta))
        for i, frame in enumerate(frames):
            encoded = io.BytesIO()
            Image.fromarray(frame, "RGB").save(
                encoded, format="WEBP", lossless=lossless, quality=quality)
            zf.writestr(f"frames/{i:06d}.webp", encoded.getvalue())
