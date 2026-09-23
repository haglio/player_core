from __future__ import annotations

from pathlib import Path

from player_core import clip_flip
from player_core.clip_flip import ClipFlip


def _clip(tmp_path: Path, name: str = "scene one.mp4") -> Path:
    folder = tmp_path / "clips"
    folder.mkdir(exist_ok=True)
    clip = folder / name
    clip.touch()
    return clip


def test_a_clip_nobody_flipped_is_shown_as_it_is(tmp_path):
    flip = ClipFlip()

    flip.follow(_clip(tmp_path))

    assert flip.on is False


def test_flipping_the_clip_on_screen_turns_it_over(tmp_path):
    flip = ClipFlip()
    flip.follow(_clip(tmp_path))

    flip.toggle()

    assert flip.on is True


def test_a_flipped_clip_is_still_flipped_in_the_next_session(tmp_path):
    clip = _clip(tmp_path)
    this_session = ClipFlip()
    this_session.follow(clip)
    this_session.toggle()

    next_session = ClipFlip()
    next_session.follow(clip)

    assert next_session.on is True


def test_flipping_it_again_puts_it_back_for_good(tmp_path):
    clip = _clip(tmp_path)
    this_session = ClipFlip()
    this_session.follow(clip)
    this_session.toggle()
    this_session.toggle()

    next_session = ClipFlip()
    next_session.follow(clip)

    assert (this_session.on, next_session.on) == (False, False)


def test_the_flip_belongs_to_the_one_clip(tmp_path):
    flipped, other = _clip(tmp_path, "scene one.mp4"), _clip(tmp_path, "scene two.mp4")
    flip = ClipFlip()
    flip.follow(flipped)
    flip.toggle()

    flip.follow(other)
    shown_after_moving_on = flip.on
    flip.follow(flipped)

    assert (shown_after_moving_on, flip.on) == (False, True)


def test_a_flip_another_session_saved_survives_this_one_flipping(tmp_path):
    first, second = _clip(tmp_path, "scene one.mp4"), _clip(tmp_path, "scene two.mp4")
    headset, desktop = ClipFlip(), ClipFlip()
    headset.follow(first)
    desktop.follow(second)

    headset.toggle()
    desktop.toggle()

    later = ClipFlip()
    later.follow(first)
    assert later.on is True


def test_the_record_is_read_when_the_clip_changes_not_every_frame(tmp_path, monkeypatch):
    reads: list[Path] = []
    read = clip_flip._flipped_names
    monkeypatch.setattr(clip_flip, "_flipped_names",
                        lambda record: reads.append(record) or read(record))
    clip = _clip(tmp_path)
    flip = ClipFlip()

    for _frame in range(120):
        flip.follow(clip)

    assert len(reads) == 1


def test_a_flip_that_could_not_be_saved_still_shows_and_says_so(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(clip_flip, "publish_whole", lambda _record, _text: False)
    flip = ClipFlip()
    flip.follow(_clip(tmp_path))

    flip.toggle()

    assert flip.on is True
    assert "scene one.mp4" in caplog.text


def test_with_no_clip_on_screen_there_is_nothing_to_flip(tmp_path):
    flip = ClipFlip()

    flip.toggle()

    assert flip.on is False
    assert list(tmp_path.iterdir()) == []


def test_a_flipped_clip_is_shown_half_a_loop_over(tmp_path):
    flip = ClipFlip()
    flip.follow(_clip(tmp_path))
    as_it_is = flip.applied_to(0.25)
    flip.toggle()

    assert (as_it_is, flip.applied_to(0.25), flip.applied_to(0.75)) == (0.25, 0.75, 0.25)
