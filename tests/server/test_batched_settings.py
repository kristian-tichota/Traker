import pytest

pytestmark = pytest.mark.usefixtures("server_db")


def set_setting(member, key, value):
    return member.post(f"/api/settings/{key}", json={"value": value})


class TestReadingSeveralAtOnce:
    def test_it_answers_every_key_the_member_has_set(self, member_a):
        set_setting(member_a, "ex_graph_slot_1", "Bench Press")
        set_setting(member_a, "ex_graph_slot_2", "Deadlift")

        response = member_a.get("/api/settings?keys=ex_graph_slot_1,ex_graph_slot_2")

        assert response.status_code == 200
        assert response.get_json() == {
            "ex_graph_slot_1": "Bench Press", "ex_graph_slot_2": "Deadlift"}

    def test_a_key_never_set_is_absent_rather_than_empty(self, member_a):
        set_setting(member_a, "ex_graph_slot_1", "Bench Press")

        answered = member_a.get("/api/settings?keys=ex_graph_slot_1,never_set").get_json()

        assert answered == {"ex_graph_slot_1": "Bench Press"}

    def test_it_answers_only_the_keys_asked_for(self, member_a):
        set_setting(member_a, "wanted", "yes")
        set_setting(member_a, "unwanted", "no")

        answered = member_a.get("/api/settings?keys=wanted").get_json()

        assert answered == {"wanted": "yes"}

    def test_whitespace_around_a_key_is_ignored(self, member_a):
        set_setting(member_a, "spaced", "value")

        answered = member_a.get("/api/settings?keys= spaced , ").get_json()

        assert answered == {"spaced": "value"}

    def test_naming_no_keys_answers_nothing_rather_than_everything(self, member_a):
        set_setting(member_a, "something", "value")

        assert member_a.get("/api/settings?keys=").get_json() == {}
        assert member_a.get("/api/settings").get_json() == {}

    def test_one_read_answers_what_nine_reads_would_have(self, member_a):
        for slot in range(1, 10):
            set_setting(member_a, f"ex_graph_slot_{slot}", f"Exercise {slot}")

        keys = ",".join(f"ex_graph_slot_{slot}" for slot in range(1, 10))
        batched = member_a.get(f"/api/settings?keys={keys}").get_json()

        one_at_a_time = {
            f"ex_graph_slot_{slot}":
                member_a.get(f"/api/settings/ex_graph_slot_{slot}").get_json()["value"]
            for slot in range(1, 10)
        }
        assert batched == one_at_a_time


class TestItIsScopedToTheMember:
    def test_it_never_answers_with_the_other_members_preference(
            self, member_a, member_b):
        set_setting(member_a, "ex_graph_slot_1", "Bench Press")
        set_setting(member_b, "ex_graph_slot_1", "Deadlift")

        assert member_a.get("/api/settings?keys=ex_graph_slot_1").get_json() == {
            "ex_graph_slot_1": "Bench Press"}
        assert member_b.get("/api/settings?keys=ex_graph_slot_1").get_json() == {
            "ex_graph_slot_1": "Deadlift"}

    def test_a_key_only_the_other_member_set_is_absent(self, member_a, member_b):
        set_setting(member_b, "theirs", "value")

        assert member_a.get("/api/settings?keys=theirs").get_json() == {}

    def test_it_requires_a_token(self, anon):
        assert anon.get("/api/settings?keys=anything").status_code == 401


class TestTheClientSideDefaults:
    def test_an_unset_key_comes_back_as_its_default(self, db_client, member_a):
        set_setting(member_a, "ex_graph_slot_1", "Bench Press")

        answered = db_client.get_settings(
            ["ex_graph_slot_1", "ex_graph_slot_2"],
            {"ex_graph_slot_1": "None", "ex_graph_slot_2": "None"})

        assert answered == {"ex_graph_slot_1": "Bench Press", "ex_graph_slot_2": "None"}

    def test_every_key_asked_for_is_present_in_the_answer(self, db_client):
        answered = db_client.get_settings(["a", "b", "c"], {"a": "1"})

        assert set(answered) == {"a", "b", "c"}
        assert answered["a"] == "1"
        assert answered["b"] == ""

    def test_asking_for_nothing_makes_no_request(self, db_client):
        assert db_client.get_settings([]) == {}

    def test_it_agrees_with_the_single_key_read(self, db_client, member_a):
        set_setting(member_a, "ex_graph_slot_1", "Bench Press")

        assert db_client.get_settings(["ex_graph_slot_1"])["ex_graph_slot_1"] == \
            db_client.get_setting("ex_graph_slot_1", "None")
