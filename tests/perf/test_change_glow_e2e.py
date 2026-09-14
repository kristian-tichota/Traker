import time

import pytest
from PyQt6.QtGui import QPixmap

pytestmark = [pytest.mark.perf, pytest.mark.gui]


def shot(widget):
    pixmap = QPixmap(widget.size())
    widget.render(pixmap)
    return pixmap.toImage()


def distinct_colours(image, step=7):
    return {image.pixel(x, y)
            for y in range(0, image.height(), step)
            for x in range(0, image.width(), step)}


def differing_pixel_rows(before, after, step=3):
    return [y for y in range(min(before.height(), after.height()))
            if any(before.pixel(x, y) != after.pixel(x, y)
                   for x in range(0, min(before.width(), after.width()), step))]


@pytest.fixture
def window(qapp, live_client, settled):
    from src.gui.main_window import MainWindow

    built = MainWindow(live_client)
    built.resize(1200, 800)
    built.show()
    settled()
    built._on_reveal_poll()
    yield built
    built.close()
    built.deleteLater()


@pytest.fixture
def food_tab(qapp, window, settled):
    index = window.tab_indices["food"]
    window.tabs.setCurrentIndex(index)
    settled()
    window._on_reveal_poll()
    deadline = time.perf_counter() + 5.0
    while window.tab_animator.covering and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert not window.tab_animator.covering, "the veil never came off"
    view = window.views["food"]
    assert view.model_for(0).rowCount() > 1000, "the seeded ledger should be here"
    return window.tabs.widget(index), view


def test_a_write_does_not_blank_the_tab(window, food_tab, settled):
    page, _view = food_tab
    quiet = distinct_colours(shot(page))
    assert len(quiet) > 20, "the tab should have something on it to lose"

    window.command_line.setText("log 2 b Rolled Oats")
    window.execute_command()
    settled()

    assert not window.tab_animator.covering
    assert len(distinct_colours(shot(page))) > 20


def test_only_the_changed_row_moves_under_the_wash(window, food_tab, settled):
    _page, view = food_tab
    table = view._table_widgets[0]
    model = view.model_for(0)

    rows = list(model.rows)
    target = next(position for position, row in enumerate(rows)
                  if not getattr(row, "is_heading", False))
    edited = list(rows[target])
    edited[-1] = (edited[-1] or 0) + 1
    rows[target] = type(rows[target])(*edited)
    view.set_rows(0, rows)
    assert model.changed_rows() == frozenset({target}), model.changed_rows()

    model.highlight_changes(1.0)
    washed = shot(table)
    model.highlight_changes(0.0)
    quiet = shot(table)

    bands = differing_pixel_rows(quiet, washed)
    assert bands, "the wash must reach some pixels or it says nothing"
    assert len(bands) < table.height() // 10, (
        f"{len(bands)} of {table.height()} pixel rows moved — that is a blink, "
        f"not a highlight")
    assert max(bands) < table.height() // 3, (
        "the wash reached down the table rather than staying on its row")


def test_a_refresh_that_changed_nothing_moves_no_pixel(window, food_tab, settled):
    _page, view = food_tab
    table = view._table_widgets[0]

    before = shot(table)
    view.set_rows(0, list(view.model_for(0).rows))
    after = shot(table)

    assert view.model_for(0).changed_rows() == frozenset()
    assert differing_pixel_rows(before, after) == []

CHART_TABS = ("food_graphs", "exercise_graphs", "caffeine_graph",
              "supplement_graphs", "heatmap")


@pytest.mark.parametrize("key", CHART_TABS)
def test_a_chart_tabs_first_visit_says_it_is_working(qapp, window, key):
    from PyQt6.QtCore import QAbstractAnimation

    from src.gui.animations import SPINNER_GRACE_MS

    index = window.tab_indices[key]
    view = window.views[key]
    assert view.canvas._image is None, "this test is about the *first* visit"

    overlay = window.tab_animator.overlay
    started = time.perf_counter()
    window.tabs.setCurrentIndex(index)
    assert window.tab_animator.covering, "the arrival veil should be up"

    arc_seen, wait_ended = False, None
    deadline = started + 10.0
    while window.tab_animator.covering and time.perf_counter() < deadline:
        qapp.processEvents()
        arc_seen = arc_seen or overlay.spinner.showing
        if (wait_ended is None
                and window.tab_animator.anim.state() == QAbstractAnimation.State.Running):
            wait_ended = time.perf_counter()
        time.sleep(0.004)
    waited_ms = ((wait_ended or time.perf_counter()) - started) * 1000

    print(f"\n  {key:18s} waited {waited_ms:6.0f} ms   arc shown: {arc_seen}")
    assert view.canvas._image is not None, f"{key} never rendered"
    if waited_ms > SPINNER_GRACE_MS * 1.5:
        assert arc_seen, (
            f"{key}: the member waited {waited_ms:.0f} ms and was told nothing")
    elif waited_ms < SPINNER_GRACE_MS:
        assert not arc_seen, (
            f"{key}: the wait was only {waited_ms:.0f} ms and an arc still "
            f"flashed — the grace is what stops that")


def test_the_arc_comes_off_when_the_chart_arrives(qapp, window, settled):
    index = window.tab_indices["food_graphs"]
    window.tabs.setCurrentIndex(index)
    settled()
    window._on_reveal_poll()
    deadline = time.perf_counter() + 5.0
    while window.tab_animator.covering and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    view = window.views["food_graphs"]
    assert view.canvas._image is not None, "the chart should have arrived"
    assert not window.tab_animator.overlay.spinner.showing
    assert not view.canvas.spinner.showing
    assert not view.canvas.spinner._timer.isActive()
