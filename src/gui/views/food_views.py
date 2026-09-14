import datetime
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from src.config import PALETTE
from src.database.analytics import daily_totals
from src.database.rows import grouped_by_set
from src.domain.activity import kcal_from_met_hours
from src.gui.views.base import BaseManagedView, lay_out_tables
from src.gui.components.calorie_bar import AnimatedProgressBar


def estimated_line(totals) -> str:
    """Report how much of the day was estimated rather than read off a label."""
    if totals is None or not totals.estimated_rows:
        return ""
    rows = "row" if totals.estimated_rows == 1 else "rows"
    return (f"\u2248 {totals.estimated_kcal:,.0f} of {totals.energy_kcal:,.0f} kcal "
            f"estimated ({totals.estimated_share:.0%}) \u00b7 "
            f"{totals.estimated_rows} {rows} with no macros")


class FoodView(BaseManagedView):
    def __init__(self, db):
        h_logs = ["Est", "Date", "Meal Type", "Food Name", "Servings", "Grams", "Meal Set", "Calories", "Protein", "Carbs", "Sugars", "Fats", "Sat Fat", "Salt", "Fibre"]
        h_items = ["Food Name", "Category", "Energy (kcal)", "Total Fat (g)", "Sat Fat (g)", "Total Carbs (g)", "Sugars (g)", "Fibre (g)", "Protein (g)", "Salt (g)", "Serving Size (g)"]
        h_sets = ["Meal Set", "Food Name", "Grams"]
        m_logs = {"Date": "date", "Meal Type": "meal_type", "Food Name": "food_item_id", "Servings": "servings", "Grams": "grams"}
        m_items = {"Food Name": "name", "Category": "category", "Energy (kcal)": "energy", "Total Fat (g)": "fat_total", "Sat Fat (g)": "fat_saturated", "Total Carbs (g)": "carbs_total", "Sugars (g)": "carbs_sugars", "Fibre (g)": "fibre", "Protein (g)": "protein", "Salt (g)": "salt", "Serving Size (g)": "serving_size"}
        m_sets = {"Food Name": "food_item_id", "Grams": "amount"}
        super().__init__(db,
                         ["food_logs", "food_items", "food_set_components"],
                         [h_logs, h_items, h_sets],
                         [m_logs, m_items, m_sets])

        main_layout = QVBoxLayout(self)

        bars_layout = QHBoxLayout()
        bars_layout.setSpacing(10)

        self.cal_bar = AnimatedProgressBar("calories")
        self.prot_bar = AnimatedProgressBar("protein")
        self.salt_bar = AnimatedProgressBar("salt")

        bars_layout.addWidget(self.cal_bar)
        bars_layout.addWidget(self.prot_bar)
        bars_layout.addWidget(self.salt_bar)

        main_layout.addLayout(bars_layout)

        self.estimate_note = QLabel("")
        self.estimate_note.setStyleSheet(
            f"color: {PALETTE['orange']}; padding: 1px 4px; font-style: italic;")
        self.estimate_note.hide()
        main_layout.addWidget(self.estimate_note)

        v1, self.table = self.build_table_layout("Food Log Ledger", h_logs, 0)
        v2, self.t_items = self.build_table_layout("Food Item Database", h_items, 1)
        v3, self.t_sets = self.build_table_layout("Meal Sets", h_sets, 2)
        main_layout.addLayout(lay_out_tables(QHBoxLayout(), v1, v2, v3))

    def refresh(self):
        def fetch_data():
            today = datetime.date.today().isoformat()
            rows = self.db.get_food_logs()
            return rows, grouped_by_set(rows), self.db.get_activity_heatmap_data(since=today)

        self.fetch(fetch_data, self._on_data_fetched)
        self.fetch_table(1, self.db.get_all_foods)
        self.fetch_table(2, lambda: self.db.get_sets("food"))

    def _on_data_fetched(self, result):
        data, grouped, heatmap_data = result
        self.populate_table(self.table, grouped, table_idx=0)

        today_str = datetime.date.today().isoformat()

        today = daily_totals(data).get(today_str)

        for bar in (self.cal_bar, self.prot_bar, self.salt_bar):
            bar.reload_targets()

        breakdown = heatmap_data.get(today_str, {}).get("breakdown", {})
        weight = float(self.cal_bar.profile.get_metric("biometrics", "weight_kg", 75.0))

        today_burned = kcal_from_met_hours(
            breakdown.get("Mobility", 0.0) + breakdown.get("Exercise_MET_hrs", 0.0), weight)

        self.cal_bar.set_burned_value(today_burned)
        self.cal_bar.set_value(today.energy_kcal if today else 0.0)
        self.prot_bar.set_value(today.protein_g if today else 0.0)
        self.salt_bar.set_value(today.salt_g if today else 0.0)

        note = estimated_line(today)
        self.estimate_note.setText(note)
        self.estimate_note.setVisible(bool(note))
