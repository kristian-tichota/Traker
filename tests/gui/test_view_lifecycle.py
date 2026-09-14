import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from src.gui.graphs.food_graph import FoodGraphView
from src.gui.graphs.heatmap import ActivityHeatmapView
from src.gui.lifecycle import ShutdownMixin, stop_timers
from src.gui.main_window import MainWindow
from src.gui.views.base import BaseManagedView

pytestmark = pytest.mark.gui


class TestStopTimers:
    def test_it_stops_a_timer_the_widget_owns(self, qapp):
        widget = QWidget()
        timer = QTimer(widget)
        timer.start(50)

        stop_timers(widget)

        assert not timer.isActive()
        widget.deleteLater()

    def test_it_reaches_a_timer_inside_a_child_widget(self, qapp):
        parent = QWidget()
        child = QWidget(parent)
        timer = QTimer(child)
        timer.start(30)

        stop_timers(parent)

        assert not timer.isActive()
        parent.deleteLater()

    def test_a_timer_added_later_needs_no_new_code(self, qapp):
        class ViewWithANewTimer(ShutdownMixin, QWidget):
            def __init__(self):
                super().__init__()
                self.some_timer_nobody_listed = QTimer(self)
                self.some_timer_nobody_listed.start(10)

        view = ViewWithANewTimer()

        view.shutdown()

        assert not view.some_timer_nobody_listed.isActive()
        view.deleteLater()


class TestEveryViewAnswersShutdown:
    def test_a_table_view_does(self, qapp, profile_path, recording_db):
        view = BaseManagedView(recording_db, ["food_logs"], [[]], [{}])

        view.shutdown()

    def test_a_graph_view_stops_its_pulse(self, qapp, profile_path, recording_db):
        view = FoodGraphView(recording_db)
        view.show()
        assert view.pulse_timer.isActive()

        view.shutdown()

        assert not view.pulse_timer.isActive()
        view.deleteLater()

    def test_a_graph_view_does_not_pulse_before_it_is_ever_shown(
            self, qapp, profile_path, recording_db):
        view = FoodGraphView(recording_db)
        try:
            assert not view.pulse_timer.isActive()
        finally:
            view.shutdown()
            view.deleteLater()

    def test_the_heatmap_stops_its_faster_pulse(self, qapp, profile_path, recording_db):
        view = ActivityHeatmapView(recording_db)

        view.shutdown()

        assert not view.pulse_timer.isActive()
        view.deleteLater()


class TestTheWindowAsksAndIsAsked:
    def test_the_window_is_not_what_a_break_takes_over(self):
        for name in ("enter_strict_mode", "leave_strict_mode",
                     "show_break_media", "hide_break_media"):
            assert not hasattr(MainWindow, name), name

    def test_the_window_offers_a_public_way_to_mark_tabs_stale(self):
        assert callable(MainWindow.mark_all_tabs_stale)

    def test_a_view_reports_by_signal_rather_than_reaching_up(self):
        assert hasattr(BaseManagedView, "data_changed")
        assert hasattr(BaseManagedView, "status_message")


class TestProgressBarTargets:
    def test_setting_a_value_does_not_recompute_the_target(self, qapp, write_profile):
        from src.gui.components.calorie_bar import AnimatedProgressBar

        write_profile("[goals]\nsalt_g = 5.0\n")
        bar = AnimatedProgressBar("salt")
        assert bar.target_val == pytest.approx(5.0)

        recomputes = []
        bar._recalculate_targets = lambda: recomputes.append(1)

        bar.set_value(3.0)

        assert recomputes == []
        assert bar.actual_value == pytest.approx(3.0)
        bar.deleteLater()

    def test_reloading_targets_picks_up_an_edited_profile(self, qapp, write_profile, profile_path):
        from src.gui.components.calorie_bar import AnimatedProgressBar

        write_profile("[goals]\nsalt_g = 5.0\n")
        bar = AnimatedProgressBar("salt")

        profile_path.write_text("[goals]\nsalt_g = 3.0\n", encoding="utf-8")
        bar.reload_targets()

        assert bar.target_val == pytest.approx(3.0)
        bar.deleteLater()
