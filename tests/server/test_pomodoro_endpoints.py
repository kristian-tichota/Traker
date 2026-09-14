import datetime

import pytest

STATES = ["focus", "rest", "focus_overtime", "rest_overtime"]


def heartbeat(minute, state="focus", second=0, date="2026-09-05", mode="Default"):
    return {"date": date, "minute_of_day": minute, "second": second,
            "state": state, "mode": mode}


class TestHeartbeats:
    @pytest.mark.exact
    @pytest.mark.parametrize("state", STATES)
    def test_the_four_states_are_the_only_ones_accepted(self, member_a, state):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, state))

        (row,) = member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()
        assert row[2] == state

    def test_a_state_outside_the_four_is_not_stored(self, member_a):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, "procrastinating"))

        assert member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json() == []

    @pytest.mark.exact
    def test_re_crossing_a_stored_minute_replaces_the_row(self, member_a):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, "focus"))
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, "rest"))

        rows = member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()
        assert len(rows) == 1, "one row per minute of the day, not an append log"
        assert rows[0][2] == "rest"

    def test_the_row_carries_the_active_mode_name(self, member_a):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, mode="Hardcore Gaming"))

        (row,) = member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()
        assert row[3] == "Hardcore Gaming"

    @pytest.mark.parametrize("minute", [0, 1439])
    def test_the_day_boundaries_are_valid_minutes(self, member_a, minute):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(minute))
        assert len(member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()) == 1

    @pytest.mark.parametrize("minute", [-1, 1440])
    def test_a_minute_outside_the_day_is_not_stored(self, member_a, minute):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(minute))
        assert member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json() == []

    def test_heartbeats_are_fetched_one_day_at_a_time(self, member_a):
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, date="2026-09-05"))
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, date="2026-09-04"))

        assert len(member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()) == 1
        assert member_a.get("/api/pomodoro/heartbeats/2026-09-01").get_json() == []


class TestDailySummary:
    @pytest.fixture
    def today(self):
        return datetime.date.today().isoformat()

    @pytest.mark.exact
    def test_each_state_is_counted_into_its_own_column(self, member_a, today):
        minutes = {"focus": 3, "rest": 2, "focus_overtime": 4, "rest_overtime": 1}
        minute_of_day = 0
        for state, count in minutes.items():
            for _ in range(count):
                member_a.post("/api/pomodoro/heartbeat", json=heartbeat(minute_of_day, state, date=today))
                minute_of_day += 1

        (row,) = member_a.get("/api/pomodoro/daily-summary").get_json()
        assert row == [today, 3, 2, 4, 1]

    def test_days_are_returned_oldest_first(self, member_a):
        today = datetime.date.today()
        for offset in (0, 3, 1):
            date = (today - datetime.timedelta(days=offset)).isoformat()
            member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, date=date))

        dates = [row[0] for row in member_a.get("/api/pomodoro/daily-summary").get_json()]
        assert dates == sorted(dates)

    def test_the_summary_covers_the_last_thirty_days(self, member_a):
        today = datetime.date.today()
        member_a.post("/api/pomodoro/heartbeat",
                      json=heartbeat(600, date=(today - datetime.timedelta(days=5)).isoformat()))
        member_a.post("/api/pomodoro/heartbeat",
                      json=heartbeat(600, date=(today - datetime.timedelta(days=45)).isoformat()))

        dates = [row[0] for row in member_a.get("/api/pomodoro/daily-summary").get_json()]
        assert len(dates) == 1
        assert dates[0] == (today - datetime.timedelta(days=5)).isoformat()

    def test_a_day_with_nothing_logged_is_simply_absent(self, member_a):
        assert member_a.get("/api/pomodoro/daily-summary").get_json() == []


class TestTimelineEvents:
    def test_a_manual_action_is_recorded_with_its_moment(self, member_a):
        member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-05T10:15:30", "event_type": "paused_focus", "amount_ms": 0,
        })

        (row,) = member_a.get("/api/pomodoro/events/2026-09-05").get_json()
        assert row == ["2026-09-05T10:15:30", "paused_focus", 0]

    def test_a_skip_records_how_much_time_remained(self, member_a):
        member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-05T10:15:30", "event_type": "skipped_focus",
            "amount_ms": 420000,
        })

        (row,) = member_a.get("/api/pomodoro/events/2026-09-05").get_json()
        assert row[2] == 420000

    def test_the_amount_defaults_to_zero(self, member_a):
        member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-05T10:15:30", "event_type": "resumed_focus",
        })

        assert member_a.get("/api/pomodoro/events/2026-09-05").get_json()[0][2] == 0

    def test_events_are_returned_in_the_order_they_happened(self, member_a):
        for stamp, kind in [("2026-09-05T12:00:00", "paused_focus"),
                            ("2026-09-05T09:00:00", "resumed_focus"),
                            ("2026-09-05T11:00:00", "skipped_break")]:
            member_a.post("/api/pomodoro/event", json={
                "timestamp": stamp, "event_type": kind, "amount_ms": 0,
            })

        kinds = [row[1] for row in member_a.get("/api/pomodoro/events/2026-09-05").get_json()]
        assert kinds == ["resumed_focus", "skipped_break", "paused_focus"]

    def test_events_are_fetched_by_calendar_day(self, member_a):
        member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-04T23:59:00", "event_type": "paused_focus", "amount_ms": 0,
        })

        assert member_a.get("/api/pomodoro/events/2026-09-05").get_json() == []
        assert len(member_a.get("/api/pomodoro/events/2026-09-04").get_json()) == 1

    def test_several_events_may_share_a_minute(self, member_a):
        for kind in ("paused_focus", "resumed_focus"):
            member_a.post("/api/pomodoro/event", json={
                "timestamp": "2026-09-05T10:15:30", "event_type": kind, "amount_ms": 0,
            })

        assert len(member_a.get("/api/pomodoro/events/2026-09-05").get_json()) == 2


class TestStressOverrides:
    def test_setting_an_override_returns_it_keyed_by_date(self, member_a):
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": 0.75})

        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {"2026-09-05": 0.75}

    def test_re_setting_a_date_replaces_the_value(self, member_a):
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": 0.75})
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": 1.4})

        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {"2026-09-05": 1.4}

    def test_clearing_an_override_removes_it(self, member_a):
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": 0.75})

        member_a.delete("/api/pomodoro/dsi-override/2026-09-05")

        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {}

    def test_clearing_an_override_that_is_not_there_is_refused_not_confirmed(self, member_a):
        response = member_a.delete("/api/pomodoro/dsi-override/2026-09-05")

        assert response.status_code == 404
        assert "2026-09-05" in response.get_json()["error"]

    def test_a_malformed_date_in_the_url_is_refused(self, member_a):
        assert member_a.get("/api/pomodoro/heartbeats/05.09.2026").status_code == 400
        assert member_a.get("/api/pomodoro/events/05.09.2026").status_code == 400
        assert member_a.delete("/api/pomodoro/dsi-override/nonsense").status_code == 400

    def test_a_negative_override_is_not_stored(self, member_a):
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": -1.0})

        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {}

    def test_an_override_leaves_the_stored_history_untouched(self, member_a):
        today = datetime.date.today().isoformat()
        member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, "focus", date=today))

        member_a.post("/api/pomodoro/dsi-override", json={"date": today, "override_dsi": 0.1})

        assert member_a.get("/api/pomodoro/daily-summary").get_json() == [[today, 1, 0, 0, 0]]


class TestTheTelemetryWritePathIsGuardedToo:
    @pytest.mark.parametrize("written", ["1e400", "inf", "nan"])
    def test_a_stress_override_that_is_not_finite_is_refused(self, member_a, written):
        response = member_a.post("/api/pomodoro/dsi-override",
                                 json={"date": "2026-09-05", "override_dsi": written})

        assert response.status_code == 400
        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {}

    def test_text_where_a_stress_override_belongs_is_refused(self, member_a):
        response = member_a.post("/api/pomodoro/dsi-override",
                                 json={"date": "2026-09-05", "override_dsi": "high"})

        assert response.status_code == 400
        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {}

    def test_a_heartbeat_with_a_bad_date_is_refused(self, member_a):
        response = member_a.post("/api/pomodoro/heartbeat", json=heartbeat(600, date="not-a-date"))

        assert response.status_code == 400
        assert member_a.get("/api/pomodoro/daily-summary").get_json() == []

    def test_an_event_timestamp_that_is_not_a_moment_is_refused(self, member_a):
        response = member_a.post("/api/pomodoro/event",
                                 json={"timestamp": "whenever", "event_type": "skip"})

        assert response.status_code == 400

    def test_a_date_alone_is_not_a_moment(self, member_a):
        response = member_a.post("/api/pomodoro/event",
                                 json={"timestamp": "2026-09-05", "event_type": "skip"})

        assert response.status_code == 400

    def test_a_well_formed_moment_still_goes_through(self, member_a):
        moment = datetime.datetime(2026, 9, 5, 14, 30, 15, 123456).isoformat()

        member_a.post("/api/pomodoro/event", json={"timestamp": moment, "event_type": "skip"})

        (row,) = member_a.get("/api/pomodoro/events/2026-09-05").get_json()
        assert row[0] == moment

    def test_a_negative_amount_is_refused(self, member_a):
        response = member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-05T14:30:00", "event_type": "skip", "amount_ms": -5,
        })

        assert response.status_code == 400

    @pytest.mark.parametrize("table", [
        "pomodoro_heartbeats", "pomodoro_events", "pomodoro_dsi_overrides", "user_settings",
    ])
    def test_no_telemetry_row_may_be_edited_or_deleted_by_id(self, member_a, table):
        assert member_a.patch(f"/api/logs/{table}/1", json={"col": "date", "val": "2026-09-05"}).status_code == 400
        assert member_a.delete(f"/api/logs/{table}/1").status_code == 400
