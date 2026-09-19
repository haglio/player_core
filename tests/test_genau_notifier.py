from __future__ import annotations

from pathlib import Path

from player_core.genau_notifier import GenauNotifier


class FakeSocket:
    def __init__(self):
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


def test_notify_clip_sends_clip_stem():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.notify_clip(Path("demo.mp4"))

    assert sock.sent == [(b"CLIP demo", ("127.0.0.1", 9999))]


def test_notify_visible_deduplicates_repeated_state():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.notify_visible(True)
    notifier.notify_visible(True)
    notifier.notify_visible(False)

    assert sock.sent == [
        (b"VISIBLE 1", ("127.0.0.1", 9999)),
        (b"VISIBLE 0", ("127.0.0.1", 9999)),
    ]


def test_the_notifier_has_only_the_two_things_it_says():
    """CLIP and VISIBLE, each with one caller.

    A third method wrapped them to send both at once, for a first tick that
    had already had its CLIP sent by the clip selection a moment earlier --
    so it put the same datagram on the wire twice at every launch.
    """
    assert not hasattr(GenauNotifier, "announce_visible")


def test_close_closes_socket():
    sock = FakeSocket()
    notifier = GenauNotifier("127.0.0.1", 9999, sock=sock)

    notifier.close()

    assert sock.closed is True


class TestAGenauArrivingInARoom:
    """The companion follows the Genau that has the room; an arriving one says
    nothing until it takes the room, and then says what it is showing."""

    def test_it_says_nothing_while_held(self):
        sock = FakeSocket()
        notifier = GenauNotifier("127.0.0.1", 9999, sock=sock, held=True)

        notifier.notify_clip(Path("demo.mp4"))
        notifier.notify_visible(True)

        assert sock.sent == []

    def test_letting_go_says_the_clip_and_whether_it_shows(self):
        sock = FakeSocket()
        notifier = GenauNotifier("127.0.0.1", 9999, sock=sock, held=True)
        notifier.notify_clip(Path("one.mp4"))
        notifier.notify_clip(Path("two.mp4"))
        notifier.notify_visible(True)

        notifier.let_go()

        assert sock.sent == [
            (b"CLIP two", ("127.0.0.1", 9999)),
            (b"VISIBLE 1", ("127.0.0.1", 9999)),
        ]

    def test_after_letting_go_it_speaks_as_ever(self):
        sock = FakeSocket()
        notifier = GenauNotifier("127.0.0.1", 9999, sock=sock, held=True)
        notifier.notify_visible(True)
        notifier.let_go()

        notifier.notify_visible(True)
        notifier.notify_clip(Path("three.mp4"))

        assert sock.sent == [
            (b"VISIBLE 1", ("127.0.0.1", 9999)),
            (b"CLIP three", ("127.0.0.1", 9999)),
        ]

    def test_a_held_notifier_that_heard_nothing_says_nothing_when_let_go(self):
        sock = FakeSocket()
        notifier = GenauNotifier("127.0.0.1", 9999, sock=sock, held=True)

        notifier.let_go()

        assert sock.sent == []
