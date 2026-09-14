import pytest

from src.desktop.activities import DOCUMENT, VIDEO, readout_of
from src.domain.media import (PAGES, Place, TIME, UNKNOWN, as_elapsed,
                              away_ms, fraction, how_far, opens_in)

pytestmark = pytest.mark.exact


class TestAPositionAsTheMemberReadsIt:
    def test_minutes_and_seconds(self):
        assert as_elapsed(1_593_000) == "26:33"

    def test_the_hour_appears_only_once_there_is_one(self):
        assert as_elapsed(5_195_000) == "1:26:35"
        assert as_elapsed(3_599_000) == "59:59"

    def test_the_start_of_something(self):
        assert as_elapsed(0) == "0:00"

    def test_and_a_second_is_not_rounded_up_to_the_next_one(self):
        assert as_elapsed(59_999) == "0:59"


class TestHowFarIntoAVideo:
    def test_it_says_where_and_out_of_what(self):
        assert how_far(Place(1_593_000, 5_195_000)) == "26:33 / 1:26:35"

    def test_the_proportion_is_the_same_two_numbers(self):
        place = Place(1_593_000, 5_195_000)

        assert fraction(place) == pytest.approx(1_593_000 / 5_195_000)

    def test_a_length_nothing_knows_says_nothing(self):
        assert how_far(Place(12_000, 0)) == UNKNOWN
        assert fraction(Place(12_000, 0)) == 0.0

    def test_nothing_stored_at_all_is_the_same_answer(self):
        assert how_far(Place()) == UNKNOWN

    def test_a_position_past_the_end_is_the_end(self):
        assert how_far(Place(5_200_000, 5_195_000)) == "1:26:35 / 1:26:35"
        assert fraction(Place(5_200_000, 5_195_000)) == 1.0


class TestHowFarIntoADocument:
    def test_pages_are_counted_from_one(self):
        assert how_far(Place(41, 310), PAGES) == "42 / 310"

    def test_the_first_page_is_not_none_of_it(self):
        assert fraction(Place(0, 310), PAGES) == pytest.approx(1 / 310)

    def test_the_last_page_is_all_of_it(self):
        assert fraction(Place(309, 310), PAGES) == 1.0

    def test_a_document_nothing_is_known_about(self):
        assert how_far(Place(4, 0), PAGES) == UNKNOWN


class TestWhichReadoutAKindGets:
    def test_a_video_is_a_clock(self):
        assert readout_of(VIDEO) == TIME

    def test_a_document_is_a_count_of_pages(self):
        assert readout_of(DOCUMENT) == PAGES

BREAK_MS, LONG_MS = 30 * 60_000, 60 * 60_000


class TestHowLongABreakKeepsToItself:
    def test_an_ordinary_break_waits_what_the_profile_says(self):
        assert away_ms(300, BREAK_MS, BREAK_MS) == 300_000

    def test_a_long_break_waits_in_proportion_to_its_length(self):
        assert away_ms(300, LONG_MS, BREAK_MS) == 600_000

    def test_nothing_configured_is_a_break_that_opens_at_once(self):
        assert away_ms(0, BREAK_MS, BREAK_MS) == 0

    def test_a_wait_longer_than_the_break_is_the_break(self):
        assert away_ms(3600, BREAK_MS, BREAK_MS) == BREAK_MS

    def test_a_split_with_no_ordinary_break_in_it_is_not_scaled(self):
        assert away_ms(300, LONG_MS, 0) == 300_000


class TestWhatIsLeftOfTheWait:
    def test_the_moment_a_break_lands(self):
        assert opens_in(300_000, BREAK_MS, BREAK_MS) == 300_000

    def test_part_way_through_it(self):
        assert opens_in(300_000, BREAK_MS, BREAK_MS - 89_000) == 211_000

    def test_once_it_is_up_there_is_nothing_left_of_it(self):
        assert opens_in(300_000, BREAK_MS, BREAK_MS - 300_000) == 0

    def test_and_it_does_not_go_negative_for_the_rest_of_the_break(self):
        assert opens_in(300_000, BREAK_MS, 1_000) == 0

    def test_a_break_that_waits_for_nothing_is_open_from_the_start(self):
        assert opens_in(0, BREAK_MS, BREAK_MS) == 0

    def test_it_is_said_the_way_every_other_position_is(self):
        assert as_elapsed(opens_in(300_000, BREAK_MS, BREAK_MS - 29_000)) == "4:31"
