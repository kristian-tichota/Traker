import datetime
import importlib
import time

import pytest
from PyQt6.QtCore import QElapsedTimer, QThreadPool, QTimer, Qt

pytestmark = [pytest.mark.perf, pytest.mark.gui]

INTERACTIVE_BUDGET_MS = 100.0

CANVAS_SIZE = (1330, 690)

PROBE_INTERVAL_MS = 5

RENDER_SHARE_LIMIT = 0.75

GIL_BOUND_CHARTS = {"ExerciseGraphView"}


def _settle_render(qapp, view, timeout_s=20.0):
    pool = QThreadPool.globalInstance()
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        qapp.processEvents()
        if (pool.activeThreadCount() == 0 and view.figure_bg is not None
                and not view._needs_bg_recapture):
            return
        time.sleep(0.002)
    raise AssertionError(f"{type(view).__name__} never finished a render")


def _report(label, millis, extra=""):
    print(f"\n  {label:<46} {millis:8.3f} ms  {extra}")


def _time(callable_, repeats=3):
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        callable_()
        best = min(best, (time.perf_counter() - started) * 1000)
    return best


def _interface_lateness(qapp, start_work, settle_ms=4000):
    gaps = []
    clock = QElapsedTimer()
    clock.start()
    state = {"last": 0.0}

    probe = QTimer()
    probe.setTimerType(Qt.TimerType.PreciseTimer)

    def tick():
        now = clock.nsecsElapsed() / 1e6
        gaps.append(now - state["last"])
        state["last"] = now

    probe.timeout.connect(tick)
    probe.start(PROBE_INTERVAL_MS)

    started = time.perf_counter()
    start_work()
    pool = QThreadPool.globalInstance()
    deadline = time.perf_counter() + settle_ms / 1000
    while time.perf_counter() < deadline:
        qapp.processEvents()
        if pool.activeThreadCount() == 0 and len(gaps) > 4:
            break
        time.sleep(0.001)
    qapp.processEvents()
    wall = (time.perf_counter() - started) * 1000
    probe.stop()

    return (max(gaps[1:]) if len(gaps) > 1 else 0.0), wall

CHARTS = (
    ("Nutrient Graphs", "src.gui.graphs.food_graph", "FoodGraphView"),
    ("Exercise Graphs", "src.gui.graphs.exercise_graph", "ExerciseGraphView"),
    ("Heatmap", "src.gui.graphs.heatmap", "ActivityHeatmapView"),
    ("Caffeine Graph", "src.gui.graphs.caffeine_graph", "CaffeineGraphView"),
    ("Supplement Graphs", "src.gui.graphs.supplement_graph", "SupplementGraphView"),
)


def _pin_exercise_slots(client, how_many=9):
    names = client.get_all_exercise_names()
    assert names, "the seeded catalog has no exercises"
    for slot in range(1, how_many + 1):
        client.set_setting(f"ex_graph_slot_{slot}", names[(slot - 1) % len(names)])
    client.set_setting("ex_graph_layout_dims", "3x3")


def _build(module_name, class_name, client):
    view_class = getattr(importlib.import_module(module_name), class_name)
    view = view_class(client)
    view.resize(*CANVAS_SIZE)
    if class_name == "ExerciseGraphView":
        view._dims = "3x3"
    return view


@pytest.fixture(autouse=True)
def _warm_matplotlib(qapp):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(4, 3))
    axes = figure.subplots()
    axes.plot([0, 1], [0, 1], marker="o")
    axes.set_title("warm", fontname="Fira Code")
    FigureCanvasAgg(figure).draw()


@pytest.mark.parametrize("label,module_name,class_name", CHARTS)
def test_what_one_chart_costs_the_interface_thread(
        qapp, live_client, label, module_name, class_name):
    if class_name == "ExerciseGraphView":
        _pin_exercise_slots(live_client)

    construct = _time(lambda: _build(module_name, class_name, live_client).shutdown())

    view = _build(module_name, class_name, live_client)
    view.show()
    qapp.processEvents()

    read = _time(view.read_chart_data)
    data = view.read_chart_data()

    def build_and_rasterise():
        view.reset_axes()
        view.draw_chart(data)
        view.canvas.draw_offscreen()
        view.canvas.snapshot()

    render = _time(build_and_rasterise)

    worst, wall = _interface_lateness(qapp, view.refresh)

    _report(f"{label}: construct", construct)
    _report(f"{label}: read (worker)", read)
    _report(f"{label}: build + rasterise (worker)", render)
    _report(f"{label}: refresh -> on screen, wall", wall)
    _report(f"{label}: WORST INTERFACE-THREAD GAP", worst,
            f"({worst / INTERACTIVE_BUDGET_MS:.2f}x the budget)")

    view.shutdown()

    assert worst < RENDER_SHARE_LIMIT * render, (
        f"{label} held the interface thread for {worst:.0f} ms of a "
        f"{render:.0f} ms render; the render is supposed to be on the pool")
    if class_name not in GIL_BOUND_CHARTS:
        assert worst < 3 * INTERACTIVE_BUDGET_MS, (
            f"{label} held the interface thread for {worst:.0f} ms, which is "
            f"past the budget for a chart whose cost is rasterisation")


def test_startup_cost_of_the_five_chart_tabs(qapp, live_client):
    total = 0.0
    for label, module_name, class_name in CHARTS:
        millis = _time(lambda m=module_name, c=class_name:
                       _build(m, c, live_client).shutdown())
        total += millis
        _report(f"construct {label}", millis)
    _report("all five chart tabs", total)


def test_the_pulse_animation_stays_off_the_budget(qapp, live_client, settled):
    _pin_exercise_slots(live_client)

    for label, module_name, class_name in CHARTS:
        view = _build(module_name, class_name, live_client)
        view.show()
        view.refresh()
        _settle_render(qapp, view)

        if not view.has_animation():
            _report(f"pulse {label}", 0.0, "(nothing animated)")
            view.shutdown()
            continue

        millis = _time(view.update_animation, repeats=20)
        _report(f"pulse {label}", millis, f"({len(view.anim_nodes)} artists)")
        view.shutdown()

        assert millis < 0.2 * INTERACTIVE_BUDGET_MS, (
            f"{label}'s pulse costs {millis:.1f} ms, at {1000 / view.PULSE_INTERVAL_MS:.0f} Hz")


def test_what_a_chart_pays_for_its_data_when_nothing_is_cached(qapp, live_client):
    from src.gui.graphs.caffeine_graph import CaffeineGraphView
    from src.gui.graphs.heatmap import calendar_start
    from src.gui.graphs.supplement_graph import SupplementGraphView

    def cold(label, read, rows_of=len):
        live_client.invalidate()
        started = time.perf_counter()
        answer = read()
        millis = (time.perf_counter() - started) * 1000
        _report(label, millis, f"({rows_of(answer):,} rows)")
        return millis

    beverage_since = (datetime.date.today() - datetime.timedelta(
        days=CaffeineGraphView.WINDOW_DAYS - 1)).isoformat()
    supplement_since = (datetime.date.today() - datetime.timedelta(
        days=SupplementGraphView.WINDOW_DAYS - 1)).isoformat()

    cold("cold read: nutrient chart (whole food ledger)",
         live_client.get_daily_aggregates)
    cold("cold read: caffeine chart (30 days)",
         lambda: live_client.get_beverage_logs(beverage_since))
    cold("cold read: supplement chart (7 days)",
         lambda: live_client.get_supplement_logs(supplement_since))
    cold("cold read: activity calendar (3 months)",
         lambda: live_client.get_activity_heatmap_data(
             calendar_start(datetime.date.today()).isoformat()))
    cold("cold read: exercise grid (whole exercise ledger)",
         live_client.get_exercise_logs)

    live_client.invalidate()
    started = time.perf_counter()
    rows = live_client.get_food_logs()
    download = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    from src.database.analytics import daily_totals
    totals = daily_totals(rows)
    grouping = (time.perf_counter() - started) * 1000
    _report("  ...of which: download the food ledger", download, f"({len(rows):,} rows)")
    _report("  ...of which: group it into daily totals", grouping, f"({len(totals):,} days)")
