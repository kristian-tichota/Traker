import pytest

from src.domain.eye_rest import (GAZE, SET_REPETITIONS, ScreenTime, blink_set, length_ms,
                                 look_away, step_at)

pytestmark = pytest.mark.exact


def test_a_rest_is_one_blink_cycle_then_the_gaze():
    rest = look_away(20_000)

    assert [step.said for step in rest] == ["CLOSE GENTLY", "OPEN", "CLOSE GENTLY",
                                            "SQUEEZE", "OPEN", GAZE]
    assert length_ms(rest) == 28_000


def test_a_blink_set_is_fifteen_close_squeeze_opens():
    routine = blink_set()

    assert [step.said for step in routine[:3]] == ["CLOSE", "SQUEEZE", "OPEN"]
    assert len(routine) == 3 * SET_REPETITIONS
    assert length_ms(routine) == 75_000


def test_a_step_runs_to_its_last_millisecond():
    rest = look_away(20_000)

    assert step_at(rest, 0) == (0, 2000)
    assert step_at(rest, 1999) == (0, 1)
    assert step_at(rest, 2000) == (1, 1000)
    assert step_at(rest, 27_999) == (5, 1)
    assert step_at(rest, 28_000) is None


def test_screen_time_falls_due_at_the_interval():
    screen = ScreenTime(every_ms=60_000, rested_after_ms=28_000)

    assert screen.advance(59_999, 0) is False
    assert screen.advance(1, 0) is True


def test_a_glance_away_shorter_than_a_rest_is_still_screen_time():
    screen = ScreenTime(60_000, 28_000)

    screen.advance(30_000, 27_999)

    assert screen.screen_ms == 30_000


def test_eyes_away_as_long_as_a_rest_start_it_again():
    screen = ScreenTime(60_000, 28_000)
    screen.advance(50_000, 0)

    assert screen.advance(1000, 28_000) is False
    assert screen.screen_ms == 0
