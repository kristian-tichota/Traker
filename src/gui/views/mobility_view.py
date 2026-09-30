from src.domain.tables import MOBILITY
from src.gui.views.base import CatalogueView


class MobilityView(CatalogueView):
    DOMAIN = MOBILITY
    TITLES = ("Mobility & Flexibility Logs", "Mobility Routines Database", "Routine Sets")
    HEADERS = (["Date", "Routine Name", "Routine Set", "Duration (mins)", "METs"],
               ["Routine Name", "METs", "Notes"],
               ["Routine Set", "Routine Name", "Minutes"])
    MAPPINGS = ({"Date": "date", "Routine Name": "mobility_item_id",
                 "Duration (mins)": "duration_mins"},
                {"Routine Name": "name", "METs": "mets", "Notes": "notes"},
                {"Routine Name": "mobility_item_id", "Minutes": "amount"})

    def read_ledger(self):
        return self.db.get_mobility_logs()

    def read_catalogue(self):
        return self.db.get_all_mobility()
