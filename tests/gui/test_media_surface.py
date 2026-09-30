import socket
import sys
import tempfile
import time

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThreadPool, Qt
from PyQt6.QtGui import QPageSize, QPainter, QPdfWriter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QLabel, QTreeWidgetItemIterator, QWidget

from src.desktop import anki, rest_positions
from src.desktop.activities import (ANY_DECK, BOOK, BreakActivity, DECK, DOCUMENT, SHELF,
                                    VIDEO)
from src.config import PALETTE
from src.domain import media
from src.domain.media import Place
from src.gui.components import media_progress, media_surface
from src.gui.components.book_pane import BookPane
from src.gui.components.media_surface import (AGAIN_SAID, ANSWER, GOOD_SAID, QUESTION,
                                              UNDONE, DeckPane, DocumentPane,
                                              LibraryPane, MediaSurface, MpvScreen,
                                              PagePane, VideoPane, build_pane,
                                              card_page)
from tests.anki_double import FakeAnki

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]

PAGES = 3


@pytest.fixture
def paper(qapp, tmp_path):
    path = str(tmp_path / "paper.pdf")
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    painter = QPainter(writer)
    for page in range(PAGES):
        painter.drawText(200, 200, f"page {page + 1}")
        if page < PAGES - 1:
            writer.newPage()
    painter.end()
    return path


@pytest.fixture
def timer_double():
    class Timer:
        time_left_ms = 125_000
        release_hold_secs = 10
        waiting_for_work_start = False
        over_by_ms = staticmethod(lambda: 83_000)

        def wall_hint(self):
            return ("PRESS ESC TO START FOCUS" if self.waiting_for_work_start
                    else "HOLD ESC 10s TO LEAVE")

    return Timer()


def failure_of(pane) -> str:
    return " ".join(label.text() for label in pane.findChildren(QLabel))


class TestReadingADocument:
    def test_the_page_is_given_the_whole_pane(self, qapp, paper):
        pane = DocumentPane(paper)

        pane.resize(1600, 900)
        pane.show()
        qapp.processEvents()

        assert pane.view.geometry() == pane.rect()
        assert pane.view.viewport().height() == pane.height()
        pane.close()
        pane.deleteLater()

    def test_it_opens_at_the_first_page(self, paper):
        pane = DocumentPane(paper)

        assert pane.document.pageCount() == PAGES
        assert pane.position() == 0

    def test_a_page_forward_and_a_page_back(self, paper):
        pane = DocumentPane(paper)

        pane.step(1)
        assert pane.position() == 1

        pane.step(-1)
        assert pane.position() == 0

    def test_the_big_key_turns_the_page(self, paper):
        pane = DocumentPane(paper)

        pane.toggle()

        assert pane.position() == 1

    def test_it_does_not_go_before_the_first_page(self, paper):
        pane = DocumentPane(paper)

        pane.step(-5)

        assert pane.position() == 0

    def test_or_past_the_last(self, paper):
        pane = DocumentPane(paper)

        pane.step(PAGES + 5)

        assert pane.position() == PAGES - 1

    def test_it_comes_back_to_the_page_it_was_left_on(self, paper):
        pane = DocumentPane(paper, start_at=2)

        assert pane.position() == 2

    def test_and_stays_on_it_once_the_screen_shows_it(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)

        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        assert pane.position() == 2
        assert pane.view.verticalScrollBar().value() > 0
        pane.close()

    def test_the_member_paging_away_from_it_settles_there(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)
        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        pane.step(-1)
        qapp.processEvents()

        assert pane.position() == 1
        pane.close()

    def test_and_neither_does_scrolling_out_of_it(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)
        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        for _ in range(8):
            pane.nudge(1)
        qapp.processEvents()

        assert pane.position() < 2
        pane.close()

    def test_scrolling_carries_on_through_the_document(self, paper):
        pane = DocumentPane(paper)

        for _ in range(6):
            pane.nudge(-1)
        assert pane.position() > 0

        for _ in range(20):
            pane.nudge(1)
        assert pane.position() == 0

    def test_a_file_that_is_not_there_says_so_on_the_screen(self, qapp, tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))

        assert pane.view.isHidden() is True
        assert "COULD NOT READ" in failure_of(pane)

    def test_a_second_file_goes_through_the_same_pane(self, qapp, paper, tmp_path):
        pane = DocumentPane(paper)
        pane.step(2)
        assert pane.position() == PAGES - 1

        pane.open(paper)

        assert pane.document.pageCount() == PAGES
        assert pane.position() == 0

    def test_re_opening_it_carries_on_where_it_stopped(self, qapp, paper):
        pane = DocumentPane(paper)
        pane.stop()

        pane.open(paper, start_at=2)

        assert pane.position() == 2

    def test_a_file_it_could_not_read_does_not_damn_the_next_one(self, qapp, paper,
                                                                 tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))
        assert "COULD NOT READ" in failure_of(pane)

        pane.open(paper)

        assert pane.view.isHidden() is False
        assert pane.document.pageCount() == PAGES

    def test_and_takes_its_keys_without_raising(self, qapp, tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))

        pane.toggle()
        pane.step(1)
        pane.nudge(1)
        pane.stop()

        assert pane.position() == 0


NOVEL = "".join(f"<p>{'吾輩は猫である。名前はまだ無い。' * 6}（{n}）</p>" for n in range(30))


def settle_the_book(qapp, pane, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QThreadPool.globalInstance().waitForDone(10)
        qapp.processEvents()
        if not pane.busy and (pane.laid_out is not None or failure_of(pane)):
            return pane
        time.sleep(0.005)
    raise AssertionError("the book never settled")


@pytest.fixture
def reading(qapp, epub):
    novel = epub("<p>表紙</p>", NOVEL, "<p>了</p>", title="吾輩は猫である",
                 language="ja", vertical=True, direction="rtl")
    opened = []

    def _open(start_at=0, path=None):
        pane = BookPane(path or novel, start_at)
        pane.resize(900, 700)
        pane.show()
        opened.append(pane)
        return settle_the_book(qapp, pane)

    def _turn(pane, *turns):
        for turn in turns:
            turn()
            settle_the_book(qapp, pane)
        return pane.chapter, pane.laid_out["page"]

    _open.turn = _turn
    yield _open
    for pane in opened:
        pane.stop()
        pane.close()


class TestReadingABook:
    def test_it_opens_at_the_start_with_its_own_title(self, reading):
        pane = reading()

        assert (pane.chapter, pane.laid_out["page"], pane.position()) == (0, 0, 0)
        assert pane.title() == "吾輩は猫である" and pane.duration() > 0

    def test_a_long_chapter_is_several_pages(self, reading):
        pane = reading()

        reading.turn(pane, pane.toggle)

        assert pane.laid_out["pages"] > 1

    def test_the_page_turns_on_across_chapters_and_back(self, reading):
        pane = reading()

        assert reading.turn(pane, pane.toggle, pane.toggle) == (1, 1)
        assert reading.turn(pane, pane.undo, pane.undo) == (0, 0)

    def test_the_arrow_pointing_along_a_right_to_left_book_turns_on(self, reading):
        pane = reading()

        assert pane.rtl is True
        assert reading.turn(pane, lambda: pane.step(-1)) == (1, 0)
        assert reading.turn(pane, lambda: pane.step(1)) == (0, 0)

    def test_up_goes_to_the_start_of_the_chapter_and_then_the_one_before(self, reading):
        pane = reading()
        reading.turn(pane, lambda: pane.nudge(-1), pane.toggle)

        assert reading.turn(pane, lambda: pane.nudge(1)) == (1, 0)
        assert reading.turn(pane, lambda: pane.nudge(1)) == (0, 0)

    def test_it_comes_back_to_the_page_it_was_left_on(self, reading):
        first = reading()
        reading.turn(first, first.toggle, first.toggle, first.toggle)

        again = reading(start_at=first.position())

        assert (again.chapter, again.laid_out["page"], again.position()) == (
            first.chapter, first.laid_out["page"], first.position())

    def test_the_last_page_is_the_whole_of_it(self, reading):
        pane = reading(start_at=10**9)

        assert pane.chapter == 2 and pane.position() == pane.duration()

    def test_the_page_is_set_light_in_the_middle_of_the_pane(self, reading):
        pane = reading()

        painted = pane.grab().toImage()

        assert pane.view.width() < pane.width() and pane.view.height() < pane.height()
        assert painted.pixelColor(3, 3).name() == PALETTE['base3']
        assert painted.pixelColor(pane.view.x() + 3, pane.view.y() + 3).name() == PALETTE['base3']

    def test_a_file_that_is_not_a_book_says_so(self, qapp, reading, tmp_path):
        written = tmp_path / "x.epub"
        written.write_bytes(b"not a zip")

        pane = reading(path=str(written))

        assert "COULD NOT READ" in failure_of(pane)

    def test_a_machine_without_the_web_engine_says_so(self, qapp, monkeypatch):
        monkeypatch.setitem(sys.modules, "PyQt6.QtWebEngineWidgets", None)

        pane = BookPane()

        assert pane.view is None and "COULD NOT READ" in failure_of(pane)

    def test_a_book_unpacked_for_a_pane_already_gone_is_not_left_behind(
            self, qapp, epub, settled, tmp_path, monkeypatch):
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(scratch))
        pane = BookPane(epub("<p>一</p>"))

        sip.delete(pane)
        settled()

        assert list(scratch.iterdir()) == []


@pytest.fixture
def browsing(qapp, monkeypatch):
    from PyQt6.QtWebEngineCore import QWebEngineProfile
    profile = QWebEngineProfile()
    monkeypatch.setattr(media_surface, "_page_profile", lambda: profile)
    opened = []

    def _open(url):
        pane = PagePane(url)
        opened.append(pane)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (pane.loaded or failure_of(pane)):
            qapp.processEvents()
            time.sleep(0.005)
        return pane

    yield _open
    for pane in opened:
        pane.shutdown()


def closed_port() -> int:
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        return bound.getsockname()[1]


class TestOpeningAPage:
    def test_a_page_that_loads_is_shown(self, browsing):
        pane = browsing("data:text/html,<p>x</p>")

        assert pane.loaded and failure_of(pane) == ""

    def test_the_same_url_again_keeps_the_page_as_it_was_left(self, browsing, monkeypatch):
        pane = browsing("data:text/html,<p>x</p>")
        loads = []
        monkeypatch.setattr(pane.view, "load", loads.append)

        pane.open("data:text/html,<p>x</p>")

        assert loads == []

    def test_a_page_that_does_not_answer_says_so(self, browsing):
        url = f"http://127.0.0.1:{closed_port()}/"

        pane = browsing(url)

        assert f"COULD NOT OPEN {url}" == failure_of(pane).replace("\n", " ")

    def test_a_machine_without_the_web_engine_says_so(self, qapp, monkeypatch):
        monkeypatch.setitem(sys.modules, "PyQt6.QtWebEngineWidgets", None)

        pane = PagePane()

        assert pane.view is None and "COULD NOT OPEN" in failure_of(pane)


class TestPlayingAVideo:
    def test_it_is_built_and_asked_for_its_position(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.position() == 0

    def test_a_file_that_is_not_there_says_so_on_the_screen(self, qapp, tmp_path,
                                                            settled):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        pane.screen_widget.player = None
        pane._show_failure("no such file")
        settled()

        assert "COULD NOT PLAY" in failure_of(pane)

    def test_a_player_that_would_not_start_says_why_in_its_own_words(
            self, qapp, tmp_path, monkeypatch, settled):
        def refuse(screen):
            screen.player_error = "libmpv would not load: undefined symbol"
            return None
        monkeypatch.setattr(MpvScreen, "_start_mpv", refuse)

        pane = VideoPane(str(tmp_path / "talk.mkv"))
        settled()

        said = failure_of(pane)
        assert "COULD NOT PLAY" in said
        assert "undefined symbol" in said

    def test_it_takes_its_keys_without_raising(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        pane.toggle()
        pane.step(1)
        pane.step(-1)
        pane.nudge(1)
        pane.nudge(-1)
        pane.stop()

    def test_the_picture_is_libmpv_drawing_into_our_own_surface(self, qapp,
                                                                tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert isinstance(pane.screen_widget, MpvScreen)
        assert isinstance(pane.screen_widget, QOpenGLWidget)
        assert pane.screen_widget.parent() is pane

    def test_the_picture_is_given_the_whole_pane(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        pane.resize(1600, 900)
        pane.show()
        qapp.processEvents()

        assert pane.screen_widget.size() == pane.size()
        pane.close()
        pane.deleteLater()

    def test_a_second_file_goes_through_the_same_player(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        widget, player = pane.screen_widget, pane.player

        pane.open(str(tmp_path / "other.mkv"))

        assert pane.screen_widget is widget
        assert pane.player is player

    def test_nothing_is_asked_to_follow_a_file_that_ends(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.player is not None
        assert pane.player.keep_open in ("yes", True)
        assert len(pane.player.playlist) <= 1

    def test_it_takes_none_of_my_keys_and_draws_none_of_its_own_furniture(
            self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.player.input_default_bindings is False
        assert pane.player.input_vo_keyboard is False
        assert pane.player.osc is False

    def test_the_volume_stays_inside_itself(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        for _ in range(20):
            pane.nudge(1)
        assert pane.player.volume == pytest.approx(100.0)

        for _ in range(30):
            pane.nudge(-1)
        assert pane.player.volume == pytest.approx(0.0)

    def test_letting_go_stops_the_player_it_started(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        assert pane.player is not None

        pane.shutdown()

        assert pane.player is None
        assert pane.screen_widget.player is None


@pytest.fixture
def reviewing(qapp, settled):
    def _open(fake=None, deck="Japanese"):
        fake = fake or FakeAnki()
        pane = DeckPane(deck, client=fake)
        settled()
        return pane, fake

    return _open


def answered(pane, settled, direction=1):
    pane.step(direction)
    settled()
    pane.step(direction)
    settled()


class TestReviewingADeck:
    def test_the_card_anki_chose_is_on_the_screen(self, reviewing):
        pane, _ = reviewing()

        assert (pane.card.card_id, pane.side) == (100, QUESTION)

    def test_space_shows_the_answer_and_then_answers_good(self, reviewing, settled):
        pane, fake = reviewing()

        pane.toggle()
        settled()
        assert (pane.side, fake.answers) == (ANSWER, [])

        pane.toggle()
        settled()
        assert fake.answers == [(100, anki.GOOD)]
        assert (pane.card.card_id, pane.side) == (101, QUESTION)

    def test_back_answers_again_once_the_answer_shows(self, reviewing, settled):
        pane, fake = reviewing()

        answered(pane, settled, direction=-1)

        assert fake.answers == [(100, anki.AGAIN)]

    def test_a_press_while_anki_moves_on_is_not_a_second_answer(self, reviewing,
                                                                settled):
        pane, fake = reviewing(FakeAnki(lag=3))
        pane.toggle()
        settled()

        pane.toggle()
        pane.toggle()
        pane.step(-1)
        settled()

        assert fake.calls.count("guiAnswerCard") == 1
        assert (pane.card.card_id, pane.side) == (101, QUESTION)

    def test_backspace_takes_the_answer_back(self, reviewing, settled):
        pane, fake = reviewing()
        answered(pane, settled)

        pane.undo()
        settled()

        assert (pane.card.card_id, pane.answered, fake.reps[100]) == (100, 0, 0)

    def test_the_next_card_says_the_answer_was_good(self, reviewing, settled):
        pane, _ = reviewing()

        answered(pane, settled, 1)

        assert pane.verdict == GOOD_SAID

    def test_or_that_it_was_again(self, reviewing, settled):
        pane, _ = reviewing()

        answered(pane, settled, -1)

        assert pane.verdict == AGAIN_SAID

    def test_an_answer_taken_back_says_so(self, reviewing, settled):
        pane, _ = reviewing()
        answered(pane, settled)

        pane.undo()
        settled()

        assert pane.verdict == UNDONE

    def test_the_answer_side_carries_no_verdict(self, reviewing, settled):
        pane, _ = reviewing()
        answered(pane, settled)

        pane.step(1)
        settled()

        assert (pane.side, pane.verdict) == (ANSWER, None)

    def test_nothing_is_taken_back_before_an_answer(self, reviewing, settled):
        pane, fake = reviewing()

        pane.undo()
        settled()

        assert "guiUndo" not in fake.calls

    def test_how_far_is_the_cards_answered_out_of_those_owed(self, reviewing,
                                                            settled):
        pane, _ = reviewing()

        answered(pane, settled)

        assert (pane.position(), pane.duration()) == (1, 3)

    def test_a_deck_with_nothing_due_says_so(self, reviewing):
        pane, _ = reviewing(FakeAnki(cards=()))

        assert "NOTHING DUE IN Japanese" in failure_of(pane)

    def test_a_deck_anki_does_not_have_says_so(self, reviewing):
        pane, _ = reviewing(deck="Nope")

        assert "no deck called \u201cNope\u201d" in failure_of(pane)

    def test_anki_not_running_says_so_on_the_screen(self, qapp, settled,
                                                    offline_requests):
        pane = DeckPane("Japanese", client=anki.AnkiConnect())
        settled()

        assert "not answering" in failure_of(pane)

    def test_what_anki_says_after_it_was_let_go_is_dropped(self, qapp, settled):
        pane = DeckPane("Japanese", client=FakeAnki())

        pane.stop()
        settled()

        assert pane.card is None and pane.busy is False

    def test_a_machine_without_the_web_engine_says_so(self, qapp, monkeypatch):
        monkeypatch.setitem(sys.modules, "PyQt6.QtWebEngineWidgets", None)

        pane = DeckPane("Japanese", client=FakeAnki())

        assert pane.view is None and "COULD NOT REVIEW" in failure_of(pane)


LIBRARY = {"Japanese": ("j1",), "Japanese::Kaishi 1.5k": ("k1", "k2"),
           "Japanese::Kanji": (), "Personal Math": ("p1",)}


@pytest.fixture
def choosing(qapp, settled):
    def _open(decks=LIBRARY):
        fake = FakeAnki(decks=decks)
        pane = DeckPane(ANY_DECK, client=fake)
        settled()
        return pane, fake

    return _open


def rows(pane):
    listed, walk = [], QTreeWidgetItemIterator(pane.chooser)
    while walk.value() is not None:
        row, parent, depth = walk.value(), walk.value().parent(), 0
        while parent is not None:
            parent, depth = parent.parent(), depth + 1
        listed.append(["    " * depth + row.text(0)] + [row.text(column) for column in (1, 2, 3)])
        walk += 1
    return listed


class TestChoosingADeck:
    def test_every_deck_is_listed_under_its_parent_with_what_it_owes(self, choosing):
        pane, _ = choosing()

        assert rows(pane) == [["Japanese", "0", "0", "1"],
                              ["    Kaishi 1.5k", "0", "0", "2"],
                              ["    Kanji", "0", "0", "0"],
                              ["Personal Math", "0", "0", "1"]]

    def test_the_first_deck_that_owes_cards_is_marked(self, choosing):
        pane, _ = choosing({"Japanese": (), "Japanese::Kanji": ("k1",)})

        assert (pane.choosing, pane.marked) == (True, 1)

    def test_up_and_down_mark_the_deck_beside_within_the_list(self, choosing):
        pane, _ = choosing()

        pane.nudge(-1)
        assert pane.marked == 1
        pane.nudge(1)
        pane.nudge(1)
        assert pane.marked == 0

    def test_left_and_right_skip_to_a_deck_that_owes_cards(self, choosing):
        pane, _ = choosing()

        pane.step(1)
        pane.step(1)
        assert pane.marked == 3
        pane.step(1)
        assert pane.marked == 0
        pane.step(-1)
        assert pane.marked == 3

    def test_space_reviews_the_marked_deck(self, choosing, settled):
        pane, fake = choosing()
        pane.nudge(-1)

        pane.toggle()
        settled()

        assert (fake.reviewing, pane.card.card_id) == ("Japanese::Kaishi 1.5k", 101)
        assert (pane.choosing, pane.title()) == (False, "Japanese::Kaishi 1.5k")

    def test_back_reads_the_list_again_and_marks_the_next_deck_owing(self, choosing,
                                                                    settled):
        pane, _ = choosing()
        pane.toggle()
        settled()
        answered(pane, settled)

        assert pane.back() is True
        settled()

        assert (pane.choosing, pane.marked, rows(pane)[0][3]) == (True, 1, "0")

    def test_a_deck_left_while_it_owes_cards_stays_marked(self, choosing, settled):
        pane, _ = choosing()
        pane.nudge(-1)
        pane.toggle()
        settled()

        pane.back()
        settled()

        assert pane.marked == 1

    def test_space_once_nothing_is_left_goes_back_to_the_list(self, choosing, settled):
        pane, _ = choosing()
        pane.toggle()
        settled()
        answered(pane, settled)
        assert "NOTHING DUE IN Japanese" in failure_of(pane)

        pane.toggle()
        settled()

        assert pane.choosing

    def test_each_change_of_the_keys_is_announced(self, choosing, settled):
        pane, _ = choosing()
        heard = []
        pane.changed.connect(lambda: heard.append(pane.choosing))

        pane.toggle()
        settled()
        pane.back()
        settled()

        assert heard == [False, True]

    def test_a_deck_named_outright_has_no_list_to_go_back_to(self, reviewing):
        pane, _ = reviewing()

        assert (pane.back(), pane.title()) == (False, "")


@pytest.fixture
def library(qapp, tmp_path):
    root = tmp_path / "Media"
    for name in ("Books/a.epub", "Books/b.epub", "Books/Series/s1.epub",
                 "Videos/e1.mkv", "loose.pdf"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"")
    positions = str(tmp_path / "rest-positions.json")

    def _open(path):
        return LibraryPane(str(root / path), root=str(root), positions=positions)

    _open.root, _open.positions = root, positions
    return _open


def listed(pane):
    return [pane.chooser.topLevelItem(row).text(0)
            for row in range(pane.chooser.topLevelItemCount())]


class TestChoosingAFile:
    def test_it_lists_the_folder_of_the_file_it_marks(self, library):
        pane = library("Books/b.epub")

        assert listed(pane) == ["Series/", "a.epub", "b.epub"]
        assert (pane.marked, pane.title()) == (2, "Media/Books")

    def test_up_and_down_mark_the_entry_beside_and_a_page_ten_at_once(self, library):
        pane = library("Books/b.epub")

        pane.nudge(1)
        assert pane.marked == 1
        pane.turn(-1)
        assert pane.marked == 0
        pane.turn(1)
        assert pane.marked == 2

    def test_space_lists_a_marked_folder_and_hands_over_a_marked_file(self, library):
        pane = library("Books/Series")
        chosen = []
        pane.chosen.connect(chosen.append)

        pane.undo()
        pane.toggle()
        pane.step(1)

        assert chosen == [str(library.root / "Books" / "Series" / "s1.epub")]

    def test_left_goes_up_a_folder_no_higher_than_the_media_folder(self, library):
        pane = library("Books/a.epub")

        pane.step(-1)
        pane.undo()

        assert listed(pane) == ["Books/", "Videos/", "loose.pdf"]
        assert (pane.marked, pane.title()) == (0, "Media")

    def test_each_file_says_how_far_into_it_the_member_is(self, library):
        rest_positions.remember(str(library.root / "Books" / "a.epub"), 37,
                                library.positions, 100)

        pane = library("Books/a.epub")

        assert [pane.chooser.topLevelItem(row).text(1) for row in range(3)] == [
            "", "37%", ""]

    def test_a_folder_with_nothing_to_show_says_so(self, qapp, tmp_path):
        pane = LibraryPane(str(tmp_path), root=str(tmp_path),
                           positions=str(tmp_path / "rest-positions.json"))

        assert "NOTHING TO SHOW IN" in failure_of(pane)


class TestACardPage:
    def test_the_sound_is_left_to_anki(self):
        assert "[anki:play" not in card_page("x[anki:play:q:0]", 0)

    def test_the_body_carries_the_classes_anki_gives_it_by_day(self):
        page = card_page("x", 1)

        assert 'class="card card2 isLin"' in page and "nightMode" not in page
        assert PALETTE['base3'] in page

    def test_the_answer_is_scrolled_to_and_the_question_is_not(self):
        assert "scrollIntoView" in card_page("x", 0, answer=True)
        assert "scrollIntoView" not in card_page("x", 0)

    @pytest.mark.parametrize("verdict, word, colour", [
        (GOOD_SAID, "GOOD", 'green'), (AGAIN_SAID, "AGAIN", 'red'),
        (UNDONE, "TAKEN BACK", 'yellow')])
    def test_a_verdict_is_worded_and_coloured(self, verdict, word, colour):
        page = card_page("x", 0, verdict=verdict)

        assert f">{word}</div>" in page and PALETTE[colour] in page

    def test_a_card_with_no_verdict_carries_none(self):
        assert "traker-verdict" not in card_page("x", 0)


class TestWhichPaneIsBuilt:
    def test_a_deck_is_reviewed(self, qapp, monkeypatch):
        monkeypatch.setattr(anki.AnkiConnect, "call", FakeAnki().call)

        pane = build_pane(BreakActivity("Japanese", "Japanese", DECK))

        assert isinstance(pane, DeckPane) and pane.deck == "Japanese"

    def test_a_document_is_read(self, paper):
        pane = build_pane(BreakActivity("Reading", paper, DOCUMENT))

        assert isinstance(pane, DocumentPane)

    def test_anything_else_is_played(self, qapp, tmp_path):
        pane = build_pane(BreakActivity("Watching", str(tmp_path / "a.mkv"), VIDEO))

        assert isinstance(pane, VideoPane)

    def test_a_shelf_is_listed(self, library):
        pane = build_pane(BreakActivity("Books", str(library.root / "Books"), SHELF))

        assert isinstance(pane, LibraryPane)

    def test_a_book_is_read(self, qapp, epub, settled):
        pane = build_pane(BreakActivity("Novel", epub("<p>a</p>"), BOOK))
        settled()

        assert isinstance(pane, BookPane)
        pane.stop()


class Recorder(QWidget):
    def __init__(self, activity=None, start_at=0, parent=None):
        super().__init__(parent)
        self.at = 42_000
        self.of = 90_000
        self.opened = [] if activity is None else [(activity.path, start_at)]

    def open(self, path, start_at=0):
        self.opened.append((path, start_at))
        self.at = 42_000

    def position(self):
        return self.at

    def duration(self):
        return self.of

    def stop(self):
        self.at = self.of = 0

    def toggle(self):
        pass


class TestTheSurfaceAroundThem:
    @pytest.fixture
    def activity(self, tmp_path):
        return BreakActivity("Watching", str(tmp_path / "talk.mkv"), VIDEO)

    @pytest.fixture
    def paper_activity(self, paper):
        return BreakActivity("Reading", paper, DOCUMENT)

    def test_nothing_is_showing_until_it_is_asked_for(self, qapp):
        surface = MediaSurface(None, pane_factory=Recorder)

        assert surface.activity is None
        assert surface.pane is None
        assert surface.panes == {}

    def test_it_reads_the_place_before_it_stops_the_pane(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        assert surface.stop() == Place(42_000, 90_000)

    def test_stopping_puts_the_empty_page_back(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        pane = surface.open(activity)

        surface.stop()

        assert surface.activity is None
        assert surface.pane is None
        assert surface.stack.currentWidget() is not pane

    def test_closing_it_and_opening_it_again_is_the_same_pane(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        pane = surface.open(activity)
        surface.stop()

        again = surface.open(activity, start_at=90_000)

        assert again is pane
        assert pane.opened == [(activity.path, 0), (activity.path, 90_000)]
        assert surface.stack.currentWidget() is pane

    def test_a_video_and_a_document_get_a_pane_each(self, qapp, activity,
                                                    paper_activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        watching = surface.open(activity)
        reading = surface.open(paper_activity)

        assert watching is not reading
        assert set(surface.panes) == {VIDEO, DOCUMENT}
        assert surface.stack.currentWidget() is reading

    def test_the_screen_shows_the_file_and_nothing_else(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        assert surface.strip is None

    def test_a_break_with_no_other_screen_keeps_one_line(self, qapp, activity,
                                                         timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        assert "REST 02:05" in surface.strip.text()
        assert "HOLD ESC" in surface.strip.text()

    def test_that_line_says_when_the_break_has_run_out(self, qapp, activity,
                                                       timer_double):
        timer_double.waiting_for_work_start = True

        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        assert "BREAK OVER +1:23" in surface.strip.text()
        assert "PRESS ESC TO START FOCUS" in surface.strip.text()

    def test_and_how_much_of_the_exit_has_been_paid(self, qapp, activity,
                                                    timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        surface.show_hold(0.7, True)

        assert "LEAVING IN 3s" in surface.strip.text()

    def test_letting_go_puts_the_exit_back(self, qapp, activity, timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)
        surface.show_hold(0.7, True)

        surface.show_hold(0.0, False)

        assert "HOLD ESC" in surface.strip.text()

    def test_the_pane_it_was_given_is_the_pane_it_holds(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        surface.open(activity)

        assert isinstance(surface.pane, Recorder)
        assert surface.activity is activity

    def test_the_screen_showing_the_file_names_no_keys_on_it(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        surface.open(activity, key_hints=[("SPACE", "pause")])

        assert surface.keys.isVisibleTo(surface) is False

    def test_a_break_with_no_other_screen_keeps_the_card(self, qapp, activity,
                                                         timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        surface.open(activity, key_hints=[("SPACE", "pause")])
        assert surface.keys.isVisibleTo(surface) is True

        surface.stop()
        assert surface.keys.isVisibleTo(surface) is False

    def test_a_book_is_set_on_a_light_surface_and_nothing_else_is(self, qapp, activity,
                                                                  timer_double):
        wall = QWidget()
        wall.setObjectName("wall")
        wall.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        wall.setStyleSheet(f"#wall {{ background-color: {PALETTE['base03']}; }}")
        wall.resize(800, 600)
        surface = MediaSurface(timer_double, pane_factory=Recorder, only_screen=True,
                               parent=wall)
        surface.resize(800, 600)

        def painted():
            image = wall.grab().toImage()
            return image.pixelColor(5, 5).name(), image.pixelColor(5, 597).name()

        surface.open(BreakActivity("Novel", "/x/novel.epub", BOOK))
        reading = painted()
        surface.open(BreakActivity("Anki", ANY_DECK, DECK))
        reviewing = painted()
        surface.open(activity)

        assert reading == reviewing == (PALETTE['base3'], PALETTE['base2'])
        assert painted() == (PALETTE['base03'], PALETTE['base02'])


class TestWhereInTheFileTheMemberIs:
    @pytest.fixture
    def activity(self, tmp_path):
        return BreakActivity("Watching", str(tmp_path / "talk.mkv"), VIDEO)

    @pytest.fixture
    def alone(self, qapp, timer_double):
        built = []

        def _alone(width=1920, height=1080):
            surface = MediaSurface(timer_double, pane_factory=Recorder,
                                   only_screen=True)
            surface.resize(width, height)
            surface.show()
            qapp.processEvents()
            built.append(surface)
            return surface

        yield _alone
        for surface in built:
            surface.close()
            surface.deleteLater()
        qapp.processEvents()

    def test_the_surface_answers_where_the_pane_has_got_to(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        place, unit = surface.place()

        assert media.how_far(place, unit) == "0:42 / 1:30"
        assert media.fraction(place, unit) == pytest.approx(42 / 90)

    def test_a_document_answers_its_page_instead(self, qapp, paper):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(BreakActivity("Reading", paper, DOCUMENT))
        surface.pane.at, surface.pane.of = 41, 310

        place, unit = surface.place()

        assert media.how_far(place, unit) == "42 / 310"

    def test_nothing_showing_is_no_place_at_all(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        assert surface.place() is None

        surface.open(activity)
        surface.stop()

        assert surface.place() is None

    def test_the_player_is_asked_once_for_it(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)
        asked = []
        surface.pane.position = lambda: asked.append(1) or 42_000

        surface.place()

        assert len(asked) == 1

    def test_a_break_with_another_screen_draws_none_of_it_here(self, qapp,
                                                               activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        assert surface.progress is None

    def test_a_break_with_no_other_screen_keeps_the_row(self, qapp, alone,
                                                        activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        assert surface.progress is not None
        assert surface.progress.isVisibleTo(surface) is True

    def test_it_says_where_in_the_file_the_member_is(self, qapp, alone, activity):
        surface = alone()
        surface.open(activity)

        surface.show_progress()

        assert surface.progress.says == "0:42 / 1:30"
        assert surface.progress.fraction == pytest.approx(42 / 90)

    def test_it_takes_the_view_s_own_read_when_it_is_given_one(self, qapp,
                                                               alone, activity):
        surface = alone()
        surface.open(activity)

        surface.show_progress((media.Place(63_000, 90_000), media.TIME))

        assert surface.progress.says == "1:03 / 1:30"

    def test_it_is_a_row_under_the_picture_not_a_band_on_it(self, qapp, alone,
                                                            activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        assert surface.layout().indexOf(surface.progress) != -1
        assert not surface.progress.geometry().intersects(surface.stack.geometry())
        assert surface.progress.height() == media_progress.HEIGHT

    def test_the_row_goes_when_the_file_does(self, qapp, alone, activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        surface.stop()
        qapp.processEvents()

        assert surface.progress.isVisibleTo(surface) is False

    def test_a_length_the_player_has_not_read_yet_draws_nothing(self, qapp,
                                                                alone, activity):
        surface = alone()
        surface.open(activity)
        surface.pane.of = 0

        surface.show_progress()

        assert surface.progress.says == media.UNKNOWN
        assert surface.progress.fraction == 0.0

    def test_the_member_can_actually_see_it(self, qapp, alone, activity):
        surface = alone(800, 600)
        surface.open(activity)
        surface.pane.at, surface.pane.of = 45_000, 90_000
        surface.show_progress()
        qapp.processEvents()

        shot = surface.grab().toImage()
        band = surface.progress.geometry()
        along = band.bottom()
        assert shot.pixelColor(200, along).name() == PALETTE['cyan']
        assert shot.pixelColor(600, along).name() == PALETTE['base01']
        ink = {shot.pixelColor(x, y).name()
               for y in range(band.top(), band.bottom())
               for x in range(band.width() - 140, band.width())}
        assert PALETTE['base2'] in ink
        assert surface.progress.says == "0:45 / 1:30"

    def test_a_frame_that_says_the_same_thing_is_not_repainted(self, qapp,
                                                               alone, activity):
        surface = alone()
        surface.open(activity)
        asked = []
        surface.progress.update = lambda: asked.append(1)

        for _ in range(50):
            surface.show_progress()
        assert asked == []

        surface.pane.at = 63_000
        surface.show_progress()
        assert len(asked) == 1
