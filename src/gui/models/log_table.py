from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont

from src.config import PALETTE
from src.domain.clock import as_displayed_date
from src.gui.animations import blend
from src.gui.completion import normalize

PENDING_TEXT = "…"

ORPHAN_NAME_TEXT = "—"

ORPHAN_VALUE_TEXT = "0.00"

DATE_HEADERS = ("Date",)

FLAG_SET_TEXT = "~"
FLAG_CLEAR_TEXT = ""

ROW_GROUND = QColor(PALETTE['base3'])
CHANGE_ACCENT = QColor(PALETTE['blue'])

CHANGE_PEAK = 0.22

ALIGN_RIGHT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
ALIGN_LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
ALIGN_CENTRE = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
BASE_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
EDITABLE_FLAGS = BASE_FLAGS | Qt.ItemFlag.ItemIsEditable

HEADING_FONT = QFont()
HEADING_FONT.setBold(True)

_ABSENT = object()


def _cell(row, column):
    """Return the raw value behind a cell of row, or None where it is short."""
    position = column + 1
    return row[position] if position < len(row) else None


def numeric_fields(row_type):
    """Return which fields of a row NamedTuple hold a number, by index."""
    return _fields_annotated(row_type, (int, float))


def boolean_fields(row_type):
    """Return which fields hold a flag, by index."""
    return _fields_annotated(row_type, (bool,))


def _fields_annotated(row_type, wanted):
    """Return the field indices whose annotation is one of wanted, or None."""
    hints = next((held for held in
                  (getattr(cls, "__annotations__", None)
                   for cls in getattr(row_type, "__mro__", (row_type,)))
                  if held), None)
    if not hints:
        return None
    found = set()
    for index, annotation in enumerate(hints.values()):
        for candidate in getattr(annotation, "__args__", (annotation,)):
            if any(candidate is target for target in wanted):
                found.add(index)
                break
    return found


def editable_columns(headers, mapping):
    """Return the column indices that may be typed into, from the mapping."""
    return [index for index, header in enumerate(headers) if header in mapping]


class LogTableModel(QAbstractTableModel):
    """One log or catalog table's rows, formatted on demand."""

    edit_requested = pyqtSignal(int, int, str, str)

    def __init__(self, headers, mapping, table_idx=0, parent=None,
                 date_headers=DATE_HEADERS):
        super().__init__(parent)
        self._headers = list(headers)
        self._mapping = dict(mapping)
        self.table_idx = table_idx
        self._rows = []
        self._editable = frozenset(editable_columns(self._headers, self._mapping))
        self._item_columns = frozenset(
            index for index, header in enumerate(self._headers)
            if self._mapping.get(header, "").endswith("_item_id"))
        self._date_columns = frozenset(
            index for index, header in enumerate(self._headers)
            if header in set(date_headers))
        self._folded = {}
        self._pending_rows = set()
        self._changed_rows = frozenset()
        self._change_brush = None
        self._populated = False
        self._numeric_fields = None
        self._flag_fields = None
        self._headings = frozenset()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._headers[section] if section < len(self._headers) else None
        return section + 1

    def value_at(self, row_index, column):
        """Return the raw value behind a cell, for a reader that cannot use the text."""
        return self._value_at(row_index, column)

    def values_by_header(self, row_index) -> dict:
        """Return one row as {header: typed value}, as a filter reads it."""
        return {self._headers[column]: self._value_at(row_index, column)
                for column in range(len(self._headers))}

    def fold_all(self, rows=None):
        """Fold every row, without touching Qt."""
        rows = self._rows if rows is None else rows
        return {index: self._fold_row(index, rows) for index in range(len(rows))}

    def adopt_fold(self, prebuilt, rows):
        """Take a fold computed off-thread, where it still describes these rows."""
        if rows is not self._rows:
            return False
        self._folded = prebuilt
        return True

    def _fold_row(self, row_index, rows=None):
        row = (self._rows if rows is None else rows)[row_index]
        by_header = {}
        for column, header in enumerate(self._headers):
            value = _cell(row, column)
            by_header[header] = "" if value is None else normalize(str(value))
        whole = " ".join(text for text in by_header.values() if text)
        return whole, by_header

    def values_of(self, row_index, headers):
        """Return only these columns of a row, typed."""
        return {header: self._value_at(row_index, self._headers.index(header))
                for header in headers if header in self._headers}

    def folded(self, row_index):
        """Return (row text, {header: folded cell}) for matching, cached."""
        cached = self._folded.get(row_index)
        if cached is None:
            cached = self._fold_row(row_index)
            self._folded[row_index] = cached
        return cached

    def _value_at(self, row_index, column):
        """Return the raw value behind a cell of the rows currently held."""
        return _cell(self._rows[row_index], column)

    def _references_an_item(self, column):
        """Report whether this column names the catalog item rather than a value."""
        return column in self._item_columns

    def display_text(self, row_index, column):
        """Return what the cell shows."""
        value = self._value_at(row_index, column)
        if value is None:
            if row_index in self._pending_rows:
                return PENDING_TEXT
            if row_index in self._headings:
                return ""
            if self._is_flag_column(column):
                return FLAG_CLEAR_TEXT
            return ORPHAN_VALUE_TEXT if self._is_numeric_column(column) else ORPHAN_NAME_TEXT
        if isinstance(value, bool):
            return FLAG_SET_TEXT if value else FLAG_CLEAR_TEXT
        if column in self._date_columns:
            return as_displayed_date(value)
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def _is_flag_column(self, column):
        """Report whether this column holds a flag, so an empty cell reads blank."""
        if self._flag_fields is None:
            return False
        return (column + 1) in self._flag_fields

    def _is_numeric_column(self, column):
        """Report whether this column holds numbers, so an empty cell reads zero."""
        if self._numeric_fields is None:
            return not self._references_an_item(column)
        return (column + 1) in self._numeric_fields

    def _is_numeric_cell(self, row_index, column):
        value = self._value_at(row_index, column)
        if value is None:
            return self._is_numeric_column(column)
        return isinstance(value, float)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row_index, column = index.row(), index.column()
        if row_index >= len(self._rows) or column >= len(self._headers):
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self.display_text(row_index, column)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if self._is_flag_column(column):
                return ALIGN_CENTRE
            return ALIGN_RIGHT if self._is_numeric_cell(row_index, column) else ALIGN_LEFT
        if role == Qt.ItemDataRole.BackgroundRole:
            if self._change_brush is None:
                return None
            return self._change_brush if row_index in self._changed_rows else None
        if role == Qt.ItemDataRole.FontRole:
            return HEADING_FONT if row_index in self._headings else None
        if role == Qt.ItemDataRole.UserRole:
            return self._row_id_at(row_index)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.row() in self._headings:
            return BASE_FLAGS
        return EDITABLE_FLAGS if index.column() in self._editable else BASE_FLAGS

    def is_heading(self, row_index) -> bool:
        """Report whether this row heads a group rather than describing a stored row."""
        return row_index in self._headings

    def editable_columns(self):
        return sorted(self._editable)

    def _row_id_at(self, row_index):
        row = self._rows[row_index]
        return row[0] if len(row) else None

    def row_id(self, index):
        """Return the database id behind an index, or None for a pending row."""
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        return self._row_id_at(index.row())

    def row_at(self, index):
        """Return the whole NamedTuple behind an index, typed."""
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        return self._rows[index.row()]

    @property
    def rows(self):
        return self._rows

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if index.column() not in self._editable:
            return False
        row_id = self.row_id(index)
        if row_id is None:
            return False
        self.edit_requested.emit(
            self.table_idx, row_id, self._headers[index.column()], str(value).strip())
        return True

    def set_rows(self, rows):
        incoming = list(rows)
        changed = self._changes_in(incoming)
        self.beginResetModel()
        self._rows = incoming
        self._headings = frozenset(
            position for position, row in enumerate(incoming)
            if getattr(row, "is_heading", False))
        described = next((row for row in incoming
                          if not getattr(row, "is_heading", False)), None)
        self._numeric_fields = (
            None if described is None else numeric_fields(type(described)))
        self._flag_fields = (
            None if described is None else boolean_fields(type(described)))
        self._pending_rows.clear()
        self._folded.clear()
        self._changed_rows = changed
        self._populated = True
        self.endResetModel()

    def _changes_in(self, incoming):
        """Return the positions in incoming that are new here or hold a new value."""
        if not self._populated:
            return frozenset()
        known = {row[0]: row for row in self._rows
                 if len(row) and not getattr(row, "is_heading", False)}
        return frozenset(
            position for position, row in enumerate(incoming)
            if not getattr(row, "is_heading", False)
            and (not len(row) or known.get(row[0], _ABSENT) != row))

    def changed_rows(self):
        """Return the positions the last refresh brought in or altered."""
        return self._changed_rows

    def highlight_changes(self, strength: float):
        """Wash the changed rows strength of the way towards the accent."""
        rows, columns = len(self._rows), len(self._headers)
        if strength <= 0:
            faded, self._changed_rows = self._changed_rows, frozenset()
            self._change_brush = None
        else:
            faded = self._changed_rows
            self._change_brush = QBrush(
                blend(ROW_GROUND, CHANGE_ACCENT, strength * CHANGE_PEAK))
        if not faded or not columns:
            return
        for position in faded:
            if position < rows:
                self.dataChanged.emit(
                    self.index(position, 0), self.index(position, columns - 1),
                    [Qt.ItemDataRole.BackgroundRole])

    def insert_pending_row(self, row):
        """Show a row the service has confirmed but not yet described."""
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append(row)
        self._folded.pop(position, None)
        self._pending_rows.add(position)
        self._changed_rows = self._changed_rows | {position}
        self.endInsertRows()
        return position

    def has_pending_rows(self):
        return bool(self._pending_rows)

    def is_pending(self, row_index):
        return row_index in self._pending_rows
