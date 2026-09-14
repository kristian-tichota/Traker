import pytest

VACUUM = {"name": "Vacuum", "period_days": 7, "anchor": "2026-09-11"}
BINS = {"name": "Bins", "period_days": 7, "anchor": "2026-09-08",
        "grace_days": 1, "notes": "Tuesday night"}


@pytest.fixture
def board(member_a):
    member_a.post("/api/chores", json=VACUUM)
    member_a.post("/api/chores", json=BINS)
    return member_a


def rows_by_name(client):
    return {row["name"]: row for row in client.get("/api/chores").get_json()}


class TestDefiningOne:
    def test_a_chore_is_defined_with_its_cadence(self, board):
        row = rows_by_name(board)["Vacuum"]
        assert (row["period_days"], row["anchor"]) == (7, "2026-09-11")

    def test_an_undeclared_grace_stays_unanswered_rather_than_zero(self, board):
        assert rows_by_name(board)["Vacuum"]["grace_days"] is None
        assert rows_by_name(board)["Bins"]["grace_days"] == 1

    def test_a_chore_starts_active(self, board):
        assert rows_by_name(board)["Vacuum"]["active"] == 1

    def test_a_chore_starts_with_no_completions(self, board):
        row = rows_by_name(board)["Vacuum"]
        assert (row["last_done"], row["done_count"]) == (None, 0)

    def test_a_name_is_one_identity_however_it_is_capitalised(self, board):
        answer = board.post("/api/chores", json=dict(VACUUM, name="VACUUM"))
        assert answer.status_code == 400

    def test_a_cadence_of_zero_is_refused_by_the_store(self, member_a):
        answer = member_a.post("/api/chores", json=dict(VACUUM, period_days=0))
        assert answer.status_code == 400

    def test_a_negative_grace_is_refused_at_the_boundary(self, member_a):
        answer = member_a.post("/api/chores", json=dict(VACUUM, grace_days=-2))
        assert answer.status_code == 400

    def test_an_anchor_that_is_not_a_date_is_refused(self, member_a):
        answer = member_a.post("/api/chores", json=dict(VACUUM, anchor="Friday"))
        assert answer.status_code == 400

    def test_text_in_the_cadence_is_refused_rather_than_stored(self, member_a):
        answer = member_a.post("/api/chores", json=dict(VACUUM, period_days="7d"))
        assert answer.status_code == 400

    def test_a_body_missing_the_cadence_is_refused(self, member_a):
        answer = member_a.post("/api/chores", json={"name": "Vacuum"})
        assert answer.status_code == 400


class TestOneSharedBoard:
    def test_both_members_see_the_same_chores(self, board, member_b):
        assert sorted(rows_by_name(member_b)) == ["Bins", "Vacuum"]

    def test_either_member_may_define_one(self, board, member_b):
        assert member_b.post(
            "/api/chores",
            json={"name": "Descale", "period_days": 30,
                  "anchor": "2026-10-01"}).status_code == 201
        assert "Descale" in rows_by_name(board)

    def test_one_member_ticking_it_clears_it_for_the_other(self, board, member_b):
        member_b.post("/api/chores/done",
                      json={"name": "Vacuum", "date": "2026-09-11"})
        assert rows_by_name(board)["Vacuum"]["last_done"] == "2026-09-11"

    def test_the_history_says_who_did_it(self, board, member_b):
        member_b.post("/api/chores/done",
                      json={"name": "Bins", "date": "2026-09-08"})
        (row,) = board.get("/api/chores/completions").get_json()
        assert row[1:] == ["2026-09-08", "Bins", member_b.username]


class TestTickingOne:
    def test_the_last_completion_is_what_the_board_reports(self, board):
        for day in ("2026-09-04", "2026-09-11"):
            board.post("/api/chores/done", json={"name": "Vacuum", "date": day})
        row = rows_by_name(board)["Vacuum"]
        assert (row["last_done"], row["done_count"]) == ("2026-09-11", 2)

    def test_a_second_press_on_one_day_is_the_one_completion_it_is(self, board):
        first = board.post("/api/chores/done",
                           json={"name": "Vacuum", "date": "2026-09-11"})
        again = board.post("/api/chores/done",
                           json={"name": "Vacuum", "date": "2026-09-11"})
        assert first.get_json()["repeated"] is False
        assert again.get_json()["repeated"] is True
        assert rows_by_name(board)["Vacuum"]["done_count"] == 1

    def test_a_chore_may_be_ticked_by_a_name_typed_in_any_case(self, board):
        answer = board.post("/api/chores/done",
                            json={"name": "vacuum", "date": "2026-09-11"})
        assert answer.status_code == 200
        assert rows_by_name(board)["Vacuum"]["last_done"] == "2026-09-11"

    def test_ticking_a_chore_nobody_defined_is_refused_by_name(self, board):
        answer = board.post("/api/chores/done",
                            json={"name": "Hoover", "date": "2026-09-11"})
        assert answer.status_code == 400
        assert "Hoover" in answer.get_json()["error"]

    def test_a_completion_on_a_date_that_is_not_one_is_refused(self, board):
        answer = board.post("/api/chores/done",
                            json={"name": "Vacuum", "date": "tomorrow"})
        assert answer.status_code == 400


class TestTheHistory:
    def test_it_reads_most_recent_first(self, board):
        for day in ("2026-09-04", "2026-09-18", "2026-09-11"):
            board.post("/api/chores/done", json={"name": "Vacuum", "date": day})
        dates = [row[1] for row in board.get("/api/chores/completions").get_json()]
        assert dates == ["2026-09-18", "2026-09-11", "2026-09-04"]

    def test_a_bounded_read_answers_only_its_window(self, board):
        for day in ("2026-09-04", "2026-09-18"):
            board.post("/api/chores/done", json={"name": "Vacuum", "date": day})
        rows = board.get("/api/chores/completions?since=2026-09-10").get_json()
        assert [row[1] for row in rows] == ["2026-09-18"]

    def test_a_malformed_bound_is_refused_rather_than_answered_with_everything(
        self, board
    ):
        assert board.get(
            "/api/chores/completions?since=last-week").status_code == 400

    def test_a_completion_may_be_corrected_by_row(self, board):
        board.post("/api/chores/done", json={"name": "Vacuum", "date": "2026-09-12"})
        (row,) = board.get("/api/chores/completions").get_json()
        answer = board.patch(f"/api/logs/chore_completions/{row[0]}",
                             json={"col": "date", "val": "2026-09-11"})
        assert answer.status_code == 200
        assert rows_by_name(board)["Vacuum"]["last_done"] == "2026-09-11"

    def test_re_pointing_a_completion_at_another_chore_is_refused(self, board):
        board.post("/api/chores/done", json={"name": "Vacuum", "date": "2026-09-11"})
        (row,) = board.get("/api/chores/completions").get_json()
        answer = board.patch(f"/api/logs/chore_completions/{row[0]}",
                             json={"col": "chore_id", "val": 2})
        assert answer.status_code == 400

    def test_deleting_a_chore_takes_its_history_with_it(self, board):
        board.post("/api/chores/done", json={"name": "Vacuum", "date": "2026-09-11"})
        chore_id = rows_by_name(board)["Vacuum"]["id"]
        assert board.delete(f"/api/logs/chores/{chore_id}").status_code == 200
        assert board.get("/api/chores/completions").get_json() == []


class TestEditingOne:
    def test_a_cadence_is_editable_by_row(self, board):
        chore_id = rows_by_name(board)["Vacuum"]["id"]
        answer = board.patch(f"/api/logs/chores/{chore_id}",
                             json={"col": "period_days", "val": 14})
        assert answer.status_code == 200
        assert rows_by_name(board)["Vacuum"]["period_days"] == 14

    def test_a_chore_may_be_paused_without_being_deleted(self, board):
        chore_id = rows_by_name(board)["Vacuum"]["id"]
        board.patch(f"/api/logs/chores/{chore_id}", json={"col": "active", "val": 0})
        assert rows_by_name(board)["Vacuum"]["active"] == 0

    def test_a_column_that_is_not_writable_is_refused(self, board):
        chore_id = rows_by_name(board)["Vacuum"]["id"]
        answer = board.patch(f"/api/logs/chores/{chore_id}",
                             json={"col": "done_count", "val": 9})
        assert answer.status_code == 400

    def test_a_write_that_matched_no_row_is_a_404(self, board):
        answer = board.patch("/api/logs/chores/9999",
                             json={"col": "period_days", "val": 3})
        assert answer.status_code == 404


class TestAuthentication:
    @pytest.mark.parametrize("verb,path", [
        ("get", "/api/chores"),
        ("get", "/api/chores/completions"),
        ("post", "/api/chores"),
        ("post", "/api/chores/done"),
    ])
    def test_every_route_needs_a_token(self, anon, verb, path):
        answer = getattr(anon, verb)(path, json={})
        assert answer.status_code == 401
