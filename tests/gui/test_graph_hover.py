import pytest

from src.gui.graphs.caffeine_graph import CaffeineGraphView
from src.gui.graphs.exercise_graph import ExerciseGraphView
from src.gui.graphs.heatmap import ActivityHeatmapView
from src.gui.graphs.supplement_graph import SupplementGraphView

pytestmark = pytest.mark.gui

HOVERING = [CaffeineGraphView, SupplementGraphView, ActivityHeatmapView, ExerciseGraphView]


class MoveEvent:
    def __init__(self, axes, xdata=1.0, ydata=1.0):
        self.inaxes = axes
        self.xdata, self.ydata = xdata, ydata
        self.x, self.y = 100.0, 100.0


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
    QThreadPool.globalInstance().waitForDone(2000)
    qapp.processEvents()
    for view in built:
        view.shutdown()
        view.deleteLater()


@pytest.mark.parametrize("view_class", HOVERING, ids=lambda c: c.__name__)
class TestHoveringBeforeAnyDataHasArrived:
    def test_hovering_inside_the_axes_does_not_raise(self, make_view, view_class):
        view = make_view(view_class)
        axes = getattr(view, "ax", None) or view.fig.gca()

        view.on_hover(MoveEvent(axes))

    def test_hovering_outside_the_axes_does_not_raise(self, make_view, view_class):
        view = make_view(view_class)

        view.on_hover(MoveEvent(None))

    def test_a_hover_with_no_coordinates_does_not_raise(self, make_view, view_class):
        view = make_view(view_class)
        axes = getattr(view, "ax", None) or view.fig.gca()

        view.on_hover(MoveEvent(axes, xdata=None, ydata=None))


class TestHoveringOnceDataIsThere:
    def test_the_caffeine_chart_reads_the_day_under_the_cursor(self, make_view):
        from src.database.rows import BeverageLogRow

        view = make_view(CaffeineGraphView)
        view.draw_chart([
            BeverageLogRow.from_server(
                [1, "2026-09-05", "08:30", "Black Coffee", None, 1.0, 0.0, 80.0],
                "0.0 hrs")
        ])

        view.on_hover(MoveEvent(view.ax, xdata=float(len(view.hover_dates_list) - 1)))

        assert view._last_hovered is not None

    def test_an_index_past_the_end_is_ignored(self, make_view):
        view = make_view(CaffeineGraphView)
        view.draw_chart([])

        view.on_hover(MoveEvent(view.ax, xdata=9999.0))

        assert view._last_hovered is None
