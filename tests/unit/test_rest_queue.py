import pytest

from src.desktop import rest_queue

pytestmark = pytest.mark.accessibility


@pytest.fixture
def queue_path(tmp_path):
    return str(tmp_path / "state" / "rest-queue.m3u")


class TestReading:
    def test_a_file_that_is_not_there_is_an_empty_queue(self, queue_path):
        import os

        assert rest_queue.read(queue_path) == []
        assert not os.path.exists(queue_path)

    def test_comments_and_blank_lines_are_not_entries(self, tmp_path):
        path = tmp_path / "q.m3u"
        path.write_text("# a note\n\n/tmp/a.mp4\n   \n  # indented\n/tmp/b.mp4\n")

        assert rest_queue.read(str(path)) == ["/tmp/a.mp4", "/tmp/b.mp4"]

    def test_an_unreadable_file_is_reported_rather_than_raised(self, tmp_path, caplog):
        with caplog.at_level("WARNING"):
            assert rest_queue.read(str(tmp_path)) == []

        assert "queue" in caplog.text


class TestWriting:
    def test_appending_keeps_the_order_things_were_added_in(self, queue_path):
        rest_queue.append("/tmp/a.mp4", queue_path)

        assert rest_queue.append("/tmp/b.mp4", queue_path) == [
            "/tmp/a.mp4", "/tmp/b.mp4"]

    def test_a_leading_tilde_is_expanded_because_there_is_no_shell(self, queue_path):
        import os

        rest_queue.append("~/Videos/a.mp4", queue_path)

        assert rest_queue.read(queue_path) == [os.path.expanduser("~/Videos/a.mp4")]

    def test_queueing_the_same_thing_twice_is_not_two_entries(self, queue_path):
        rest_queue.append("/tmp/a.mp4", queue_path)

        assert rest_queue.append("/tmp/a.mp4", queue_path) == ["/tmp/a.mp4"]

    def test_queueing_nothing_is_refused(self, queue_path):
        with pytest.raises(ValueError):
            rest_queue.append("   ", queue_path)

    def test_the_file_says_what_it_is_for(self, queue_path):
        rest_queue.append("/tmp/a.mp4", queue_path)
        rest_queue.append("/tmp/b.mp4", queue_path)

        assert open(queue_path).read().startswith("# Traker:")

    def test_removing_counts_from_one_the_way_the_surface_shows_it(self, queue_path):
        rest_queue.append("/tmp/a.mp4", queue_path)
        rest_queue.append("/tmp/b.mp4", queue_path)

        assert rest_queue.remove(1, queue_path) == ["/tmp/b.mp4"]

    @pytest.mark.parametrize("position", [0, 3, -1])
    def test_removing_something_that_is_not_there_is_refused(self, queue_path, position):
        rest_queue.append("/tmp/a.mp4", queue_path)

        with pytest.raises(ValueError):
            rest_queue.remove(position, queue_path)

    def test_clearing_empties_it_and_keeps_the_file(self, queue_path):
        rest_queue.append("/tmp/a.mp4", queue_path)

        assert rest_queue.clear(queue_path) == []
        assert open(queue_path).read().startswith("# Traker:")

    def test_a_path_that_cannot_be_written_is_refused_with_a_reason(self, tmp_path):
        blocked = tmp_path / "afile"
        blocked.write_text("not a directory")

        with pytest.raises(ValueError):
            rest_queue.append("/tmp/a.mp4", str(blocked / "q.m3u"))


class TestHowItReads:
    def test_an_entry_is_named_by_its_own_file_name(self):
        assert rest_queue.label("/home/x/Videos/Talk 3.mkv") == "Talk 3.mkv"

    def test_a_folder_is_named_by_its_last_part(self):
        assert rest_queue.label("~/Videos/rest/") == "rest"

    def test_an_empty_queue_says_so(self):
        assert rest_queue.describe([]) == "empty."

    def test_a_queue_reads_as_its_keys_and_names(self):
        assert rest_queue.describe(["/tmp/a.mp4", "/tmp/b.mp4"]) == "1 a.mp4 · 2 b.mp4"


class TestWhereItLives:
    def test_the_suite_never_reaches_the_members_own_queue(self):
        assert "traker-tests-" in rest_queue.DEFAULT_PATH

    def test_the_profile_may_say(self, write_profile):
        profile = write_profile('[strict_break.queue]\npath = "/tmp/mine.m3u"\n')

        assert rest_queue.path_for(profile) == "/tmp/mine.m3u"

    def test_a_leading_tilde_in_that_path_is_expanded_too(self, write_profile):
        import os

        profile = write_profile('[strict_break.queue]\npath = "~/q.m3u"\n')

        assert rest_queue.path_for(profile) == os.path.expanduser("~/q.m3u")

    def test_a_profile_that_says_nothing_gets_the_default(self, user_profile):
        assert rest_queue.path_for(user_profile) == rest_queue.DEFAULT_PATH
