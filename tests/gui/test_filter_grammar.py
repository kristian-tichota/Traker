import pytest

from src.gui.filtering import EMPTY, FilterError, Term, parse, resolve_field

pytestmark = pytest.mark.accessibility

HEADERS = ["Date", "Meal Type", "Food Name", "Servings", "Calories", "Protein",
           "Carbs", "Sugars", "Fats", "Sat Fat", "Salt", "Fibre"]

ROW = {"Date": "2026-09-05", "Meal Type": "Breakfast", "Food Name": "Rolled Oats",
       "Servings": 2.0, "Calories": 312.4, "Protein": 20.0, "Carbs": 40.0,
       "Sugars": 2.0, "Fats": 5.0, "Sat Fat": 1.0, "Salt": 0.5, "Fibre": 8.0}

ACCENTED = dict(ROW, **{"Food Name": "Řízek s bramborem"})


def matches(text, row=None, headers=None):
    return parse(text, headers or HEADERS).matches(row or ROW)


class TestTheBareWordFastPath:
    def test_one_word_searches_every_column(self):
        assert matches("oats") is True
        assert matches("breakfast") is True
        assert matches("2026-09") is True

    def test_a_word_in_no_column_does_not_match(self):
        assert matches("salmon") is False

    def test_letter_case_is_ignored(self):
        assert matches("ROLLED") is True
        assert matches("rolled") is True

    def test_accents_are_ignored(self):
        assert matches("rizek", ACCENTED) is True
        assert matches("Rizek", ACCENTED) is True
        assert matches("řízek", ACCENTED) is True

    def test_it_matches_a_number_column_as_text(self):
        assert matches("312") is True

    def test_an_empty_filter_matches_everything(self):
        assert parse("", HEADERS) is EMPTY
        assert parse("   ", HEADERS).matches(ROW) is True
        assert not parse("", HEADERS)

    def test_a_none_cell_never_matches_a_word(self):
        orphaned = dict(ROW, **{"Food Name": None})
        assert parse("oats", HEADERS).matches(orphaned) is False


class TestNamingAColumn:
    def test_a_field_term_narrows_to_that_column(self):
        assert matches("food:oats") is True
        assert matches("meal:oats") is False

    def test_a_full_header_names_its_column(self):
        assert resolve_field("Calories", HEADERS) == "Calories"
        assert resolve_field("calories", HEADERS) == "Calories"

    def test_an_alias_names_its_column(self):
        assert resolve_field("kcal", HEADERS) == "Calories"
        assert resolve_field("cal", HEADERS) == "Calories"
        assert resolve_field("prot", HEADERS) == "Protein"
        assert resolve_field("food", HEADERS) == "Food Name"

    def test_a_prefix_names_its_column_when_it_is_unambiguous(self):
        assert resolve_field("fib", HEADERS) == "Fibre"

    def test_an_ambiguous_prefix_is_refused_rather_than_guessed(self):
        with pytest.raises(FilterError) as refused:
            resolve_field("s", HEADERS)
        assert "matches" in str(refused.value)

    def test_a_column_that_does_not_exist_is_refused(self):
        with pytest.raises(FilterError) as refused:
            resolve_field("nonsense", HEADERS)
        assert "No column called 'nonsense'" in str(refused.value)

    def test_the_refusal_lists_the_columns_that_do_exist(self):
        with pytest.raises(FilterError) as refused:
            resolve_field("nonsense", HEADERS)
        assert "Calories" in str(refused.value)

    def test_the_units_need_not_be_typed(self):
        headers = ["Date", "Beverage Name", "Caffeine (mg)", "Antioxidants (mg)"]
        assert resolve_field("caf", headers) == "Caffeine (mg)"


class TestComparisons:
    def test_greater_than_compares_as_a_number(self):
        assert matches("kcal>300") is True
        assert matches("kcal>400") is False

    def test_the_comparison_is_numeric_not_textual(self):
        small = dict(ROW, Calories=9.0)
        assert parse("kcal>300", HEADERS).matches(small) is False

    def test_less_than_and_the_inclusive_forms(self):
        assert matches("kcal<400") is True
        assert matches("prot>=20") is True
        assert matches("prot<=20") is True
        assert matches("prot>20") is False

    def test_not_equal(self):
        assert matches("meal!=lunch") is True
        assert matches("meal!=breakfast") is False

    def test_colon_and_equals_mean_the_same(self):
        assert matches("meal:breakfast") == matches("meal=breakfast")

    def test_a_text_match_is_containment_but_a_number_match_is_exact(self):
        assert matches("food:oat") is True
        assert matches("kcal:312.4") is True
        assert matches("kcal:312") is False

    def test_a_missing_value_never_satisfies_a_comparison(self):
        orphaned = dict(ROW, Calories=None)
        assert parse("kcal>0", HEADERS).matches(orphaned) is False
        assert parse("kcal<1000000", HEADERS).matches(orphaned) is False


class TestDatesAreTypedTheWayTheyAreRead:
    def test_a_czech_date_compares_against_the_stored_iso(self):
        assert matches("date>01.08.2026") is True
        assert matches("date>01.10.2026") is False

    def test_the_stored_iso_form_works_too(self):
        assert matches("date>2026-08-01") is True
        assert matches("date>2026-10-01") is False

    def test_the_two_spellings_agree(self):
        assert matches("date>01.08.2026") == matches("date>2026-08-01")

    def test_an_exact_date_matches(self):
        assert matches("date:2026-09-05") is True


class TestMealShortcuts:
    @pytest.mark.parametrize("shortcut,meal", [
        ("b", "Breakfast"), ("l", "Lunch"), ("d", "Dinner"), ("s", "Supplement")])
    def test_each_shortcut_names_its_meal(self, shortcut, meal):
        row = dict(ROW, **{"Meal Type": meal})
        assert parse(f"meal:{shortcut}", HEADERS).matches(row) is True

    def test_a_shortcut_does_not_match_another_meal(self):
        assert matches("meal:l") is False

    def test_they_are_read_from_the_command_grammar(self):
        from src.gui.commands import MEAL_SHORTCUTS
        from src.gui.filtering import _MEAL_SHORTCUTS

        assert set(_MEAL_SHORTCUTS) == set(MEAL_SHORTCUTS)

    def test_the_full_word_still_works(self):
        assert matches("meal:breakfast") is True


class TestTermsCombine:
    def test_two_terms_both_have_to_match(self):
        assert matches("oats meal:b") is True
        assert matches("oats meal:l") is False

    def test_a_bare_word_mixes_with_a_field_term(self):
        assert matches("oats date>01.08.2026") is True
        assert matches("oats date>01.10.2026") is False

    def test_three_terms(self):
        assert matches("oats meal:b kcal>300") is True
        assert matches("oats meal:b kcal>400") is False

    def test_the_term_count_is_readable(self):
        assert len(parse("oats meal:b kcal>300", HEADERS)) == 3


class TestAMalformedTermIsRefused:
    def test_an_unknown_column_raises(self):
        with pytest.raises(FilterError):
            parse("nonsense:x", HEADERS)

    def test_a_comparison_against_a_word_raises(self):
        with pytest.raises(FilterError) as refused:
            parse("kcal>abc", HEADERS)
        assert "not a number or a date" in str(refused.value)

    def test_a_term_with_no_value_raises(self):
        with pytest.raises(FilterError) as refused:
            parse("kcal>", HEADERS)
        assert "missing a value" in str(refused.value)

    def test_a_good_term_beside_a_bad_one_still_raises(self):
        with pytest.raises(FilterError):
            parse("oats nonsense:x", HEADERS)

    def test_an_equality_against_a_word_is_fine(self):
        assert matches("food:oats") is True

    def test_a_word_containing_a_colon_is_a_bare_term_not_a_field(self):
        row = dict(ROW, **{"Food Name": "Yoghurt: Greek"})
        assert parse("greek", HEADERS).matches(row) is True


class TestTermsAreReadable:
    def test_a_term_says_what_it_is(self):
        (term,) = parse("kcal>300", HEADERS).terms
        assert isinstance(term, Term)
        assert (term.field, term.operator, term.value) == ("Calories", ">", "300")

    def test_a_bare_term_names_no_field(self):
        (term,) = parse("oats", HEADERS).terms
        assert term.field is None

    def test_the_longest_operator_wins(self):
        (term,) = parse("kcal>=300", HEADERS).terms
        assert term.operator == ">="
        assert term.value == "300"
