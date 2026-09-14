import logging
import math
import os
import datetime
import tomllib

from PyQt6.QtCore import Qt

from src.domain import formulas
from src.domain.clock import minutes_of_day, within_window

log = logging.getLogger(__name__)

PROFILE_PATH = os.path.expanduser("~/.config/traker/user_profile.toml")

DEFAULT_DAILY_ADJUSTMENT_KCAL = 200.0
DEFAULT_TICK_MARKERS = [-300, 0, 300]
DEFAULT_OVERFLOW_BUFFER = 500.0
DEFAULT_ACTIVITY_LEVEL = 1.55
DEFAULT_NEAT_TAX_PERCENT = 15.0
DEFAULT_SALT_G = 5.0
DEFAULT_PROTEIN_MULTIPLIER = 2.0
DEFAULT_WEIGHT_KG = 75.0

DEFAULT_FOCUS_MINS = 30
DEFAULT_BREAK_MINS = 30
DEFAULT_LONG_BREAK_MINS = 60
DEFAULT_LONG_BREAKS_PER_DAY = 2
DEFAULT_IDLE_PAUSE_SECS = 300
DEFAULT_STOP_HOLD_SECS = 10

DEFAULT_SUPPLEMENT_TARGETS = [
    {"key": "b12", "name": "B12 (mcg)", "target": 0.0},
    {"key": "iodine", "name": "Iodine (mcg)", "target": 0.0},
    {"key": "creatine", "name": "Creatine (g)", "target": 0.0},
    {"key": "d3", "name": "D3 (IU)", "target": 0.0},
    {"key": "k2", "name": "K2 (mcg)", "target": 0.0},
    {"key": "dha", "name": "DHA (mg)", "target": 0.0},
    {"key": "epa", "name": "EPA (mg)", "target": 0.0},
    {"key": "calcium", "name": "Calcium (mg)", "target": 0.0},
    {"key": "magnesium", "name": "Magnesium (mg)", "target": 0.0},
    {"key": "zinc", "name": "Zinc (mg)", "target": 0.0},
    {"key": "c", "name": "C (mg)", "target": 0.0},
    {"key": "l_theanine", "name": "L-Theanine (mg)", "target": 0.0},
]


def _supplement_targets_toml() -> str:
    """The [supplement_targets] tables, rendered from the list above."""
    return "\n".join(
        f'[supplement_targets.{entry["key"]}]\n'
        f'name = "{entry["name"]}"\n'
        f'target = {entry["target"]}\n'
        for entry in DEFAULT_SUPPLEMENT_TARGETS)

_document_cache = {}


def _profile_stamp(path):
    """Enough of the file's identity to notice an edit."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size, stat.st_ino)


def load_profile_document() -> dict:
    """The parsed profile document, re-read only when the file has changed."""
    path = PROFILE_PATH
    stamp = _profile_stamp(path)
    cached = _document_cache.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    data = {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        log.error("Could not read %s: %s", path, e)
    except tomllib.TOMLDecodeError as e:
        log.error("Failed to parse %s: %s", path, e)

    _document_cache[path] = (stamp, data)
    return data


def reload_profile() -> None:
    """Drop the cached document, so the next read parses the file again."""
    _document_cache.clear()


def _generate_default_profile():
    """Write a full default document, including every section the app reads."""
    from src.config import LOCAL_SERVER_URL, PALETTE

    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    default_toml = f"""# ==========================================
# TRAKER - USER CONFIGURATION
# ==========================================

# Where this client finds the household service, and the token it identifies
# itself with. The service mints that token and logs it the first time it starts
# with this member named; paste it in below. The environment variables
# TRAKER_SERVER_URL and TRAKER_API_TOKEN override what is written here; if this
# section is removed, the built-in localhost address is used and no token is sent.
[server]
url = "{LOCAL_SERVER_URL}"
token = ""

# Which tabs exist. The default is the everyday logging and the graphs that
# read it; everything else is written down as false rather than left out, and
# is one true away. A graph tab also needs the graphs extra, without which it
# is skipped and the rest of the app runs.
[windows]
food = true
beverages = true            # drinks, and today's caffeine as it will be at bedtime
exercise = true
mobility = true             # mobility and cardio
food_graphs = true          # Nutrient Graphs
exercise_graphs = true
caffeine_graph = true       # 30 days of that bedtime figure
pomodoro = false            # the Focus Timer
supplements = false
supplement_graphs = false
heatmap = false             # a calendar of training and mobility energy
plans = false               # training cycles
chores = false              # the household chore board

[biometrics]
weight_kg = 75.0
height_cm = 180.0
age = 30
gender = "M"

[goals]
# lose_weight | gain_weight | maintain_weight. The adjustment below is applied
# in the direction of this goal, so its own sign does not matter.
goal_type = "maintain_weight"
daily_adjustment_kcal = {DEFAULT_DAILY_ADJUSTMENT_KCAL:g}
tick_markers = {DEFAULT_TICK_MARKERS}
overflow_buffer = 500
protein_multiplier = 2.0
salt_g = 5.0
activity_level = 1.55
neat_tax_percent = 15.0

sleep_time = "23:00"
caffeine_half_life = 5.0
max_sleep_caffeine = 20.0

# The one focus/break split, used all day. There are no timer modes.
[timer]
focus_mins = {DEFAULT_FOCUS_MINS}
break_mins = {DEFAULT_BREAK_MINS}
# What a break queued with ":break long" runs for, and how many of those are
# available in a day. The rest of the day's breaks are break_mins.
long_break_mins = {DEFAULT_LONG_BREAK_MINS}
long_breaks_per_day = {DEFAULT_LONG_BREAKS_PER_DAY}
# Whether a break takes every screen: the overlays, the release hold and the
# keys that open an activity. Off is a countdown you can pause and skip.
strict = false
# After this many seconds with neither a key nor the mouse, the interval
# pauses itself and the time counts as rest overtime. Input carries it on from
# where it stopped, the break behind it with it. 0 disables the pause.
idle_pause_secs = {DEFAULT_IDLE_PAUSE_SECS}
# Seconds the play button or ESC MUST be held to stop a running interval. The
# time it buys is focus overtime, the same as any other pause.
stop_hold_secs = {DEFAULT_STOP_HOLD_SECS}

# Recurring household chores, defined on the Chores tab. This says whether a
# break shows what is due today and lets you tick it off with the letter beside
# it. Off, the break surface does not mention them.
[chores]
on_break = false

# Which virtual desktop and activity Traker's own window opens on. Empty, the
# default, writes nothing to the compositor's configuration.
#
# Both are named as the pager and the activity switcher name them --
# "Desktop 5", "Personal", case-insensitively -- and are resolved to ids on
# every launch, so renaming or rebuilding one leaves no stale id behind. A
# desktop may also be given as its position: desktop = 5. A name this session
# does not have costs that one dimension and a line in the log.
#
# The window cannot be dragged off, and KWin drops the rule when Traker closes.
# Launching Traker does not switch you to the desktop; the log says where the
# window went.
[window]
desktop = ""
activity = ""
# Which monitor, by the name kscreen-doctor -o gives -- e.g. "DP-1". The
# output is asked for by name rather than by index, because KDE's own "Screen"
# window rule indexes a list the compositor rebuilds every boot.
screen = ""

# Take the colour out of every screen between these hours. KWin's own filter
# does it, so it covers the whole compositor output: every application on every
# monitor. Plasma 6.6 or newer is REQUIRED -- an older KWin answers the same
# request with a red-green filter rather than refusing it.
#
# Off leaves the filter untouched: nothing is written and nothing is switched
# off for you.
#
# This is a schedule, not a hold. Nothing is enforced and nothing is undone
# when Traker closes. Setting enabled = false returns the colour within the
# minute while Traker runs; set while it is closed, the screens stay as they
# are until you untick the effect yourself.
[grayscale]
enabled = false
from = "20:00"
to = "06:00"
# How far towards grey: 0.05 to 1.0. Not 0 -- KWin reads that as all the way.
intensity = 1.0

# What a strict break costs to leave.
[strict_break]
# Seconds of audible warning before a strict break takes the screens; 0 is off.
warn_secs = 60
# Seconds the release key (Escape) must be held to abandon a strict break.
release_hold_secs = 10
# Seconds at the start of a break before an activity may be opened. The offers
# are listed throughout and say when they open, and the chores stay tickable.
# Proportional: a break twice as long waits twice as long. 0 opens them the
# moment the break lands.
away_secs = 300
# Ask KWin to keep the break on every virtual desktop and activity. Qt cannot
# say that on Wayland, so without this one shortcut steps around a break.
follow_across_desktops = true
# Sound the warning carries: a theme name, and a file that wins if it is set.
sound_name = "dialog-warning"
sound_file = ""
# What KWin calls Traker's windows. Empty means ask Qt.
app_id = ""
# Which output shows what a break plays or reads -- the name kscreen-doctor -o
# gives, e.g. "DP-1". Empty follows [window] screen; with neither set it is the
# primary screen as Qt reports it, which on Wayland is the first output the
# compositor announced and not KDE's own primary.
media_screen = ""
# Put the virtual desktop or activity back if it changes while a break holds.
# Off, the break only follows the member.
refuse_switch = true
# Force the break's walls onto every desktop and activity with a KWin window
# rule, written to kwinrulesrc for the length of the break and discarded by
# KWin when the wall closes. This is the only form of the request KWin applies
# rather than refusing in silence. Off leaves the walls where the compositor
# put them, which is one desktop each where the script is refused.
pin_with_rule = true

# What a break may open on the screen it took: a PDF is read, anything else is
# played. Only what is listed here is offered, and only on the key for it. The
# first entry is on Enter, the rest on 1-9 in the order they appear.
#
# While an activity shows, that screen shows it alone; the other screens go on
# showing the countdown, the chores and what is coming. SPACE pauses a video or
# turns a page, the arrows (and PgUp/PgDn) seek 30 s or turn pages, UP/DOWN are
# volume or scroll, and 0 puts the wall back.
#
# [[strict_break.activities]]
# name = "Reading"
# path = "~/Documents/reading.pdf"
#
# [[strict_break.activities]]
# name = "Something to watch"
# path = "~/Videos/rest/talk.mkv"

# Where the queue of paths added with ":rest <path>" is kept. It is a plain
# file, one path per line, m3u-shaped, so anything else may append to it.
# Empty means ~/.config/traker/rest-queue.m3u; the position within an entry is
# remembered beside it.
[strict_break.queue]
path = ""

[keybinds]
up = "k"
down = "j"
left = "h"
right = "l"
edit = "e"
command_mode = "i"
sheet_mode = "s"
filter = "/"
sort = "o"

# Which regime each part of the day belongs to. The names are yours; a time
# outside every block reports "Unscheduled". A [schedule.<weekday>] table,
# lower case, replaces this one for that day.
[schedule.default]
"09:00-13:00" = "Work"
"13:00-14:00" = "Break"
"14:00-18:00" = "Admin"
"18:00-22:00" = "Personal"

# One colour per regime name above, plus "Unscheduled". A name with no entry
# here falls back to the colour the view asks for.
[regime_colors]
"Work" = "{PALETTE['magenta']}"
"Break" = "{PALETTE['blue']}"
"Admin" = "{PALETTE['violet']}"
"Personal" = "{PALETTE['green']}"
"Unscheduled" = "{PALETTE['base01']}"

# A target per exercise, drawn on the Exercise graph beside what the ledger
# holds. The key is the exercise's catalog name in lower case, spaces or
# underscores. Both fields are required for a goal to be drawn.
#
# [exercise_goals.overhead_press]
# target_weight = 30.0
# target_reps = "10,10,12"
[exercise_goals]

{_supplement_targets_toml()}"""
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(default_toml)

LEGACY_WINDOW_KEYS = {
    "food": ("food_logs", "food_db"),
}


class UserProfile:
    """A read-only view of the profile document."""

    def __init__(self):
        if not os.path.exists(PROFILE_PATH):
            _generate_default_profile()
            log.info("Generated a default user profile at %s", PROFILE_PATH)

        self.data = load_profile_document()

    def reload(self) -> None:
        """Re-read the document from disk, discarding what was cached."""
        reload_profile()
        self.data = load_profile_document()

    def is_window_enabled(self, window_key: str, default: bool = True) -> bool:
        windows = self.data.get("windows", {})
        if window_key in windows:
            return bool(windows[window_key])

        superseded = LEGACY_WINDOW_KEYS.get(window_key, ())
        present = [windows[key] for key in superseded if key in windows]
        if present:
            return any(bool(value) for value in present)

        return bool(default)

    def get_metric(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)

    def number(self, section: str, key: str, default: float,
               low: float = None, high: float = None) -> float:
        """One hand-edited setting as a number, clamped, and never raising."""
        raw = self.get_metric(section, key, default)
        try:
            value = None if isinstance(raw, bool) else float(raw)
        except (TypeError, ValueError):
            value = None
        if value is None or not math.isfinite(value):
            log.warning("[%s] %s is not a number (%r); using %s.",
                        section, key, raw, default)
            value = float(default)
        if low is not None:
            value = max(low, value)
        if high is not None:
            value = min(high, value)
        return value

    def timer_split(self) -> dict:
        """The one split, and the long break that can be queued in place of one."""
        if "pomodoro_modes" in self.data and "timer" not in self.data:
            log.info("[pomodoro_modes] is no longer read: the timer is one "
                     "split now. Write a [timer] section to change it, and "
                     "[timer] strict = true for the enforced break.")

        return {
            "focus_mins": self._whole("focus_mins", DEFAULT_FOCUS_MINS),
            "break_mins": self._whole("break_mins", DEFAULT_BREAK_MINS),
            "long_break_mins": self._whole("long_break_mins",
                                           DEFAULT_LONG_BREAK_MINS),
            "long_breaks_per_day": int(self.number(
                "timer", "long_breaks_per_day", DEFAULT_LONG_BREAKS_PER_DAY,
                low=0)),
            "strict": bool(self.get_metric("timer", "strict", False)),
        }

    def _whole(self, key: str, default: int) -> int:
        """One of the timer's durations, in whole minutes and at least one."""
        return int(self.number("timer", key, default, low=1))

    def get_current_regime(self) -> str:
        """Which regime the schedule says is running now, or "Unscheduled"."""
        now = datetime.datetime.now()
        day_name = now.strftime("%A").lower()
        current = now.hour * 60 + now.minute

        schedule = self.data.get("schedule", {})
        day_schedule = schedule.get(day_name, schedule.get("default", {}))

        for time_range, regime_name in day_schedule.items():
            start, _, end = str(time_range).partition("-")
            start, end = minutes_of_day(start), minutes_of_day(end)
            if start is None or end is None:
                continue
            if within_window(current, start, end):
                return str(regime_name)
        return "Unscheduled"

    def get_regime_color(self, regime_name: str, default_hex: str) -> str:
        colors = self.data.get("regime_colors", {})
        return str(colors.get(regime_name, default_hex)).strip()

    def calculate_bmr(self) -> float:
        weight = self.weight_kg()
        height = float(self.get_metric("biometrics", "height_cm", 180.0))
        age = int(self.get_metric("biometrics", "age", 30))
        gender = str(self.get_metric("biometrics", "gender", "M")).strip().upper()
        if gender == "M":
            return (10 * weight) + (6.25 * height) - (5 * age) + 5
        return (10 * weight) + (6.25 * height) - (5 * age) - 161

    def calculate_tdee(self) -> float:
        bmr = self.calculate_bmr()
        activity = float(self.get_metric("goals", "activity_level", DEFAULT_ACTIVITY_LEVEL))
        return bmr * activity

    def weight_kg(self) -> float:
        return float(self.get_metric("biometrics", "weight_kg", DEFAULT_WEIGHT_KG))

    def daily_adjustment_kcal(self) -> float:
        """How far from maintenance this member is aiming, unsigned."""
        return float(self.get_metric("goals", "daily_adjustment_kcal",
                                     DEFAULT_DAILY_ADJUSTMENT_KCAL))

    def tick_markers(self) -> list:
        """The offsets from maintenance the calorie bar marks."""
        return self.get_metric("goals", "tick_markers", DEFAULT_TICK_MARKERS)

    def overflow_buffer(self) -> float:
        return float(self.get_metric("goals", "overflow_buffer", DEFAULT_OVERFLOW_BUFFER))

    def goal_type(self) -> str:
        """The declared goal, folded."""
        return formulas.normalise_goal(self.get_metric("goals", "goal_type", None))

    def calculate_target_calories(self) -> float:
        """Maintenance need, adjusted in the direction of the declared goal."""
        return formulas.energy_target(
            self.calculate_tdee(),
            self.daily_adjustment_kcal(),
            self.get_metric("goals", "goal_type", None),
        )

    def calculate_target_protein(self) -> float:
        legacy_static = self.get_metric("goals", "protein_g", None)
        if legacy_static is not None and self.get_metric("goals", "protein_multiplier", None) is None:
            return float(legacy_static)

        weight = self.weight_kg()
        multiplier = float(self.get_metric("goals", "protein_multiplier",
                                           DEFAULT_PROTEIN_MULTIPLIER))
        return weight * multiplier

    def get_supplement_targets(self) -> list:
        """One entry per tracked nutrient: key, name and target."""
        targets = self.data.get("supplement_targets", {})
        if not targets:
            return [dict(entry) for entry in DEFAULT_SUPPLEMENT_TARGETS]

        return [
            {
                "key": key,
                "name": conf.get("name", key),
                "target": float(conf.get("target", 0.0)),
            }
            for key, conf in targets.items()
        ]


def get_qt_key(key_str: str, default_key: Qt.Key) -> Qt.Key:
    val = str(key_str).strip().upper()
    if val in ["ESC", "ESCAPE"]:
        return Qt.Key.Key_Escape
    if val in ["ENTER", "RETURN"]:
        return Qt.Key.Key_Return
    if val == "TAB":
        return Qt.Key.Key_Tab
    try:
        return getattr(Qt.Key, f"Key_{val}")
    except AttributeError:
        return default_key
