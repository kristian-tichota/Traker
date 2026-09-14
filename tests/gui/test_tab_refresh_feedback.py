import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp, profile_path, recording_db):
    from src.gui.main_window import MainWindow

    built = MainWindow(recording_db)
    yield built
    built.close()
    built.deleteLater()


def index_of(window, key):
    return window.tab_indices[key]


class TestTheFadeFollowsTheData:
    def test_the_manager_is_not_driven_by_the_tab_changing(self, window):
        assert window.tab_animator.overlay is not None
        window.dirty_tabs = set()
        window.tab_animator.covering = False

        window._on_tab_changed(index_of(window, "food"))

        assert not window.tab_animator.covering

    def test_a_clean_tab_is_not_veiled_at_all(self, window):
        window.dirty_tabs = set()
        window.tab_animator.covering = False

        window._on_tab_changed(index_of(window, "supplements"))

        assert not window.tab_animator.covering

    def test_a_dirty_tab_is_veiled_while_its_read_is_out(self, window):
        target = index_of(window, "food")
        window.dirty_tabs = {target}

        window._on_tab_changed(target)

        assert window.tab_animator.covering

    def test_the_veil_is_lifted_once_the_read_has_landed(self, window, settled):
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)
        assert window.tab_animator.covering

        settled()
        window._on_reveal_poll()

        assert window.tab_animator.anim.endValue() == 0

    def test_covering_puts_the_veil_over_the_tab_being_read(self, window):
        target = index_of(window, "exercise")
        window.dirty_tabs = {target}

        window._on_tab_changed(target)

        assert window.tab_animator.overlay.parent() is window.tabs.widget(target)

    def test_revealing_a_veil_that_is_not_up_does_nothing(self, window):
        window.tab_animator.covering = False

        window.tab_animator.reveal()

        assert not window.tab_animator.covering

    def test_the_veil_state_does_not_depend_on_an_unshown_parent(self, window):
        target = index_of(window, "food")
        window.dirty_tabs = {target}

        window._on_tab_changed(target)

        assert window.tab_animator.covering is True


class TestAnInFlightReadIsNotAnEmptyLog:
    def test_the_status_line_says_it_is_reading(self, window):
        target = index_of(window, "food")
        window.dirty_tabs = {target}

        window._on_tab_changed(target)

        assert "Reading" in window.status_bar.text()

    def test_a_clean_tab_says_nothing(self, window):
        window.status_bar.setText("")
        window.dirty_tabs = set()

        window._on_tab_changed(index_of(window, "food"))

        assert window.status_bar.text() == ""

    def test_the_reading_notice_is_cleared_when_the_read_lands(
            self, window, settled):
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)
        assert "Reading" in window.status_bar.text()

        settled()
        window._on_reveal_poll()

        assert "Reading" not in window.status_bar.text()

    def test_a_message_written_during_the_read_is_not_wiped(
            self, window, settled):
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)

        window.status_bar.setText(" Saved.")
        settled()
        window._on_reveal_poll()

        assert window.status_bar.text() == " Saved."

    def test_the_poll_stops_once_nothing_is_in_flight(self, window, settled):
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)

        settled()
        window._on_reveal_poll()

        assert not window._reveal_poll.isActive()

    def test_the_poll_keeps_waiting_while_work_is_still_out(self, window):
        import threading
        import time

        from PyQt6.QtCore import QThreadPool

        from src.gui.workers import discard, run_in_background

        pool = QThreadPool.globalInstance()
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)

        release = threading.Event()
        run_in_background(pool, release.wait, discard, None, 5.0)
        try:
            deadline = time.monotonic() + 5.0
            while pool.activeThreadCount() == 0 and time.monotonic() < deadline:
                time.sleep(0.001)
            assert pool.activeThreadCount() > 0, "the held worker never started"

            window._on_reveal_poll()

            assert window._reveal_poll.isActive()
        finally:
            release.set()
            pool.waitForDone(5000)


class TestTheGridAsksForItsSettingsOnce:
    def test_a_refresh_reads_every_slot_in_one_request(
            self, qapp, profile_path, recording_db, settled):
        from src.gui.graphs.exercise_graph import ExerciseGraphView

        view = ExerciseGraphView(recording_db)
        view.resize(900, 600)
        view.show()
        settled()
        recording_db.setting_batches.clear()
        recording_db.setting_reads.clear()

        view.refresh()
        settled()

        assert len(recording_db.setting_batches) == 1, \
            f"one request expected, got {recording_db.setting_batches}"
        view.shutdown()
        view.deleteLater()

    def test_that_one_request_names_every_slot(
            self, qapp, profile_path, recording_db, settled):
        from src.gui.graphs.exercise_graph import ExerciseGraphView

        view = ExerciseGraphView(recording_db)
        view.resize(900, 600)
        view.show()
        settled()
        recording_db.setting_batches.clear()

        view.refresh()
        settled()

        asked = recording_db.setting_batches[0]
        assert all(key.startswith("ex_graph_slot_") for key in asked)
        assert len(asked) == len(set(asked))
        view.shutdown()
        view.deleteLater()

    def test_a_slot_the_member_never_pinned_reads_as_None(
            self, qapp, profile_path, recording_db, settled):
        from src.gui.graphs.exercise_graph import ExerciseGraphView

        view = ExerciseGraphView(recording_db)
        settled()

        slots = view._pinned_timelines(4)

        assert [name for name, _timeline in slots] == ["None"] * 4
        view.shutdown()
        view.deleteLater()

    def test_a_pinned_slot_comes_back_with_its_exercise(
            self, qapp, profile_path, recording_db, settled):
        from src.gui.graphs.exercise_graph import ExerciseGraphView

        recording_db.settings["ex_graph_slot_2"] = "Overhead Press"
        view = ExerciseGraphView(recording_db)
        settled()

        slots = view._pinned_timelines(4)

        assert slots[1][0] == "Overhead Press"
        view.shutdown()
        view.deleteLater()


class TestARefreshInPlaceDoesNotTakeTheTabAway:
    def test_a_write_does_not_veil_the_tab_the_member_is_reading(self, window):
        window.dirty_tabs = set()
        window.tab_animator.covering = False

        window.mark_domains_stale(("food",))

        assert not window.tab_animator.covering

    def test_the_stream_does_not_veil_it_either(self, window):
        window.tab_animator.covering = False

        window.mark_all_tabs_stale()

        assert not window.tab_animator.covering

    def test_switching_to_a_stale_tab_still_veils_it(self, window):
        target = index_of(window, "exercise")
        window.dirty_tabs = {target}
        window.tab_animator.covering = False

        window._on_tab_changed(target)

        assert window.tab_animator.covering

    def test_a_write_still_dispatches_the_refresh(self, window):
        target = window.tabs.currentIndex()
        window.dirty_tabs = {target}

        window._refresh_visible_tab()

        assert target not in window.dirty_tabs

    def test_a_write_leaves_a_clean_visible_tab_alone(self, window):
        window.dirty_tabs = {index_of(window, "exercise")}

        window._refresh_visible_tab()

        assert window.dirty_tabs == {index_of(window, "exercise")}

    def test_a_write_does_not_say_it_is_reading(self, window):
        target = window.tabs.currentIndex()
        window.dirty_tabs = {target}
        window.status_bar.setText("")

        window._refresh_visible_tab()

        assert "Reading" not in window.status_bar.text()


class TestAWriteDoesNotThrowAwayTheFilter:
    def test_the_filter_bar_stays_open_across_a_write(self, window):
        window.tabs.setCurrentIndex(index_of(window, "food"))
        window.open_filter()
        window.filter_line.setText("oats")

        window.mark_domains_stale(("food",))

        assert window._filter_open
        assert window.filter_line.text() == "oats"

    def test_the_member_is_left_in_filter_mode(self, window):
        window.tabs.setCurrentIndex(index_of(window, "food"))
        window.open_filter()

        window.mark_domains_stale(("food",))

        assert window.current_mode == "FILTER"

    def test_a_real_tab_change_still_drops_it(self, window):
        window.tabs.setCurrentIndex(index_of(window, "food"))
        window.open_filter()

        window._on_tab_changed(index_of(window, "exercise"))

        assert not window._filter_open


class TestTheLoadingArc:
    @pytest.fixture
    def spinner(self, qapp):
        from src.gui.animations import FadeOverlay

        overlay = FadeOverlay()
        overlay.resize(200, 120)
        overlay.show()
        yield overlay.spinner
        overlay.spinner.stop()
        overlay.deleteLater()

    def waited(self, spinner, millis):
        spinner.started_at -= millis / 1000.0

    def test_an_idle_spinner_says_nothing(self, spinner):
        assert spinner.phase is None
        assert not spinner.showing

    def test_a_short_wait_never_shows_it(self, spinner):
        from src.gui.animations import SPINNER_GRACE_MS

        spinner.start()
        self.waited(spinner, SPINNER_GRACE_MS - 40)

        assert spinner.phase is None

    def test_a_wait_past_the_grace_shows_it(self, spinner):
        from src.gui.animations import SPINNER_GRACE_MS

        spinner.start()
        self.waited(spinner, SPINNER_GRACE_MS + 40)

        assert spinner.phase is not None
        assert 0.0 <= spinner.phase < 1.0

    def test_the_phase_wraps_round_the_circle(self, spinner):
        from src.gui.animations import SPINNER_GRACE_MS, SPINNER_PERIOD_MS

        spinner.start()
        self.waited(spinner, SPINNER_GRACE_MS + 40)
        first = spinner.phase
        assert first is not None
        self.waited(spinner, SPINNER_PERIOD_MS)

        assert spinner.phase == pytest.approx(first, abs=0.05)

    def test_stopping_takes_it_off(self, spinner):
        from src.gui.animations import SPINNER_GRACE_MS

        spinner.start()
        self.waited(spinner, SPINNER_GRACE_MS + 40)

        spinner.stop()

        assert spinner.phase is None

    def test_a_second_start_mid_wait_does_not_restart_the_grace(self, spinner):
        from src.gui.animations import SPINNER_GRACE_MS

        spinner.start()
        self.waited(spinner, SPINNER_GRACE_MS + 40)
        began = spinner.started_at

        spinner.start()

        assert spinner.started_at == began
        assert spinner.showing

    def test_advancing_a_stopped_spinner_does_nothing(self, spinner):
        spinner.advance()

        assert spinner.phase is None

    def test_it_reaches_pixels_on_the_veil(self, qapp):
        from PyQt6.QtGui import QPixmap

        from src.gui.animations import FadeOverlay, SPINNER_GRACE_MS

        overlay = FadeOverlay()
        overlay.resize(200, 120)
        overlay.show()

        def colours():
            pixmap = QPixmap(overlay.size())
            overlay.render(pixmap)
            image = pixmap.toImage()
            return {image.pixel(x, y)
                    for y in range(image.height()) for x in range(image.width())}

        assert len(colours()) == 1, "an idle veil is the flat panel it always was"

        overlay.spinner.start()
        overlay.spinner.started_at -= (SPINNER_GRACE_MS + 40) / 1000.0
        overlay.spinner.advance()
        qapp.processEvents()

        assert len(colours()) > 1, "the arc must reach some pixel or it says nothing"

        overlay.spinner.stop()
        qapp.processEvents()

        assert len(colours()) == 1, "and it must come off again"
        overlay.deleteLater()


class TestTheVeilDrivesTheArc:
    def test_covering_starts_the_wait(self, window):
        target = index_of(window, "food")
        window.dirty_tabs = {target}

        window._on_tab_changed(target)

        assert window.tab_animator.overlay.spinner._timer.isActive()

    def test_revealing_ends_it(self, window, settled):
        target = index_of(window, "food")
        window.dirty_tabs = {target}
        window._on_tab_changed(target)

        settled()
        window._on_reveal_poll()

        assert not window.tab_animator.overlay.spinner._timer.isActive()

    def test_a_clean_tab_starts_no_wait(self, window):
        window.tab_animator.overlay.spinner.stop()
        window.tab_animator.covering = False
        window.dirty_tabs = set()

        window._on_tab_changed(index_of(window, "food"))

        assert not window.tab_animator.overlay.spinner._timer.isActive()

    def test_a_refresh_in_place_raises_no_veil_and_no_veil_arc(self, window):
        window.tab_animator.overlay.spinner.stop()
        window.tab_animator.covering = False
        window.dirty_tabs = set()

        window.mark_domains_stale(("food",))

        assert not window.tab_animator.covering
        assert not window.tab_animator.overlay.spinner._timer.isActive()
