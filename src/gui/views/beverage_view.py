import datetime

from src.domain import formulas
from src.domain.clock import minutes_of_day
from src.domain.tables import BEVERAGE
from src.gui.components.calorie_bar import AnimatedProgressBar
from src.gui.views.base import CatalogueView
from src.profile import UserProfile


class BeveragesView(CatalogueView):
    DOMAIN = BEVERAGE
    TITLES = ("Beverage Logs Ledger", "Beverage Inventory Matrix", "Drink Sets")
    HEADERS = (["Date", "Time", "Beverage Name", "Drink Set", "Servings",
                "Antioxidants (mg)", "Caffeine (mg)", "Sleep Metric Delay"],
               ["Beverage Name", "Caffeine (mg)", "Antioxidants (mg)"],
               ["Drink Set", "Beverage Name", "Servings"])
    MAPPINGS = ({"Date": "date", "Time": "time", "Beverage Name": "beverage_item_id",
                 "Servings": "servings"},
                {"Beverage Name": "name", "Caffeine (mg)": "caffeine_mg",
                 "Antioxidants (mg)": "antioxidants_mg"},
                {"Beverage Name": "beverage_item_id", "Servings": "amount"})

    def __init__(self, db):
        super().__init__(db)
        self.caffeine_bar = AnimatedProgressBar("caffeine")
        self.layout().insertWidget(0, self.caffeine_bar)

    def read_ledger(self):
        return self.db.get_beverage_logs()

    def read_catalogue(self):
        return self.db.get_all_beverages()

    def read_day(self, rows):
        """Return the caffeine today's drinks will leave at bedtime."""
        today = datetime.date.today().isoformat()
        profile = UserProfile()
        sleep_mins = minutes_of_day(
            str(profile.get_metric("goals", "sleep_time", "23:00")).strip(), default=23 * 60)
        half_life = float(profile.get_metric("goals", "caffeine_half_life", 5.0))
        return sum(formulas.residual_at_bedtime(row.caffeine_mg or 0.0,
                                                minutes_of_day(row.time, default=0),
                                                sleep_mins, half_life)
                   for row in rows if row.date == today)

    def show_day(self, residual):
        self.caffeine_bar.reload_targets()
        self.caffeine_bar.set_value(residual)
