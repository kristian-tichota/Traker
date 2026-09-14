import time

import pytest

pytestmark = [pytest.mark.perf, pytest.mark.gui]

INTERACTIVE_BUDGET_MS = 100.0


def _report(label, millis, extra=""):
    print(f"\n  {label:<46} {millis:8.3f} ms  {extra}")


def _render(table):
    from PyQt6.QtGui import QPixmap

    viewport = table.viewport()
    pixmap = QPixmap(max(1, viewport.width()), max(1, viewport.height()))
    table.render(pixmap)


def _idle_cpu(qapp, seconds, tick):
    import resource

    def cpu_seconds():
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_utime + usage.ru_stime

    before = cpu_seconds()
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(tick)
    return cpu_seconds() - before


def _time(callable_, repeats=3):
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        callable_()
        best = min(best, (time.perf_counter() - started) * 1000)
    return best

VIEWS_UNDER_TEST = (
    ("Food Logs", "src.gui.views.food_views", "FoodView", "get_food_logs"),
    ("Supplements", "src.gui.views.supplement_view", "SupplementsView", "get_supplement_logs"),
    ("Exercise", "src.gui.views.exercise_view", "ExerciseView", "get_exercise_logs"),
    ("Beverages", "src.gui.views.beverage_view", "BeveragesView", "get_beverage_logs"),
    ("Mobility", "src.gui.views.mobility_view", "MobilityView", "get_mobility_logs"),
)


@pytest.mark.parametrize("label,module_name,class_name,getter", VIEWS_UNDER_TEST)
def test_populating_a_log_table_stays_interactive(
        qapp, live_client, label, module_name, class_name, getter):
    import importlib

    view_class = getattr(importlib.import_module(module_name), class_name)
    rows = getattr(live_client, getter)()
    assert rows, f"{label}: the seeded ledger should not be empty"

    view = view_class(live_client)
    table = view._table_widgets[0]

    def populate_and_paint():
        view.populate_table(table, rows, table_idx=0)
        _render(table)

    millis = _time(populate_and_paint)
    _report(f"populate {label}", millis, f"({len(rows):,} rows)")
    view.shutdown()

    assert millis < 10 * INTERACTIVE_BUDGET_MS, (
        f"{label} took {millis:.0f} ms to render {len(rows)} rows")


def test_population_scales_with_the_ledger_not_the_screen(qapp, live_client):
    from src.gui.views.food_views import FoodView

    rows = live_client.get_food_logs()
    assert len(rows) > 2000, "seeded ledger is too small to show a slope"

    view = FoodView(live_client)
    table = view._table_widgets[0]

    half = rows[: len(rows) // 2]

    def paint(subset):
        def run():
            view.populate_table(table, subset, table_idx=0)
            _render(table)
        return run

    small = _time(paint(half))
    large = _time(paint(rows))
    view.shutdown()

    ratio = large / small if small else 0.0
    _report("populate half the ledger", small, f"({len(half):,} rows)")
    _report("populate the whole ledger", large, f"({len(rows):,} rows)")
    print(f"  {'slope (whole / half)':<46} {ratio:8.2f} x")


def test_the_change_diff_is_cheap_against_the_whole_ledger(qapp, live_client):
    from src.gui.views.food_views import FoodView

    rows = live_client.get_food_logs()
    assert len(rows) > 2000, "seeded ledger is too small to be a load"

    view = FoodView(live_client)
    model = view._table_models[0]
    model.set_rows(rows)

    row_type = type(rows[0])
    after = list(rows)
    edited = list(after[len(after) // 2])
    edited[-1] = (edited[-1] or 0) + 1
    after[len(after) // 2] = row_type(*edited)
    arrival = list(after[-1])
    arrival[0] = max(row[0] for row in rows) + 1
    after.append(row_type(*arrival))

    millis = _time(lambda: model._changes_in(after))
    changed = model._changes_in(after)
    view.shutdown()

    _report("diff a refresh for changed rows", millis, f"({len(after):,} rows)")
    assert len(changed) == 2, f"expected the edit and the append, got {changed}"
    assert millis < INTERACTIVE_BUDGET_MS, (
        f"the change diff took {millis:.1f} ms for {len(after)} rows")


def test_wall_clock_from_a_write_to_the_row_being_visible(qapp, live_client, settled):
    from src.gui.views.food_views import FoodView

    foods = live_client.get_all_foods()
    assert foods, "seeded catalog is empty"
    food_name = foods[0][1]

    view = FoodView(live_client)
    view.refresh()
    settled()

    started = time.perf_counter()
    ok, message = live_client.add_food_log(
        {"date": "2026-09-06", "meal_type": "Lunch", "food_name": food_name,
         "servings": 1.0})
    assert ok, message
    view.refresh()
    settled()
    millis = (time.perf_counter() - started) * 1000

    rendered = view.model_for(0).rowCount()
    _report("write -> row visible", millis, f"({rendered:,} rows on screen)")
    view.shutdown()


def test_wall_clock_for_a_tab_switch_to_a_dirty_tab(qapp, live_client, settled):
    from src.gui.views.supplement_view import SupplementsView

    view = SupplementsView(live_client)
    view.refresh()
    settled()

    started = time.perf_counter()
    view.refresh()
    settled()
    millis = (time.perf_counter() - started) * 1000

    _report("refresh a dirty tab (read + render)",
            millis, f"({view.model_for(0).rowCount():,} rows)")
    view.shutdown()


def test_idle_cpu_of_the_whole_window(qapp, live_client, settled):
    from src.gui.main_window import MainWindow

    window = MainWindow(live_client)
    window.show()
    settled()
    for index in range(window.tabs.count()):
        if window.tabs.tabText(index).endswith("Mobility"):
            window.tabs.setCurrentIndex(index)
            break
    else:
        raise AssertionError("no Mobility tab to measure a quiet window on")
    settled()

    quiet = _idle_cpu(qapp, seconds=3.0, tick=0.025)
    _report("idle CPU, whole window, 3 s wall", quiet * 1000,
            f"({quiet / 3.0 * 100:.1f}% of one core)")

    from PyQt6.QtCore import QTimer

    from src.gui.views.pomodoro_view import PomodoroView

    restored = []
    for timer in window.findChildren(QTimer):
        if timer is window._reveal_poll:
            continue
        restored.append((timer, timer.interval(), timer.isActive()))
        timer.start(30)
    timer_engine = window.views.get("pomodoro")
    if isinstance(timer_engine, PomodoroView):
        timer_engine.refresh_timer.start(timer_engine.visible_interval_ms())

    busy = _idle_cpu(qapp, seconds=3.0, tick=0.025)
    _report("  ...with every timer running (before)", busy * 1000,
            f"({busy / 3.0 * 100:.1f}% of one core)")
    if quiet > 0:
        print(f"  {'ratio (forced-on / as it ships)':<46} {busy / quiet:8.1f} x")

    for timer, interval, was_active in restored:
        timer.stop()
        if was_active:
            timer.start(interval)

    window.close()
    settled()


def test_idle_cpu_on_a_tab_with_no_animation(qapp, live_client):
    import os

    from src.gui.views.food_views import FoodView

    view = FoodView(live_client)
    view.populate_table(view._table_widgets[0], live_client.get_food_logs(), table_idx=0)
    view.hide()

    burned = _idle_cpu(qapp, seconds=2.0, tick=0.025)

    _report("idle CPU, view hidden, 2 s wall", burned * 1000,
            f"({burned / 2.0 * 100:.1f}% of one core)  pid={os.getpid()}")
    view.shutdown()

FILTERS = ("oats", "rizek", "meal:b", "kcal>300", "oats meal:b",
           "date>2026-06-01", "kcal>300 meal:d")


def test_filtering_stays_inside_a_keystroke(qapp, live_client, settled):
    from src.gui.filtering import parse
    from src.gui.views.food_views import FoodView

    view = FoodView(live_client)
    view.set_rows(0, live_client.get_food_logs())
    view.warm_fold(0)
    settled()
    headers = view.headers[0]
    rows = view.model_for(0).rowCount()
    assert rows > 2000, "seeded ledger is too small to measure a filter"

    worst = 0.0
    for text in FILTERS:
        query = parse(text, headers)

        def apply():
            view.apply_filter(query)
            view.clear_filter()

        millis = _time(apply)
        worst = max(worst, millis)
        _report(f"filter /{text}", millis,
                f"({rows:,} rows -> {_matched(view, query):,})")
    view.shutdown()

    assert worst < INTERACTIVE_BUDGET_MS, (
        f"a filter keystroke cost {worst:.0f} ms, which stops feeling live")


def _matched(view, query):
    view.apply_filter(query)
    count = view.proxy_for(0).rowCount()
    view.clear_filter()
    return count


def test_the_fold_is_warmed_off_the_interface_thread(qapp, live_client, settled):
    from src.gui.views.food_views import FoodView

    view = FoodView(live_client)
    view.set_rows(0, live_client.get_food_logs())
    view.warm_fold(0)
    settled()

    model = view.model_for(0)
    folded = len(model._folded)
    _report("rows folded before the first keystroke", 0.0,
            f"({folded:,} of {model.rowCount():,})")
    view.shutdown()

    assert folded == model.rowCount(), "the fold was not warmed"


def test_sorting_a_filtered_table(qapp, live_client, settled):
    from src.gui.filtering import parse
    from src.gui.views.food_views import FoodView
    from PyQt6.QtCore import Qt as _Qt

    view = FoodView(live_client)
    view.set_rows(0, live_client.get_food_logs())
    view.warm_fold(0)
    settled()
    view.apply_filter(parse("oats", view.headers[0]))
    column = view.headers[0].index("Calories")

    order = [_Qt.SortOrder.AscendingOrder, _Qt.SortOrder.DescendingOrder]

    def sort():
        view.sort_by(column, order[0])
        view.sort_by(column, order[1])

    millis = _time(sort)
    _report("sort a filtered table, both directions", millis,
            f"({view.proxy_for(0).rowCount():,} rows)")
    view.shutdown()
