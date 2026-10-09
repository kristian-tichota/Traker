import datetime

import pytest

from src.database.rows import SupplementLogRow
from src.gui.graphs.caffeine_graph import CaffeineGraphView
from src.gui.graphs.supplement_graph import SupplementGraphView, daily_amounts, log_column_for

pytestmark = pytest.mark.gui

LOG_COLUMNS = [name for name in SupplementLogRow._fields
               if name.endswith(("_mcg", "_mg", "_g", "_iu"))]


def supplement_row(date, **nutrients):
    values = dict.fromkeys(LOG_COLUMNS, 0.0)
    values.update(nutrients)
    return SupplementLogRow.from_server(
        [1, date, "Morning Stack", None, 1.0] + [values[name] for name in LOG_COLUMNS])


@pytest.fixture
def make_view(qapp, profile_path, recording_db):
    built = []

    def _make(cls):
        view = cls(recording_db)
        view.resize(900, 600)
        view.show()
        view.pulse_timer.stop()
        built.append(view)
        return view

    yield _make

    from PyQt6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    for view in built:
        view.shutdown()
        view.deleteLater()


class TestANutrientIsMatchedByItsKey:
    def test_the_key_names_the_column_whatever_the_unit_suffix(self):
        assert log_column_for({"key": "b12", "name": "B12 (mcg)"}, LOG_COLUMNS) == "b12_mcg"

    def test_a_multi_word_key_is_matched(self):
        assert log_column_for(
            {"key": "l_theanine", "name": "L-Theanine (mg)"}, LOG_COLUMNS) == "l_theanine_mg"

    def test_a_one_letter_key_does_not_swallow_a_longer_column(self):
        assert log_column_for({"key": "c", "name": "C (mg)"}, LOG_COLUMNS) == "c_mg"

    def test_a_renamed_label_still_finds_its_column(self):
        assert log_column_for(
            {"key": "b12", "name": "Vitamin B12 (mcg)"}, LOG_COLUMNS) == "b12_mcg"

    def test_a_label_that_spells_the_column_works_without_a_key(self):
        assert log_column_for(
            {"key": "vitamin_b12", "name": "B12 (mcg)"}, LOG_COLUMNS) == "b12_mcg"

    def test_a_target_naming_nothing_in_the_log_is_answered_with_none(self):
        assert log_column_for({"key": "selenium", "name": "Selenium (mcg)"},
                              LOG_COLUMNS) is None


class TestSupplementHistoryIsChartedAgainstTheTarget:
    B12_TARGET = 500.0

    @pytest.fixture
    def b12_target(self, profile_path):
        """Declare a B12 target, which a generated profile leaves at zero."""
        import src.profile as profile_module

        profile_module.UserProfile()
        written = profile_path.read_text(encoding="utf-8")
        declared = '[supplement_targets.b12]\nname = "B12 (mcg)"\ntarget = '
        assert f"{declared}0.0" in written, "the [supplement_targets] template has moved"
        profile_path.write_text(
            written.replace(f"{declared}0.0", f"{declared}{self.B12_TARGET}"),
            encoding="utf-8")
        profile_module.reload_profile()

    @pytest.fixture
    def rendered(self, b12_target, make_view, recording_db):
        def _render(rows, window):
            view = make_view(SupplementGraphView)
            view.rolling_period = window
            view.draw_chart(rows)
            return view

        return _render

    @staticmethod
    def days_ago(count):
        return (datetime.date.today() - datetime.timedelta(days=count)).isoformat()

    def test_the_history_runs_from_the_first_log_to_today_with_gaps_as_zero(self):
        dates, amounts = daily_amounts(
            [supplement_row(self.days_ago(10), b12_mcg=self.B12_TARGET),
             supplement_row(self.days_ago(0), b12_mcg=self.B12_TARGET)],
            ["b12_mcg"], datetime.date.today())

        assert dates[0] == self.days_ago(10)
        assert dates[-1] == self.days_ago(0)
        assert list(amounts[0]) == [self.B12_TARGET] + [0.0] * 9 + [self.B12_TARGET]

    def test_a_daily_dose_holds_the_weekly_average_at_the_target(self, rendered):
        view = rendered([supplement_row(self.days_ago(day), b12_mcg=self.B12_TARGET)
                         for day in range(10)], window=7)

        (b12,) = view.hover_data.values()
        assert len(b12["amounts"]) == 10 - 7 + 1
        assert b12["amounts"] == pytest.approx([self.B12_TARGET] * 4)
        assert "100%" in SupplementGraphView.hover_text(b12, 0)

    def test_a_target_of_zero_is_not_charted(self, make_view):
        view = make_view(SupplementGraphView)

        view.draw_chart([supplement_row(self.days_ago(0), b12_mcg=1000.0)])

        assert view.hover_data == {}
        assert view.axes == []

    def test_the_chart_draws_the_whole_ledger(self, b12_target, make_view, recording_db,
                                              settled):
        recording_db.supplement_logs = [supplement_row(self.days_ago(90), b12_mcg=1.0)]
        recording_db.settings["supplement_graph_period"] = "7 Days (Weekly Average)"
        view = make_view(SupplementGraphView)

        view.refresh()
        settled()

        (b12,) = view.hover_data.values()
        assert b12["dates"][0] == self.days_ago(90 - 6)

    def test_the_default_window_is_thirty_days(self, make_view, settled):
        view = make_view(SupplementGraphView)
        settled()

        assert view.rolling_period == 30

    def test_the_window_follows_its_own_stored_preference(self, make_view, recording_db,
                                                           settled):
        recording_db.settings["supplement_graph_period"] = "7 Days (Weekly Average)"

        view = make_view(SupplementGraphView)
        settled()

        assert view.rolling_period == 7

    def test_a_window_it_does_not_offer_falls_back_to_thirty_days(self, make_view,
                                                                   recording_db, settled):
        recording_db.settings["supplement_graph_period"] = "1 Day (Raw)"

        view = make_view(SupplementGraphView)
        settled()

        assert view.rolling_period == 30


class TestTheCaffeineTooltipStatesTheDistanceBothWays:
    @pytest.fixture
    def view(self, make_view):
        return make_view(CaffeineGraphView)

    def a_day(self, residual):
        return {"residual": residual, "total": residual * 2, "logs": 1}

    def test_a_breach_is_named_with_its_size(self, view):
        threshold = float(view.profile.get_metric("goals", "max_sleep_caffeine", 20.0))

        text = view.hover_text("2026-09-05", self.a_day(threshold + 12.0))

        assert "+12 mg over threshold" in text

    def test_a_safe_day_is_told_its_headroom(self, view):
        threshold = float(view.profile.get_metric("goals", "max_sleep_caffeine", 20.0))

        text = view.hover_text("2026-09-05", self.a_day(threshold - 8.0))

        assert "8 mg under threshold" in text

    def test_the_date_is_in_the_households_format(self, view):
        assert "05.09.2026" in view.hover_text("2026-09-05", self.a_day(1.0))

    def test_the_residual_is_what_the_day_is_named_by(self, view):
        assert "Est. at Sleep: 17 mg" in view.hover_text("2026-09-05", self.a_day(17.0))

    def test_the_chart_asks_only_for_the_thirty_days_it_draws(
        self, view, recording_db, settled
    ):
        view.refresh()
        settled()

        expected = (datetime.date.today()
                    - datetime.timedelta(days=CaffeineGraphView.WINDOW_DAYS - 1)).isoformat()
        assert ("beverage_logs", expected) in recording_db.since_asked
