import logging
import time
from typing import NamedTuple

import requests

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8765"
API_VERSION = 6
TIMEOUT_SECS = 5.0

AGAIN, GOOD = 1, 3

POLL_SECS = 0.05
SETTLE_SECS = 5.0

SEPARATOR = "::"


class AnkiUnreachable(ConnectionError):
    """Nothing answered at the AnkiConnect address."""


class AnkiRefused(RuntimeError):
    """AnkiConnect answered with an error of its own."""


class NoSuchDeck(LookupError):
    """Anki has no deck by the name asked for."""


class AnkiStalled(TimeoutError):
    """Anki did not take the answer in time, or did not move on from it."""


EXPECTED = (AnkiUnreachable, AnkiRefused, NoSuchDeck, AnkiStalled)


class Shown(NamedTuple):
    """The card Anki's reviewer holds, and how many cards the deck still owes."""

    card_id: int
    question: str
    answer: str
    ordinal: int
    due: int


class Deck(NamedTuple):
    """One deck as Anki's deck list shows it, and what it still owes today."""

    name: str
    new: int
    learning: int
    review: int

    @property
    def depth(self) -> int:
        return self.name.count(SEPARATOR)

    @property
    def leaf(self) -> str:
        """Return the last part of the name, the one Anki's list shows."""
        return self.name.rsplit(SEPARATOR, 1)[-1]

    @property
    def owed(self) -> int:
        return self.new + self.learning + self.review


class AnkiConnect:
    """AnkiConnect's HTTP interface, one action per call."""

    def __init__(self, url=DEFAULT_URL, timeout=TIMEOUT_SECS):
        self.url = str(url or DEFAULT_URL)
        self.timeout = timeout

    def call(self, action, **params):
        """Run one action and return its result."""
        body = {"action": action, "version": API_VERSION, "params": params}
        try:
            reply = requests.post(self.url, json=body, timeout=self.timeout).json()
        except (requests.RequestException, ValueError) as error:
            raise AnkiUnreachable(f"{self.url}: {error}") from error
        if not isinstance(reply, dict):
            raise AnkiRefused(f"{action}: unexpected reply {reply!r}")
        if reply.get("error"):
            raise AnkiRefused(f"{action}: {reply['error']}")
        return reply.get("result")


def begin(client, deck) -> tuple:
    """Open Anki's reviewer on deck: (media folder, first card or None when none is due)."""
    if not client.call("guiDeckReview", name=deck):
        raise NoSuchDeck(deck)
    return str(client.call("getMediaDirPath") or ""), current(client, deck)


def current(client, deck):
    """Return the card Anki's reviewer holds, or None once the deck owes nothing."""
    active, card, stats = _many(client, ("guiReviewActive", {}), ("guiCurrentCard", {}),
                                ("getDeckStats", {"decks": [deck]}))
    if not active.get("result") or card.get("error"):
        return None
    card = card["result"]
    return Shown(int(card["cardId"]), str(card.get("question") or ""),
                 str(card.get("answer") or ""), int(card.get("fieldOrder") or 0),
                 _due(stats.get("result")))


def decks(client) -> list:
    """Return every deck Anki's deck list shows, in its order, with what each owes."""
    ids = client.call("deckNamesAndIds") or {}
    if not isinstance(ids, dict):
        raise AnkiRefused(f"deckNamesAndIds: unexpected reply {ids!r}")
    stats = client.call("getDeckStats", decks=list(ids)) or {}
    if not isinstance(stats, dict):
        raise AnkiRefused(f"getDeckStats: unexpected reply {stats!r}")
    listed = [Deck(str(name), *_owed(stats[str(deck_id)]))
              for name, deck_id in ids.items()
              if isinstance(stats.get(str(deck_id)), dict)]
    return sorted(listed, key=lambda deck: [part.casefold()
                                            for part in deck.name.split(SEPARATOR)])


def reveal(client) -> bool:
    """Turn Anki's card to its answer, reporting whether the reviewer holds one."""
    return bool(client.call("guiShowAnswer"))


def grade(client, deck, card_id, ease, sleep=time.sleep, clock=time.monotonic) -> tuple:
    """Answer the card, wait until Anki has taken it, and return (landed, next card)."""
    before = _reps(client, card_id)
    if not client.call("guiAnswerCard", ease=int(ease)):
        return False, current(client, deck)
    deadline = clock() + SETTLE_SECS
    while _reps(client, card_id) <= before:
        if clock() >= deadline:
            raise AnkiStalled(f"card {card_id} was answered and never recorded")
        sleep(POLL_SECS)
    return True, current(client, deck)


def take_back(client, deck):
    """Undo the last answer and open the deck again on the card it restored."""
    client.call("guiUndo")
    return begin(client, deck)[1]


def _many(client, *actions) -> list:
    """Run several actions in one request, each answering {result, error}."""
    answers = client.call("multi", actions=[
        {"action": name, "version": API_VERSION, "params": params}
        for name, params in actions])
    if not isinstance(answers, list) or len(answers) != len(actions) \
            or not all(isinstance(answer, dict) for answer in answers):
        raise AnkiRefused(f"multi: unexpected reply {answers!r}")
    return answers


def _reps(client, card_id) -> int:
    """Return how many times Anki has recorded an answer to card_id."""
    info = client.call("cardsInfo", cards=[int(card_id)])
    if not info or not isinstance(info[0], dict) or "reps" not in info[0]:
        raise AnkiRefused(f"cardsInfo: no card {card_id}")
    return int(info[0]["reps"])


def _due(stats) -> int:
    """Return what the one deck getDeckStats was asked about still owes today."""
    return sum(sum(_owed(entry)) for entry in (stats or {}).values()
               if isinstance(entry, dict))


def _owed(entry) -> tuple:
    """Return the new, learning and review cards one getDeckStats entry owes today."""
    return tuple(int(entry.get(key) or 0)
                 for key in ("new_count", "learn_count", "review_count"))
