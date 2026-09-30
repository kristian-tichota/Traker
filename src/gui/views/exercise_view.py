from src.domain.tables import EXERCISE
from src.gui.views.base import CatalogueView

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


class ExerciseView(CatalogueView):
    DOMAIN = EXERCISE
    TITLES = ("Training Set Tracking Logs Ledger", "Structural Kinesiology Matrix", "Workouts")
    HEADERS = (LOG_HEADERS, ITEM_HEADERS, COMPONENT_HEADERS)
    MAPPINGS = (LOG_COLUMNS, ITEM_COLUMNS, COMPONENT_COLUMNS)

    def read_ledger(self):
        return self.db.get_exercise_logs()

    def read_catalogue(self):
        return self.db.get_all_exercises()
