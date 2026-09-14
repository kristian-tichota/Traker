import pytest

from src.database.cache import (
    NOTHING_CHANGED, LedgerCache, domain_for_path)
from src.database.rows import FoodLogRow


def food_row(row_id, date):
    return FoodLogRow.from_server(
        [row_id, 0, date, "Breakfast", "Oats", 1.0, 100.0, None, 380.0, 13.0,
         60.0, 1.0, 7.0, 1.2, 0.0, 10.0])

ROWS = [food_row(1, "2026-01-01"), food_row(2, "2026-06-15"), food_row(3, "2026-09-01")]


class TestKeyingAndHits:
    def test_an_unasked_read_is_a_miss(self):
        cache = LedgerCache()

        assert cache.get("food") is None
        assert cache.misses == 1

    def test_what_was_stored_comes_back(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.get("food") == ROWS
        assert cache.hits == 1

    def test_the_rows_handed_back_are_not_the_stored_list(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        answered = cache.get("food")
        answered.append(food_row(99, "2026-12-01"))

        assert len(cache.get("food")) == len(ROWS)

    def test_domains_do_not_share_entries(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.get("exercise") is None

    def test_a_bound_is_part_of_the_key(self):
        cache = LedgerCache()
        cache.put("food", "2026-06-01", ROWS[1:])

        assert cache.get("food", "2026-06-01") == ROWS[1:]


class TestAFullReadAnswersABoundedOne:
    def test_a_bounded_read_is_served_from_the_full_one(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.get("food", "2026-06-01") == ROWS[1:]

    def test_the_bound_is_inclusive_of_its_own_day(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.get("food", "2026-06-15") == ROWS[1:]

    def test_a_bound_beyond_every_row_answers_empty_not_missing(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.get("food", "2027-01-01") == []

    def test_a_bounded_read_does_not_answer_a_wider_one(self):
        cache = LedgerCache()
        cache.put("food", "2026-06-01", ROWS[1:])

        assert cache.get("food", "2026-01-01") is None
        assert cache.get("food") is None

    def test_a_bounded_read_does_not_answer_a_different_bound(self):
        cache = LedgerCache()
        cache.put("food", "2026-06-01", ROWS[1:])

        assert cache.get("food", "2026-07-01") is None

    def test_a_row_whose_date_cannot_be_read_is_kept(self):
        cache = LedgerCache()
        cache.put("food", None, [("no-date-here",)])

        assert cache.get("food", "2026-06-01") == [("no-date-here",)]


class TestInvalidation:
    def test_dropping_a_domain_forgets_it(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        cache.drop(("food",))

        assert cache.get("food") is None

    def test_dropping_a_domain_forgets_its_bounded_reads_too(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)
        cache.put("food", "2026-06-01", ROWS[1:])

        cache.drop(("food",))

        assert cache.get("food", "2026-06-01") is None

    def test_dropping_one_domain_leaves_the_others(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)
        cache.put("exercise", None, ROWS)

        cache.drop(("food",))

        assert cache.get("exercise") is not None

    def test_a_bare_string_is_accepted_as_one_domain(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        cache.drop("food")

        assert cache.get("food") is None

    def test_dropping_nothing_drops_nothing(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)

        assert cache.drop(()) == 0
        assert cache.get("food") is not None

    def test_clear_forgets_every_domain(self):
        cache = LedgerCache()
        cache.put("food", None, ROWS)
        cache.put("exercise", None, ROWS)

        cache.clear()

        assert len(cache) == 0

    def test_there_is_no_expiry_to_configure(self):
        cache = LedgerCache()

        for forbidden in ("ttl", "expiry", "max_age", "expires_at"):
            assert not hasattr(cache, forbidden)


class TestWhichDomainAWriteChanges:
    @pytest.mark.parametrize("path,expected", [
        ("/api/logs/food", "food"),
        ("/api/logs/beverage", "beverage"),
        ("/api/logs/exercise", "exercise"),
        ("/api/logs/supplement", "supplement"),
        ("/api/logs/mobility", "mobility"),
        ("/api/catalog/food", "food"),
        ("/api/catalog/exercise", "exercise"),
        ("/api/logs/food_logs/7", "food"),
        ("/api/logs/food_items/7", "food"),
        ("/api/logs/exercise_items/3", "exercise"),
        ("/api/plans", "plan"),
        ("/api/plans/2/sessions", "plan"),
        ("/api/logs/plan_movements/9", "plan"),
    ])
    def test_a_named_path_names_its_domain(self, path, expected):
        assert domain_for_path(path) == expected

    def test_a_catalog_write_names_the_subject_so_the_logs_drop_too(self):
        assert domain_for_path("/api/catalog/food") == domain_for_path("/api/logs/food")

    def test_a_settings_write_changes_no_household_data(self):
        assert domain_for_path("/api/settings/ex_graph_slot_1") is NOTHING_CHANGED
        assert not NOTHING_CHANGED

    def test_a_delete_by_name_cannot_say_which_catalog(self):
        assert domain_for_path("/api/catalog/items/Rolled%20Oats") is None

    def test_logging_a_planned_session_names_both_subjects_it_changed(self):
        assert domain_for_path("/api/plans/2/log") == ("plan", "exercise")

    def test_a_pomodoro_write_names_pomodoro(self):
        assert domain_for_path("/api/pomodoro/heartbeat") == "pomodoro"

    def test_a_query_string_does_not_confuse_it(self):
        assert domain_for_path("/api/logs/food?since=2026-01-01") == "food"

    def test_an_unrecognised_path_cannot_tell(self):
        assert domain_for_path("/api/nonsense") is None
        assert domain_for_path("") is None
