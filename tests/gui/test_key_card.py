import time

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel

from src.config import PALETTE
from src.desktop.dictum import Gate
from src.gui.components.key_card import KeyCard, MarkedLine, mark_of

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]

ROWS = [("SPACE", "pause"), ("0", "back to Traker"), ("ESC 10s", "leave the break")]


@pytest.fixture
def card(qapp):
    return KeyCard(ROWS)


class TestWhatItSays:
    def test_it_keeps_the_rows_it_was_given(self, card):
        assert card.hints == tuple(ROWS)

    def test_it_can_be_told_something_else(self, card):
        card.set_hints([("SPACE", "turn the page")])

        assert card.hints == (("SPACE", "turn the page"),)

    def test_nothing_to_say_is_no_card_at_all(self, qapp):
        card = KeyCard([])

        assert card.hints == ()
        assert card.sizeHint().isEmpty()
        card.resize(80, 40)
        card.grab()


class TestTheInputsThatSendAKey:
    def test_a_row_may_name_them(self, qapp):
        card = KeyCard([("SPACE", "pause", ("right pedal", "brow_raise")), ("0", "back")])

        assert card.hints == (("SPACE", "pause"), ("0", "back"))
        assert card.inputs == (("right pedal", "brow_raise"), ())

    def test_naming_them_widens_the_card(self, card):
        named = KeyCard([(key, says, ("right pedal",)) for key, says in ROWS])

        assert named.sizeHint().width() > card.sizeHint().width()

    def test_a_larger_card_is_larger_throughout(self, card):
        large = KeyCard(ROWS, scale=2.0)

        assert large.sizeHint().height() == pytest.approx(2 * card.sizeHint().height(), abs=2)

    def test_it_draws_them(self, qapp):
        card = KeyCard([("SPACE", "pause", ("right pedal",))], calm=True)
        card.resize(card.sizeHint())

        assert card.grab().size() == card.sizeHint()


class TestWhereItSits:
    def test_it_sizes_itself_to_its_rows(self, card):
        wide = KeyCard(ROWS + [("1-9", "a much longer thing to do")])

        assert wide.sizeHint().width() > card.sizeHint().width()
        assert wide.sizeHint().height() > card.sizeHint().height()

    def test_it_goes_in_the_top_right_corner(self, card):
        card.place_top_right(QRect(0, 0, 1920, 1080))

        assert card.geometry().right() < 1920
        assert card.geometry().left() > 1920 // 2
        assert card.geometry().top() < 1080 // 4

    def test_the_corner_is_the_one_it_is_placed_within(self, card):
        card.place_top_right(QRect(0, 0, 600, 400))

        assert card.geometry().right() < 600


class TestItIsAReadoutAndNothingElse:
    def test_it_never_takes_the_focus(self, card):
        assert card.focusPolicy() == Qt.FocusPolicy.NoFocus

    def test_it_does_not_take_the_mouse_either(self, card):
        assert card.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True

    def test_it_draws_itself(self, card):
        card.resize(card.sizeHint())

        assert card.grab().size() == card.sizeHint()


def held(name, served=0.0, hold=1.0) -> Gate:
    return Gate(name, time.monotonic() - served * hold, hold)


def blue_pixels(widget, right_half=False) -> int:
    image = widget.grab().toImage()
    blue = QColor(PALETTE['blue'])
    return sum(1 for x in range(image.width() // 2 if right_half else 0, image.width())
               for y in range(image.height())
               if abs(image.pixelColor(x, y).blue() - blue.blue()) < 24
               and abs(image.pixelColor(x, y).red() - blue.red()) < 24
               and abs(image.pixelColor(x, y).green() - blue.green()) < 24)


class TestHowEachInputIsDrawn:
    def test_a_gesture_is_its_sign_on_its_side(self):
        assert mark_of("left_thumbs_up") == ("sign", "thumbs_up", "left")
        assert mark_of("brow_raise") == ("sign", "brow_raise", "")

    def test_a_pedal_is_its_glyph(self):
        assert mark_of("middle pedal") == ("pedal", 1)

    def test_a_phrase_or_a_shape_without_a_sign_is_its_words(self):
        assert mark_of("“send space”") == ("text", "“send space”")
        assert mark_of("smile") == ("text", "smile")


HELD_ROWS = [("SPACE", "pause", ("right pedal", "brow_raise")),
             ("←", "seek back", ("left_fist",)), ("0", "back to Traker")]


class TestAGestureServingItsHold:
    def test_it_outlines_the_rows_it_drives(self, qapp):
        card = KeyCard(HELD_ROWS)

        assert blue_pixels(card, right_half=True) == 0

        card.set_gate(held("brow_raise"))

        assert card.held_rows == (("SPACE", "pause"),)
        assert blue_pixels(card, right_half=True) > 0

    def test_a_gesture_the_card_does_not_name_outlines_nothing(self, qapp):
        card = KeyCard(HELD_ROWS)

        card.set_gate(held("smile"))

        assert card.held_rows == ()
        assert blue_pixels(card) == 0

    def test_its_ring_fills_as_it_is_held(self, qapp):
        card = KeyCard(HELD_ROWS)
        card.set_gate(held("left_fist", served=0.05))
        begun = blue_pixels(card)

        card.set_gate(held("left_fist", served=0.95))

        assert blue_pixels(card) > begun > 0

    def test_letting_go_takes_the_outline_away(self, qapp):
        card = KeyCard(HELD_ROWS)
        card.set_gate(held("left_fist", served=0.5))

        card.set_gate(None)

        assert card.held_rows == () and blue_pixels(card) == 0

    def test_a_card_of_the_held_only_shows_nothing_until_one_is_held(self, qapp):
        card = KeyCard(HELD_ROWS, held_only=True)
        assert card.sizeHint().isEmpty()

        card.set_gate(held("left_fist"))

        assert card.sizeHint().height() < KeyCard(HELD_ROWS, held_only=False).sizeHint().height()
        assert not card.sizeHint().isEmpty()


class TestALineMarkedWithItsInputs:
    def test_it_is_outlined_while_one_of_them_is_held(self, qapp):
        line = MarkedLine(QLabel("1  Anki"))
        line.set_names(("left_fist", "right pedal"))
        line.resize(line.sizeHint())
        assert blue_pixels(line) == 0

        line.set_gate(held("left_fist", served=0.5))

        assert line.marks.held and blue_pixels(line, right_half=True) > 0
