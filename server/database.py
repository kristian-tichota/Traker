import logging
import os
import sqlite3

from server.config import DB_PATH, USER_TOKENS
from server.sets import SET_DOMAINS, SET_SPECS

log = logging.getLogger(__name__)

CATALOG_TABLE_NAMES = tuple(spec.catalog_table for spec in SET_SPECS.values())

AD_HOC_CATEGORY = "Ad hoc"

SET_AWARE_LOG_TABLES = tuple(spec.log_table for spec in SET_SPECS.values())

FOOD_LOGS_DDL = """
    CREATE TABLE IF NOT EXISTS {table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        meal_type TEXT NOT NULL CHECK(meal_type IN ('Breakfast', 'Lunch', 'Dinner', 'Supplement')),
        food_item_id INTEGER,
        servings REAL CHECK(servings IS NULL OR servings > 0),
        grams REAL CHECK(grams IS NULL OR grams > 0),
        estimated INTEGER NOT NULL DEFAULT 0 CHECK(estimated IN (0, 1)),
        set_id INTEGER,
        CHECK ((servings IS NULL) <> (grams IS NULL)),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (food_item_id) REFERENCES food_items(id) ON DELETE SET NULL,
        FOREIGN KEY (set_id) REFERENCES item_sets(id) ON DELETE SET NULL
    );
"""


class ServerDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def init_db(self):
        conn = self.get_connection()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    api_token TEXT NOT NULL UNIQUE
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS food_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    category TEXT NOT NULL,
                    energy REAL NOT NULL CHECK(energy >= 0),
                    fat_total REAL NOT NULL CHECK(fat_total >= 0),
                    fat_saturated REAL NOT NULL CHECK(fat_saturated >= 0),
                    carbs_total REAL NOT NULL CHECK(carbs_total >= 0),
                    carbs_sugars REAL NOT NULL CHECK(carbs_sugars >= 0),
                    fibre REAL NOT NULL CHECK(fibre >= 0),
                    protein REAL NOT NULL CHECK(protein >= 0),
                    salt REAL NOT NULL CHECK(salt >= 0),
                    serving_size REAL NOT NULL CHECK(serving_size > 0)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS beverage_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    caffeine_mg REAL NOT NULL CHECK(caffeine_mg >= 0),
                    antioxidants_mg REAL NOT NULL CHECK(antioxidants_mg >= 0)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exercise_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    muscle_group TEXT NOT NULL,
                    movement_pattern TEXT NOT NULL,
                    secondary_muscles TEXT,
                    plane_of_motion TEXT,
                    joint_mechanics TEXT,
                    equipment_type TEXT,
                    unilateral_bilateral TEXT,
                    metric_type TEXT NOT NULL CHECK(metric_type IN ('Reps', 'Seconds'))
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supplement_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    b12_mcg REAL DEFAULT 0.0 CHECK(b12_mcg >= 0),
                    iodine_mcg REAL DEFAULT 0.0 CHECK(iodine_mcg >= 0),
                    creatine_g REAL DEFAULT 0.0 CHECK(creatine_g >= 0),
                    d3_iu REAL DEFAULT 0.0 CHECK(d3_iu >= 0),
                    k2_mcg REAL DEFAULT 0.0 CHECK(k2_mcg >= 0),
                    dha_mg REAL DEFAULT 0.0 CHECK(dha_mg >= 0),
                    epa_mg REAL DEFAULT 0.0 CHECK(epa_mg >= 0),
                    calcium_mg REAL DEFAULT 0.0 CHECK(calcium_mg >= 0),
                    magnesium_mg REAL DEFAULT 0.0 CHECK(magnesium_mg >= 0),
                    zinc_mg REAL DEFAULT 0.0 CHECK(zinc_mg >= 0),
                    c_mg REAL DEFAULT 0.0 CHECK(c_mg >= 0),
                    l_theanine_mg REAL DEFAULT 0.0 CHECK(l_theanine_mg >= 0)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mobility_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    mets REAL NOT NULL CHECK(mets > 0),
                    notes TEXT
                );
            """)

            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS item_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL CHECK(domain IN (
                        {', '.join(repr(d) for d in SET_DOMAINS)})),
                    name TEXT NOT NULL COLLATE NOCASE,
                    UNIQUE (domain, name)
                );
            """)

            for spec in SET_SPECS.values():
                if not spec.has_single_amount:
                    continue
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {spec.components_table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        set_id INTEGER NOT NULL,
                        {spec.item_column} INTEGER NOT NULL,
                        amount REAL NOT NULL CHECK(amount > 0),
                        FOREIGN KEY (set_id) REFERENCES item_sets(id) ON DELETE CASCADE,
                        FOREIGN KEY ({spec.item_column}) REFERENCES {spec.catalog_table}(id),
                        UNIQUE (set_id, {spec.item_column})
                    );
                """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS exercise_set_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    set_id INTEGER NOT NULL,
                    exercise_item_id INTEGER NOT NULL,
                    set1 REAL NOT NULL DEFAULT 0 CHECK(set1 >= 0),
                    set2 REAL NOT NULL DEFAULT 0 CHECK(set2 >= 0),
                    set3 REAL NOT NULL DEFAULT 0 CHECK(set3 >= 0),
                    set4 REAL NOT NULL DEFAULT 0 CHECK(set4 >= 0),
                    set5 REAL NOT NULL DEFAULT 0 CHECK(set5 >= 0),
                    weight_kg REAL NOT NULL CHECK(weight_kg >= 0),
                    rpe REAL NOT NULL CHECK(rpe BETWEEN 0 AND 10),
                    FOREIGN KEY (set_id) REFERENCES item_sets(id) ON DELETE CASCADE,
                    FOREIGN KEY (exercise_item_id) REFERENCES exercise_items(id),
                    UNIQUE (set_id, exercise_item_id)
                );
            """)

            conn.execute(FOOD_LOGS_DDL.format(table="food_logs"))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS beverage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    beverage_item_id INTEGER,
                    servings REAL NOT NULL CHECK(servings > 0),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (beverage_item_id) REFERENCES beverage_items(id) ON DELETE SET NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exercise_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    exercise_item_id INTEGER,
                    set1 REAL NOT NULL DEFAULT 0 CHECK(set1 >= 0),
                    set2 REAL NOT NULL DEFAULT 0 CHECK(set2 >= 0),
                    set3 REAL NOT NULL DEFAULT 0 CHECK(set3 >= 0),
                    set4 REAL NOT NULL DEFAULT 0 CHECK(set4 >= 0),
                    set5 REAL NOT NULL DEFAULT 0 CHECK(set5 >= 0),
                    weight_kg REAL NOT NULL CHECK(weight_kg >= 0),
                    rpe REAL NOT NULL CHECK(rpe BETWEEN 0 AND 10),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (exercise_item_id) REFERENCES exercise_items(id) ON DELETE SET NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supplement_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    supplement_item_id INTEGER,
                    servings REAL NOT NULL CHECK(servings > 0),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (supplement_item_id) REFERENCES supplement_items(id) ON DELETE SET NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mobility_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    mobility_item_id INTEGER,
                    duration_mins REAL NOT NULL CHECK(duration_mins > 0),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (mobility_item_id) REFERENCES mobility_items(id) ON DELETE SET NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pomodoro_heartbeats (
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    minute_of_day INTEGER NOT NULL CHECK(minute_of_day BETWEEN 0 AND 1439),
                    second INTEGER NOT NULL DEFAULT 0 CHECK(second BETWEEN 0 AND 59),
                    state TEXT NOT NULL CHECK(state IN ('focus', 'rest', 'focus_overtime', 'rest_overtime')),
                    mode TEXT NOT NULL DEFAULT 'Default',
                    PRIMARY KEY (user_id, date, minute_of_day, second),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pomodoro_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    amount_ms INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pomodoro_dsi_overrides (
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    override_dsi REAL NOT NULL CHECK(override_dsi >= 0),
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (user_id, key),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    start_date TEXT NOT NULL,
                    weeks INTEGER NOT NULL CHECK(weeks > 0),
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE (user_id, name)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    week INTEGER NOT NULL CHECK(week >= 1),
                    name TEXT NOT NULL,
                    block TEXT,
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES training_plans(id) ON DELETE CASCADE,
                    UNIQUE (plan_id, date)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0 CHECK(position >= 0),
                    exercise_item_id INTEGER,
                    sets INTEGER NOT NULL DEFAULT 3 CHECK(sets >= 0 AND sets <= 5),
                    target_low REAL NOT NULL DEFAULT 0 CHECK(target_low >= 0),
                    target_high REAL NOT NULL DEFAULT 0 CHECK(target_high >= 0),
                    weight_kg REAL NOT NULL DEFAULT 0 CHECK(weight_kg >= 0),
                    rpe REAL NOT NULL DEFAULT 0 CHECK(rpe BETWEEN 0 AND 10),
                    tempo TEXT,
                    grouping TEXT,
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES plan_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (exercise_item_id)
                        REFERENCES exercise_items(id) ON DELETE SET NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS chores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    period_days INTEGER NOT NULL CHECK(period_days >= 1),
                    anchor TEXT NOT NULL,
                    grace_days INTEGER CHECK(grace_days IS NULL OR grace_days >= 0),
                    notes TEXT,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS chore_completions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chore_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    done_by TEXT,
                    FOREIGN KEY (chore_id) REFERENCES chores(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chore_completions_chore
                ON chore_completions(chore_id, date);
            """)

            for table in CATALOG_TABLE_NAMES:
                self._ensure_folded_name_index(conn, table)

            self._adopt_generalised_sets(conn)
            self._ensure_food_log_amounts(conn)
            self._drop_superseded_meal_sets(conn)
            for table in SET_AWARE_LOG_TABLES:
                self._ensure_column(
                    conn, table, "set_id",
                    "INTEGER REFERENCES item_sets(id) ON DELETE SET NULL")

            self._seed_users(conn)
        conn.close()

    @staticmethod
    def _ensure_column(conn, table: str, column: str, declaration: str) -> None:
        """Add column to table if a pre-existing database lacks it."""
        held = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column in held:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        log.info("Added %s.%s to an existing database", table, column)

    @staticmethod
    def _tables_present(conn) -> set:
        return {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}

    @classmethod
    def _adopt_generalised_sets(cls, conn) -> None:
        """Move meal_sets into item_sets, ids preserved."""
        present = cls._tables_present(conn)
        if "meal_sets" not in present:
            return
        adopted = conn.execute(
            "INSERT OR IGNORE INTO item_sets (id, domain, name) "
            "SELECT id, 'food', name FROM meal_sets").rowcount
        if "meal_set_components" in present:
            conn.execute(
                "INSERT OR IGNORE INTO food_set_components "
                "(id, set_id, food_item_id, amount) "
                "SELECT id, meal_set_id, food_item_id, grams FROM meal_set_components")
        if adopted:
            log.info("Adopted %d meal set(s) into the generalised item_sets table",
                     adopted)

    @classmethod
    def _drop_superseded_meal_sets(cls, conn) -> None:
        """Remove the original set tables, once nothing references them."""
        present = cls._tables_present(conn)
        if "meal_sets" not in present:
            return
        held = {row["name"] for row in conn.execute("PRAGMA table_info(food_logs)")}
        if "meal_set_id" in held:
            log.warning("food_logs still references meal_sets; leaving the "
                        "superseded set tables in place")
            return
        conn.execute("DROP TABLE IF EXISTS meal_set_components")
        conn.execute("DROP TABLE IF EXISTS meal_sets")
        log.info("Dropped the superseded meal_sets tables")

    @staticmethod
    def _ensure_food_log_amounts(conn) -> None:
        """Give an existing food_logs its grams/estimated columns."""
        held = {row["name"] for row in conn.execute("PRAGMA table_info(food_logs)")}
        if "grams" in held:
            return
        legacy_set = "meal_set_id" if "meal_set_id" in held else "NULL"
        conn.execute("DROP TABLE IF EXISTS food_logs_migrated")
        conn.execute(FOOD_LOGS_DDL.format(table="food_logs_migrated"))
        conn.execute(f"""
            INSERT INTO food_logs_migrated
                (id, user_id, date, meal_type, food_item_id, servings, grams,
                 estimated, set_id)
            SELECT id, user_id, date, meal_type, food_item_id, servings, NULL,
                   0, {legacy_set}
            FROM food_logs
        """)
        conn.execute("DROP TABLE food_logs")
        conn.execute("ALTER TABLE food_logs_migrated RENAME TO food_logs")
        log.info("Rebuilt food_logs so an amount may be stored in grams")

    @staticmethod
    def _ensure_folded_name_index(conn, table: str) -> None:
        """Add the case-insensitive uniqueness index, or log the refusal."""
        try:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_name_nocase "
                f"ON {table}(name COLLATE NOCASE)"
            )
        except sqlite3.IntegrityError:
            colliding = [
                row["name"] for row in conn.execute(
                    f"SELECT name FROM {table} GROUP BY name COLLATE NOCASE "
                    f"HAVING COUNT(*) > 1"
                )
            ]
            log.error(
                "%s already holds names that differ only by case (%s); leaving it "
                "without the uniqueness index until one of each pair is renamed",
                table, ", ".join(colliding) or "unknown",
            )

    @staticmethod
    def _seed_users(conn) -> None:
        """Bring the users table in line with USER_TOKENS, id preserved."""
        for token, username in USER_TOKENS.items():
            by_name = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if by_name is not None:
                conn.execute(
                    "UPDATE users SET api_token = ? WHERE id = ?", (token, by_name["id"])
                )
                continue

            by_token = conn.execute(
                "SELECT id FROM users WHERE api_token = ?", (token,)
            ).fetchone()
            if by_token is not None:
                conn.execute(
                    "UPDATE users SET username = ? WHERE id = ?", (username, by_token["id"])
                )
                continue

            conn.execute(
                "INSERT INTO users (username, api_token) VALUES (?, ?)", (username, token)
            )

db_service = ServerDatabase()
