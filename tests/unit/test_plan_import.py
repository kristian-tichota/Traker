import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

import import_training_plan as importer  # noqa: E402


def document(*movements, **overrides):
    session = dict({"date": "2026-09-14", "week": 1, "name": "Upper A",
                    "movements": list(movements)}, **overrides.pop("session", {}))
    return dict({"name": "Cycle 1", "start_date": "2026-09-14", "weeks": 17,
                 "sessions": [session]}, **overrides)


def movement(**overrides):
    return dict({"exercise": "DB Row", "sets": 3, "target_low": 8,
                 "target_high": 12}, **overrides)


class TestAWellFormedCycle:
    def test_it_has_nothing_to_say(self):
        assert importer.complaints(document(movement())) == []


class TestAMovementWrittenWrong:
    def test_one_with_no_exercise_is_named_as_that_rather_than_as_a_missing_item(self):
        said = importer.complaints(document({"sets": 3}))

        assert any("a movement with no exercise" in line for line in said)

    def test_an_empty_exercise_is_the_same_complaint(self):
        said = importer.complaints(document(movement(exercise="")))

        assert any("a movement with no exercise" in line for line in said)

    @pytest.mark.parametrize("written", ["3x", "three", [3]])
    def test_a_set_count_that_is_not_a_number_is_a_sentence_not_a_traceback(
        self, written
    ):
        said = importer.complaints(document(movement(sets=written)))

        assert any("sets must be a whole number" in line for line in said)

    def test_a_set_count_left_out_is_the_schema_default_rather_than_a_complaint(self):
        assert importer.complaints(document(movement(sets=None))) == []

    @pytest.mark.parametrize("written", [6, -1])
    def test_a_set_count_one_ledger_row_cannot_hold_is_refused(self, written):
        said = importer.complaints(document(movement(sets=written)))

        assert any("sets must be a whole number" in line for line in said)

    def test_an_unknown_key_is_named_with_the_movement_it_is_on(self):
        said = importer.complaints(document(movement(reps=8)))

        assert any("unknown key 'reps'" in line and "DB Row" in line
                   for line in said)


class TestACycleWrittenWrong:
    def test_two_sessions_on_one_day_are_refused(self):
        doc = document(movement())
        doc["sessions"].append(dict(doc["sessions"][0], name="Lower A"))

        assert any("already on that day" in line
                   for line in importer.complaints(doc))

    @pytest.mark.parametrize("field", ["name", "start_date", "weeks"])
    def test_the_cycle_needs_its_own_fields(self, field):
        doc = document(movement())
        doc[field] = None

        assert any(field in line for line in importer.complaints(doc))

    def test_a_cycle_with_no_sessions_says_so_and_stops_there(self):
        doc = document(movement())
        doc["sessions"] = []

        assert importer.complaints(doc) == ["the cycle has no sessions"]
