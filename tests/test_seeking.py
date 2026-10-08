from __future__ import annotations

import logging

from player_core.seeking import GIVE_UP_AFTER, OwedSeek, seek_if_taken


class _Player:
    def __init__(self, *, refusals: int = 0, duration_ms: float = 5_000.0) -> None:
        self.refusals = refusals
        self.duration_ms = duration_ms
        self.seeks: list[float] = []

    def seek_ms(self, ms: float) -> None:
        if self.refusals:
            self.refusals -= 1
            raise SystemError("Error running mpv command", -12)
        self.seeks.append(ms)


class TestASeekMpvMayRefuse:
    def test_a_taken_seek_lands_and_says_so(self):
        player = _Player()

        assert seek_if_taken(player, 1_200.0) is True
        assert player.seeks == [1_200.0]

    def test_a_refused_seek_lands_nowhere_and_says_so(self):
        player = _Player(refusals=1)

        assert seek_if_taken(player, 1_200.0) is False
        assert player.seeks == []


class TestASeekOwedToTheFileOnScreen:
    def _pay(self, owed: OwedSeek, player: _Player, times: int = 1) -> None:
        for _ in range(times):
            owed.pay(player, lambda ms: seek_if_taken(player, ms))

    def test_is_asked_for_each_tick_until_mpv_takes_it(self):
        player = _Player(refusals=2)
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, player, times=3)

        assert player.seeks == [900.0]

    def test_once_taken_it_is_not_asked_for_again(self):
        player = _Player()
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, player, times=3)

        assert player.seeks == [900.0]

    def test_waits_for_the_file_to_report_a_duration(self):
        player = _Player(duration_ms=0.0)
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, player)
        player.duration_ms = 5_000.0
        self._pay(owed, player)

        assert player.seeks == [900.0]

    def test_nothing_owed_asks_for_nothing(self):
        player = _Player()
        owed = OwedSeek()
        owed.owe(None)

        self._pay(owed, player)

        assert player.seeks == []

    def test_is_let_go_with_a_warning_once_mpv_has_refused_it_long_enough(self, caplog):
        player = _Player(refusals=GIVE_UP_AFTER + 5)
        owed = OwedSeek()
        owed.owe(900.0)

        with caplog.at_level(logging.WARNING, logger="player_core.seeking"):
            self._pay(owed, player, times=GIVE_UP_AFTER + 5)

        assert player.seeks == []
        assert player.refusals == 5
        assert "never took the seek to 900 ms" in caplog.text
