import datetime

import pytest

from src.domain.clock import minutes_covered

pytestmark = pytest.mark.exact


def at(text):
    return datetime.datetime.fromisoformat(text)


class TestTheMinutesASpanCovers:
    def test_every_whole_minute_of_it(self):
        covered = minutes_covered(at("2026-09-13T10:00:30"), at("2026-09-13T10:05:30"))

        assert covered == [("2026-09-13", 601), ("2026-09-13", 602),
                           ("2026-09-13", 603), ("2026-09-13", 604),
                           ("2026-09-13", 605)]

    def test_a_span_inside_one_minute_covers_none_of_them(self):
        assert minutes_covered(at("2026-09-13T10:00:10"),
                               at("2026-09-13T10:00:50")) == []

    def test_a_span_over_midnight_carries_both_dates(self):
        covered = minutes_covered(at("2026-09-13T23:58:30"), at("2026-09-14T00:01:00"))

        assert covered == [("2026-09-13", 1439), ("2026-09-14", 0),
                           ("2026-09-14", 1)]
