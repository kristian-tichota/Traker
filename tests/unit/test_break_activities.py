import os

import pytest

from src.desktop import activities as break_activities
from src.desktop.activities import BOOK, DECK, DOCUMENT, PAGE, SHELF, VIDEO, BreakActivity
from src.domain.media import Place

pytestmark = pytest.mark.exact


class TestWhichPaneShowsIt:
    @pytest.mark.parametrize("path", ["/x/paper.pdf", "/x/PAPER.PDF", "~/a b.Pdf"])
    def test_a_pdf_is_read(self, path):
        assert break_activities.kind_of(path) == DOCUMENT

    @pytest.mark.parametrize("path", ["/x/本.epub", "/x/NOVEL.EPUB"])
    def test_an_epub_is_read_as_a_book(self, path):
        assert break_activities.kind_of(path) == BOOK

    @pytest.mark.parametrize("path", ["/x/talk.mkv", "/x/a.mp4", "/x/no-extension",
                                      "/x/lecture.webm"])
    def test_anything_else_is_played(self, path):
        assert break_activities.kind_of(path) == VIDEO


class TestTheStandingEntries:
    def test_a_name_and_a_path_are_the_whole_of_one(self):
        read = break_activities.read([
            {"name": "Reading", "path": "/home/x/Documents/reading.pdf"}])

        assert read == [break_activities.BreakActivity(
            "Reading", "/home/x/Documents/reading.pdf", DOCUMENT)]

    def test_a_deck_is_named_rather_than_found(self):
        read = break_activities.read([{"name": "Japanese", "deck": "Japanese"}])

        assert read == [break_activities.BreakActivity("Japanese", "Japanese", DECK)]

    def test_a_url_is_opened_as_a_page(self):
        read = break_activities.read([{"name": "Tutor", "url": "http://127.0.0.1:9743/"}])

        assert read == [BreakActivity("Tutor", "http://127.0.0.1:9743/", PAGE)]

    @pytest.mark.parametrize("entry", [
        {"name": "R", "path": "/x/a.pdf", "deck": "Japanese"},
        {"name": "R", "path": "/x/a.pdf", "url": "http://x/"},
        {"name": "R", "deck": "Japanese", "url": "http://x/"},
    ])
    def test_one_naming_more_than_one_thing_to_show_is_skipped(self, entry):
        assert break_activities.read([entry]) == []

    def test_the_order_is_the_members(self):
        read = break_activities.read([{"name": "B", "path": "/x/b.mkv"},
                                      {"name": "A", "path": "/x/a.mkv"}])

        assert [entry.name for entry in read] == ["B", "A"]

    def test_a_tilde_is_expanded(self):
        entry = break_activities.read([{"name": "R", "path": "~/reading.pdf"}])[0]

        assert entry.path.startswith("/") and "~" not in entry.path

    @pytest.mark.parametrize("entry", [
        {"path": "/x/a.mkv"},
        {"name": "R"},
        {"name": "R", "path": "   "},
        {"name": "R", "deck": "   "},
        ["not", "a", "table"],
    ])
    def test_an_entry_written_wrong_is_skipped(self, entry):
        assert break_activities.read([entry]) == []

    def test_the_entries_around_it_are_still_offered(self):
        read = break_activities.read([{"name": "A", "path": "/x/a.mkv"},
                                      {"name": "no path"},
                                      {"name": "C", "path": "/x/c.pdf"}])

        assert [entry.name for entry in read] == ["A", "C"]

    def test_one_written_for_the_launcher_says_so(self, caplog):
        with caplog.at_level("WARNING"):
            read = break_activities.read([{"name": "Reading",
                                           "command": ["okular", "~/reading.pdf"],
                                           "app_id": "okular"}])

        assert read == []
        assert "path" in caplog.text and "Reading" in caplog.text

    def test_nothing_written_down_is_no_offers(self):
        assert break_activities.read(None) == []
        assert break_activities.read(()) == []


class TestTheQueue:
    def test_each_path_is_an_offer_named_by_its_file(self):
        queued = break_activities.queued(["/x/talk.mkv", "/x/paper.pdf"])

        assert [(q.name, q.kind) for q in queued] == [
            ("talk.mkv", VIDEO), ("paper.pdf", DOCUMENT)]

    def test_a_video_and_a_document_together_need_no_saying(self):
        assert [q.kind for q in break_activities.queued(
            ["/x/a.mkv", "/x/b.pdf", "/x/c.mp4"])] == [VIDEO, DOCUMENT, VIDEO]

    def test_the_order_is_the_queues(self):
        queued = break_activities.queued(["/x/first.mkv", "/x/second.mkv"])

        assert [q.name for q in queued] == ["first.mkv", "second.mkv"]

    def test_an_empty_line_is_not_an_offer(self):
        assert break_activities.queued(["", "   "]) == []


class TestTheKeys:
    def test_the_first_is_on_enter(self):
        assert break_activities.offer_key(0) == "ENTER"

    def test_the_rest_are_on_their_own_digits(self):
        assert [break_activities.offer_key(i) for i in (1, 2, 8)] == ["2", "3", "9"]

    def test_past_the_ninth_there_is_no_key(self):
        assert break_activities.offer_key(9) == "—"


@pytest.fixture
def library(tmp_path):
    def shelve(*names):
        for name in names:
            path = tmp_path / "Media" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
        return str(tmp_path / "Media")

    return shelve


class TestTheLibrary:
    def test_each_subfolder_is_a_shelf_in_name_order(self, library):
        folder = library("Videos/a.mkv", "Books/b.epub", "PDF/c.pdf")

        assert [(shelf.name, shelf.kind) for shelf in break_activities.shelves(folder)] == [
            ("Books", SHELF), ("PDF", SHELF), ("Videos", SHELF)]

    def test_a_shelf_holds_what_a_break_can_show_in_natural_order(self, library):
        folder = library("Videos/s1/e10.mkv", "Videos/s1/e2.mkv", "Videos/s1/e2.srt",
                         "Videos/.e3.mkv", "Videos/cover.jpg")

        shelf, = break_activities.shelves(folder)

        assert [os.path.relpath(path, folder) for path in shelf.items] == [
            "Videos/s1/e2.mkv", "Videos/s1/e10.mkv"]

    def test_a_subfolder_with_nothing_to_show_is_no_shelf(self, library):
        folder = library("Notes/readme.txt", "Books/a.epub")

        assert [shelf.name for shelf in break_activities.shelves(folder)] == ["Books"]

    def test_files_beside_the_subfolders_are_a_shelf_of_their_own(self, library):
        folder = library("loose.mkv", "Books/a.epub")

        assert [shelf.name for shelf in break_activities.shelves(folder)] == [
            "Media", "Books"]

    def test_a_folder_that_is_not_there_offers_nothing(self, tmp_path):
        assert break_activities.shelves(str(tmp_path / "absent")) == []

    def test_a_folder_lists_the_folders_holding_something_then_its_files(self, library):
        folder = library("Books/b10.epub", "Books/b2.epub", "Books/Series/s1.epub",
                         "Books/Notes/readme.txt", "Books/.old/o.epub", "Books/cover.jpg")

        listed = break_activities.contents(os.path.join(folder, "Books"))

        assert [(entry.name, entry.folder) for entry in listed] == [
            ("Series", True), ("b2.epub", False), ("b10.epub", False)]

    def test_the_folder_is_the_one_the_profile_names(self, write_profile):
        profile = write_profile('[strict_break.library]\npath = "~/Shelf"\n')

        assert break_activities.library_for(profile) == os.path.expanduser("~/Shelf")

    def test_or_else_the_media_folder_of_the_checkout(self, write_profile):
        profile = write_profile('[strict_break.library]\npath = ""\n')

        assert break_activities.library_for(profile) == break_activities.DEFAULT_LIBRARY


class TestWhatAShelfOpens:
    SHELF = BreakActivity("Videos", "/m/Videos", SHELF,
                          ("/m/Videos/e1.mkv", "/m/Videos/e2.mkv", "/m/Videos/e3.mkv"))
    ENDED, PART_WAY = Place(1_440_000, 1_440_000), Place(60_000, 1_440_000)

    def opened(self, places):
        return break_activities.resolve(self.SHELF, places).path

    def test_its_first_file_until_one_of_them_is_opened(self):
        assert self.opened({"/elsewhere.pdf": Place(3, 10)}) == "/m/Videos/e1.mkv"

    def test_the_file_opened_last_while_it_is_part_way(self):
        assert self.opened({"/m/Videos/e2.mkv": self.PART_WAY,
                            "/elsewhere.pdf": Place(3, 10)}) == "/m/Videos/e2.mkv"

    def test_the_next_by_name_once_that_one_reached_its_end(self):
        assert self.opened({"/m/Videos/e2.mkv": self.ENDED}) == "/m/Videos/e3.mkv"

    def test_past_the_last_one_it_goes_back_to_one_not_yet_ended(self):
        assert self.opened({"/m/Videos/e1.mkv": self.ENDED,
                            "/m/Videos/e3.mkv": self.ENDED}) == "/m/Videos/e2.mkv"

    def test_the_file_is_offered_as_what_it_is(self):
        shelf = BreakActivity("Books", "/m/Books", SHELF, ("/m/Books/a.epub",))

        assert break_activities.resolve(shelf, {}) == BreakActivity(
            "a.epub", "/m/Books/a.epub", BOOK)

    def test_anything_else_opens_itself(self):
        entry = BreakActivity("Reading", "/x/reading.pdf", DOCUMENT)

        assert break_activities.resolve(entry, {}) is entry
