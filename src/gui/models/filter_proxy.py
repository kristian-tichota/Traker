from PyQt6.QtCore import QSortFilterProxyModel, Qt

from src.gui.filtering import EMPTY


class FilterProxyModel(QSortFilterProxyModel):
    """The rows of a LogTableModel that match a parsed query, in order."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = EMPTY
        self.setDynamicSortFilter(False)

    def set_query(self, query):
        """Apply a parsed src.gui.filtering.Query."""
        self._query = query
        self.invalidateFilter()

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """Sort, then re-decide which rows are acceptable."""
        super().sort(column, order)
        self.invalidateFilter()

    def clear_query(self):
        self.set_query(EMPTY)

    def is_filtered(self) -> bool:
        return bool(self._query)

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model.is_heading(source_row):
            return not (self._query.terms or self.sortColumn() >= 0)
        if not self._query.terms or model.is_pending(source_row):
            return True
        fields = self._query.fields
        values = model.values_of(source_row, fields) if fields else {}
        return self._query.matches(values, model.folded(source_row))

    def lessThan(self, left, right):
        """Compare the values rather than their renderings."""
        model = self.sourceModel()
        left_value = model.value_at(left.row(), left.column())
        right_value = model.value_at(right.row(), right.column())

        if left_value is None or right_value is None:
            if left_value is None and right_value is None:
                return False
            descending = self.sortOrder() == Qt.SortOrder.DescendingOrder
            return descending if left_value is None else not descending

        try:
            return left_value < right_value
        except TypeError:
            return str(left_value) < str(right_value)

    def matched_rows(self):
        """Return the source rows currently showing, as NamedTuples."""
        model = self.sourceModel()
        return [model.row_at(self.mapToSource(self.index(row, 0)))
                for row in range(self.rowCount())]
