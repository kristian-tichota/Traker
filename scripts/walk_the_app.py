#!/usr/bin/env python3

import datetime
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SANDBOX = Path(tempfile.mkdtemp(prefix="traker-walk-"))
(SANDBOX / "server.toml").write_text(
    '''[[members]]
username = "member-a"
token = "test-token-member-a"

[[members]]
username = "member-b"
token = "test-token-member-b"
''', encoding="utf-8")
os.environ["TRAKER_SERVER_CONFIG"] = str(SANDBOX / "server.toml")

import src.profile as profile                                    # noqa: E402
profile.PROFILE_PATH = str(SANDBOX / "user_profile.toml")

# The walk visits every tab, so it opts into the ones the default leaves off.
profile.UserProfile()
_profile_file = SANDBOX / "user_profile.toml"
_written = _profile_file.read_text(encoding="utf-8")
for _key in ("pomodoro", "supplements", "supplement_graphs", "heatmap",
             "plans", "chores"):
    _written = _written.replace(f"\n{_key} = false", f"\n{_key} = true")
_profile_file.write_text(_written.replace("on_break = false", "on_break = true"),
                         encoding="utf-8")
profile.reload_profile()
import server.config as server_config                            # noqa: E402
server_config.DB_PATH = str(SANDBOX / "walk.db")

import importlib                                                 # noqa: E402
import server.database                                           # noqa: E402
importlib.reload(server.database)
import server.db_session                                         # noqa: E402
importlib.reload(server.db_session)

from PyQt6.QtCore import Qt, QThreadPool                         # noqa: E402
from PyQt6.QtGui import QKeyEvent                                # noqa: E402
from PyQt6.QtWidgets import QApplication                         # noqa: E402
from werkzeug.serving import make_server                         # noqa: E402

from server.app import create_app                                # noqa: E402
from server.config import USER_TOKENS                            # noqa: E402
from src.config import STYLESHEET                                # noqa: E402
from src.database import DatabaseClient                          # noqa: E402
from src.domain import plans as plans_maths                      # noqa: E402
from src.domain.clock import as_displayed_date                   # noqa: E402
from src.gui.columns import setting_key                          # noqa: E402
from src.gui.components.vim_table_view import VimTableView       # noqa: E402
from src.gui.main_window import MainWindow                       # noqa: E402
from src.gui.views.food_views import FoodView                    # noqa: E402

FAILURES = []


def check(what, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {what}{'   ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(what)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> int:
    port = free_port()
    httpd = make_server("127.0.0.1", port, create_app(), threaded=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.3)

    app = QApplication([])
    app.setStyleSheet(STYLESHEET)
    db = DatabaseClient(base_url=f"http://127.0.0.1:{port}",
                        token=next(iter(USER_TOKENS)))
    window = MainWindow(db)
    window.show()

    def settle(ms=5000):
        QThreadPool.globalInstance().waitForDone(ms)
        for _ in range(6):
            app.processEvents()
            time.sleep(0.02)
            app.processEvents()

    def run(line):
        window.command_line.setText(line)
        window.execute_command()
        settle()
        return window.status_bar.text()

    def on_tab(key):
        window.tabs.setCurrentIndex(window.tab_indices[key])
        settle()

    print("== definitions ==")
    for line in (
        "define Rolled Oats;Grain;379;6.5;1.1;67.7;0.99;10.1;13.2;0.02;40",
        "define Blueberries;Fruit;57;0.3;0;14.5;10;2.4;0.7;0;100",
        "bevdefine Black Coffee;80;120",
        "exdefine Bench Press;Chest;Push;Triceps;Sagittal;Compound;Barbell;Bilateral;Reps",
        "suppdefine Creatine Mono;0;0;5;0;0;0;0;0;0;0;0;0",
        "mobdefine Hip Opener;2.5;evening routine",
    ):
        check(line.split(";")[0], "Fail" not in run(line))

    print("== named sets, one per domain ==")
    for line in (
        "mealset Blue Oatmeal;Rolled Oats 100; Blueberries 50",
        "bevset Morning;Black Coffee 2",
        "suppset Daily;Creatine Mono 1",
        "mobset Evening;Hip Opener 10",
        "exset Push Day;Bench Press 8,8,6 60 8",
    ):
        check(line.split(";")[0], "Fail" not in run(line))

    print("== logging ==")
    on_tab("food")
    for line in ("log 1 b Rolled Oats", "log 100g l Rolled Oats",
                 "log 2 d Blue Oatmeal", "quick 550 d Restaurant Pizza"):
        check(line, "Fail" not in run(line))
    on_tab("beverages")
    check("bevlog a drink set", "Fail" not in run("bevlog 1 08:30 Morning"))
    on_tab("exercise")
    check("wlog a workout", "Fail" not in run("wlog Push Day"))
    check("exlog refuses a workout's name", "Fail" in run("exlog 8,8 60 8 Push Day"))
    on_tab("supplements")
    check("supplog a stack", "Fail" not in run("supplog Daily"))
    on_tab("mobility")
    check("moblog a routine set", "Fail" not in run("moblog 1 Evening"))

    print("== what the store refuses ==")
    refusal = run("log 1e307 b Blue Oatmeal")
    check("a set expansion that would not be finite", "Fail" in refusal,
          refusal.strip()[:78])
    check("rm refuses an item a set needs", "Fail" in run("rm Rolled Oats"))

    print("== every tab draws ==")
    for key in window.tab_indices:
        on_tab(key)
        check(f"tab {key}", window.tabs.currentWidget().isVisible())

    print("== the mode readout ==")

    def press(target, key):
        """Through Qt's own dispatch, so the filters and the focus are real."""
        app.sendEvent(target, QKeyEvent(QKeyEvent.Type.KeyPress, key,
                                        Qt.KeyboardModifier.NoModifier))
        settle(500)

    for key in window.tab_indices:
        on_tab(key)
        check(f"the mode is still named on {key}",
              "NORMAL" in window.mode_label.text(),
              window.mode_label.text().strip()[:48])

    on_tab("food")
    press(window, window.key_sheet)
    check("the sheet key enters SHEET", window.current_mode == "SHEET",
          window.mode_label.text().strip()[:48])
    table = window.views["food"].findChildren(VimTableView)[0]
    press(table, Qt.Key.Key_Escape)
    check("Escape returns to NORMAL", window.current_mode == "NORMAL")
    check("and the window has the keyboard", window.focusWidget() is window,
          type(window.focusWidget()).__name__)
    press(window, Qt.Key.Key_0)
    check("so a tab key answers again", window.tabs.currentIndex() == 0)

    press(window, window.key_sheet)
    on_tab("heatmap")
    check("a mode does not outlive its tab", window.current_mode == "NORMAL",
          window.mode_label.text().strip()[:48])

    on_tab("food")
    window.status_bar.setText(" Something else entirely.")
    check("a message does not take the mode away",
          "NORMAL" in window.mode_label.text()
          and "Something else" in window.status_bar.text())

    print("== the food ledger, as a member reads it ==")
    on_tab("food")
    view = window.views["food"]
    model, headers = view.model_for(0), view.headers[0]
    shown = range(min(8, len(headers)))
    print("     " + " | ".join(headers[c][:11].rjust(11) for c in shown))
    for row in range(min(model.rowCount(), 10)):
        print("     " + " | ".join(model.display_text(row, c)[:11].rjust(11)
                                   for c in shown))
    check("the ledger has rows", model.rowCount() > 0, f"{model.rowCount()} rows")
    check("no cell reads 'None'",
          not any(model.display_text(r, c) == "None"
                  for r in range(model.rowCount()) for c in range(len(headers))))

    print("== filtering ==")
    window.open_filter()
    settle()
    window.filter_line.setText("oats")
    settle()
    narrowed = view.proxy_for(0).rowCount()
    check("a bare word narrows the ledger", 0 < narrowed < model.rowCount(),
          f"{narrowed} of {model.rowCount()}")
    window.filter_line.setText("kcal>100")
    settle()
    check("a comparison is evaluated", "Filter:" in window.status_bar.text(),
          window.status_bar.text().strip()[:60])
    window.close_filter()
    settle()

    print("== arranging the columns ==")
    on_tab("food")
    check("a column is switched off", "hidden" in run("cols hide Sugars"))
    check("the ledger stops showing it",
          "Sugars" not in view.column_layout(0).visible)
    check("a column is moved", "moved" in run("cols move 1 kcal"))
    check("the ledger shows it first",
          view.column_layout(0).visible[0] == "Calories")
    stored = db.get_setting(setting_key("food_logs"), "")
    check("the service kept the layout", "-Sugars" in stored, stored[:64])
    rebuilt = FoodView(db)
    rebuilt.load_column_layouts()
    settle()
    check("a tab built again is arranged the same way",
          rebuilt.column_layout(0).visible[0] == "Calories"
          and "Sugars" not in rebuilt.column_layout(0).visible)
    rebuilt.shutdown()
    check("and it can be put back", "declares" in run("cols reset"))

    print("== a training plan, over the same socket ==")
    today = datetime.date.today().isoformat()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    written, message = db.add_training_plan({
        "name": "Walkthrough Cycle", "start_date": yesterday, "weeks": 2,
        "sessions": [
            {"date": yesterday, "week": 1, "name": "Upper A", "block": "base",
             "movements": [{"exercise": "Bench Press", "sets": 3,
                            "target_low": 8, "target_high": 12,
                            "weight_kg": 40, "rpe": 8}]},
            {"date": today, "week": 1, "name": "Lower A", "block": "base",
             "movements": [{"exercise": "Bench Press", "sets": 2,
                            "target_low": 10, "target_high": 10,
                            "weight_kg": 30, "rpe": 7}]},
        ]})
    check("a cycle is defined in one call", written, str(message)[:60])

    on_tab("plans")
    plan_view = window.views["plans"]
    plan_view.refresh()
    settle()
    check("the tab reads the cycle back",
          plan_view.plan is not None and len(plan_view.sessions) == 2,
          f"{len(plan_view.sessions)} sessions")
    check("it opens on today's session", plan_view.selected_date == today,
          plan_view.selected_date)
    check("the day's movements are on screen",
          len(plan_view.model_for(0).rows) == 1)

    check("the session is logged from the plan",
          "Logged the session" in run(f"planlog {as_displayed_date(today)}"))
    settle()
    plan_view.refresh()
    settle()
    row = plan_view.model_for(0).rows[0]
    check("the ledger now answers the prescription",
          row.logged.startswith("10/10") and row.result == "hit",
          f"{row.logged!r} {row.result!r}")
    check("the calendar marks the day done",
          plans_maths.status(today, {r.date for r in plan_view.logs}) == plans_maths.DONE)

    on_tab("exercise")
    settle()
    check("and the Exercise tab shows the same rows",
          any(r.name == "Bench Press" and r.date == today
              for r in window.views["exercise"].model_for(0).rows))

    on_tab("plans")
    plan_view.refresh()
    settle()
    check("yesterday's untrained session reads as missed",
          plans_maths.status(yesterday, {r.date for r in plan_view.logs})
          == plans_maths.MISSED)
    check("moving the cursor needs no further read",
          (plan_view.on_day_selected(yesterday) or True)
          and len(plan_view.model_for(0).rows) == 1)

    print("== chores ==")
    four_days_ago = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    check("a chore is defined",
          "recurs every" in run(
              f"chorenew 7 {as_displayed_date(four_days_ago)} Vacuum the flat"))

    on_tab("chores")
    chore_view = window.views["chores"]
    chore_view.refresh()
    settle()
    board = chore_view.model_for(0).rows
    check("the board reads it back", len(board) == 1, f"{len(board)} rows")
    check("and says it is four days over",
          board[0].standing == "OVERDUE" and board[0].next_due == four_days_ago,
          f"{board[0].standing!r} {board[0].next_due!r}")

    check("ticking it is confirmed", "Ticked" in run("chore Vacuum the flat"))
    chore_view.refresh()
    settle()
    row = chore_view.model_for(0).rows[0]
    expected = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    check("the next one lands on the cadence, not a week from today",
          row.next_due == expected, f"{row.next_due!r} wanted {expected!r}")
    check("and the history says who did it",
          any(r.name == "Vacuum the flat" for r in chore_view.model_for(1).rows))

    check("a fortnightly chore is defined in weeks",
          "always a" in run("chorenew 2w Change the bed linen"))
    chore_view.refresh()
    settle()
    (linen,) = [r for r in chore_view.model_for(0).rows
                if r.name == "Change the bed linen"]
    today_day = datetime.date.today().strftime("%a")
    check("it is stored as days", linen.period_days == 14,
          f"{linen.period_days} days")
    check("and the board says which day it keeps",
          linen.lands_on == today_day, f"{linen.lands_on!r} wanted {today_day!r}")

    print("== shutdown ==")
    window.mark_all_tabs_stale()
    window.close()
    check("the window closed with a refresh in flight",
          QThreadPool.globalInstance().waitForDone(5000))

    httpd.shutdown()
    print()
    print("FAILURES:", ", ".join(FAILURES) if FAILURES else "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
