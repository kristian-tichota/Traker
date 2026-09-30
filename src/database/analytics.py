from src.database.rows import DailyTotals
from src.domain import activity
from src.profile import (DEFAULT_ACTIVITY_LEVEL, DEFAULT_NEAT_TAX_PERCENT,
                         UserProfile)


def daily_totals(food_rows, burn_by_date=None) -> dict:
    """Return each day's nutrient totals, keyed by date."""
    burnt = burn_by_date or {}
    by_date = {}
    for row in food_rows:
        by_date.setdefault(row.date, []).append(row)
    return {date: DailyTotals.of(date, rows, burnt.get(date, 0.0))
            for date, rows in by_date.items()}


class DBAnalyticsMixin:
    def get_daily_aggregates(self):
        """Return each day's nutrient totals, oldest first, as DailyTotals."""
        totals = daily_totals(self.get_food_logs(), self.get_daily_burn())
        return [totals[date] for date in sorted(totals)]

    def get_daily_burn(self, since: str = None) -> dict:
        """Return each day's estimated training burn in calories, keyed by date."""
        weight = UserProfile().weight_kg()
        return {date: activity.burn_kcal(point["breakdown"], weight)
                for date, point in self.get_activity_heatmap_data(since).items()}

    def get_activity_heatmap_data(self, since: str = None):
        """Return MET-hours above the member's own baseline, per day."""
        profile = UserProfile()
        activity_level = float(profile.get_metric("goals", "activity_level", DEFAULT_ACTIVITY_LEVEL))
        neat_tax_percent = float(profile.get_metric("goals", "neat_tax_percent", DEFAULT_NEAT_TAX_PERCENT))
        tax_multiplier = activity.neat_tax_multiplier(neat_tax_percent)

        points = {}
        for row in self.get_exercise_logs(since=since):
            entry = points.setdefault(row.date, {"breakdown": {}})["breakdown"]
            worked = row.active_sets
            if worked:
                entry["Exercise_MET_hrs"] = entry.get("Exercise_MET_hrs", 0.0) + activity.strength_met_hours(
                    worked, row.muscle_group, row.rpe, activity_level, tax_multiplier)
        for row in self.get_mobility_logs(since=since):
            entry = points.setdefault(row.date, {"breakdown": {}})["breakdown"]
            entry["Mobility"] = entry.get("Mobility", 0.0) + activity.mobility_met_hours(
                float(row.duration_mins or 0.0), float(row.mets or 0.0),
                activity_level, tax_multiplier)
        return points
