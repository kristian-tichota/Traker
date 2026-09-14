#!/usr/bin/env python3

import argparse
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import CONFIG_PATH  # noqa: E402
from server.database import ServerDatabase  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(BASE_DIR, "data", "dev_seed.db")

DAILY_RATES = {
    "food": 12.5,
    "supplement": 4.0,
    "exercise": 1.0,
    "beverage": 0.8,
    "mobility": 0.4,
}

CATALOG_SIZES = {
    "food": 106, "beverage": 6, "exercise": 18, "supplement": 13, "mobility": 4,
}

MEAL_SET_COUNT = 8
MEAL_SET_SIZE = (2, 6)

MEAL_SET_SHARE = 0.35

GRAMS_SHARE = 0.4

ESTIMATE_SHARE = 0.08

MEAL_TYPES = ("Breakfast", "Lunch", "Dinner", "Supplement")
MUSCLE_GROUPS = ("Chest", "Back", "Legs", "Calves", "Shoulders", "Arms", "Core")
MOVEMENTS = ("Push", "Pull", "Squat", "Hinge", "Carry", "Rotation")
STATES = ("focus", "rest", "focus_overtime", "rest_overtime")

FOOD_STEMS = ("Oats", "Rýže", "Kuřecí prsa", "Losos", "Vejce", "Tvaroh", "Banán",
              "Jablko", "Brambory", "Čočka", "Mandle", "Olivový olej", "Špenát",
              "Řízek", "Jogurt", "Chléb", "Tuňák", "Cizrna", "Máslo", "Sýr")
FOOD_QUALIFIERS = ("", " (raw)", " (cooked)", " 100 g", " bio", " light",
                   " full-fat", " grilled")


def _spread(rng, per_day, days):
    """Return how many rows land on each day, jittered around the rate."""
    for offset in range(days):
        count = int(per_day) + (1 if rng.random() < (per_day % 1) else 0)
        count = max(0, int(round(count * rng.uniform(0.4, 1.6))))
        yield offset, count


def _catalog_names(stems, qualifiers, wanted):
    """Build distinct names, which every catalog folds COLLATE NOCASE UNIQUE."""
    names, index = [], 0
    while len(names) < wanted:
        stem = stems[index % len(stems)]
        qualifier = qualifiers[(index // len(stems)) % len(qualifiers)]
        suffix = "" if index < len(stems) * len(qualifiers) else f" #{index}"
        names.append(f"{stem}{qualifier}{suffix}")
        index += 1
    return names[:wanted]


def seed(target_path, scale, days, seed_value, quiet=False):
    rng = random.Random(seed_value)
    if os.path.exists(target_path):
        os.remove(target_path)
        for suffix in ("-wal", "-shm"):
            stale = target_path + suffix
            if os.path.exists(stale):
                os.remove(stale)

    database = ServerDatabase(target_path)
    conn = database.get_connection()
    user_ids = [row["id"] for row in conn.execute("SELECT id FROM users ORDER BY id")]
    if not user_ids:
        print(f"[-] No users seeded; name a member under [[members]] in {CONFIG_PATH}")
        sys.exit(1)
    owner = user_ids[0]

    last_day = date.today()
    first_day = last_day - timedelta(days=days - 1)
    counts = {}

    with conn:
        foods = _catalog_names(FOOD_STEMS, FOOD_QUALIFIERS, CATALOG_SIZES["food"])
        conn.executemany(
            "INSERT INTO food_items (name, category, energy, fat_total, fat_saturated,"
            " carbs_total, carbs_sugars, fibre, protein, salt, serving_size)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(name, rng.choice(("Protein", "Carb", "Fat", "Veg", "Dairy")),
              round(rng.uniform(20, 600), 1), round(rng.uniform(0, 40), 1),
              round(rng.uniform(0, 15), 1), round(rng.uniform(0, 70), 1),
              round(rng.uniform(0, 30), 1), round(rng.uniform(0, 12), 1),
              round(rng.uniform(0, 35), 1), round(rng.uniform(0, 3), 2),
              round(rng.choice((100.0, 30.0, 250.0, 50.0)), 1)) for name in foods])

        beverages = _catalog_names(("Espresso", "Black tea", "Green tea", "Cola",
                                    "Matcha", "Yerba maté"), ("",), CATALOG_SIZES["beverage"])
        conn.executemany(
            "INSERT INTO beverage_items (name, caffeine_mg, antioxidants_mg) VALUES (?,?,?)",
            [(name, round(rng.uniform(0, 120), 1), round(rng.uniform(0, 300), 1))
             for name in beverages])

        exercises = _catalog_names(
            ("Bench press", "Deadlift", "Back squat", "Pull-up", "Overhead press",
             "Row", "Calf raise", "Plank", "Curl"), ("", " (dumbbell)"),
            CATALOG_SIZES["exercise"])
        conn.executemany(
            "INSERT INTO exercise_items (name, muscle_group, movement_pattern,"
            " secondary_muscles, plane_of_motion, joint_mechanics, equipment_type,"
            " unilateral_bilateral, metric_type) VALUES (?,?,?,?,?,?,?,?,?)",
            [(name, rng.choice(MUSCLE_GROUPS), rng.choice(MOVEMENTS), "", "Sagittal",
              rng.choice(("Compound", "Isolation")), rng.choice(("Barbell", "Bodyweight")),
              rng.choice(("Bilateral", "Unilateral")),
              "Seconds" if "Plank" in name else "Reps") for name in exercises])

        supplements = _catalog_names(
            ("B12", "Iodine", "Creatine", "D3", "K2", "Omega-3", "Calcium",
             "Magnesium", "Zinc", "Vitamin C", "L-theanine", "Multivitamin", "Iron"),
            ("",), CATALOG_SIZES["supplement"])
        nutrient_columns = ("b12_mcg", "iodine_mcg", "creatine_g", "d3_iu", "k2_mcg",
                            "dha_mg", "epa_mg", "calcium_mg", "magnesium_mg", "zinc_mg",
                            "c_mg", "l_theanine_mg")
        for position, name in enumerate(supplements):
            carried = {nutrient_columns[position % len(nutrient_columns)]:
                       round(rng.uniform(5, 500), 1)}
            columns = ", ".join(carried)
            conn.execute(
                f"INSERT INTO supplement_items (name, {columns}) VALUES (?, ?)",
                (name, *carried.values()))

        mobilities = _catalog_names(("Walking", "Cycling", "Stretching", "Yoga"),
                                    ("",), CATALOG_SIZES["mobility"])
        conn.executemany(
            "INSERT INTO mobility_items (name, mets, notes) VALUES (?,?,?)",
            [(name, round(rng.uniform(1.5, 8.0), 1), "") for name in mobilities])

        item_ids = {domain: [row["id"] for row in conn.execute(f"SELECT id FROM {domain}_items")]
                    for domain in ("food", "beverage", "exercise", "supplement", "mobility")}

        recipes = {}
        for number in range(1, MEAL_SET_COUNT + 1):
            name = f"Meal Set {number}"
            cursor = conn.execute(
                "INSERT INTO item_sets (domain, name) VALUES ('food', ?)", (name,))
            foods = rng.sample(item_ids["food"], rng.randint(*MEAL_SET_SIZE))
            recipe = [(food_id, round(rng.uniform(10, 250), 1)) for food_id in foods]
            conn.executemany(
                "INSERT INTO food_set_components (set_id, food_item_id, amount)"
                " VALUES (?,?,?)",
                [(cursor.lastrowid, food_id, grams) for food_id, grams in recipe])
            recipes[cursor.lastrowid] = recipe
        counts["item_sets"] = len(recipes)
        counts["food_set_components"] = sum(len(r) for r in recipes.values())

        def day_of(offset):
            return (first_day + timedelta(days=offset)).isoformat()

        def member(rng):
            return owner if rng.random() < 0.8 else rng.choice(user_ids)

        food_rows = []
        for offset, count in _spread(rng, DAILY_RATES["food"] * scale, days):
            written = 0
            while written < count:
                who, when = member(rng), day_of(offset)
                meal = rng.choice(MEAL_TYPES)
                if recipes and rng.random() < MEAL_SET_SHARE:
                    set_id = rng.choice(list(recipes))
                    multiplier = round(rng.uniform(0.5, 2.0), 2)
                    for food_id, grams in recipes[set_id]:
                        food_rows.append((who, when, meal, food_id, None,
                                          round(grams * multiplier, 1), 0, set_id))
                    written += len(recipes[set_id])
                else:
                    in_grams = rng.random() < GRAMS_SHARE
                    food_rows.append((
                        who, when, meal, rng.choice(item_ids["food"]),
                        None if in_grams else round(rng.uniform(0.25, 3.0), 2),
                        round(rng.uniform(20, 400), 1) if in_grams else None,
                        1 if rng.random() < ESTIMATE_SHARE else 0, None))
                    written += 1
        conn.executemany("INSERT INTO food_logs (user_id, date, meal_type, food_item_id,"
                         " servings, grams, estimated, set_id) VALUES (?,?,?,?,?,?,?,?)",
                         food_rows)
        counts["food_logs"] = len(food_rows)

        bev_rows = []
        for offset, count in _spread(rng, DAILY_RATES["beverage"] * scale, days):
            for _ in range(count):
                bev_rows.append((member(rng), day_of(offset),
                                 f"{rng.randrange(6, 22):02d}:{rng.randrange(0, 60):02d}",
                                 rng.choice(item_ids["beverage"]), round(rng.uniform(0.5, 2.0), 2)))
        conn.executemany("INSERT INTO beverage_logs (user_id, date, time, beverage_item_id,"
                         " servings) VALUES (?,?,?,?,?)", bev_rows)
        counts["beverage_logs"] = len(bev_rows)

        ex_rows = []
        for offset, count in _spread(rng, DAILY_RATES["exercise"] * scale, days):
            for _ in range(count):
                sets = [float(rng.randrange(0, 15)) for _ in range(5)]
                ex_rows.append((member(rng), day_of(offset), rng.choice(item_ids["exercise"]),
                                *sets, round(rng.uniform(0, 140), 1), round(rng.uniform(5, 10), 1)))
        conn.executemany("INSERT INTO exercise_logs (user_id, date, exercise_item_id, set1,"
                         " set2, set3, set4, set5, weight_kg, rpe)"
                         " VALUES (?,?,?,?,?,?,?,?,?,?)", ex_rows)
        counts["exercise_logs"] = len(ex_rows)

        sup_rows = []
        for offset, count in _spread(rng, DAILY_RATES["supplement"] * scale, days):
            for _ in range(count):
                sup_rows.append((member(rng), day_of(offset), rng.choice(item_ids["supplement"]),
                                 round(rng.uniform(0.5, 2.0), 2)))
        conn.executemany("INSERT INTO supplement_logs (user_id, date, supplement_item_id,"
                         " servings) VALUES (?,?,?,?)", sup_rows)
        counts["supplement_logs"] = len(sup_rows)

        mob_rows = []
        for offset, count in _spread(rng, DAILY_RATES["mobility"] * scale, days):
            for _ in range(count):
                mob_rows.append((member(rng), day_of(offset), rng.choice(item_ids["mobility"]),
                                 round(rng.uniform(5, 90), 1)))
        conn.executemany("INSERT INTO mobility_logs (user_id, date, mobility_item_id,"
                         " duration_mins) VALUES (?,?,?,?)", mob_rows)
        counts["mobility_logs"] = len(mob_rows)

        beats, events = [], []
        for offset in range(days):
            day = day_of(offset)
            if rng.random() < 0.15:
                continue
            start = rng.randrange(8 * 60, 11 * 60)
            worked = int(rng.uniform(90, 380) * scale)
            for minute in range(start, min(start + worked, 1440)):
                beats.append((owner, day, minute, 0,
                              STATES[0] if (minute - start) % 60 < 30 else STATES[1]))
            for _ in range(rng.randrange(2, 9)):
                events.append((owner, f"{day}T{rng.randrange(8, 20):02d}:"
                                      f"{rng.randrange(0, 60):02d}:00",
                               rng.choice(("long_break_started", "skip", "pause",
                                           "overridden_break")),
                               rng.randrange(0, 900000)))
        conn.executemany("INSERT INTO pomodoro_heartbeats (user_id, date, minute_of_day,"
                         " second, state) VALUES (?,?,?,?,?)", beats)
        conn.executemany("INSERT INTO pomodoro_events (user_id, timestamp, event_type,"
                         " amount_ms) VALUES (?,?,?,?)", events)
        counts["pomodoro_heartbeats"] = len(beats)
        counts["pomodoro_events"] = len(events)

    conn.close()

    if not quiet:
        print(f"[+] Seeded {target_path}")
        print(f"    {days} days ({first_day} to {last_day}), scale {scale}x, seed {seed_value}")
        for table, count in sorted(counts.items()):
            print(f"    {table:<24} {count:>7,}")
        size_mb = os.path.getsize(target_path) / (1024 * 1024)
        print(f"    {'on disk':<24} {size_mb:>7.1f} MB")
    return counts


def main():
    parser = argparse.ArgumentParser(description="Build a server-shaped database at realistic scale, for the perf benchmarks.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="database to write (overwritten)")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="multiplier on the household's per-day logging rate")
    parser.add_argument("--days", type=int, default=250, help="days of history")
    parser.add_argument("--seed", type=int, default=20260906,
                        help="RNG seed; the same seed gives the same database")
    args = parser.parse_args()
    if args.days < 1 or args.scale <= 0:
        print("[-] --days must be >= 1 and --scale > 0")
        sys.exit(1)
    seed(args.out, args.scale, args.days, args.seed)


if __name__ == "__main__":
    main()
