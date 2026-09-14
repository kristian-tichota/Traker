from src.database.rows import DailyTotals
from src.domain import activity
from src.profile import (DEFAULT_ACTIVITY_LEVEL, DEFAULT_NEAT_TAX_PERCENT,
                         UserProfile)


def daily_totals(food_rows) -> dict:
    """Return each day's nutrient totals, keyed by date."""
    by_date = {}
    for row in food_rows:
        by_date.setdefault(row.date, []).append(row)
    return {date: DailyTotals.of(date, rows) for date, rows in by_date.items()}


class DBAnalyticsMixin:
    def get_daily_aggregates(self):
        """Return each day's nutrient totals, oldest first, as DailyTotals."""
        totals = daily_totals(self.get_food_logs())
        return [totals[date] for date in sorted(totals)]

    def get_exercise_history_by_name(self, exercise_name: str):
        """Return one point per logged session of this movement, oldest first."""
        timeline = []
        for row in self.get_exercise_logs():
            if not row.name or row.name.lower() != exercise_name.lower():
                continue
            timeline.append((row.date, row.volume, row.one_rep_max,
                             row.sets_display, row.weight_kg, row.rpe))
        timeline.sort(key=lambda point: point[0])
        return timeline

    def get_activity_heatmap_data(self, since: str = None):
        """Return MET-hours above the member's own baseline, per day."""
        profile = UserProfile()
        activity_level = float(profile.get_metric("goals", "activity_level", DEFAULT_ACTIVITY_LEVEL))
        neat_tax_percent = float(profile.get_metric("goals", "neat_tax_percent", DEFAULT_NEAT_TAX_PERCENT))
        tax_multiplier = activity.neat_tax_multiplier(neat_tax_percent)

        points = {}

        def breakdown_for(date):
            if date not in points:
                points[date] = {"breakdown": {}}
            return points[date]["breakdown"]

        for row in self.get_exercise_logs(since=since):
            entry = breakdown_for(row.date)

            if row.active_sets == 0:
                continue

            met_hours = activity.strength_met_hours(
                row.active_sets, row.muscle_group, row.rpe, activity_level, tax_multiplier
            )
            entry["Exercise_MET_hrs"] = entry.get("Exercise_MET_hrs", 0.0) + met_hours

        for row in self.get_mobility_logs(since=since):
            entry = breakdown_for(row.date)
            met_hours = activity.mobility_met_hours(
                float(row.duration_mins or 0.0), float(row.mets or 0.0),
                activity_level, tax_multiplier,
            )
            entry["Mobility"] = entry.get("Mobility", 0.0) + met_hours

        return points
