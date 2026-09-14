from PyQt6.QtWidgets import QHBoxLayout

from src.database.rows import grouped_by_set
from src.gui.views.base import BaseManagedView, lay_out_tables

NUTRIENT_HEADERS = ["B12 (mcg)", "Iodine (mcg)", "Creatine (g)", "D3 (IU)",
                    "K2 (mcg)", "DHA (mg)", "EPA (mg)", "Calcium (mg)",
                    "Magnesium (mg)", "Zinc (mg)", "C (mg)", "L-Theanine (mg)"]

NUTRIENT_COLUMNS = {
    "B12 (mcg)": "b12_mcg", "Iodine (mcg)": "iodine_mcg",
    "Creatine (g)": "creatine_g", "D3 (IU)": "d3_iu", "K2 (mcg)": "k2_mcg",
    "DHA (mg)": "dha_mg", "EPA (mg)": "epa_mg", "Calcium (mg)": "calcium_mg",
    "Magnesium (mg)": "magnesium_mg", "Zinc (mg)": "zinc_mg", "C (mg)": "c_mg",
    "L-Theanine (mg)": "l_theanine_mg",
}


class SupplementsView(BaseManagedView):
    def __init__(self, db):
        h_logs = ["Date", "Supplement Name", "Stack", "Servings Eaten"] + NUTRIENT_HEADERS
        h_items = ["Supplement Name"] + NUTRIENT_HEADERS
        h_sets = ["Stack", "Supplement Name", "Servings"]
        m_logs = {"Date": "date", "Supplement Name": "supplement_item_id",
                  "Servings Eaten": "servings"}
        m_items = {"Supplement Name": "name", **NUTRIENT_COLUMNS}
        m_sets = {"Supplement Name": "supplement_item_id", "Servings": "amount"}
        super().__init__(db,
                         ["supplement_logs", "supplement_items",
                          "supplement_set_components"],
                         [h_logs, h_items, h_sets],
                         [m_logs, m_items, m_sets])

        v1, self.t_logs = self.build_table_layout("Supplement Log History", h_logs, 0)
        v2, self.t_items = self.build_table_layout(
            "Supplement Database Inventory", h_items, 1)
        v3, self.t_sets = self.build_table_layout("Stacks", h_sets, 2)
        lay_out_tables(QHBoxLayout(self), v1, v2, v3)

    def refresh(self):
        self.fetch_table(0, self._read_logs)
        self.fetch_table(1, self.db.get_all_supplements)
        self.fetch_table(2, lambda: self.db.get_sets("supplement"))

    def _read_logs(self):
        """Read the ledger, grouped so a logged stack reads as one line of doses."""
        return grouped_by_set(self.db.get_supplement_logs())
