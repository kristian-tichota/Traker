import datetime

import pytest

from src.database.rows import PomodoroDailyRow
from PyQt6.QtWidgets import QWidget

from src.gui.views.pomodoro_view import StressCalendar, read_day

pytestmark = pytest.mark.gui


@pytest.fixture
def calendar_factory(qapp, profile_path, recording_db):
    built = []

    def _build():
        host = QWidget()
        calendar = StressCalendar(recording_db, host)
        calendar.anim_timer.stop()
        built.append((calendar, host))
        return calendar

    yield _build
    for calendar, host in built:
        calendar.deleteLater()
        host.deleteLater()


def summary_row(date, focus=0, rest=0, focus_ot=0, rest_ot=0):
    return PomodoroDailyRow.from_server([date, focus, rest, focus_ot, rest_ot])


class TestFormula:
    @pytest.mark.exact
    def test_the_index_is_penalty_over_recovery(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(
            ([summary_row("2026-09-05", focus=60, rest=30, focus_ot=10, rest_ot=20)], {})
        )

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(
            (60 + 10) / (30 + 20))

    @pytest.mark.exact
    def test_a_second_of_overtime_costs_a_second_of_focus(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data((
            [summary_row("2026-09-05", focus=20, rest=10),
             summary_row("2026-09-06", focus_ot=20, rest_ot=10)],
            {},
        ))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(2.0)
        assert calendar.data_map["2026-09-06"]["dsi"] == pytest.approx(2.0)

    @pytest.mark.exact
    def test_the_prescribed_split_lands_on_the_sustainable_boundary(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(
            ([summary_row("2026-09-05", focus=30, rest=30)], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(1.0)

    @pytest.mark.exact
    def test_a_day_with_no_recovery_reports_the_penalty_rather_than_dividing_by_zero(
        self, calendar_factory
    ):
        calendar = calendar_factory()

        calendar.apply_summary_data(([summary_row("2026-09-05", focus=30)], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(30 * 60)

    def test_a_day_with_nothing_logged_scores_zero_and_is_not_active(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(([summary_row("2026-09-05")], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == 0
        assert calendar.data_map["2026-09-05"]["active"] is False

    def test_a_day_with_only_rest_is_restorative(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(([summary_row("2026-09-05", rest=60)], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(0.0)
        assert calendar.data_map["2026-09-05"]["active"] is True

    @pytest.mark.parametrize(
        "row, reading",
        [(summary_row("d", focus=30, rest=60), "sustainable"),
         (summary_row("d", focus=60, rest=60), "sustainable"),
         (summary_row("d", focus=72, rest=60), "borderline"),
         (summary_row("d", focus=90, rest=60), "borderline"),
         (summary_row("d", focus=120, rest=60), "overloaded")],
    )
    def test_the_colour_bands_follow_the_index(self, calendar_factory, row, reading):
        calendar = calendar_factory()
        calendar.apply_summary_data(([row], {}))

        index = calendar.data_map["d"]["dsi"]
        bands = {"sustainable": index <= 1.0,
                 "borderline": 1.0 < index <= 1.5,
                 "overloaded": index > 1.5}
        assert bands[reading], f"index {index} did not read as {reading}"


class TestEveryDayIsScoredTheSameWay:
    def test_two_calendars_score_one_day_alike(self, calendar_factory):
        first, second = calendar_factory(), calendar_factory()
        row = summary_row("2026-09-05", focus=60, rest=60)

        first.apply_summary_data(([row], {}))
        second.apply_summary_data(([row], {}))

        assert first.data_map["2026-09-05"]["dsi"] == pytest.approx(1.0)
        assert second.data_map["2026-09-05"]["dsi"] == pytest.approx(1.0)

    def test_stored_history_is_recomputed_on_display_not_rewritten(self, calendar_factory):
        calendar = calendar_factory()
        row = summary_row("2026-09-05", focus=60, rest=60)

        calendar.apply_summary_data(([row], {}))
        calendar.apply_summary_data(([row], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(1.0)
        assert row == summary_row("2026-09-05", focus=60, rest=60), \
            "the stored minutes are untouched"

    def test_a_calendar_with_no_host_at_all_still_scores(self, qapp, profile_path,
                                                        recording_db):
        calendar = StressCalendar(recording_db, None)
        calendar.anim_timer.stop()

        calendar.apply_summary_data(([summary_row("2026-09-05", focus=60, rest=60)], {}))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(1.0)
        calendar.deleteLater()


class TestOverrides:
    def test_an_override_is_shown_in_place_of_the_computed_index(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data((
            [summary_row("2026-09-05", focus=120, rest=60)], {"2026-09-05": 0.4},
        ))

        day = calendar.data_map["2026-09-05"]
        assert day["override_dsi"] == 0.4
        assert day["is_overridden"] is True

    def test_the_day_is_marked_as_overridden_rather_than_silently_replaced(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data((
            [summary_row("2026-09-05", focus=120, rest=60)], {"2026-09-05": 0.4},
        ))

        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(2.0), (
            "the computed index must survive alongside the override"
        )

    def test_overriding_a_day_with_no_history_makes_it_active(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(([], {"2026-09-05": 1.2}))

        day = calendar.data_map["2026-09-05"]
        assert day["active"] is True
        assert day["override_dsi"] == 1.2
        assert day["dsi"] == 0.0

    def test_clearing_an_override_returns_the_computed_index(self, calendar_factory):
        calendar = calendar_factory()
        rows = [summary_row("2026-09-05", focus=120, rest=60)]
        calendar.apply_summary_data((rows, {"2026-09-05": 0.4}))

        calendar.apply_summary_data((rows, {}))

        assert "override_dsi" not in calendar.data_map["2026-09-05"]
        assert calendar.data_map["2026-09-05"]["dsi"] == pytest.approx(2.0)

    def test_other_days_are_unaffected_by_an_override(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data((
            [summary_row("2026-09-05", focus=120, rest=60),
             summary_row("2026-09-04", focus=60, rest=60)],
            {"2026-09-05": 0.4},
        ))

        assert "is_overridden" not in calendar.data_map["2026-09-04"]


class TestRefresh:
    def test_the_calendar_reads_both_the_summary_and_the_overrides(self, calendar_factory, recording_db):
        calendar = calendar_factory()

        summary, overrides = read_day(calendar.db)

        assert summary == []
        assert overrides == {}

    def test_a_client_without_overrides_still_works(self, calendar_factory):
        calendar = calendar_factory()

        class OverrideFreeDb:
            def get_pomodoro_daily_summary(self):
                return [summary_row("2026-09-05", focus=60, rest=60)]

        calendar.db = OverrideFreeDb()

        summary, overrides = read_day(calendar.db)

        assert overrides == {}
        assert summary[0][1] == 60

    def test_applying_a_new_summary_replaces_the_previous_one(self, calendar_factory):
        calendar = calendar_factory()
        calendar.apply_summary_data(([summary_row("2026-09-04", focus=60, rest=60)], {}))

        calendar.apply_summary_data(([summary_row("2026-09-05", focus=60, rest=60)], {}))

        assert list(calendar.data_map) == ["2026-09-05"]

    def test_an_empty_history_leaves_an_empty_calendar(self, calendar_factory):
        calendar = calendar_factory()

        calendar.apply_summary_data(([], {}))

        assert calendar.data_map == {}


class TestLiveIndex:
    @pytest.mark.exact
    @pytest.mark.parametrize(
        "focus_ms, rest_ms, focus_ot_ms, rest_ot_ms",
        [(3_600_000, 1_800_000, 0, 0),
         (3_600_000, 1_800_000, 600_000, 1_200_000),
         (60_000, 60_000, 0, 0)],
    )
    def test_the_live_ratio_matches_the_stored_one(
        self, calendar_factory, focus_ms, rest_ms, focus_ot_ms, rest_ot_ms
    ):
        calendar = calendar_factory()
        today = datetime.date.today().isoformat()

        calendar.apply_summary_data(([summary_row(
            today,
            focus=focus_ms // 60000, rest=rest_ms // 60000,
            focus_ot=focus_ot_ms // 60000, rest_ot=rest_ot_ms // 60000,
        )], {}))

        penalty = (focus_ms + focus_ot_ms) / 1000.0
        recovery = (rest_ms + rest_ot_ms) / 1000.0
        live = penalty / recovery if recovery > 0 else penalty

        assert calendar.data_map[today]["dsi"] == pytest.approx(live)
