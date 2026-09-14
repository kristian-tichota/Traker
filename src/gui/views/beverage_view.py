#!/usr/bin/env python3

import datetime
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout
from src.database.rows import grouped_by_set
from src.domain import formulas
from src.domain.clock import minutes_of_day
from src.gui.views.base import BaseManagedView, lay_out_tables
from src.gui.components.calorie_bar import AnimatedProgressBar
from src.profile import UserProfile


class BeveragesView(BaseManagedView):
    def __init__(self, db):
        h_logs = ["Date", "Time", "Beverage Name", "Drink Set", "Servings", "Antioxidants (mg)", "Caffeine (mg)", "Sleep Metric Delay"]
        h_items = ["Beverage Name", "Caffeine (mg)", "Antioxidants (mg)"]
        h_sets = ["Drink Set", "Beverage Name", "Servings"]
        m_logs = {"Date": "date", "Time": "time", "Beverage Name": "beverage_item_id", "Servings": "servings"}
        m_items = {"Beverage Name": "name", "Caffeine (mg)": "caffeine_mg", "Antioxidants (mg)": "antioxidants_mg"}
        m_sets = {"Beverage Name": "beverage_item_id", "Servings": "amount"}
        super().__init__(db,
                         ["beverage_logs", "beverage_items", "beverage_set_components"],
                         [h_logs, h_items, h_sets],
                         [m_logs, m_items, m_sets])

        main_layout = QVBoxLayout(self)

        self.caffeine_bar = AnimatedProgressBar("caffeine")
        main_layout.addWidget(self.caffeine_bar)

        v1, self.t_logs = self.build_table_layout("Beverage Logs Ledger", h_logs, 0)
        v2, self.t_items = self.build_table_layout("Beverage Inventory Matrix", h_items, 1)
        v3, self.t_sets = self.build_table_layout("Drink Sets", h_sets, 2)
        main_layout.addLayout(lay_out_tables(QHBoxLayout(), v1, v2, v3))

    def refresh(self):
        self.fetch(self._read_logs, self._on_logs_fetched)
        self.fetch_table(1, self.db.get_all_beverages)
        self.fetch_table(2, lambda: self.db.get_sets("beverage"))

    def _read_logs(self):
        """The ledger, grouped so a logged drink set reads as one line."""
        rows = self.db.get_beverage_logs()
        return rows, grouped_by_set(rows)

    def _on_logs_fetched(self, result):
        data, grouped = result
        self.populate_table(self.t_logs, grouped, table_idx=0)

        today_str = datetime.date.today().isoformat()

        prof = UserProfile()
        sleep_str = str(prof.get_metric("goals", "sleep_time", "23:00")).strip()
        half_life = float(prof.get_metric("goals", "caffeine_half_life", 5.0))

        sleep_mins = minutes_of_day(sleep_str, default=23 * 60)

        total_residual = 0.0
        for row in data:
            if row.date != today_str:
                continue

            log_time_str = row.time
            caffeine_mg = row.caffeine_mg or 0.0

            log_mins = minutes_of_day(log_time_str, default=0)
            total_residual += formulas.residual_at_bedtime(
                caffeine_mg, log_mins, sleep_mins, half_life)
        self.caffeine_bar.reload_targets()
        self.caffeine_bar.set_value(total_residual)
