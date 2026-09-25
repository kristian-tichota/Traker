import itertools

import pytest
import requests

from src.desktop import anki
from tests.anki_double import FakeAnki

pytestmark = [pytest.mark.exact, pytest.mark.accessibility]


def no_wait(_seconds):
    pass


def answer(fake, ease, **waiting):
    card = anki.current(fake, "Japanese")
    anki.reveal(fake)
    return anki.grade(fake, "Japanese", card.card_id, ease, sleep=no_wait, **waiting)


class TestOpeningADeck:
    def test_the_first_card_is_the_one_anki_chose(self):
        media, shown = anki.begin(FakeAnki(), "Japanese")

        assert (media, shown.card_id, shown.due) == ("/media", 100, 3)

    def test_a_deck_anki_does_not_have_is_named(self):
        with pytest.raises(anki.NoSuchDeck):
            anki.begin(FakeAnki(), "Nope")

    def test_a_deck_with_nothing_due_is_no_card_at_all(self):
        assert anki.begin(FakeAnki(cards=()), "Japanese")[1] is None


class TestAnswering:
    def test_the_next_card_is_waited_for_and_the_answer_given_once(self):
        fake = FakeAnki(lag=3)
        anki.begin(fake, "Japanese")

        landed, shown = answer(fake, anki.GOOD)

        assert (landed, shown.card_id) == (True, 101)
        assert fake.calls.count("guiAnswerCard") == 1
        assert fake.answers == [(100, anki.GOOD)]

    def test_a_card_that_comes_straight_back_is_shown_again(self):
        fake = FakeAnki(cards=("only",))
        anki.begin(fake, "Japanese")

        landed, shown = answer(fake, anki.AGAIN)

        assert (landed, shown.card_id, fake.reps[100]) == (True, 100, 1)

    def test_the_last_card_is_the_end_of_the_deck(self):
        fake = FakeAnki(cards=("only",))
        anki.begin(fake, "Japanese")

        assert answer(fake, anki.GOOD) == (True, None)

    def test_an_answer_before_the_answer_shows_is_not_taken(self):
        fake = FakeAnki()
        anki.begin(fake, "Japanese")

        landed, shown = anki.grade(fake, "Japanese", 100, anki.GOOD, sleep=no_wait)

        assert (landed, shown.card_id, fake.reps[100]) == (False, 100, 0)

    def test_an_answer_anki_never_records_is_reported(self):
        fake = FakeAnki(lag=10_000)
        anki.begin(fake, "Japanese")

        with pytest.raises(anki.AnkiStalled):
            answer(fake, anki.GOOD, clock=itertools.count().__next__)


class TestTakingBack:
    def test_the_card_it_restored_is_shown_again(self):
        fake = FakeAnki()
        anki.begin(fake, "Japanese")
        answer(fake, anki.GOOD)

        shown = anki.take_back(fake, "Japanese")

        assert (shown.card_id, fake.reps[100]) == (100, 0)


class TestTheConnection:
    def test_the_request_is_the_one_ankiconnect_reads(self, monkeypatch):
        posted = []

        class Reply:
            def json(self):
                return {"result": 6, "error": None}

        def post(url, json=None, timeout=None):
            posted.append((url, json))
            return Reply()

        monkeypatch.setattr(anki.requests, "post", post)

        assert anki.AnkiConnect("http://anki.test").call("version") == 6
        assert posted == [("http://anki.test",
                           {"action": "version", "version": 6, "params": {}})]

    def test_an_address_nothing_answers_is_unreachable(self, offline_requests):
        with pytest.raises(anki.AnkiUnreachable):
            anki.AnkiConnect().call("version")

    def test_an_error_anki_reports_is_refused(self, monkeypatch):
        class Reply:
            def json(self):
                return {"result": None, "error": "collection is not available"}

        monkeypatch.setattr(anki.requests, "post", lambda *a, **k: Reply())

        with pytest.raises(anki.AnkiRefused, match="collection is not available"):
            anki.AnkiConnect().call("guiDeckReview", name="Japanese")

    def test_an_answer_that_is_not_json_is_unreachable(self, monkeypatch):
        class Reply:
            def json(self):
                raise requests.JSONDecodeError("Expecting value", "", 0)

        monkeypatch.setattr(anki.requests, "post", lambda *a, **k: Reply())

        with pytest.raises(anki.AnkiUnreachable):
            anki.AnkiConnect().call("version")
