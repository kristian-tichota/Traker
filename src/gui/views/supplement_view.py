from src.domain.tables import SUPPLEMENT
from src.gui.views.base import CatalogueView

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


class SupplementsView(CatalogueView):
    DOMAIN = SUPPLEMENT
    TITLES = ("Supplement Log History", "Supplement Database Inventory", "Stacks")
    HEADERS = (["Date", "Supplement Name", "Stack", "Servings Eaten"] + NUTRIENT_HEADERS,
               ["Supplement Name"] + NUTRIENT_HEADERS,
               ["Stack", "Supplement Name", "Servings"])
    MAPPINGS = ({"Date": "date", "Supplement Name": "supplement_item_id",
                 "Servings Eaten": "servings"},
                {"Supplement Name": "name", **NUTRIENT_COLUMNS},
                {"Supplement Name": "supplement_item_id", "Servings": "amount"})

    def read_ledger(self):
        return self.db.get_supplement_logs()

    def read_catalogue(self):
        return self.db.get_all_supplements()
