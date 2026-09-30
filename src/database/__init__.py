import logging

import requests
from requests import RequestException
from src.config import SERVER_URL, API_TOKEN, CAFFEINE_HALF_LIFE, SLEEP_CAFFEINE_THRESHOLD
from src.database.analytics import DBAnalyticsMixin
from src.database.cache import LedgerCache, domain_for_path
from src.database.rows import (BeverageItemRow, BeverageLogRow,
                               ChoreDoneRow, ChoreRow,
                               ExerciseItemRow, ExerciseLogRow, FoodItemRow,
                               FoodLogRow, MobilityItemRow, MobilityLogRow,
                               PlanMovementRow, PlanSessionRow,
                               PomodoroDailyRow, SetComponentRow,
                               SupplementItemRow, SupplementLogRow,
                               TrainingPlanRow, WorkoutComponentRow)
from src.domain import formulas, plans
from src.profile import UserProfile

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 5

_CAFFEINE = BeverageLogRow._fields.index("caffeine_mg")


class ConnectionStatus:
    """Whether the household service is answering, and why not if it is not."""

    def __init__(self):
        self.online = True
        self.last_error = None
        self.on_change = None

    def record_success(self):
        self._set(True, None)

    def record_failure(self, reason: str):
        self._set(False, reason)

    def _set(self, online, reason):
        changed = (online != self.online)
        self.online = online
        self.last_error = reason
        if changed and self.on_change is not None:
            self.on_change(online, reason or "")


def _refusal(response) -> str:
    """Return the reason a response carries, whatever shape it arrived in."""
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "").strip()[:200] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        return str(payload.get("error", payload))
    return str(payload)


def _since(since):
    """Build the ?since= query parameters for a date-bounded read."""
    return {"since": since} if since else None


def _each(shape):
    """Return a builder of shape rows from the rows a read answered."""
    return lambda body: [shape.from_server(row) for row in body]


class DatabaseClient(DBAnalyticsMixin):
    def __init__(self, base_url: str = SERVER_URL, token: str = API_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.connection = ConnectionStatus()
        self.cache = LedgerCache()

    def _fetch(self, path: str, params: dict = None):
        """Return the parsed answer to a read, or None where there is none."""
        try:
            r = requests.get(f"{self.base_url}{path}", headers=self.headers, params=params, timeout=REQUEST_TIMEOUT_S)
        except RequestException as e:
            log.warning("GET %s failed: %s", path, e)
            self.connection.record_failure(str(e))
            return None

        if r.status_code >= 400:
            self.connection.record_success()
            log.warning("GET %s refused: %s", path, _refusal(r))
            return None

        try:
            body = r.json()
        except ValueError as e:
            log.warning("GET %s answered something that is not JSON: %s", path, e)
            self.connection.record_failure(f"unreadable response from {path}")
            return None
        self.connection.record_success()
        return body

    def _get(self, path: str, params: dict = None):
        body = self._fetch(path, params)
        return [] if body is None else body

    def _post(self, path: str, payload: dict):
        try:
            r = requests.post(f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=REQUEST_TIMEOUT_S)
        except RequestException as e:
            log.warning("POST %s failed: %s", path, e)
            self.connection.record_failure(str(e))
            return False, str(e)
        self.connection.record_success()
        if r.status_code >= 400:
            return False, _refusal(r)
        self.invalidate(domain_for_path(path))
        return True, "Success"

    def _delete(self, path: str):
        success, message, _payload = self._delete_with_body(path)
        return success, message

    def _delete_with_body(self, path: str):
        """Delete and return whatever the answer carried."""
        try:
            r = requests.delete(f"{self.base_url}{path}", headers=self.headers, timeout=REQUEST_TIMEOUT_S)
        except RequestException as e:
            log.warning("DELETE %s failed: %s", path, e)
            self.connection.record_failure(str(e))
            return False, str(e), None
        self.connection.record_success()
        if r.status_code >= 400:
            return False, _refusal(r), None
        try:
            payload = r.json()
        except ValueError:
            payload = None
        self.invalidate(domain_for_path(path))
        return True, "Success", payload

    def get_setting(self, key: str, default_val: str) -> str:
        data = self._get(f"/api/settings/{key}", params={"default": default_val})
        return data.get("value", default_val) if isinstance(data, dict) else default_val

    def get_settings(self, keys, defaults=None) -> dict:
        """Return several preferences in one round trip, filling in defaults here."""
        keys = list(keys)
        if not keys:
            return {}
        answered = self._get("/api/settings", params={"keys": ",".join(keys)})
        if not isinstance(answered, dict):
            answered = {}
        fallbacks = defaults or {}
        return {key: answered.get(key, fallbacks.get(key, "")) for key in keys}

    def set_setting(self, key: str, value: str):
        return self._post(f"/api/settings/{key}", {"value": value})

    def _catalog(self, domain: str, shape):
        """Return one shared catalog as shape."""
        return _each(shape)(self._get(f"/api/catalog/{domain}"))

    def get_all_foods(self):
        return self._catalog("food", FoodItemRow)

    def add_food_item(self, d: dict):
        return self._post("/api/catalog/food", d)

    def get_sets(self, domain: str):
        """Return every shared set of one domain, one row per component."""
        shape = WorkoutComponentRow if domain == "exercise" else SetComponentRow
        return self._catalog(f"sets/{domain}", shape)

    def add_set(self, domain: str, d: dict):
        return self._post(f"/api/catalog/sets/{domain}", d)

    def get_all_beverages(self):
        return self._catalog("beverage", BeverageItemRow)

    def add_beverage_item(self, d: dict):
        return self._post("/api/catalog/beverage", d)

    def get_all_exercises(self):
        return self._catalog("exercise", ExerciseItemRow)

    def get_all_exercise_names(self):
        return [item.name for item in self.get_all_exercises()]

    def add_exercise_item(self, d: dict):
        return self._post("/api/catalog/exercise", d)

    def get_all_supplements(self):
        return self._catalog("supplement", SupplementItemRow)

    def add_supplement_item(self, d: dict):
        return self._post("/api/catalog/supplement", d)

    def get_all_mobility(self):
        return self._catalog("mobility", MobilityItemRow)

    def add_mobility_item(self, d: dict):
        return self._post("/api/catalog/mobility", d)

    def delete_item_by_name(self, name: str):
        """Remove an item from every catalog that holds it, and say how many."""
        success, message, payload = self._delete_with_body(f"/api/catalog/items/{name}")
        if not success:
            return False, message

        removed = payload.get("removed") if isinstance(payload, dict) else None
        if not isinstance(removed, int):
            return True, f" Removed '{name}'."
        catalogs = "catalog" if removed == 1 else "catalogs"
        return True, f" Removed '{name}' from {removed} {catalogs}."

    def invalidate(self, domains=None):
        """Forget cached reads: everything, or just these domains."""
        if domains is None:
            self.cache.clear()
        else:
            self.cache.drop(domains)

    def _cached(self, domain, path, rows_of, since=None):
        """Answer from the cache where it can, otherwise read and remember."""
        held = self.cache.get(domain, since)
        if held is not None:
            return held
        generation = self.cache.generation(domain)
        body = self._fetch(path, _since(since))
        if body is None:
            return []
        rows = rows_of(body)
        self.cache.put(domain, since, rows, generation)
        return rows

    def get_food_logs(self, since: str = None):
        return self._cached("food", "/api/logs/food", _each(FoodLogRow), since)

    def add_food_log(self, d: dict):
        return self._post("/api/logs/food", d)

    def add_quick_food_log(self, d: dict):
        """Log a meal nobody has a label for, as an estimate in calories."""
        return self._post("/api/logs/food/quick", d)

    def get_beverage_logs(self, since: str = None):
        return self._cached("beverage", "/api/logs/beverage", _beverage_rows, since)

    def add_beverage_log(self, d: dict):
        return self._post("/api/logs/beverage", d)

    def get_exercise_logs(self, since: str = None):
        return self._cached("exercise", "/api/logs/exercise", _each(ExerciseLogRow), since)

    def add_exercise_log(self, d: dict):
        return self._post("/api/logs/exercise", d)

    def add_workout_log(self, d: dict):
        """Log every movement of a workout, as the template describes it."""
        return self._post("/api/logs/exercise/workout", d)

    def get_supplement_logs(self, since: str = None):
        return self._cached("supplement", "/api/logs/supplement", _each(SupplementLogRow), since)

    def add_supplement_log(self, d: dict):
        return self._post("/api/logs/supplement", d)

    def get_mobility_logs(self, since: str = None):
        return self._cached("mobility", "/api/logs/mobility", _each(MobilityLogRow), since)

    def add_mobility_log(self, d: dict):
        return self._post("/api/logs/mobility", d)

    def delete_record(self, table: str, row_id: int):
        return self._delete(f"/api/logs/{table}/{row_id}")

    def update_record(self, table: str, row_id: int, col_name: str, new_val: str, column_mapping: dict):
        db_col = column_mapping.get(col_name)
        if not db_col:
            return False, "Target database column lookup mapping failed."
        try:
            r = requests.patch(
                f"{self.base_url}/api/logs/{table}/{row_id}",
                headers=self.headers,
                json={"col": db_col, "val": new_val},
                timeout=REQUEST_TIMEOUT_S
            )
        except RequestException as e:
            log.warning("PATCH /api/logs/%s/%s failed: %s", table, row_id, e)
            self.connection.record_failure(str(e))
            return False, str(e)
        self.connection.record_success()
        if r.status_code >= 400:
            return False, _refusal(r)
        self.invalidate(domain_for_path(f"/api/logs/{table}/{row_id}"))
        return True, "Success"

    def get_chores(self):
        """Return the board: every chore, its cadence and its last completion."""
        return self._cached("chore", "/api/chores", _each(ChoreRow))

    def get_chore_completions(self, since: str = None):
        """Return the shared history, most recent first."""
        return _each(ChoreDoneRow)(self._get("/api/chores/completions", _since(since)))

    def add_chore(self, d: dict):
        return self._post("/api/chores", d)

    def complete_chore(self, d: dict):
        """Tick one chore for one day."""
        return self._post("/api/chores/done", d)

    def get_training_plans(self):
        return self._cached("plan", "/api/plans", _each(TrainingPlanRow))

    def get_plan_sessions(self, plan_id: int):
        return _each(PlanSessionRow)(self._get(f"/api/plans/{plan_id}/sessions"))

    def get_plan_movements(self, plan_id: int):
        """Return every movement of one cycle, in one read."""
        return _each(PlanMovementRow)(self._get(f"/api/plans/{plan_id}/movements"))

    def add_training_plan(self, d: dict):
        return self._post("/api/plans", d)

    def log_planned_session(self, d: dict):
        """Write the session planned for one date into the exercise ledger."""
        plan = plans.current_plan(self.get_training_plans())
        if plan is None:
            return False, "There is no training plan to log a session from."
        return self._post(f"/api/plans/{plan.id}/log", {"date": d["date"]})

    def get_pomodoro_daily_summary(self):
        return _each(PomodoroDailyRow)(self._get("/api/pomodoro/daily-summary"))

    def get_pomodoro_heartbeats_for_day(self, date: str):
        rows = self._get(f"/api/pomodoro/heartbeats/{date}")
        return {(r[0] + (r[1] / 60.0)): (r[2], r[3]) for r in rows}

    def log_pomodoro_heartbeat(self, d: dict):
        return self._post("/api/pomodoro/heartbeat", d)

    def get_pomodoro_events_for_day(self, date: str):
        rows = self._get(f"/api/pomodoro/events/{date}")
        return [tuple(r) for r in rows]

    def log_pomodoro_event(self, d: dict):
        return self._post("/api/pomodoro/event", d)

    def get_pomodoro_dsi_overrides(self):
        return self._get("/api/pomodoro/dsi-overrides") or {}

    def set_pomodoro_dsi_override(self, d: dict):
        return self._post("/api/pomodoro/dsi-override", d)

    def clear_pomodoro_dsi_override(self, date: str):
        return self._delete(f"/api/pomodoro/dsi-override/{date}")


def _beverage_rows(body):
    """Build beverage rows, each with its wait until the dose is sleep-safe."""
    profile = UserProfile()
    half_life = float(profile.get_metric("goals", "caffeine_half_life", CAFFEINE_HALF_LIFE))
    threshold = float(profile.get_metric("goals", "max_sleep_caffeine", SLEEP_CAFFEINE_THRESHOLD))

    def wait(row):
        hours = formulas.hours_until_caffeine_safe(row[_CAFFEINE] or 0.0, threshold, half_life)
        return f"{hours:.1f} hrs"

    return [BeverageLogRow.from_server(row, wait(row)) for row in body]
