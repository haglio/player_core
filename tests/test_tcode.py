from __future__ import annotations

from player_core.tcode import UdpTCodeSink, format_tcode_command


class FakeSock:
    def __init__(self):
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


class TestUdpTCodeSink:
    def test_send_transmits_newline_terminated_ascii_datagram(self):
        sock = FakeSock()
        sink = UdpTCodeSink(host="127.0.0.1", port=50557, sock=sock)
        sink.send("L05000I33")
        assert sock.sent == [(b"L05000I33\n", ("127.0.0.1", 50557))]

    def test_close_closes_socket(self):
        sock = FakeSock()
        sink = UdpTCodeSink(sock=sock)
        sink.close()
        assert sock.closed is True

    def test_defaults(self):
        sock = FakeSock()
        sink = UdpTCodeSink(sock=sock)
        sink.send("L09999I50")
        assert sock.sent == [(b"L09999I50\n", ("127.0.0.1", 50557))]


class TestFormatTcodeCommand:
    def test_max_position(self):
        assert format_tcode_command("L0", 9999, 33) == "L09999I33"

    def test_min_position(self):
        assert format_tcode_command("L0", 0, 100) == "L00000I100"

    def test_center_position(self):
        assert format_tcode_command("L0", 5000, 50) == "L05000I50"

    def test_clamps_position_above_max(self):
        assert format_tcode_command("L0", 10500, 33) == "L09999I33"

    def test_clamps_position_below_zero(self):
        assert format_tcode_command("L0", -5, 33) == "L00000I33"
