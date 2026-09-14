import pytest

OATS = {"name": "Rolled Oats", "category": "Carbs", "energy": 380, "fat_total": 7,
        "fat_saturated": 1.2, "carbs_total": 60, "carbs_sugars": 1, "fibre": 10,
        "protein": 13, "salt": 0, "serving_size": 50}
BLUE = {"name": "Blueberries", "category": "Fruit", "energy": 57, "fat_total": 0.3,
        "fat_saturated": 0, "carbs_total": 14, "carbs_sugars": 10, "fibre": 2.4,
        "protein": 0.7, "salt": 0, "serving_size": 100}

NAME, SERVINGS, GRAMS, SET, KCAL = 4, 5, 6, 7, 8


@pytest.fixture
def stocked(member_a):
    member_a.post("/api/catalog/food", json=OATS)
    member_a.post("/api/catalog/food", json=BLUE)
    return member_a


def define(api, domain, name, components):
    return api.post(f"/api/catalog/sets/{domain}",
                    json={"name": name, "components": components})


def blue_oatmeal(api, oats=100, blueberries=50):
    parts = [{"item_name": "Rolled Oats", "amount": oats}]
    if blueberries:
        parts.append({"item_name": "Blueberries", "amount": blueberries})
    return define(api, "food", "Blue Oatmeal", parts)


class TestDefiningAMealSet:
    def test_define_and_read_back(self, stocked):
        r = blue_oatmeal(stocked)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["components"] == 2

        rows = stocked.get("/api/catalog/sets/food").get_json()
        assert [(row[1], row[2], row[3]) for row in rows] == [
            ("Blue Oatmeal", "Blueberries", 50.0),
            ("Blue Oatmeal", "Rolled Oats", 100.0)]

    def test_a_component_is_matched_however_it_is_capitalised(self, stocked):
        assert define(stocked, "food", "Porridge", [
            {"item_name": "rolled oats", "amount": 100}]).status_code == 200

    def test_a_set_may_not_take_a_foods_name(self, stocked):
        r = define(stocked, "food", "rolled oats",
                   [{"item_name": "Blueberries", "amount": 10}])
        assert r.status_code == 400
        assert "already a food item" in r.get_json()["error"]

    def test_an_unknown_component_is_refused(self, stocked):
        r = define(stocked, "food", "Mystery",
                   [{"item_name": "Unobtainium", "amount": 10}])
        assert r.status_code == 400
        assert "not found in catalog" in r.get_json()["error"]
        assert stocked.get("/api/catalog/sets/food").get_json() == []

    def test_a_negative_amount_is_refused(self, stocked):
        r = define(stocked, "food", "Mystery",
                   [{"item_name": "Rolled Oats", "amount": -5}])
        assert r.status_code == 400
        assert stocked.get("/api/catalog/sets/food").get_json() == []

    def test_text_in_the_amount_is_refused(self, stocked):
        r = define(stocked, "food", "Mystery",
                   [{"item_name": "Rolled Oats", "amount": "100o"}])
        assert r.status_code == 400
        assert "not a number" in r.get_json()["error"]

    def test_a_duplicate_set_name_is_refused(self, stocked):
        assert blue_oatmeal(stocked).status_code == 200
        assert blue_oatmeal(stocked).status_code == 400
        assert len(stocked.get("/api/catalog/sets/food").get_json()) == 2

    def test_a_component_listed_twice_is_refused(self, stocked):
        r = define(stocked, "food", "Blue Oatmeal", [
            {"item_name": "Rolled Oats", "amount": 100},
            {"item_name": "rolled oats", "amount": 50}])
        assert r.status_code == 400
        assert "twice" in r.get_json()["error"]

    def test_a_set_with_no_components_is_refused(self, stocked):
        assert define(stocked, "food", "Empty", []).status_code == 400

    def test_a_domain_with_no_sets_is_refused(self, stocked):
        assert stocked.get("/api/catalog/sets/pomodoro").status_code == 400
        assert define(stocked, "pomodoro", "Nope", []).status_code == 400


class TestLoggingAMealSet:
    def test_it_expands_into_one_ordinary_row_per_ingredient(self, stocked):
        blue_oatmeal(stocked)
        r = stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "blue oatmeal", "servings": 1})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["rows"] == 2
        assert r.get_json()["meal_set"] == "Blue Oatmeal"

        by_food = {row[NAME]: row for row in stocked.get("/api/logs/food").get_json()}
        assert by_food["Rolled Oats"][SET] == "Blue Oatmeal"
        assert by_food["Rolled Oats"][GRAMS] == pytest.approx(100.0)
        assert by_food["Rolled Oats"][SERVINGS] == pytest.approx(2.0)
        assert by_food["Rolled Oats"][KCAL] == pytest.approx(380.0)
        assert by_food["Blueberries"][GRAMS] == pytest.approx(50.0)
        assert by_food["Blueberries"][SERVINGS] == pytest.approx(0.5)
        assert by_food["Blueberries"][KCAL] == pytest.approx(28.5)

    def test_the_multiplier_scales_every_ingredient(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 2.5})
        (row,) = stocked.get("/api/logs/food").get_json()
        assert row[GRAMS] == pytest.approx(250.0)
        assert row[SERVINGS] == pytest.approx(5.0)

    def test_correcting_a_label_leaves_the_recipe_meaning_the_same_food(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 1})
        oats = {r["name"]: r["id"] for r in stocked.get("/api/catalog/food").get_json()}
        stocked.patch(f"/api/logs/food_items/{oats['Rolled Oats']}",
                      json={"col": "serving_size", "val": 25})

        (row,) = stocked.get("/api/logs/food").get_json()
        assert row[GRAMS] == pytest.approx(100.0), "the mass eaten is unchanged"
        assert row[KCAL] == pytest.approx(380.0), "and so are its calories"
        assert row[SERVINGS] == pytest.approx(4.0), "but a serving is smaller now"

    def test_a_plain_food_still_logs_as_one_row(self, stocked):
        r = stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Lunch",
            "food_name": "Rolled Oats", "servings": 1})
        assert r.get_json()["rows"] == 1
        (row,) = stocked.get("/api/logs/food").get_json()
        assert row[SET] is None

    def test_a_name_in_neither_is_refused(self, stocked):
        r = stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Lunch",
            "food_name": "Nonexistent", "servings": 1})
        assert r.status_code == 400
        assert "no meal set by that name" in r.get_json()["error"]

    def test_a_meal_set_cannot_be_logged_in_grams(self, stocked):
        blue_oatmeal(stocked)
        r = stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "grams": 200})
        assert r.status_code == 400
        assert "log it as a multiple" in r.get_json()["error"]

    def test_logging_an_empty_set_is_refused(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        (row,) = stocked.get("/api/catalog/sets/food").get_json()
        stocked.delete(f"/api/logs/food_set_components/{row[0]}")
        r = stocked.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 1})
        assert r.status_code == 400
        assert "no components yet" in r.get_json()["error"]


class TestASupplementStack:
    @pytest.fixture
    def stacked(self, member_a):
        member_a.post("/api/catalog/supplement",
                      json={"name": "B12", "b12_mcg": 500.0})
        member_a.post("/api/catalog/supplement",
                      json={"name": "Creatine", "creatine_g": 5.0})
        define(member_a, "supplement", "Morning", [
            {"item_name": "B12", "amount": 1},
            {"item_name": "Creatine", "amount": 2}])
        return member_a

    def test_logging_it_writes_one_row_per_supplement(self, stacked):
        r = stacked.post("/api/logs/supplement", json={
            "date": "2026-09-07", "supp_name": "morning", "servings": 1})
        assert r.status_code == 200, r.get_json()
        assert r.get_json() == {"status": "success", "rows": 2, "set": "Morning"}

        rows = stacked.get("/api/logs/supplement").get_json()
        by_name = {row[2]: row for row in rows}
        assert by_name["B12"][3] == "Morning"
        assert by_name["B12"][4] == pytest.approx(1.0)
        assert by_name["B12"][5] == pytest.approx(500.0)
        assert by_name["Creatine"][4] == pytest.approx(2.0)

    def test_the_multiplier_scales_the_whole_stack(self, stacked):
        stacked.post("/api/logs/supplement", json={
            "date": "2026-09-07", "supp_name": "Morning", "servings": 0.5})
        by_name = {row[2]: row for row in stacked.get("/api/logs/supplement").get_json()}
        assert by_name["B12"][4] == pytest.approx(0.5)
        assert by_name["Creatine"][4] == pytest.approx(1.0)

    def test_a_stack_may_share_a_name_with_another_domains_set(self, stacked):
        stacked.post("/api/catalog/beverage",
                     json={"name": "Water", "caffeine_mg": 0, "antioxidants_mg": 0})
        assert define(stacked, "beverage", "Morning",
                      [{"item_name": "Water", "amount": 1}]).status_code == 200

    def test_removing_a_supplement_the_stack_needs_is_refused(self, stacked):
        r = stacked.delete("/api/catalog/items/B12")
        assert r.status_code == 409
        assert "stack" in r.get_json()["error"]
        assert "Morning" in r.get_json()["error"]


class TestADrinkSet:
    @pytest.fixture
    def poured(self, member_a):
        member_a.post("/api/catalog/beverage",
                      json={"name": "Black Coffee", "caffeine_mg": 80.0,
                            "antioxidants_mg": 200.0})
        member_a.post("/api/catalog/beverage",
                      json={"name": "Water", "caffeine_mg": 0.0, "antioxidants_mg": 0.0})
        define(member_a, "beverage", "Wake Up", [
            {"item_name": "Black Coffee", "amount": 2},
            {"item_name": "Water", "amount": 1}])
        return member_a

    def test_every_drink_is_logged_at_the_one_time(self, poured):
        r = poured.post("/api/logs/beverage", json={
            "date": "2026-09-07", "time": "07:30", "bev_name": "Wake Up",
            "servings": 1})
        assert r.get_json()["rows"] == 2

        rows = poured.get("/api/logs/beverage").get_json()
        assert {row[2] for row in rows} == {"07:30"}
        assert {row[4] for row in rows} == {"Wake Up"}
        by_name = {row[3]: row for row in rows}
        assert by_name["Black Coffee"][7] == pytest.approx(160.0)


class TestARoutineSet:
    @pytest.fixture
    def stretched(self, member_a):
        member_a.post("/api/catalog/mobility", json={"name": "Hips", "mets": 3.0})
        member_a.post("/api/catalog/mobility", json={"name": "Spine", "mets": 2.5})
        define(member_a, "mobility", "Evening", [
            {"item_name": "Hips", "amount": 10},
            {"item_name": "Spine", "amount": 5}])
        return member_a

    def test_the_components_carry_their_own_minutes(self, stretched):
        stretched.post("/api/logs/mobility", json={
            "date": "2026-09-07", "mob_name": "Evening", "duration_mins": 1})
        by_name = {row[2]: row for row in stretched.get("/api/logs/mobility").get_json()}
        assert by_name["Hips"][4] == pytest.approx(10.0)
        assert by_name["Spine"][4] == pytest.approx(5.0)

    def test_the_leading_number_is_a_multiple_of_the_set(self, stretched):
        stretched.post("/api/logs/mobility", json={
            "date": "2026-09-07", "mob_name": "Evening", "duration_mins": 2})
        by_name = {row[2]: row for row in stretched.get("/api/logs/mobility").get_json()}
        assert by_name["Hips"][4] == pytest.approx(20.0)


class TestAWorkout:
    @pytest.fixture
    def programmed(self, member_a):
        for name, group, metric in (("Bench Press", "Chest", "Reps"),
                                    ("Plank", "Core", "Seconds")):
            member_a.post("/api/catalog/exercise", json={
                "name": name, "muscle_group": group, "movement_pattern": "Push",
                "secondary_muscles": "", "plane_of_motion": "", "joint_mechanics": "",
                "equipment_type": "", "unilateral_bilateral": "", "metric_type": metric})
        define(member_a, "exercise", "Push Day", [
            {"item_name": "Bench Press", "set1": 8, "set2": 8, "set3": 6,
             "weight_kg": 60, "rpe": 8},
            {"item_name": "Plank", "set1": 60, "weight_kg": 0, "rpe": 6}])
        return member_a

    def test_a_component_declares_the_whole_set_scheme(self, programmed):
        rows = programmed.get("/api/catalog/sets/exercise").get_json()
        by_name = {row[2]: row for row in rows}
        assert by_name["Bench Press"][3:] == [8.0, 8.0, 6.0, 0.0, 0.0, 60.0, 8.0]
        assert by_name["Plank"][3:] == [60.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0]

    def test_logging_it_records_each_movement_as_the_template_describes_it(
            self, programmed):
        r = programmed.post("/api/logs/exercise/workout",
                            json={"date": "2026-09-07", "name": "push day"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json() == {"status": "success", "rows": 2, "set": "Push Day"}

        by_name = {row[2]: row for row in programmed.get("/api/logs/exercise").get_json()}
        assert by_name["Bench Press"][3] == "Push Day"
        assert by_name["Bench Press"][4:11] == [8.0, 8.0, 6.0, 0.0, 0.0, 60.0, 8.0]

    def test_exlog_refuses_a_workout_name_rather_than_ignoring_the_numbers(
            self, programmed):
        r = programmed.post("/api/logs/exercise", json={
            "date": "2026-09-07", "ex_name": "Push Day", "weight_kg": 30,
            "rpe": 8, "set1": 8})
        assert r.status_code == 400
        assert ":wlog" in r.get_json()["error"]
        assert programmed.get("/api/logs/exercise").get_json() == []

    def test_an_unknown_workout_is_refused(self, programmed):
        r = programmed.post("/api/logs/exercise/workout",
                            json={"date": "2026-09-07", "name": "Leg Day"})
        assert r.status_code == 400
        assert "No workout" in r.get_json()["error"]


class TestRulesThatHoldForEverySet:
    def test_removing_a_food_a_set_uses_is_refused(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        r = stocked.delete("/api/catalog/items/Rolled Oats")
        assert r.status_code == 409
        assert "Blue Oatmeal" in r.get_json()["error"]
        assert len(stocked.get("/api/catalog/food").get_json()) == 2

    def test_the_store_refuses_it_too(self, stocked, server_db):
        import sqlite3

        blue_oatmeal(stocked, blueberries=None)
        conn = server_db.get_connection()
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute("DELETE FROM food_items WHERE name = 'Rolled Oats'")
        conn.close()

    def test_removing_the_set_itself_works_and_takes_its_components(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        r = stocked.delete("/api/catalog/items/Blue Oatmeal")
        assert r.status_code == 200, r.get_json()
        assert stocked.get("/api/catalog/sets/food").get_json() == []
        assert stocked.delete("/api/catalog/items/Rolled Oats").status_code == 200

    def test_a_set_with_no_components_still_shows(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        (row,) = stocked.get("/api/catalog/sets/food").get_json()
        assert stocked.delete(
            f"/api/logs/food_set_components/{row[0]}").status_code == 200
        assert stocked.get("/api/catalog/sets/food").get_json() == [
            [None, "Blue Oatmeal", None, None]]

    def test_a_components_amount_can_be_edited_in_place(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        (row,) = stocked.get("/api/catalog/sets/food").get_json()
        r = stocked.patch(f"/api/logs/food_set_components/{row[0]}",
                          json={"col": "amount", "val": "150"})
        assert r.status_code == 200, r.get_json()
        assert stocked.get("/api/catalog/sets/food").get_json()[0][3] == 150.0

    def test_a_workouts_movement_can_be_edited_in_place(self, member_a):
        member_a.post("/api/catalog/exercise", json={
            "name": "Bench Press", "muscle_group": "Chest", "movement_pattern": "Push",
            "secondary_muscles": "", "plane_of_motion": "", "joint_mechanics": "",
            "equipment_type": "", "unilateral_bilateral": "", "metric_type": "Reps"})
        define(member_a, "exercise", "Push Day", [
            {"item_name": "Bench Press", "set1": 8, "weight_kg": 60, "rpe": 8}])
        (row,) = member_a.get("/api/catalog/sets/exercise").get_json()

        assert member_a.patch(f"/api/logs/exercise_set_components/{row[0]}",
                              json={"col": "weight_kg", "val": 65}).status_code == 200
        assert member_a.get("/api/catalog/sets/exercise").get_json()[0][8] == 65.0

    def test_the_set_is_shared_between_members_and_the_logs_are_not(
            self, stocked, member_b):
        blue_oatmeal(stocked, blueberries=None)
        assert len(member_b.get("/api/catalog/sets/food").get_json()) == 1
        member_b.post("/api/logs/food", json={
            "date": "2026-09-07", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 1})

        assert len(member_b.get("/api/logs/food").get_json()) == 1
        assert stocked.get("/api/logs/food").get_json() == []

    def test_a_name_used_in_two_domains_names_both_at_once(self, stocked):
        blue_oatmeal(stocked, blueberries=None)
        stocked.post("/api/catalog/supplement",
                     json={"name": "Rolled Oats", "b12_mcg": 0.0})
        define(stocked, "supplement", "Odd Stack",
               [{"item_name": "Rolled Oats", "amount": 1}])

        error = stocked.delete("/api/catalog/items/Rolled Oats").get_json()["error"]

        assert "Blue Oatmeal" in error
        assert "Odd Stack" in error
        assert "meal set" in error and "stack" in error
