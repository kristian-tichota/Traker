import pytest

from src.gui.domains import (
    BEVERAGE, EVERY_DOMAIN, EXERCISE, FOOD, MOBILITY, POMODORO, SUPPLEMENT,
    TABLE_DOMAINS, TAB_DOMAINS, domain_of_table, domains_for_tab, tabs_reading)

pytestmark = pytest.mark.gui


class TestTheMappingIsComplete:
    def test_every_registered_server_table_has_a_domain(self):
        from server.tables import _REGISTRY

        NO_DOMAIN = {"user_settings", "item_sets"}

        for spec in _REGISTRY.values():
            if spec.name in NO_DOMAIN:
                continue
            assert spec.name in TABLE_DOMAINS, f"{spec.name} belongs to no domain"

    def test_a_sets_own_table_cannot_name_a_subject(self):
        from src.gui.domains import domain_of_table

        assert domain_of_table("item_sets") is None
        assert domain_of_table("supplement_set_components") == SUPPLEMENT

    def test_every_tab_the_window_builds_declares_its_domains(self):
        from src.gui.main_window import MainWindow

        built = {key for key, _label, _build, _cmd in MainWindow.TAB_REGISTRY}

        assert built == set(TAB_DOMAINS), (
            "every tab the window builds declares the domains it reads, and "
            "nothing declares domains for a tab that is not built")

    def test_a_catalog_and_its_log_share_one_domain(self):
        for subject in ("food", "beverage", "exercise", "supplement", "mobility"):
            assert TABLE_DOMAINS[f"{subject}_items"] == TABLE_DOMAINS[f"{subject}_logs"]

    def test_an_unknown_table_has_no_domain_rather_than_a_wrong_one(self):
        assert domain_of_table("user_settings") is None
        assert domain_of_table("nonsense") is None

    def test_an_undeclared_tab_reads_everything(self):
        assert domains_for_tab("a_tab_nobody_registered") == EVERY_DOMAIN


class TestWhichTabsAWriteReaches:
    def test_a_food_write_reaches_the_food_tabs(self):
        assert tabs_reading((FOOD,)) == {"food", "food_graphs"}

    def test_a_food_write_does_not_reach_the_other_ledgers(self):
        reached = tabs_reading((FOOD,))
        assert not (reached & {"exercise", "supplements", "mobility", "beverages"})

    def test_an_exercise_write_reaches_the_tabs_deriving_from_it(self):
        assert tabs_reading((EXERCISE,)) == {
            "exercise", "exercise_graphs", "heatmap", "food", "plans"}

    def test_a_mobility_write_reaches_the_calendar_and_the_burn_deduction(self):
        assert tabs_reading((MOBILITY,)) == {"mobility", "heatmap", "food"}

    def test_a_beverage_write_reaches_the_caffeine_chart(self):
        assert tabs_reading((BEVERAGE,)) == {"beverages", "caffeine_graph"}

    def test_a_supplement_write_reaches_the_supplement_chart(self):
        assert tabs_reading((SUPPLEMENT,)) == {"supplements", "supplement_graphs"}

    def test_a_pomodoro_write_reaches_only_the_focus_timer(self):
        assert tabs_reading((POMODORO,)) == {"pomodoro"}

    def test_every_domain_together_reaches_every_tab(self):
        assert tabs_reading(EVERY_DOMAIN) == set(TAB_DOMAINS)

    def test_no_domain_reaches_no_tab(self):
        assert tabs_reading(()) == set()


class TestEveryCommandSaysWhatItWrites:
    def test_each_logging_command_names_its_subject(self):
        from src.gui.commands import COMMANDS

        expected = {"log": FOOD, "bevlog": BEVERAGE, "exlog": EXERCISE,
                    "supplog": SUPPLEMENT, "moblog": MOBILITY, "setdsi": POMODORO}
        for name, domain in expected.items():
            assert COMMANDS[name].domains == (domain,), name

    def test_each_definition_names_the_subject_not_the_catalog(self):
        from src.gui.commands import COMMANDS

        expected = {"define": FOOD, "bevdefine": BEVERAGE, "exdefine": EXERCISE,
                    "suppdefine": SUPPLEMENT, "mobdefine": MOBILITY}
        for name, domain in expected.items():
            assert COMMANDS[name].domains == (domain,), name

    def test_removal_claims_every_domain_because_it_searches_every_catalog(self):
        from src.gui.commands import COMMANDS

        assert set(COMMANDS["rm"].domains) == set(EVERY_DOMAIN)

    def test_a_chart_preference_claims_none(self):
        from src.gui.commands import COMMANDS

        assert COMMANDS["track"].domains == ()
        assert COMMANDS["graphlayout"].domains == ()

    def test_every_command_answers_the_question_one_way_or_the_other(self):
        from src.gui.commands import COMMANDS

        for name, command in COMMANDS.items():
            assert isinstance(command.domains, tuple), name


class TestAViewSaysWhatItChanged:
    def test_a_log_view_names_its_domain(self, qapp, profile_path, recording_db):
        from src.gui.views.food_views import FoodView

        view = FoodView(recording_db)
        assert view.domain_of(0) == FOOD
        view.shutdown()
        view.deleteLater()

    def test_a_two_table_view_names_the_same_domain_for_both(
            self, qapp, profile_path, recording_db):
        from src.gui.views.exercise_view import ExerciseView

        view = ExerciseView(recording_db)
        assert view.domain_of(0) == EXERCISE
        assert view.domain_of(1) == EXERCISE
        view.shutdown()
        view.deleteLater()

    def test_an_edit_reports_the_domain_it_changed(
            self, qapp, profile_path, recording_db, settled):
        from PyQt6.QtCore import Qt

        from src.gui.views.supplement_view import SupplementsView

        view = SupplementsView(recording_db)
        reported = []
        view.data_changed.connect(reported.append)
        model = view.model_for(0)
        model.set_rows([(1, "2026-09-05", "Morning Stack", None, 1.0, 500.0)])

        model.setData(model.index(0, 3), "2", Qt.ItemDataRole.EditRole)
        settled()

        assert reported == [SUPPLEMENT]
        view.shutdown()
        view.deleteLater()

    def test_a_delete_reports_the_domain_of_the_table_it_deleted_from(
            self, qapp, profile_path, recording_db, settled):
        from src.gui.views.exercise_view import ExerciseView

        view = ExerciseView(recording_db)
        reported = []
        view.data_changed.connect(reported.append)

        view.fetch(view._delete_row, view._on_delete_finished, "exercise_items", 3)
        settled()

        assert reported == [EXERCISE]
        view.shutdown()
        view.deleteLater()

    def test_a_refused_edit_still_reports_its_domain_so_the_cell_is_put_back(
            self, qapp, profile_path, recording_db, settled):
        from PyQt6.QtCore import Qt

        from src.gui.views.supplement_view import SupplementsView

        recording_db.result = (False, "refused")
        view = SupplementsView(recording_db)
        reported = []
        view.data_changed.connect(reported.append)
        model = view.model_for(0)
        model.set_rows([(1, "2026-09-05", "Morning Stack", None, 1.0, 500.0)])

        model.setData(model.index(0, 3), "2", Qt.ItemDataRole.EditRole)
        settled()

        assert reported == [SUPPLEMENT]
        view.shutdown()
        view.deleteLater()


class TestTheStreamsEchoNarrowsToo:
    @pytest.fixture
    def window(self, qapp, profile_path, recording_db):
        from src.gui.main_window import MainWindow

        built = MainWindow(recording_db)
        yield built
        built.close()
        built.deleteLater()

    def test_a_named_catalog_change_dirties_that_domains_tabs(self, window):
        window.dirty_tabs = set()

        window._on_remote_catalog_update({"table": "food_items", "action": "update"})

        stale = {key for key, index in window.tab_indices.items()
                 if index in window.dirty_tabs}
        assert stale == {"food", "food_graphs"}

    def test_it_dirties_the_log_tab_and_not_only_the_catalog_tab(self, window):
        window.dirty_tabs = set()

        window._on_remote_catalog_update({"table": "food_items", "action": "update"})

        assert window.tab_indices["food"] in window.dirty_tabs

    def test_an_unnamed_change_dirties_everything(self, window):
        window.dirty_tabs = set()
        visible = window.tabs.currentIndex()

        window._on_remote_catalog_update({"action": "delete", "name": "Oats"})

        expected = set(range(window.tabs.count())) - {visible}
        assert window.dirty_tabs == expected

    def test_an_empty_payload_dirties_everything_rather_than_nothing(self, window):
        window.dirty_tabs = set()
        visible = window.tabs.currentIndex()

        window._on_remote_catalog_update({})

        assert window.dirty_tabs == set(range(window.tabs.count())) - {visible}
