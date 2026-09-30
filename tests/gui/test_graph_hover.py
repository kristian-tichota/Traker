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

    def test_the_exercise_goal_is_found_after_a_day_logged_twice(self, make_view):
        from src.domain import formulas

        view = make_view(ExerciseGraphView)
        view.profile.data = {"exercise_goals": {
            "back-squat": {"target_weight": 100, "target_reps": "5, 5, 5"}}}
        history = [("2026-09-01", 1200.0, 90.0, "5,5,5", 80.0, 8.0),
                   ("2026-09-01", 1200.0, 91.0, "5,5,5", 80.0, 8.0),
                   ("2026-09-03", 1275.0, 95.0, "5,5,5", 85.0, 8.5)]
        view.reset_axes()
        view.draw_chart([("Back Squat", history)] + [("None", None)] * 3)
        ax = view.flat_axes[0]
        event = MoveEvent(ax)
        event.x, event.y = ax.transData.transform(
            (ax.xaxis.convert_units("Goal"), formulas.one_rep_max_or_weight(100.0, 5.0)))

        view.on_hover(event)

        assert view._last_hovered[1] == "goal"

    def test_every_hover_reads_the_date_as_the_member_writes_it(self, make_view):
        heatmap = make_view(ActivityHeatmapView)
        exercise = make_view(ExerciseGraphView)
        exercise.reset_axes()
        exercise.draw_chart([("Plank", [("2026-09-05", 0.0, 60.0, "60", 0.0, 7.0)])]
                            + [("None", None)] * 3)
        ax = exercise.flat_axes[0]
        event = MoveEvent(ax)
        event.x, event.y = ax.transData.transform((0, 60.0))

        assert "05.09.2026" in heatmap.hover_text("2026-09-05", {"extra_kcal": 0.0})
        assert "05.09.2026" in exercise._point_under(event)[3]
