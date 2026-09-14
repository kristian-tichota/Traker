from PyQt6.QtWidgets import QHBoxLayout

from src.database.rows import grouped_by_set
from src.gui.views.base import BaseManagedView, lay_out_tables


class MobilityView(BaseManagedView):
    def __init__(self, db):
        h_logs = ["Date", "Routine Name", "Routine Set", "Duration (mins)", "METs"]
        h_items = ["Routine Name", "METs", "Notes"]
        h_sets = ["Routine Set", "Routine Name", "Minutes"]
        m_logs = {"Date": "date", "Routine Name": "mobility_item_id",
                  "Duration (mins)": "duration_mins"}
        m_items = {"Routine Name": "name", "METs": "mets", "Notes": "notes"}
        m_sets = {"Routine Name": "mobility_item_id", "Minutes": "amount"}
        super().__init__(db,
                         ["mobility_logs", "mobility_items",
                          "mobility_set_components"],
                         [h_logs, h_items, h_sets],
                         [m_logs, m_items, m_sets])

        v1, self.t_logs = self.build_table_layout(
            "Mobility & Flexibility Logs", h_logs, 0)
        v2, self.t_items = self.build_table_layout(
            "Mobility Routines Database", h_items, 1)
        v3, self.t_sets = self.build_table_layout("Routine Sets", h_sets, 2)
        lay_out_tables(QHBoxLayout(self), v1, v2, v3)

    def refresh(self):
        self.fetch_table(0, self._read_logs)
        self.fetch_table(1, self.db.get_all_mobility)
        self.fetch_table(2, lambda: self.db.get_sets("mobility"))

    def _read_logs(self):
        """The ledger, grouped so a logged routine set reads as one line."""
        return grouped_by_set(self.db.get_mobility_logs())
