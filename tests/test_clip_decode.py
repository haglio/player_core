from __future__ import annotations

from unittest.mock import patch

import numpy as np
from rhcache_fixtures import write_rhcache

from player_core.clip_decode import load_clip_frames, read_rhcache_all_frames, read_rhcache_meta


def _make_frames(count: int, width: int = 8, height: int = 6) -> list[np.ndarray]:
    return [np.random.randint(0, 256, (height, width, 3), dtype=np.uint8) for _ in range(count)]


def test_write_and_read_meta(tmp_path):
    frames = _make_frames(5, width=16, height=12)
    cache_path = tmp_path / "clip.rhcache"

    write_rhcache(frames, cache_path, source_name="clip.mp4")

    meta = read_rhcache_meta(cache_path)
    assert meta["width"] == 16
    assert meta["height"] == 12
    assert meta["frame_count"] == 5
    assert meta["source"] == "clip.mp4"


def test_read_all_frames_lossless(tmp_path):
    frames = _make_frames(4, width=10, height=8)
    cache_path = tmp_path / "clip.rhcache"
    write_rhcache(frames, cache_path, source_name="clip.mp4", lossless=True)

    all_frames = read_rhcache_all_frames(cache_path)
    assert len(all_frames) == 4
    for i, recovered in enumerate(all_frames):
        np.testing.assert_array_equal(recovered, frames[i])


def test_load_clip_frames_from_cache(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.touch()
    cache_dir = tmp_path / ".rhcache"
    cache_dir.mkdir()

    frames_np = _make_frames(4, width=10, height=8)
    write_rhcache(frames_np, cache_dir / "clip.rhcache", source_name="clip.mp4", lossless=True)

    result = load_clip_frames(video_path, cache_dir)
    assert len(result) == 4
    for frame in result:
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (8, 10, 3)


def test_load_clip_frames_falls_back_to_ffmpeg(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.touch()
    cache_dir = tmp_path / ".rhcache"

    fake_frames = _make_frames(3)

    with patch(
        "player_core.clip_decode.decode_video_to_numpy_frames",
        return_value=fake_frames,
    ):
        result = load_clip_frames(video_path, cache_dir)

    assert len(result) == 3
    for frame in result:
        assert isinstance(frame, np.ndarray)
