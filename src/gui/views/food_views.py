import datetime

from PyQt6.QtWidgets import QHBoxLayout, QLabel

from src.config import PALETTE
from src.database.analytics import daily_totals
from src.domain.tables import FOOD
from src.gui.components.calorie_bar import AnimatedProgressBar
from src.gui.views.base import CatalogueView


def estimated_line(totals) -> str:
    """Report how much of the day was estimated rather than read off a label."""
    if totals is None or not totals.estimated_rows:
        return ""
    rows = "row" if totals.estimated_rows == 1 else "rows"
    return (f"≈ {totals.estimated_kcal:,.0f} of {totals.energy_kcal:,.0f} kcal "
            f"estimated ({totals.estimated_share:.0%}) · "
            f"{totals.estimated_rows} {rows} with no macros")


class FoodView(CatalogueView):
    DOMAIN = FOOD
    TITLES = ("Food Log Ledger", "Food Item Database", "Meal Sets")
    HEADERS = (["Est", "Date", "Meal Type", "Food Name", "Servings", "Grams", "Meal Set",
                "Calories", "Protein", "Carbs", "Sugars", "Fats", "Sat Fat", "Salt", "Fibre"],
               ["Food Name", "Category", "Energy (kcal)", "Total Fat (g)", "Sat Fat (g)",
                "Total Carbs (g)", "Sugars (g)", "Fibre (g)", "Protein (g)", "Salt (g)",
                "Serving Size (g)"],
               ["Meal Set", "Food Name", "Grams"])
    MAPPINGS = ({"Date": "date", "Meal Type": "meal_type", "Food Name": "food_item_id",
                 "Servings": "servings", "Grams": "grams"},
                {"Food Name": "name", "Category": "category", "Energy (kcal)": "energy",
                 "Total Fat (g)": "fat_total", "Sat Fat (g)": "fat_saturated",
                 "Total Carbs (g)": "carbs_total", "Sugars (g)": "carbs_sugars",
                 "Fibre (g)": "fibre", "Protein (g)": "protein", "Salt (g)": "salt",
                 "Serving Size (g)": "serving_size"},
                {"Food Name": "food_item_id", "Grams": "amount"})

    def __init__(self, db):
        super().__init__(db)

        self.cal_bar = AnimatedProgressBar("calories")
        self.prot_bar = AnimatedProgressBar("protein")
        self.salt_bar = AnimatedProgressBar("salt")
        bars = QHBoxLayout()
        bars.setSpacing(10)
        for bar in (self.cal_bar, self.prot_bar, self.salt_bar):
            bars.addWidget(bar)

        self.estimate_note = QLabel("")
        self.estimate_note.setStyleSheet(
            f"color: {PALETTE['orange']}; padding: 1px 4px; font-style: italic;")
        self.estimate_note.hide()

        self.layout().insertLayout(0, bars)
        self.layout().insertWidget(1, self.estimate_note)

    def read_ledger(self):
        return self.db.get_food_logs()

    def read_catalogue(self):
        return self.db.get_all_foods()

    def read_day(self, rows):
        """Return today's totals and training burn."""
        today = datetime.date.today().isoformat()
        burn_by_date = self.db.get_daily_burn(since=today)
        return daily_totals(rows, burn_by_date).get(today), burn_by_date.get(today, 0.0)

    def show_day(self, day):
        today, burned = day
        for bar in (self.cal_bar, self.prot_bar, self.salt_bar):
            bar.reload_targets()

        self.cal_bar.set_burned_value(burned)
        self.cal_bar.set_value(today.energy_kcal if today else 0.0)
        self.prot_bar.set_value(today.protein_g if today else 0.0)
        self.salt_bar.set_value(today.salt_g if today else 0.0)

        note = estimated_line(today)
        self.estimate_note.setText(note)
        self.estimate_note.setVisible(bool(note))
