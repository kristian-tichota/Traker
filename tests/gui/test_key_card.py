import pytest
from PyQt6.QtCore import QRect, Qt

from src.gui.components.key_card import KeyCard

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
