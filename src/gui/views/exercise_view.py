from PyQt6.QtWidgets import QHBoxLayout

from src.database.rows import grouped_by_set
from src.gui.views.base import BaseManagedView, lay_out_tables

SET_HEADERS = ["Set 1", "Set 2", "Set 3", "Set 4", "Set 5"]
SET_COLUMNS = {header: f"set{n}" for n, header in enumerate(SET_HEADERS, start=1)}

LOG_HEADERS = (["Date", "Exercise", "Workout"] + SET_HEADERS
               + ["Weight (kg)", "Perceived Effort", "Muscle Group",
                  "Total Reps", "Max Reps", "Total Volume", "1RM"])
LOG_COLUMNS = {"Date": "date", "Exercise": "exercise_item_id", **SET_COLUMNS,
               "Weight (kg)": "weight_kg", "Perceived Effort": "rpe"}

ITEM_HEADERS = ["Exercise", "Muscle Group", "Movement Pattern",
                "Secondary Muscles", "Plane of Motion", "Joint Mechanics",
                "Equipment Type", "Unilateral/Bilateral", "Metric Type"]
ITEM_COLUMNS = {"Exercise": "name", "Muscle Group": "muscle_group",
                "Movement Pattern": "movement_pattern",
                "Secondary Muscles": "secondary_muscles",
                "Plane of Motion": "plane_of_motion",
                "Joint Mechanics": "joint_mechanics",
                "Equipment Type": "equipment_type",
                "Unilateral/Bilateral": "unilateral_bilateral",
                "Metric Type": "metric_type"}

COMPONENT_HEADERS = (["Workout", "Exercise"] + SET_HEADERS
                     + ["Weight (kg)", "Perceived Effort"])
COMPONENT_COLUMNS = {"Exercise": "exercise_item_id", **SET_COLUMNS,
                     "Weight (kg)": "weight_kg", "Perceived Effort": "rpe"}


class ExerciseView(BaseManagedView):
    def __init__(self, db):
        h_logs, h_items, h_sets = LOG_HEADERS, ITEM_HEADERS, COMPONENT_HEADERS
        super().__init__(db,
                         ["exercise_logs", "exercise_items",
                          "exercise_set_components"],
                         [h_logs, h_items, h_sets],
                         [LOG_COLUMNS, ITEM_COLUMNS, COMPONENT_COLUMNS])

        v1, self.t_logs = self.build_table_layout(
            "Training Set Tracking Logs Ledger", h_logs, 0)
        v2, self.t_items = self.build_table_layout(
            "Structural Kinesiology Matrix", h_items, 1)
        v3, self.t_sets = self.build_table_layout("Workouts", h_sets, 2)
        lay_out_tables(QHBoxLayout(self), v1, v2, v3)

    def refresh(self):
        self.fetch_table(0, self._read_logs)
        self.fetch_table(1, self.db.get_all_exercises)
        self.fetch_table(2, lambda: self.db.get_sets("exercise"))

    def _read_logs(self):
        """Read the ledger, grouped so a workout reads as one line of volume."""
        return grouped_by_set(self.db.get_exercise_logs())
