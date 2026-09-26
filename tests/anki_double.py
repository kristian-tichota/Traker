import itertools

from src.desktop import anki


class FakeAnki:
    """Anki's reviewer as AnkiConnect drives it: it answers late and does not refresh on undo."""

    url = "http://anki.test"

    def __init__(self, cards=("q1", "q2", "q3"), lag=0, decks=("Japanese",)):
        """Hold decks by name, or by name to their cards, where None is a deck the list hides."""
        if not isinstance(decks, dict):
            decks = dict.fromkeys(decks, cards)
        numbers = itertools.count(100)
        self.ids = {name: index for index, name in enumerate(decks, start=1)}
        self.hidden = {name for name, texts in decks.items() if texts is None}
        self.queues, self.text, self.home = {}, {}, {}
        for name, texts in decks.items():
            self.queues[name] = [next(numbers) for _ in texts or ()]
            self.text.update(zip(self.queues[name], texts or ()))
            self.home.update(dict.fromkeys(self.queues[name], name))
        self.reps = dict.fromkeys(self.text, 0)
        self.reviewing = None
        self.shown = None
        self.state = None
        self.lag = lag
        self.pending = None
        self.answers = []
        self.calls = []

    @property
    def queue(self):
        return self.queues.get(self.reviewing, [])

    def call(self, action, **params):
        self.calls.append(action)
        self._tick()
        return self._run(action, params)

    def _run(self, action, params):
        return getattr(self, action)(**params)

    def _tick(self):
        if self.pending is not None:
            self.pending[2] -= 1
            if self.pending[2] <= 0:
                self._land()

    def _land(self):
        card, ease, _left = self.pending
        self.pending = None
        self.reps[card] += 1
        self.queue.remove(card)
        if ease == anki.AGAIN:
            self.queue.append(card)
        self.answers.append((card, ease))
        self._next()

    def _next(self):
        self.shown = self.queue[0] if self.queue else None
        self.state = "question" if self.shown is not None else None

    def _active(self):
        return self.shown is not None and self.state is not None

    def guiDeckReview(self, name):
        if name not in self.ids:
            return False
        self.reviewing = name
        self._next()
        return True

    def guiReviewActive(self):
        return self._active()

    def guiCurrentCard(self):
        if not self._active():
            raise anki.AnkiRefused("guiCurrentCard: Gui review is not currently active.")
        text = self.text[self.shown]
        return {"cardId": self.shown, "question": f"<b>{text}</b>[anki:play:q:0]",
                "answer": f"<b>{text}</b><hr id=answer>{text} answered",
                "fieldOrder": 0, "buttons": [1, 3]}

    def guiShowAnswer(self):
        if not self._active():
            return False
        self.state = "answer"
        return True

    def guiAnswerCard(self, ease):
        if not self._active() or self.state != "answer":
            return False
        self.state = "transition"
        self.pending = [self.shown, ease, self.lag]
        if self.lag <= 0:
            self._land()
        return True

    def guiUndo(self):
        if self.answers:
            card, ease = self.answers.pop()
            self.reps[card] -= 1
            queue = self.queues[self.home[card]]
            if ease == anki.AGAIN:
                queue.remove(card)
            queue.insert(0, card)
        return True

    def cardsInfo(self, cards):
        return [{"cardId": card, "reps": self.reps[card]} for card in cards]

    def deckNamesAndIds(self):
        return dict(self.ids)

    def getDeckStats(self, decks):
        return {str(self.ids[name]): {"deck_id": self.ids[name],
                                      "name": name.rsplit("::", 1)[-1],
                                      "new_count": 0, "learn_count": 0,
                                      "review_count": len(self.queues[name])}
                for name in decks if name in self.ids and name not in self.hidden}

    def getMediaDirPath(self):
        return "/media"

    def multi(self, actions):
        replies = []
        for action in actions:
            try:
                replies.append({"result": self._run(action["action"],
                                                    action.get("params", {})),
                                "error": None})
            except anki.AnkiRefused as error:
                replies.append({"result": None, "error": str(error)})
        return replies
