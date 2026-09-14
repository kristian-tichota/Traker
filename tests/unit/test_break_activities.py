import pytest

from src.desktop import activities as break_activities
from src.desktop.activities import DOCUMENT, VIDEO

pytestmark = pytest.mark.exact


class TestWhichPaneShowsIt:
    @pytest.mark.parametrize("path", ["/x/paper.pdf", "/x/PAPER.PDF", "~/a b.Pdf"])
    def test_a_pdf_is_read(self, path):
        assert break_activities.kind_of(path) == DOCUMENT

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
