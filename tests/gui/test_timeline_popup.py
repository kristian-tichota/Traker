import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap, QWheelEvent

from src.gui.components.timeline_popup import TimelineCanvas, TimelinePopupWidget

pytestmark = pytest.mark.gui

A_DAY = {
    minute: ("focus" if minute % 2 else "rest", "Deep Work")
    for minute in range(8 * 60, 12 * 60)
}

SOME_EVENTS = [
    ("2026-09-05T09:15:00", "pause", 0),
    ("2026-09-05T09:47:30", "skip", 0),
    ("2026-09-05T10:00:00", "mode_switch_deep_work", 0),
]


@pytest.fixture
def canvas(qapp):
    widget = TimelineCanvas()
    widget.resize(600, 160)
    yield widget
    widget.deleteLater()


@pytest.fixture
def popup(qapp):
    widget = TimelinePopupWidget()
    widget.resize(700, 400)
    yield widget
    widget.deleteLater()


def paint(widget, qapp):
    pixmap = QPixmap(widget.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap)
    qapp.processEvents()


class TestTheDayIsDrawn:
    def test_an_empty_day_paints(self, canvas, qapp):
        canvas.set_data({}, [])

        paint(canvas, qapp)

    def test_a_full_day_of_heartbeats_paints(self, canvas, qapp):
        canvas.set_data(A_DAY, SOME_EVENTS)

        paint(canvas, qapp)

    def test_four_events_at_one_moment_stack(self, canvas, qapp):
        canvas.set_data(A_DAY, [("2026-09-05T09:15:00", "pause", 0)] * 4)

        paint(canvas, qapp)

    def test_more_than_four_events_at_one_moment_collapse(self, canvas, qapp):
        canvas.set_data(A_DAY, [("2026-09-05T09:15:00", "pause", 0)] * 9)

        paint(canvas, qapp)

    @pytest.mark.parametrize("timestamp", [
        "not-a-timestamp", "2026-09-05", "2026-09-05T25:99:99", "", None, 17,
    ])
    def test_an_unreadable_timestamp_is_skipped_rather_than_fatal(
        self, canvas, qapp, timestamp
    ):
        canvas.set_data(A_DAY, [(timestamp, "pause", 0)])

        paint(canvas, qapp)

    def test_an_unknown_state_does_not_stop_the_paint(self, canvas, qapp):
        canvas.set_data({540: ("something_new", "Deep Work")}, [])

        paint(canvas, qapp)


class TestZoomingAndPanning:
    def test_the_whole_day_is_shown_first(self, canvas):
        canvas.set_data(A_DAY, SOME_EVENTS)

        assert (canvas.view_start, canvas.view_end) == (0.0, 1440.0)

    def test_zooming_in_narrows_the_window(self, canvas, qapp):
        canvas.set_data(A_DAY, SOME_EVENTS)

        canvas.wheelEvent(QWheelEvent(
            QPointF(300, 80), QPointF(300, 80), QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False))
        paint(canvas, qapp)

        assert canvas.view_end - canvas.view_start < 1440.0

    def test_a_double_click_returns_to_the_whole_day(self, canvas, qapp):
        canvas.set_data(A_DAY, SOME_EVENTS)
        canvas.view_start, canvas.view_end = 500.0, 600.0

        canvas.mouseDoubleClickEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick, QPointF(300, 80),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        paint(canvas, qapp)

        assert (canvas.view_start, canvas.view_end) == (0.0, 1440.0)

    def test_panning_moves_the_window_without_resizing_it(self, canvas, qapp):
        canvas.set_data(A_DAY, SOME_EVENTS)
        canvas.view_start, canvas.view_end = 480.0, 720.0
        width_before = canvas.view_end - canvas.view_start

        canvas.mousePressEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPointF(300, 80),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        canvas.mouseMoveEvent(QMouseEvent(
            QMouseEvent.Type.MouseMove, QPointF(200, 80),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        canvas.mouseReleaseEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease, QPointF(200, 80),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))
        paint(canvas, qapp)

        assert canvas.view_end - canvas.view_start == pytest.approx(width_before)
        assert canvas.is_panning is False


class TestTheHeaderReadsAsADate:
    def test_the_day_is_shown_in_the_households_date_format(self, popup, qapp):
        popup.set_data("2026-09-05", A_DAY, SOME_EVENTS)

        assert popup.lbl_date.text() == "Timeline: 05.09.2026"

    def test_a_day_that_is_not_a_date_is_shown_as_it_came(self, popup, qapp):
        popup.set_data("whenever", {}, [])

        assert popup.lbl_date.text() == "Timeline: whenever"

    def test_setting_a_day_twice_does_not_accumulate_legend_entries(self, popup, qapp):
        popup.set_data("2026-09-05", A_DAY, SOME_EVENTS)
        first = popup.legend_row1.count(), popup.legend_row2.count()

        popup.set_data("2026-09-06", A_DAY, SOME_EVENTS)

        assert (popup.legend_row1.count(), popup.legend_row2.count()) == first

    def test_the_whole_popup_paints(self, popup, qapp):
        popup.set_data("2026-09-05", A_DAY, SOME_EVENTS)

        paint(popup, qapp)
