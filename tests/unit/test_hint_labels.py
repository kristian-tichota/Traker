import pytest

from src.domain.hints import LETTERS, labels, letters_of


class TestLabels:
    def test_as_many_rows_as_letters_take_one_letter_each(self):
        assert labels(3, "abc") == ["a", "b", "c"]

    def test_the_rest_take_the_fewest_letters_more(self):
        made = labels(30, LETTERS)

        assert made[:25] == list(LETTERS[:25])
        assert made[25:] == ["za", "zb", "zc", "zd", "ze"]

    @pytest.mark.parametrize("count", [0, 1, 2, 27, 676, 677, 2000])
    def test_no_label_begins_another(self, count):
        made = labels(count, LETTERS)

        assert len(set(made)) == len(made) == count
        ordered = sorted(made)
        assert not any(b.startswith(a) for a, b in zip(ordered, ordered[1:]))

    def test_two_letters_still_reach_every_row(self):
        assert labels(3, "ab") == ["a", "ba", "bb"]


class TestLettersOf:
    def test_letters_are_lowercased_and_said_once(self):
        assert letters_of("FjFk; ") == "fjk"

    def test_fewer_than_two_falls_back(self):
        assert letters_of("x") == LETTERS
