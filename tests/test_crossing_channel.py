"""The flags a crossing is run through: who is in step, and who has the room."""
from __future__ import annotations

from pathlib import Path

from player_core.crossing import ArrivingPlayer, Crossing, follow_channel, name_in_a_crossing


class TestTheFollowCommandFile:
    def test_a_follower_drains_a_channel_of_its_own(self):
        """The player that has the room is draining the real one, so a verb
        written for the arriving player has to land somewhere else."""
        assert follow_channel(Path("state/main_player_cmd.txt")) == Path(
            "state/main_player_cmd.follow.txt")

    def test_it_keeps_the_suffix_readers_key_off(self):
        assert follow_channel(Path("state/portrait_playlist.tsv")).name == (
            "portrait_playlist.follow.tsv")


class TestWhatAPlayerIsCalledInACrossing:
    def test_the_name_of_the_status_it_publishes(self):
        assert name_in_a_crossing(Path("state/main_player_status.txt")) == "main_player"
        assert name_in_a_crossing(Path("state/landscape_status.txt")) == "landscape"

    def test_its_flags_sit_beside_that_status(self, tmp_path: Path):
        ArrivingPlayer.for_status_file(tmp_path / "portrait_status.txt").in_step(True)
        assert Crossing(tmp_path, ["portrait"]).everyone_in_step


class TestOneArrivingPlayer:
    def test_it_says_when_it_is_in_step(self, tmp_path: Path):
        player = ArrivingPlayer(tmp_path, "main_player")
        assert not Crossing(tmp_path, ["main_player"]).everyone_in_step
        player.in_step(True)
        assert Crossing(tmp_path, ["main_player"]).everyone_in_step

    def test_falling_out_of_step_takes_it_back(self, tmp_path: Path):
        player = ArrivingPlayer(tmp_path, "main_player")
        player.in_step(True)
        player.in_step(False)
        assert not Crossing(tmp_path, ["main_player"]).everyone_in_step

    def test_it_is_told_when_to_take_the_room(self, tmp_path: Path):
        player = ArrivingPlayer(tmp_path, "main_player")
        assert player.take_the_room_now is False
        Crossing(tmp_path, ["main_player"]).say_take_the_room()
        assert player.take_the_room_now is True

    def test_taking_it_is_answered(self, tmp_path: Path):
        crossing = Crossing(tmp_path, ["main_player"])
        player = ArrivingPlayer(tmp_path, "main_player")
        assert not crossing.everyone_has_the_room
        player.took_the_room()
        assert crossing.everyone_has_the_room


class TestTheWholeArrivingRoom:
    def test_it_waits_for_every_player(self, tmp_path: Path):
        crossing = Crossing(tmp_path, ["main_player", "portrait", "landscape"])
        for who in ("main_player", "portrait"):
            ArrivingPlayer(tmp_path, who).in_step(True)
        assert not crossing.everyone_in_step
        ArrivingPlayer(tmp_path, "landscape").in_step(True)
        assert crossing.everyone_in_step

    def test_a_crossing_starts_with_the_last_one_s_flags_gone(self, tmp_path: Path):
        """A flag left by a crossing that failed would hand the room over before
        the arriving player had opened anything."""
        ArrivingPlayer(tmp_path, "main_player").in_step(True)
        ArrivingPlayer(tmp_path, "main_player").took_the_room()
        Crossing(tmp_path, ["main_player"]).say_take_the_room()

        crossing = Crossing(tmp_path, ["main_player"])
        crossing.begin()
        assert not crossing.everyone_in_step
        assert not crossing.everyone_has_the_room
        assert ArrivingPlayer(tmp_path, "main_player").take_the_room_now is False

    def test_it_clears_up_after_itself(self, tmp_path: Path):
        crossing = Crossing(tmp_path, ["main_player"])
        crossing.begin()
        ArrivingPlayer(tmp_path, "main_player").in_step(True)
        crossing.say_take_the_room()
        ArrivingPlayer(tmp_path, "main_player").took_the_room()
        crossing.finish()
        assert sorted(p.name for p in tmp_path.glob("crossing_*")) == []
