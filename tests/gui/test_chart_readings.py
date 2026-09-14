import datetime

import pytest

from src.database.rows import SupplementLogRow
from src.gui.graphs.caffeine_graph import CaffeineGraphView
from src.gui.graphs.supplement_graph import SupplementGraphView, log_column_for

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


class TestSaturationIsMeasuredAgainstToday:
    @pytest.fixture
    def rendered(self, make_view, recording_db):
        def _render(rows):
            view = make_view(SupplementGraphView)
            view.draw_chart(rows)
            return view

        return _render

    def test_a_full_dose_today_reads_as_reached(self, rendered):
        today = datetime.date.today().isoformat()

        view = rendered([supplement_row(today, b12_mcg=500.0)])

        b12 = next(entry for entry in view.hover_data.values()
                   if entry["name"].startswith("B12"))
        assert b12["pct"] == pytest.approx(100.0)

    def test_it_is_not_diluted_by_the_days_before_it(self, rendered):
        today = datetime.date.today().isoformat()

        view = rendered([supplement_row(today, b12_mcg=500.0)])

        b12 = next(entry for entry in view.hover_data.values()
                   if entry["name"].startswith("B12"))
        assert b12["avg"] == pytest.approx(500.0 / SupplementGraphView.WINDOW_DAYS)
        assert b12["pct"] > b12["avg"] / b12["target"] * 100.0

    def test_nothing_today_reads_as_not_reached_however_good_the_week_was(self, rendered):
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        view = rendered([supplement_row(yesterday, b12_mcg=500.0)])

        b12 = next(entry for entry in view.hover_data.values()
                   if entry["name"].startswith("B12"))
        assert b12["pct"] == pytest.approx(0.0)

    def test_the_week_is_still_carried_for_the_streak(self, rendered):
        view = rendered([])

        assert all(len(entry["daily"]) == SupplementGraphView.WINDOW_DAYS
                   for entry in view.hover_data.values())

    def test_the_chart_asks_only_for_the_window_it_draws(self, make_view, recording_db, settled):
        view = make_view(SupplementGraphView)

        view.refresh()
        settled()

        expected = (datetime.date.today()
                    - datetime.timedelta(days=SupplementGraphView.WINDOW_DAYS - 1)).isoformat()
        assert ("supplement_logs", expected) in recording_db.since_asked


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
