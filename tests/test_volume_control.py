"""A Funestra's own volume chip: what it opens showing, and what a press on it sets."""
from __future__ import annotations

from funestra_fakes import FakePlayer

from player_core.volume import CHIP_H, VolumeHud, chip_xy
from player_core.volume_control import VolumeControl

WIN_W, WIN_H = 640, 480
ROW_H = 24

_VX, _VY = chip_xy(win_w=WIN_W, win_h=WIN_H, timeline_h=ROW_H)
SPEAKER = (_VX + 7, _VY + CHIP_H // 2)
HALFWAY = (_VX + 66, _VY + CHIP_H // 2)
OFF_CHIP = (_VX - 40, _VY + CHIP_H // 2)


def _volume(*, live: bool = True):
    player = FakePlayer()
    return VolumeControl(player, live=live), player


def _press(volume, point) -> bool:
    return volume.press_at(*point, win_w=WIN_W, win_h=WIN_H, timeline_h=ROW_H)


def _drag(volume, point) -> None:
    volume.drag_at(*point, win_w=WIN_W, win_h=WIN_H, timeline_h=ROW_H)


class TestWhatItOpensAt:
    def test_a_live_chip_opens_muted_at_full(self):
        volume, _player = _volume()

        assert volume.hud.muted is True
        assert volume.hud.volume == 100

    def test_a_silent_chip_opens_empty(self):
        volume, _player = _volume(live=False)

        assert volume.hud.muted is True
        assert volume.hud.volume == 0


class TestPresses:
    def test_the_speaker_unmutes_the_player_and_mutes_it_again(self):
        volume, player = _volume()

        assert _press(volume, SPEAKER)
        assert volume.hud.muted is False
        assert player.muted is False

        assert _press(volume, SPEAKER)
        assert volume.hud.muted is True
        assert player.muted is True

    def test_the_slider_sets_the_level_and_lifts_the_mute(self):
        volume, player = _volume()

        assert _press(volume, HALFWAY)

        assert volume.hud == VolumeHud(volume=50, muted=False)
        assert (player.volume, player.muted) == (50, False)

    def test_a_press_beside_the_chip_is_not_taken(self):
        volume, player = _volume()

        assert not _press(volume, OFF_CHIP)
        assert (player.volume, player.muted) == (100, True)

    def test_a_silent_chip_swallows_its_press_without_acting_on_it(self):
        volume, player = _volume(live=False)

        assert _press(volume, SPEAKER)
        assert volume.hud.muted is True
        assert player.muted is True


class TestDrags:
    def test_a_drag_along_the_track_keeps_setting_the_level(self):
        volume, player = _volume()

        _drag(volume, HALFWAY)
        assert player.volume == 50

        _drag(volume, (_VX + 26, HALFWAY[1]))
        assert player.volume == 0

    def test_a_drag_past_the_track_s_end_saturates_instead_of_stopping(self):
        volume, player = _volume()

        _drag(volume, (_VX + 110, HALFWAY[1]))

        assert player.volume == 100

    def test_a_drag_that_began_elsewhere_misses_the_chip_and_does_nothing(self):
        volume, player = _volume()

        _drag(volume, OFF_CHIP)

        assert (player.volume, player.muted) == (100, True)

    def test_a_drag_across_the_speaker_does_not_flip_the_mute(self):
        volume, player = _volume()
        _press(volume, HALFWAY)

        _drag(volume, SPEAKER)

        assert player.muted is False
