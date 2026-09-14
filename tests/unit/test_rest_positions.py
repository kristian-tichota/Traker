import json

import pytest

from src.desktop import rest_positions
from src.domain.media import Place

pytestmark = pytest.mark.exact


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "state" / "rest-positions.json")


class TestRememberingOne:
    def test_a_video_comes_back_where_it_stopped(self, store):
        rest_positions.remember("/x/talk.mkv", 754_000, store)

        assert rest_positions.position_for("/x/talk.mkv", store) == 754_000

    def test_so_does_a_page(self, store):
        rest_positions.remember("/x/paper.pdf", 12, store)

        assert rest_positions.position_for("/x/paper.pdf", store) == 12

    def test_a_file_nothing_is_stored_for_starts_at_the_beginning(self, store):
        assert rest_positions.position_for("/x/never-seen.mkv", store) == 0

    def test_how_long_the_file_is_is_kept_beside_it(self, store):
        rest_positions.remember("/x/talk.mkv", 754_000, store, 2_400_000)

        assert rest_positions.place_for("/x/talk.mkv", store) == \
            Place(754_000, 2_400_000)

    def test_a_length_the_player_did_not_report_is_kept_as_unknown(self, store):
        rest_positions.remember("/x/talk.mkv", 754_000, store)

        assert rest_positions.place_for("/x/talk.mkv", store) == Place(754_000, 0)

    def test_nothing_stored_is_the_beginning_of_something_unmeasured(self, store):
        assert rest_positions.place_for("/x/never-seen.mkv", store) == Place()

    def test_the_start_is_not_stored_as_a_position(self, store):
        rest_positions.remember("/x/a.mkv", 0, store)

        assert rest_positions.read(store) == {}

    def test_stopping_at_the_start_again_forgets_where_it_was(self, store):
        rest_positions.remember("/x/a.mkv", 60_000, store)

        rest_positions.remember("/x/a.mkv", 0, store)

        assert rest_positions.position_for("/x/a.mkv", store) == 0

    def test_the_newest_position_is_the_one_kept(self, store):
        rest_positions.remember("/x/a.mkv", 10_000, store)

        rest_positions.remember("/x/a.mkv", 20_000, store)

        assert rest_positions.position_for("/x/a.mkv", store) == 20_000

    def test_one_file_is_not_another_files_place(self, store):
        rest_positions.remember("/x/a.mkv", 10_000, store)

        assert rest_positions.position_for("/x/b.mkv", store) == 0


class TestTheFileItself:
    def test_it_is_not_written_until_there_is_something_to_write(self, store):
        import os

        assert rest_positions.read(store) == {}
        assert not os.path.exists(store)

    def test_a_file_that_is_not_there_is_no_positions(self, tmp_path):
        assert rest_positions.read(str(tmp_path / "nothing.json")) == {}

    def test_a_file_that_will_not_parse_is_no_positions_either(self, store, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        assert rest_positions.read(str(broken)) == {}

    def test_the_oldest_are_dropped_rather_than_kept_for_ever(self, store):
        for index in range(rest_positions.KEEP + 20):
            rest_positions.remember(f"/x/{index}.mkv", 1000 + index, store)

        stored = rest_positions.read(store)
        assert len(stored) == rest_positions.KEEP
        assert "/x/0.mkv" not in stored
        assert f"/x/{rest_positions.KEEP + 19}.mkv" in stored

    def test_an_unwritable_store_is_not_the_reason_a_break_does_not_end(self, tmp_path):
        rest_positions.remember("/x/a.mkv", 1000, str(tmp_path / "a" / "b" / "x.json"))

    def test_something_else_writing_nonsense_into_it_is_ignored(self, store, tmp_path):
        odd = tmp_path / "odd.json"
        odd.write_text(json.dumps({"/x/a.mkv": "half way",
                                   "/x/b.mkv": {"at": "half way"},
                                   "/x/c.mkv": {"of": 200}}), encoding="utf-8")

        assert rest_positions.read(str(odd)) == {}


class TestTheShapeTheMemberAlreadyHas:
    def test_a_bare_number_is_still_a_position(self, tmp_path):
        older = tmp_path / "older.json"
        older.write_text(json.dumps({"/x/talk.mkv": 754_000}), encoding="utf-8")

        assert rest_positions.position_for("/x/talk.mkv", str(older)) == 754_000
        assert rest_positions.place_for("/x/talk.mkv", str(older)) == \
            Place(754_000, 0)

    def test_the_next_stop_writes_the_length_in(self, tmp_path):
        older = tmp_path / "older.json"
        older.write_text(json.dumps({"/x/talk.mkv": 754_000}), encoding="utf-8")

        rest_positions.remember("/x/talk.mkv", 800_000, str(older), 2_400_000)

        assert json.loads(older.read_text(encoding="utf-8")) == \
            {"/x/talk.mkv": {"at": 800_000, "of": 2_400_000}}

    def test_and_the_entries_it_did_not_touch_keep_theirs(self, tmp_path):
        older = tmp_path / "older.json"
        older.write_text(json.dumps({"/x/a.mkv": 10_000, "/x/b.mkv": 20_000}),
                         encoding="utf-8")

        rest_positions.remember("/x/a.mkv", 30_000, str(older), 90_000)

        assert rest_positions.read(str(older)) == {
            "/x/b.mkv": Place(20_000, 0), "/x/a.mkv": Place(30_000, 90_000)}


class TestWhereItLives:
    def test_it_sits_beside_the_queue_it_belongs_to(self):
        assert rest_positions.beside("/home/x/.config/traker/rest-queue.m3u") == \
            "/home/x/.config/traker/rest-positions.json"

    def test_a_queue_that_says_nothing_leaves_it_in_the_default_place(self):
        assert rest_positions.beside("") == rest_positions.DEFAULT_PATH
