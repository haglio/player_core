"""Tests for player_core.file_channel."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from player_core.file_channel import consume_command_file, publish_whole, read_paused_state


def test_consume_returns_empty_list_when_file_missing(tmp_path: Path):
    path = tmp_path / "cmd.txt"

    result = consume_command_file(path)

    assert result == []


def test_consume_returns_empty_list_when_file_empty(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("", encoding="utf-8")

    result = consume_command_file(path)

    assert result == []


def test_consume_returns_single_command(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("NEXT", encoding="utf-8")

    result = consume_command_file(path)

    assert result == ["NEXT"]


def test_consume_returns_multiple_commands_from_multiline(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("RESUME\nHUD_ON", encoding="utf-8")

    result = consume_command_file(path)

    assert result == ["RESUME", "HUD_ON"]


def test_consume_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("RESUME\n\nHUD_ON\n", encoding="utf-8")

    result = consume_command_file(path)

    assert result == ["RESUME", "HUD_ON"]


def test_consume_clears_file_after_reading(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("NEXT", encoding="utf-8")

    consume_command_file(path)

    assert path.read_text(encoding="utf-8") == ""


def test_consume_uppercases_commands(tmp_path: Path):
    path = tmp_path / "cmd.txt"
    path.write_text("resume\nhud_on", encoding="utf-8")

    result = consume_command_file(path)

    assert result == ["RESUME", "HUD_ON"]


def test_consume_preserves_case_when_uppercase_disabled(tmp_path: Path):
    cmd_file = tmp_path / "cmd.txt"
    cmd_file.write_text("PLAY_FILE C:/Videos/MyClip.mp4\n", encoding="utf-8")

    commands = consume_command_file(cmd_file, uppercase=False)

    assert commands == ["PLAY_FILE C:/Videos/MyClip.mp4"]


def test_consume_strips_a_byte_order_mark(tmp_path: Path):
    # A hand-edited command file (Notepad, PowerShell redirection) carries a BOM
    # that would otherwise fuse onto the first verb and match nothing.
    path = tmp_path / "cmd.txt"
    path.write_text("NEXT", encoding="utf-8-sig")

    assert consume_command_file(path) == ["NEXT"]


def test_read_paused_state_reads_flag(tmp_path: Path):
    paused_file = tmp_path / "paused.txt"

    assert read_paused_state(paused_file) is False

    paused_file.write_text("1", encoding="utf-8")
    assert read_paused_state(paused_file) is True

    paused_file.write_text("0", encoding="utf-8")
    assert read_paused_state(paused_file) is False


def test_read_paused_state_strips_a_byte_order_mark(tmp_path: Path):
    paused_file = tmp_path / "paused.txt"
    paused_file.write_text("1", encoding="utf-8-sig")

    assert read_paused_state(paused_file) is True


def test_publish_retries_past_a_reader_holding_the_file_open(tmp_path: Path):
    """Windows refuses to replace a file another process has open, so a publish
    landing inside one of the reader's polls raises.  Riding out that microsecond
    delivers the record instead of dropping it."""
    path = tmp_path / "status.txt"
    path.write_text("old\n", encoding="utf-8")
    real_replace = os.replace
    calls = []

    def flaky_replace(src, dst):
        calls.append(src)
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    with patch("player_core.file_channel.os.replace", side_effect=flaky_replace):
        assert publish_whole(path, "new\n") is True

    assert len(calls) == 2
    assert path.read_text(encoding="utf-8") == "new\n"
