"""A Funestra's own volume chip: what it opens showing, and what a press on it sets."""
from __future__ import annotations

from funestra_fakes import FakePlayer

from player_core.volume import CHIP_H, VolumeHud, chip_xy
from player_core.volume_control import RoomVolume, VolumeControl

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


class TestTheRoomsVolume:
    """The Main Funestra's sound is the room's to decide: the chip shows the level
    the room publishes, a press asks the room for a new one and shows it at once,
    and the room's answer overwrites it either way."""

    WIN = {"win_w": 800, "win_h": 600, "timeline_h": 24}
    SPEAKER = (690, 585)
    TRACK_HALFWAY = (744, 585)
    TRACK_LEFT_END = (704, 585)
    OFF_THE_CHIP = (400, 585)

    def _control(self, tmp_path, *, live: bool = True):
        player = FakePlayer()
        return RoomVolume(player, dashboard_cmd_file=tmp_path / "dashboard_cmd.txt", live=live), player

    def _asks(self, tmp_path) -> list[str]:
        path = tmp_path / "dashboard_cmd.txt"
        return path.read_text(encoding="utf-8").split() if path.exists() else []

    def test_it_starts_at_full_and_unmuted_until_the_room_says_otherwise(self, tmp_path):
        control, _player = self._control(tmp_path)

        assert (control.hud.volume, control.hud.muted) == (100, False)

    def test_a_live_build_unmutes_its_player_so_the_rooms_level_can_be_heard(self, tmp_path):
        _control, player = self._control(tmp_path, live=True)

        assert player.muted is False

    def test_a_silent_build_leaves_its_player_muted(self, tmp_path):
        _control, player = self._control(tmp_path, live=False)

        assert player.muted is True

    def test_the_rooms_answer_is_what_the_chip_shows_and_what_the_player_plays(self, tmp_path):
        control, player = self._control(tmp_path)

        control.set(40, muted=False)

        assert (control.hud.volume, control.hud.muted) == (40, False)
        assert player.volume == 40

    def test_a_mute_from_the_room_plays_silent_but_keeps_the_level_drawn(self, tmp_path):
        control, player = self._control(tmp_path)

        control.set(70, muted=True)

        assert (control.hud.volume, control.hud.muted) == (70, True)
        assert player.volume == 0

    def test_a_level_from_the_room_is_held_within_the_chips_range(self, tmp_path):
        control, player = self._control(tmp_path)

        control.set(400, muted=False)
        assert player.volume == 100
        control.set(-10, muted=False)
        assert player.volume == 0

    def test_pressing_the_speaker_mutes_the_chip_and_asks_for_the_mute(self, tmp_path):
        control, player = self._control(tmp_path)

        assert control.press_at(*self.SPEAKER, **self.WIN) is True

        assert control.hud.muted is True
        assert self._asks(tmp_path) == ["audio_mute"]
        assert player.volume == 100, "the room answers; the chip does not set the player itself"

    def test_pressing_it_again_asks_for_the_unmute(self, tmp_path):
        control, _player = self._control(tmp_path)
        control.press_at(*self.SPEAKER, **self.WIN)

        control.press_at(*self.SPEAKER, **self.WIN)

        assert control.hud.muted is False
        assert self._asks(tmp_path) == ["audio_mute", "audio_unmute"]

    def test_the_level_underneath_a_mute_is_left_where_it_was(self, tmp_path):
        control, _player = self._control(tmp_path)
        control.set(40, muted=False)

        control.press_at(*self.SPEAKER, **self.WIN)

        assert (control.hud.volume, control.hud.muted) == (40, True)

    def test_pressing_the_slider_asks_for_the_level_under_the_pointer_and_shows_it(self, tmp_path):
        control, _player = self._control(tmp_path)

        assert control.press_at(*self.TRACK_HALFWAY, **self.WIN) is True

        assert control.hud.volume == 50
        assert self._asks(tmp_path) == ["audio_set_volume|50"]

    def test_asking_for_a_level_is_asking_to_hear_it(self, tmp_path):
        control, _player = self._control(tmp_path)
        control.press_at(*self.SPEAKER, **self.WIN)

        control.press_at(*self.TRACK_HALFWAY, **self.WIN)

        assert control.hud.muted is False

    def test_a_press_that_missed_is_not_taken_and_asks_nothing(self, tmp_path):
        control, _player = self._control(tmp_path)

        assert control.press_at(*self.OFF_THE_CHIP, **self.WIN) is False
        assert self._asks(tmp_path) == []

    def test_a_taller_timeline_row_lifts_the_chip_off_the_pointer(self, tmp_path):
        control, _player = self._control(tmp_path)
        near_the_bottom = (744, 595)

        assert control.press_at(*near_the_bottom, win_w=800, win_h=600, timeline_h=24)
        assert not control.press_at(*near_the_bottom, win_w=800, win_h=600, timeline_h=48)

    def test_a_drag_keeps_asking_for_the_level(self, tmp_path):
        control, _player = self._control(tmp_path)
        control.press_at(*self.TRACK_LEFT_END, **self.WIN)

        control.drag_at(*self.TRACK_HALFWAY, **self.WIN)

        assert control.hud.volume == 50
        assert self._asks(tmp_path) == ["audio_set_volume|0", "audio_set_volume|50"]

    def test_dragging_across_the_speaker_does_not_toggle_the_mute(self, tmp_path):
        control, _player = self._control(tmp_path)

        control.drag_at(*self.SPEAKER, **self.WIN)

        assert control.hud.muted is False
        assert self._asks(tmp_path) == []

    def test_an_ignored_press_corrects_itself_when_the_room_answers(self, tmp_path):
        control, _player = self._control(tmp_path)
        control.press_at(*self.SPEAKER, **self.WIN)

        control.set(60, muted=False)

        assert control.hud.muted is False

    def test_with_no_room_to_ask_a_press_still_shows_the_level(self, tmp_path):
        player = FakePlayer()
        control = RoomVolume(player, dashboard_cmd_file=None, live=True)

        control.press_at(*self.TRACK_HALFWAY, **self.WIN)

        assert control.hud.volume == 50
