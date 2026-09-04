"""The registry's own rules — the ones no single control's test would catch."""
from __future__ import annotations

from pathlib import Path

import pytest

from player_core.control_registry import Control, Verb, bind
from player_core.flag import Flag
from player_core.genau_controls import CONTROLS, KEYS, VERBS, GenauControls
from player_core.robot_hand import RobotHandState
from player_core.robot_hand_beat import BeatEngine


def _controls(**fields) -> GenauControls:
    return GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0),
        paused=Flag(),
        step_clip=lambda _step: None,
        **fields,
    )


def _moved(_controls_arg, _value) -> bool:
    return True


class TestOneVerbHasOneOwner:
    def test_two_controls_cannot_claim_the_same_spelling(self):
        """The loser would go silently unreachable, which is the drift the
        registry exists to stop."""
        clash = (
            Control(name="one", verbs=(Verb("EXAMPLE_VERB", _moved),)),
            Control(name="two", verbs=(Verb("EXAMPLE_VERB", _moved),)),
        )

        with pytest.raises(ValueError) as refused:
            bind(clash)

        assert "EXAMPLE_VERB" in str(refused.value)
        assert "one" in str(refused.value) and "two" in str(refused.value)

    def test_the_registry_that_ships_binds(self):
        assert set(VERBS) == {
            verb.spelling for control in CONTROLS for verb in control.verbs
        }

    def test_every_verb_names_the_control_that_owns_it(self):
        for spelling, (control, verb) in VERBS.items():
            assert verb.spelling == spelling
            assert verb in control.verbs


class TestAControlSaysWhatItCannotActWithout:
    def test_a_control_needing_nothing_can_always_act(self):
        assert Control(name="free", verbs=()).can_act(_controls()) is True

    def test_a_need_this_build_did_not_wire_stops_the_control(self):
        needy = Control(name="needy", verbs=(), needs=("robot_hand",))

        assert needy.can_act(_controls()) is False
        assert needy.can_act(_controls(robot_hand=RobotHandState())) is True

    def test_every_need_names_a_field_that_exists(self):
        """A misspelled need would read as absent and silence the control."""
        fields = set(GenauControls.__dataclass_fields__)

        for control in CONTROLS:
            assert set(control.needs) <= fields, control.name


class TestHalfACommandIsNotACommand:
    """The arity is part of the spelling, and both halves of the rule matter."""

    @pytest.mark.parametrize("spelling", ["SPEED", "AMP", "CENTER"])
    def test_a_verb_that_wants_a_value_says_so(self, spelling):
        assert VERBS[spelling][1].takes_a_value is True

    @pytest.mark.parametrize(
        "spelling", ["SPEED_UP", "SPEED_DOWN", "CYCLE_SHAPE", "CYCLE_SHAPE_PREV"],
    )
    def test_a_verb_that_stands_alone_says_so(self, spelling):
        assert VERBS[spelling][1].takes_a_value is False


# Every verb the registry answers, and the key each one means.  Written down
# here so a verb added to the registry is a deliberate line in a diff -- the
# spellings are a contract with the orchestrator that sends them, kept from its
# own side in genau's tests/test_genau_vocabulary.py.
WRITTEN_DOWN_VERBS = frozenset({
    "QUIT", "PREV", "NEXT", "WEIRD", "LATEST", "SHUFFLE", "OFFSET_QUARTER_CYCLE",
    "PAUSE", "RESUME", "SPEED_DOWN", "SPEED_UP", "AMPLITUDE_DOWN", "AMPLITUDE_UP",
    "CENTER_DOWN", "CENTER_UP", "CYCLE_SHAPE", "CYCLE_SHAPE_PREV", "TOGGLE_CRUISE",
    "CRUISE_ON", "CRUISE_OFF", "TOGGLE_LOCK", "LOCK_ON", "LOCK_OFF",
    "CLIP_SECONDS_DOWN", "CLIP_SECONDS_UP", "HUD_ON", "HUD_OFF",
    "AMP", "CENTER", "SPEED", "CLIP_SECONDS", "SET_VOLUME",
})

WRITTEN_DOWN_KEYS = {
    "K_j": "SPEED_DOWN",
    "K_l": "SPEED_UP",
    "K_7": "AMPLITUDE_DOWN",
    "K_9": "AMPLITUDE_UP",
    "K_u": "CENTER_DOWN",
    "K_o": "CENTER_UP",
    "K_i": "CYCLE_SHAPE",
    "K_m": "PREV",
    "K_PERIOD": "NEXT",
    "K_k": "WEIRD",
    "K_COMMA": "TOGGLE_LOCK",
    "K_BACKSLASH": "OFFSET_QUARTER_CYCLE",
    "K_SLASH": "TOGGLE_CRUISE",
}


class TestTheVocabularyIsWrittenDown:
    def test_the_registry_declares_exactly_the_verbs_written_down(self):
        assert set(VERBS) == WRITTEN_DOWN_VERBS

    def test_each_key_means_the_verb_written_down_beside_it(self):
        assert {name: verb.spelling for name, (_control, verb) in KEYS.items()} == WRITTEN_DOWN_KEYS


class TestAVerbIsSpelledInOneFile:
    """A control used to be hand-plumbed through four to six files -- a branch in
    the dispatcher, a parameter and an attribute and a hand-off line on the
    tick, a branch in the key handler -- and the two hottest files in Genau's
    repo changed together in half its commits because of it.  Held as a ceiling
    that fails rather than as a note, and measured the way a reader would: which
    modules in this package spell the verb at all.  One is allowed: the
    registry that declares it.
    """

    @staticmethod
    def _files_naming(verb: str) -> set[str]:
        import ast

        package = Path(__file__).resolve().parents[1] / "player_core"
        naming = set()
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if any(isinstance(n, ast.Constant) and n.value == verb
                   for n in ast.walk(tree)):
                naming.add(path.name)
        return naming

    @pytest.mark.parametrize("verb", sorted(WRITTEN_DOWN_VERBS))
    def test_the_registry_is_the_one_module_that_spells_it(self, verb):
        assert self._files_naming(verb) == {"genau_controls.py"}
