import pytest
from PyQt6.QtWidgets import QWidget

from src.gui.components.calorie_bar import AnimatedProgressBar
from src.gui.graphs.food_graph import FoodGraphView
from src.gui.lifecycle import PausesWhenHidden, ShutdownMixin
from src.gui.views.pomodoro_view import StressCalendar

pytestmark = pytest.mark.gui

ANIMATED = {
    "AnimatedProgressBar": lambda db: AnimatedProgressBar("calories"),
    "StressCalendar": lambda db: StressCalendar(db),
    "FoodGraphView": lambda db: FoodGraphView(db),
}


@pytest.fixture
def make_widget(qapp, profile_path, recording_db):
    built = []

    def _make(name):
        widget = ANIMATED[name](recording_db)
        widget.resize(900, 600)
        built.append(widget)
        return widget

    yield _make

    from PyQt6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    for widget in built:
        widget.shutdown()
        widget.deleteLater()
    qapp.processEvents()


def timer_of(widget):
    return getattr(widget, widget.paused_timer_attribute)


@pytest.mark.parametrize("name", sorted(ANIMATED), ids=sorted(ANIMATED))
class TestEveryAnimatedWidgetPausesWhenHidden:
    def test_it_takes_the_shared_mixin_rather_than_its_own_pair(self, make_widget, name):
        assert isinstance(make_widget(name), PausesWhenHidden)

    def test_it_names_the_timer_the_mixin_stops(self, make_widget, name):
        widget = make_widget(name)

        assert widget.paused_timer_attribute
        assert timer_of(widget) is not None

    def test_it_animates_while_it_can_be_seen(self, make_widget, name):
        widget = make_widget(name)

        widget.show()

        assert timer_of(widget).isActive()

    def test_hiding_it_stops_the_repaint(self, make_widget, name):
        widget = make_widget(name)
        widget.show()
        assert timer_of(widget).isActive()

        widget.hide()

        assert not timer_of(widget).isActive()

    def test_showing_it_again_starts_the_repaint(self, make_widget, name):
        widget = make_widget(name)
        widget.show()
        widget.hide()

        widget.show()

        assert timer_of(widget).isActive()

    def test_it_restarts_at_its_own_interval_not_a_shared_default(
            self, make_widget, name):
        widget = make_widget(name)
        widget.show()

        assert timer_of(widget).interval() == widget.paused_timer_interval_ms

    def test_a_show_after_shutdown_does_not_restart_it(self, make_widget, name):
        widget = make_widget(name)
        widget.show()
        widget.hide()

        widget.shutdown()
        widget.show()

        assert not timer_of(widget).isActive()

    def test_shutdown_latches_so_the_check_above_is_real(self, make_widget, name):
        widget = make_widget(name)
        widget.show()

        widget.shutdown()

        assert widget.is_shut_down()


class TestTheFoodTabsBarsAreCoveredToo:
    def test_hiding_the_tab_stops_all_three(self, qapp, profile_path, recording_db):
        from src.gui.views.food_views import FoodView

        view = FoodView(recording_db)
        bars = (view.cal_bar, view.prot_bar, view.salt_bar)
        view.show()
        qapp.processEvents()
        assert all(bar.timer.isActive() for bar in bars)

        view.hide()
        qapp.processEvents()

        assert not any(bar.timer.isActive() for bar in bars)
        view.shutdown()
        view.deleteLater()


class TestTheMixinItself:
    def test_a_widget_without_shutdown_can_still_take_it(self, qapp):
        class Bare(PausesWhenHidden, QWidget):
            paused_timer_attribute = None

        widget = Bare()
        widget.shutdown()
        assert widget.is_shut_down()
        widget.deleteLater()

    def test_it_composes_with_shutdown_mixin(self, qapp):
        from PyQt6.QtCore import QTimer

        class Both(ShutdownMixin, PausesWhenHidden, QWidget):
            paused_timer_attribute = "beat"
            paused_timer_interval_ms = 17

        widget = Both()
        widget.beat = QTimer(widget)
        widget.beat.start(17)

        widget.shutdown()

        assert not widget.beat.isActive()
        assert widget.is_shut_down()
        widget.deleteLater()

    def test_a_widget_naming_no_timer_is_harmless(self, qapp):
        class Nothing(PausesWhenHidden, QWidget):
            pass

        widget = Nothing()
        widget.show()
        widget.hide()
        widget.deleteLater()
