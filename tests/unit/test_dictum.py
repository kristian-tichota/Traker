import pytest

from src.desktop.dictum import bindings, key_sent, keys_of, legend

CATALOGUE = {
    "kind": "catalogue",
    "modes": [
        {"name": "command mode", "pedals": [], "gestures": [], "groups": [
            {"name": "control", "entries": [["send space", "space", ""],
                                            ["step left", "{1=1}(left)", ""],
                                            ["number {numeric}", "{1}", ""]]}]},
        {"name": "anki mode", "pedals": [["left", "left", ""], ["middle", "backspace", ""],
                                         ["right", "space", ""]], "gestures": [], "groups": []},
        {"name": "::hand pedals", "pedals": [], "groups": [], "gestures": [
            ["brow_raise", "space", ""], ["pucker_frown", "esc", ""],
            ["left_open", "left pedal", "left pedal"], ["right_open", "right pedal", "right pedal"],
            ["left_fist", "hold(esc)", "release(esc)"]]},
    ],
}

STATE = {"kind": "state", "mode": "command mode", "gesture_mode": "::hand pedals",
         "pedal_mode": "anki mode", "asleep": []}

DECK = [("SPACE", "show, then good"), ("← →", "again, good"), ("0", "back to Traker"),
        ("1-3", "another offer"), ("ESC 10s", "leave the break")]


@pytest.fixture
def inputs():
    return bindings(CATALOGUE, STATE)


class TestWhatAResponseSends:
    def test_a_counted_key_is_that_key(self):
        assert key_sent("{1=1}(left)") == ("left", False)

    def test_a_held_key_says_so(self):
        assert key_sent("hold(esc)") == ("esc", True)

    def test_a_chord_keeps_its_parts(self):
        assert key_sent("ctrl + 0") == ("ctrl+0", False)


class TestWhoSendsWhat:
    def test_pedals_then_their_stand_ins_then_gestures_then_phrases(self, inputs):
        assert inputs[("space", False)] == ("right pedal", "right open", "brow raise",
                                            "“send space”")

    def test_a_stand_in_sends_what_its_pedal_sends(self, inputs):
        assert inputs[("left", False)] == ("left pedal", "left open", "“step left”")

    def test_a_phrase_that_takes_a_number_is_left_out(self, inputs):
        assert not any("numeric" in name for names in inputs.values() for name in names)

    def test_a_sleeping_layer_sends_nothing(self):
        asleep = bindings(CATALOGUE, {**STATE, "asleep": ["gesture", "voice"]})

        assert asleep[("space", False)] == ("right pedal",)

    def test_an_unknown_mode_sends_nothing(self):
        assert bindings(CATALOGUE, {**STATE, "pedal_mode": "gone", "gesture_mode": None,
                                    "mode": None}) == {}


class TestTheLabelsOfTheCard:
    def test_a_chord_is_one_key(self):
        assert keys_of("CTRL 0") == [("CTRL 0", "ctrl+0", False)]

    def test_a_duration_marks_a_hold(self):
        assert keys_of("ESC 10s") == [("ESC 10s", "esc", True)]

    def test_a_label_that_is_no_key_is_left_alone(self):
        assert keys_of("1-3") == [] and keys_of("LETTERS") == []


class TestTheLegend:
    def test_without_inputs_it_is_the_card_as_it_was(self):
        assert [row[:2] for row in legend(DECK, {})] == DECK

    def test_a_pair_splits_into_one_row_per_key_and_effect(self, inputs):
        rows = legend(DECK, inputs)

        assert ("←", "again", ("left pedal", "left open", "“step left”")) in rows
        assert ("→", "good", ()) in rows

    def test_a_held_key_names_only_what_holds_it(self, inputs):
        held, = [row for row in legend(DECK, inputs) if row[0] == "ESC 10s"]

        assert held[2] == ("left fist",)

    def test_a_pressed_key_names_taps_and_holds(self, inputs):
        rows = legend([("ESC", "start focus")], inputs)

        assert rows == [("ESC", "start focus", ("pucker frown", "left fist"))]
