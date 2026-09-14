from PyQt6.QtWidgets import QHBoxLayout

from src.database.rows import ChoreBoardRow
from src.domain import chores
from src.gui.views.base import BaseManagedView

BOARD_STRETCH, HISTORY_STRETCH = 7, 3

BOARD_HEADERS = ["Chore", "Every (days)", "Grace (days)", "Anchor", "Lands On",
                 "Last Done", "Next Due", "Standing", "Done", "Active", "Notes"]
HISTORY_HEADERS = ["Date", "Chore", "By"]

BOARD_MAPPING = {"Chore": "name", "Every (days)": "period_days",
                 "Grace (days)": "grace_days", "Anchor": "anchor",
                 "Active": "active", "Notes": "notes"}

HISTORY_MAPPING = {"Date": "date"}

STANDING_WORDS = {
    chores.OVERDUE: "OVERDUE",
    chores.DUE: "TODAY",
    chores.EARLY: "OK NOW",
    chores.LATER: "",
}


class ChoreView(BaseManagedView):
    DATE_HEADERS = ("Date", "Anchor", "Last Done", "Next Due")

    def __init__(self, db):
        super().__init__(db, ["chores", "chore_completions"],
                         [BOARD_HEADERS, HISTORY_HEADERS],
                         [BOARD_MAPPING, HISTORY_MAPPING])

        board, self.t_board = self.build_table_layout(
            "Household Chores", BOARD_HEADERS, 0)
        history, self.t_history = self.build_table_layout(
            "Done", HISTORY_HEADERS, 1)

        layout = QHBoxLayout(self)
        layout.addLayout(board, BOARD_STRETCH)
        layout.addLayout(history, HISTORY_STRETCH)

    def refresh(self):
        self.fetch_table(0, self._read_board)
        self.fetch_table(1, self.db.get_chore_completions)

    def _read_board(self):
        """Read the board, through the one read and the one scheduling function."""
        return [ChoreBoardRow.of(entry, STANDING_WORDS)
                for entry in chores.board(self.db.get_chores())]
