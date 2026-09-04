"""A clip's frames, as RGB arrays: off its frame cache when it has one, else
decoded with ffmpeg.

The ``.rhcache`` beside a clip is a zip of WebP frames with a ``meta.json``,
written by the tools that cut the clip; Genau only ever reads it.  A clip with
no cache is decoded whole, every frame of it, because Genau scrubs rather than
plays and has to be able to show any frame at any moment.
"""
from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from app_support.subprocess_utils import hidden_subprocess_kwargs
from PIL import Image


def ffprobe_size(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True, **hidden_subprocess_kwargs()).strip()
    width, height = out.split("x", 1)
    return int(width), int(height)


def decode_video_to_numpy_frames(path: Path) -> list[np.ndarray]:
    width, height = ffprobe_size(path)
    frame_size = width * height * 3

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-vsync",
        "0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **hidden_subprocess_kwargs())
    frames: list[np.ndarray] = []

    try:
        while True:
            buf = proc.stdout.read(frame_size) if proc.stdout else b""
            if not buf:
                break
            if len(buf) != frame_size:
                break
            frames.append(
                np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3)).copy()
            )
    finally:
        if proc.stdout:
            proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(stderr.strip() or f"ffmpeg failed for {path}")

    if not frames:
        raise RuntimeError(f"No frames decoded from: {path}")

    return frames


def read_rhcache_meta(cache_path: Path) -> dict:
    with zipfile.ZipFile(cache_path, "r") as zf:
        return json.loads(zf.read("meta.json"))


def _decode_webp_rgb(buf: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(buf)) as image:
        return np.asarray(image.convert("RGB"))


def read_rhcache_all_frames(cache_path: Path) -> list[np.ndarray]:
    meta = read_rhcache_meta(cache_path)
    with zipfile.ZipFile(cache_path, "r") as zf:
        return [
            _decode_webp_rgb(zf.read(f"frames/{i:06d}.webp"))
            for i in range(meta["frame_count"])
        ]


def load_clip_frames(video_path: Path, cache_dir: Path) -> list[np.ndarray]:
    cache_path = cache_dir / (video_path.stem + ".rhcache")
    if cache_path.exists():
        return read_rhcache_all_frames(cache_path)

    return decode_video_to_numpy_frames(video_path)
