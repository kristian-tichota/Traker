import pytest

from src.desktop import sessions
from src.desktop.sessions import Project, Session

pytestmark = pytest.mark.exact

LISTING = ("project\t/p/a\tAlpha\n"
           "session\t/p/a\tclaude-box\t1\t100\tFix\tthe  parser\n"
           "session\t/p/a\tclaude-box-7\t0\t300\t\n"
           "project\t/p/b\t\n"
           "session\t/p/gone\tx\t0\t1\ty\n"
           "noise\n")


class TestTheListing:
    def test_each_project_holds_its_sessions_the_latest_first(self):
        assert sessions.parse(LISTING)[0] == Project("/p/a", "Alpha", (
            Session("claude-box-7", 0, 300, ""), Session("claude-box", 1, 100, "Fix the parser")))

    def test_a_project_without_a_label_is_named_by_its_path(self):
        assert sessions.parse(LISTING)[1] == Project("/p/b", "/p/b")

    def test_a_session_of_no_project_listed_is_dropped(self):
        assert [project.path for project in sessions.parse(LISTING)] == ["/p/a", "/p/b"]


class TestOpening:
    def test_a_named_session_is_attached(self):
        assert sessions.opening("desk --x", "/p/a b", "s") == [
            "desk", "--x", "--open", "/p/a b", "s"]

    def test_no_session_asks_for_a_new_chat(self):
        assert sessions.opening("desk", "/p/a") == ["desk", "--open", "/p/a"]


class TestTheNote:
    @pytest.mark.parametrize("secs, said", [(59, "NOW"), (60, "1 MIN AGO"),
                                            (7_300, "2 H AGO"), (200_000, "2 D AGO")])
    def test_the_largest_whole_unit_since(self, secs, said):
        assert sessions.ago(secs) == said

    def test_a_shown_session_says_so(self):
        assert sessions.described(Session("s", 2, 1_000, ""), 1_120) == "ATTACHED · 2 MIN AGO"
