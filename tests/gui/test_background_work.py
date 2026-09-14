import pytest
from PyQt6.QtCore import Qt, QThreadPool

import src.database.rows as rows
from src.gui.commands import EVERY_CATALOG, SET_CATALOG_DOMAINS

SET_KEYS = {domain: key for key, domain in SET_CATALOG_DOMAINS.items()}
from src.gui.components.cmd_line import CommandLineEdit
from src.gui.views.base import BaseManagedView
from src.gui.workers import run_in_background
from tests.row_shapes import catalog_rows

pytestmark = pytest.mark.gui

HEADERS = ["Date", "Servings"]
MAPPING = {"Date": "date", "Servings": "servings"}


class TinyView(BaseManagedView):
    def __init__(self, db):
        super().__init__(db, ["food_logs"], [HEADERS], [MAPPING])
        self.reported = []
        self.status_message.connect(self.reported.append)


class TestAFailureOnAWorkerThread:
    def test_it_reaches_the_status_bar_instead_of_stderr(self, qapp, recording_db, settled):
        view = TinyView(recording_db)

        def explode():
            raise RuntimeError("the service said no")

        view.fetch(explode, lambda _result: pytest.fail("must not reach the result slot"))
        settled()

        assert any("the service said no" in message for message in view.reported)
        view.deleteLater()

    def test_a_successful_call_still_reaches_the_result_slot(self, qapp, recording_db, settled):
        view = TinyView(recording_db)
        landed = []

        view.fetch(lambda: 42, landed.append)
        settled()

        assert landed == [42]
        view.deleteLater()

    def test_the_helper_wires_both_outcomes(self, qapp, settled):
        failures = []

        run_in_background(
            QThreadPool.globalInstance(),
            lambda: 1 / 0,
            lambda _result: pytest.fail("must not reach the result slot"),
            failures.append,
        )
        settled()

        (error, formatted) = failures[0]
        assert isinstance(error, ZeroDivisionError)
        assert "ZeroDivisionError" in formatted


class TestWritesDoNotBlockTheInterface:
    def test_an_inline_edit_is_dispatched_off_the_calling_thread(
        self, qapp, recording_db, settled
    ):
        view = TinyView(recording_db)
        layout, table = view.build_table_layout(None, HEADERS, 0)
        view.setLayout(layout)
        view.populate_table(table, [(1, "2026-09-05", 2.0)], table_idx=0)

        model = view.model_for(0)
        model.setData(model.index(0, 1), "3", Qt.ItemDataRole.EditRole)
        assert not recording_db.called("update_record"), "must not run inline"

        settled()
        assert recording_db.called("update_record")
        view.deleteLater()


@pytest.mark.accessibility
class TestCompletionDoesNotReadThePerKeystroke:
    class CountingCatalogs:
        NAMES = ("Chicken Breast", "Rolled Oats", "Plank", "Zinc", "Hip Opener")

        def __init__(self):
            self.reads = []

        def _read(self, catalog, shape):
            self.reads.append(catalog)
            return catalog_rows(self.NAMES, shape)

        def get_all_foods(self): return self._read("food", rows.FoodItemRow)
        def get_all_beverages(self): return self._read("beverage", rows.BeverageItemRow)
        def get_all_exercises(self): return self._read("exercise", rows.ExerciseItemRow)
        def get_all_supplements(self): return self._read("supplement", rows.SupplementItemRow)
        def get_all_mobility(self): return self._read("mobility", rows.MobilityItemRow)
        def get_chores(self): return self._read("chore", rows.ChoreRow)

        def get_sets(self, domain):
            self.reads.append(SET_KEYS[domain])
            return [rows.SetComponentRow.from_server(r) for r in
                    ((1, "Blue Oatmeal", "Rolled Oats", 100.0),
                     (2, "Blue Oatmeal", "Blueberries", 50.0))]

    @pytest.fixture
    def counting_db(self):
        return self.CountingCatalogs()

    @staticmethod
    def _type(bar, line):
        for index in range(1, len(line) + 1):
            bar.setText(line[:index])

    @staticmethod
    def _settle(qapp):
        QThreadPool.globalInstance().waitForDone(5000)
        qapp.processEvents()

    def test_typing_costs_no_catalog_read_at_all(self, qapp, profile_path, counting_db):
        bar = CommandLineEdit(counting_db)
        self._settle(qapp)
        counting_db.reads.clear()

        self._type(bar, "log 1 b chicken breast")
        self._settle(qapp)

        assert counting_db.reads == []
        bar.deleteLater()

    def test_the_widest_command_reads_each_catalog_once(self, qapp, profile_path, counting_db):
        bar = CommandLineEdit(counting_db)

        self._type(bar, "rm chicken")
        self._settle(qapp)

        assert sorted(counting_db.reads) == sorted(EVERY_CATALOG)
        bar.deleteLater()

    def test_a_catalog_change_drops_the_cache(self, qapp, profile_path, counting_db):
        bar = CommandLineEdit(counting_db)
        self._type(bar, "log 1 b oats")
        self._settle(qapp)

        bar.invalidate_catalog_cache()
        bar.setText("log 1 b oat")
        self._settle(qapp)

        assert counting_db.reads.count("food") == 2
        bar.deleteLater()

    def test_a_read_that_found_nothing_because_the_service_is_down_is_not_cached(
        self, qapp, profile_path
    ):
        from src.database import ConnectionStatus

        class OfflineCatalogs:
            def __init__(self):
                self.connection = ConnectionStatus()
                self.connection.record_failure("household service is not running")

            def __getattr__(self, _name):
                return lambda: []

        bar = CommandLineEdit(OfflineCatalogs())
        self._settle(qapp)

        assert bar._names_by_catalog == {}
        bar.deleteLater()

    def test_the_suggestion_is_unchanged_by_the_cache(self, qapp, profile_path, counting_db):
        bar = CommandLineEdit(counting_db)
        self._settle(qapp)

        self._type(bar, "log 1 b chick")
        self._settle(qapp)

        assert bar.completion_text == "en Breast"
        bar.deleteLater()


class TestAStartedWorkerOutlivesTheCallThatStartedIt:
    def test_the_worker_is_held_until_it_reports_finishing(self, qapp):
        from src.gui import workers

        landed = []
        worker = workers.run_in_background(
            QThreadPool.globalInstance(), lambda: "done", landed.append)

        assert worker in workers._in_flight, "held from the moment it is started"

        QThreadPool.globalInstance().waitForDone(2000)
        qapp.processEvents()

        assert landed == ["done"]
        assert worker not in workers._in_flight, "and released once it has finished"

    def test_it_survives_a_collection_while_the_call_is_running(self, qapp):
        import gc

        from src.gui import workers

        landed = []
        for index in range(25):
            workers.run_in_background(
                QThreadPool.globalInstance(), lambda i=index: i, landed.append)
        gc.collect()

        QThreadPool.globalInstance().waitForDone(5000)
        qapp.processEvents()

        assert sorted(landed) == list(range(25))

    def test_nothing_is_retained_once_the_pool_is_idle(self, qapp):
        from src.gui import workers

        for _ in range(10):
            workers.run_in_background(QThreadPool.globalInstance(), lambda: None, lambda _r: None)
        QThreadPool.globalInstance().waitForDone(5000)
        qapp.processEvents()

        assert workers._in_flight == set()
