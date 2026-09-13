"""A button a content source declares on a player's HUD, and its published form."""
from __future__ import annotations

import json

from player_core.hud_button import Button, rows_from_raw, rows_raw


def test_a_declared_button_survives_the_round_trip_through_json():
    rows = (
        (Button("portrait_prev", "⏮", "Previous clip"),
         Button("portrait_lock", "🔒", "Lock / unlock this clip", lit=True, favorite=True)),
        (Button("origenerator_activate", "Origenerator", "Origenerator mode", width=0,
                group_break=True, dim=True),
         Button("", "", "", width=22, host_value="playback_speed")),
    )

    assert rows_from_raw(json.loads(json.dumps(rows_raw(rows)))) == rows
