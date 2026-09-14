import pytest

from src.database.rows import DailyTotals

from src.gui.graphs.base import BaseGraphView
from src.gui.graphs.caffeine_graph import CaffeineGraphView
from src.gui.graphs.exercise_graph import ExerciseGraphView
from src.gui.graphs.food_graph import FoodGraphView
from src.gui.graphs.heatmap import ActivityHeatmapView
from src.gui.graphs.supplement_graph import SupplementGraphView

pytestmark = pytest.mark.gui

ALL_VIEWS = [FoodGraphView, ExerciseGraphView, CaffeineGraphView,
             SupplementGraphView, ActivityHeatmapView]


@pytest.fixture
def make_view(qapp, profile_path, recording_db):
    built = []

    def _make(cls):
        view = cls(recording_db)
        view.resize(900, 600)
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


def _drain(qapp, timeout_s=5.0):
    import time

    from PyQt6.QtCore import QThreadPool

    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        qapp.processEvents()
        if QThreadPool.globalInstance().activeThreadCount() == 0:
            break
        time.sleep(0.005)
    qapp.processEvents()


def _wait_for_render(qapp, view, timeout_s=15.0):
    import time

    from PyQt6.QtCore import QThreadPool

    pool = QThreadPool.globalInstance()
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        qapp.processEvents()
        if (pool.activeThreadCount() == 0 and view.canvas._image is not None
                and not view._needs_bg_recapture):
            return
        time.sleep(0.002)
    raise AssertionError(f"{type(view).__name__} never finished a render")


def _rendered(view, data):
    view.reset_axes()
    view.draw_chart(data)
    view.canvas.draw_offscreen()
    view.figure_bg = view.canvas.copy_from_bbox(view.fig.bbox)
    view._needs_bg_recapture = False
    return view


@pytest.mark.parametrize("view_class", ALL_VIEWS, ids=lambda c: c.__name__)
class TestEveryChartGetsTheSameShell:
    def test_it_is_built_on_the_shared_shell(self, make_view, view_class):
        assert isinstance(make_view(view_class), BaseGraphView)

    def test_the_canvas_is_the_last_thing_in_the_layout(self, make_view, view_class):
        view = make_view(view_class)

        last = view.main_layout.itemAt(view.main_layout.count() - 1).widget()
        assert last is view.canvas, "controls sit above the canvas, never below"

    def test_the_figure_is_solarized(self, make_view, view_class):
        from src.config import PALETTE

        assert make_view(view_class).fig.get_facecolor() == pytest.approx(
            tuple(int(PALETTE['base3'].lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
        )

    def test_a_resize_invalidates_the_cached_background(self, make_view, view_class):
        view = make_view(view_class)
        view._needs_bg_recapture = False

        view.on_resize(event=None)

        assert view._needs_bg_recapture

    def test_an_idle_chart_does_no_work(self, make_view, view_class):
        view = make_view(view_class)
        view.anim_nodes.clear()
        view.figure_bg = None

        view.update_animation()

        assert view.figure_bg is None, "no background captured for an empty chart"
        assert view.master_clock == 0.0, "and the clock did not advance"

    def test_the_pulse_can_be_stopped(self, make_view, view_class):
        view = make_view(view_class)
        view.pulse_timer.start(view.PULSE_INTERVAL_MS)

        view.shutdown()

        assert not view.pulse_timer.isActive()

    def test_a_refresh_with_nothing_logged_still_draws(self, make_view, view_class):
        view = make_view(view_class)

        view.refresh()

        assert view.canvas is not None

    @pytest.mark.accessibility
    def test_a_refresh_reads_builds_and_rasterises_on_one_worker_call(
            self, make_view, view_class, qapp):
        view = make_view(view_class)
        view.show()
        view.refresh()

        _wait_for_render(qapp, view)

        assert view.canvas._image is not None, "no render reached the canvas"
        assert not view._needs_bg_recapture, "the blit cache was left stale"
        assert view.figure_bg is not None, "the worker captured no background"

    @pytest.mark.accessibility
    def test_nothing_a_chart_draws_runs_on_the_interface_thread(
            self, make_view, view_class, qapp):
        import threading

        view = make_view(view_class)
        view.show()
        interface_thread = threading.get_ident()
        ran_on = {}

        for step in ("read_chart_data", "reset_axes", "draw_chart"):
            original = getattr(view, step)

            def record(*args, _step=step, _original=original, **kwargs):
                ran_on.setdefault(_step, set()).add(threading.get_ident())
                return _original(*args, **kwargs)

            setattr(view, step, record)

        view.refresh()
        _wait_for_render(qapp, view)

        assert set(ran_on) == {"read_chart_data", "reset_axes", "draw_chart"}, \
            f"a step never ran: {sorted(ran_on)}"
        for step, threads in ran_on.items():
            assert interface_thread not in threads, \
                f"{step} ran on the interface thread"

    def test_a_chart_that_has_been_shut_down_starts_no_more_work(
            self, make_view, view_class, settled):
        view = make_view(view_class)
        settled()
        view.shutdown()

        assert view.fetch(lambda: None, print) is None
        assert view._render(read=True) is None

    @pytest.mark.accessibility
    def test_a_hidden_chart_owes_its_render_rather_than_drawing_it(
            self, make_view, view_class):
        view = make_view(view_class)
        assert not view.isVisible()

        view.on_resize()
        assert view._owed_render is False
        assert not view._resize_timer.isActive(), "a hidden chart renders nothing"

        assert view.refresh() is None
        assert view._owed_render is True, "a read is owed, not just a redraw"

    @pytest.mark.accessibility
    def test_showing_it_pays_what_it_owes(self, make_view, view_class, qapp):
        view = make_view(view_class)
        view.refresh()
        assert view._owed_render is True

        view.show()

        assert view._resize_timer.isActive()
        _wait_for_render(qapp, view)
        assert view.canvas._image is not None


class TestASupersededRenderIsDiscarded:
    def test_the_older_answer_never_draws(self, make_view):
        view = make_view(ExerciseGraphView)
        view.show()
        drawn = []
        view.draw_chart = drawn.append

        stale = view._render_generation
        view._render_generation += 1

        view._read_and_render(stale, False, view.canvas.size(), 1.0)

        assert drawn == [], "a superseded render drew over a live layout"

    def test_the_older_answer_is_not_put_on_screen(self, make_view):
        from src.gui.graphs.base import _NOTHING

        view = make_view(FoodGraphView)
        view.canvas.set_image(None)
        stale_rows = ["rows a superseded render read"]

        view._on_render_finished((view._render_generation - 1, stale_rows, None, "image"))

        assert view.canvas._image is None
        assert view._last_payload is _NOTHING, \
            "a superseded render's rows became what a resize would redraw"


class TestTheClock:
    def test_the_wave_stays_within_zero_and_one(self, make_view):
        view = make_view(FoodGraphView)

        for step in range(50):
            view.master_clock = step * 0.05
            assert 0.0 <= view.wave(3.0) <= 1.0

    def test_a_pulse_advances_the_clock_by_one_step(self, make_view):
        view = _rendered(make_view(FoodGraphView),
                         [DailyTotals("2026-09-01", 2000.0, 140.0, 0.0, 70.0, 5.0,
                                      30.0, 40.0, 0.0, 0)])

        view.update_animation()

        assert view.master_clock == pytest.approx(view.CLOCK_STEP)

    def test_a_pulse_with_no_background_yet_does_nothing(self, make_view):
        view = _rendered(make_view(FoodGraphView),
                         [DailyTotals("2026-09-01", 2000.0, 140.0, 0.0, 70.0, 5.0,
                                      30.0, 40.0, 0.0, 0)])
        view.invalidate_background()

        view.update_animation()

        assert view.master_clock == 0.0


class TestWhatEachChartSaysForItself:
    def test_the_heatmap_pulses_faster_than_the_line_charts(self):
        assert ActivityHeatmapView.PULSE_INTERVAL_MS < FoodGraphView.PULSE_INTERVAL_MS

    def test_a_lit_hover_keeps_the_exercise_chart_animating_with_no_nodes(self, make_view):
        view = make_view(ExerciseGraphView)
        view.anim_nodes.clear()
        view.hover_nodes.clear()

        assert view.has_animation() is False

        view.hover_nodes[_StubAxes()] = _StubArtist(visible=True)

        assert view.has_animation() is True

    def test_a_lit_hover_keeps_the_heatmap_animating_with_no_nodes(self, make_view):
        view = make_view(ActivityHeatmapView)
        view.anim_nodes.clear()

        assert view.has_animation() is False

        view.hover_glow = _StubArtist(visible=True)

        assert view.has_animation() is True

    def test_the_supplement_chart_grows_tick_markers_more_than_dots(self, make_view):
        view = make_view(SupplementGraphView)
        axes = _StubAxes()
        tick, dot = _StubArtist(marker='|'), _StubArtist(marker='o')
        view.anim_nodes.extend([
            {"artist": tick, "ax": axes, "base_size": 4},
            {"artist": dot, "ax": axes, "base_size": 4},
        ])
        view.master_clock = 0.5

        view.draw_animated_artists()

        assert tick.markersize > dot.markersize


class _StubArtist:
    def __init__(self, visible=False, marker='o'):
        self._visible = visible
        self._marker = marker
        self.markersize = 0.0
        self.alpha = 0.0
        self.linewidth = 0.0

    def get_visible(self):
        return self._visible

    def get_marker(self):
        return self._marker

    def set_markersize(self, value):
        self.markersize = value

    def set_alpha(self, value):
        self.alpha = value

    def set_linewidth(self, value):
        self.linewidth = value


class _StubAxes:
    def draw_artist(self, artist):
        pass


class TestTheLoadingArcOnTheCanvas:
    def spinning(self, view):
        return view.canvas.spinner._timer.isActive()

    def test_a_dispatched_render_starts_the_wait(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view.canvas.spinner.stop()

        view.refresh()

        assert self.spinning(view)

    def test_the_render_landing_ends_it(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()

        _wait_for_render(qapp, view)

        assert not self.spinning(view)
        assert view.canvas.spinner.phase is None

    def test_a_hidden_chart_starts_no_wait(self, make_view, qapp):
        view = make_view(FoodGraphView)

        view.refresh()

        assert not self.spinning(view)

    def test_hiding_a_chart_mid_render_stops_the_arc(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view._renders_out = 1
        view.canvas.spinner.start()

        view.hide()

        assert not self.spinning(view)

    def test_showing_it_again_resumes_the_arc_while_a_render_is_out(
            self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view.hide()
        view._renders_out = 1

        view.show()

        assert self.spinning(view)
        view._renders_out = 0
        view.canvas.spinner.stop()

    def test_showing_it_with_nothing_out_resumes_no_arc(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _wait_for_render(qapp, view)
        view.hide()

        view.show()

        assert not self.spinning(view)

    def test_the_last_render_out_is_what_ends_the_wait(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view._renders_out = 2
        view.canvas.spinner.start()

        view._render_settled()

        assert self.spinning(view), "one of two back is not the end of the wait"

        view._render_settled()

        assert not self.spinning(view)

    def test_a_render_that_raised_ends_the_wait(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view._renders_out = 1
        view.canvas.spinner.start()

        view._on_render_failed((RuntimeError("boom"), "traceback"))

        assert not self.spinning(view)

    def test_shutdown_stops_the_arc(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _drain(qapp)
        view._renders_out = 1
        view.canvas.spinner.start()

        view.shutdown()

        assert not self.spinning(view)


class TestWhereTheArcSits:
    def test_it_is_centred_before_the_first_render(self, make_view):
        view = make_view(FoodGraphView)
        view.canvas.resize(600, 400)

        centre = view.canvas._spinner_centre()

        assert centre.x() == pytest.approx(view.canvas.rect().center().x(), abs=1)
        assert centre.y() == pytest.approx(view.canvas.rect().center().y(), abs=1)

    def test_it_moves_to_the_corner_once_a_chart_is_up(self, make_view, qapp):
        view = make_view(FoodGraphView)
        view.show()
        _wait_for_render(qapp, view)
        assert view.canvas._image is not None

        centre = view.canvas._spinner_centre()

        assert centre.x() > view.canvas.rect().center().x()
        assert centre.y() < view.canvas.rect().center().y()

    def test_the_corner_leaves_room_for_the_whole_arc(self, make_view, qapp):
        from src.gui.animations import SPINNER_RADIUS_PX, SPINNER_THICKNESS_PX

        view = make_view(FoodGraphView)
        view.show()
        _wait_for_render(qapp, view)

        centre = view.canvas._spinner_centre()
        box = view.canvas.rect()
        needed = SPINNER_RADIUS_PX + SPINNER_THICKNESS_PX

        assert centre.x() + needed <= box.right()
        assert centre.y() - needed >= box.top()

    def test_it_reaches_pixels_over_a_finished_chart(self, make_view, qapp):
        from PyQt6.QtGui import QPixmap

        from src.gui.animations import SPINNER_GRACE_MS

        view = make_view(FoodGraphView)
        view.show()
        _wait_for_render(qapp, view)
        canvas = view.canvas

        def shot():
            pixmap = QPixmap(canvas.size())
            canvas.render(pixmap)
            return pixmap.toImage()

        quiet = shot()
        canvas.spinner.start()
        canvas.spinner.started_at -= (SPINNER_GRACE_MS + 40) / 1000.0
        canvas.spinner.advance()
        qapp.processEvents()
        waiting = shot()
        canvas.spinner.stop()

        moved = [y for y in range(quiet.height())
                 if any(quiet.pixel(x, y) != waiting.pixel(x, y)
                        for x in range(quiet.width()))]
        assert moved, "the arc must reach some pixel or it says nothing"
        assert len(moved) < canvas.height() // 4, (
            f"{len(moved)} of {canvas.height()} pixel rows moved — the arc is "
            f"meant to be a corner of the chart, not a layer over it")
