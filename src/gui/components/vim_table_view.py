from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from src.gui.columns import ColumnLayout
from src.profile import UserProfile, get_qt_key

DEFAULT_KEYBINDS = {
    "up": ("k", Qt.Key.Key_K),
    "down": ("j", Qt.Key.Key_J),
    "left": ("h", Qt.Key.Key_H),
    "right": ("l", Qt.Key.Key_L),
    "edit": ("e", Qt.Key.Key_E),
    "sort": ("o", Qt.Key.Key_O),
}

COLUMN_SAMPLE_ROWS = 100


class VimTableView(QTableView):
    mode_requested = pyqtSignal(str)

    context_menu_requested = pyqtSignal(int, QPoint)

    filter_requested = pyqtSignal()

    sort_requested = pyqtSignal(object)

    header_menu_requested = pyqtSignal(int, QPoint)

    columns_rearranged = pyqtSignal(int)

    focus_taken = pyqtSignal(object)

    def __init__(self, table_idx=0, parent=None):
        super().__init__(parent)
        self.table_idx = table_idx
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setResizeContentsPrecision(COLUMN_SAMPLE_ROWS)
        self._measured = False

        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_menu_requested)
        self.horizontalHeader().sectionMoved.connect(self._on_section_moved)
        self._rearranging = False

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)

        profile = UserProfile()
        for binding, (default_str, default_key) in DEFAULT_KEYBINDS.items():
            setattr(self, f"key_{binding}",
                    get_qt_key(profile.get_metric("keybinds", binding, default_str), default_key))

    def measure_columns_once(self):
        """Size the columns to their content, the first time there is content."""
        if self._measured or self.model() is None or self.model().rowCount() == 0:
            return
        self.resizeColumnsToContents()
        self._measured = True

    def column_layout(self, declared) -> ColumnLayout:
        """Return what this header is showing, as a ColumnLayout."""
        header = self.horizontalHeader()
        order, hidden = [], set()
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if not 0 <= logical < len(declared):
                continue
            order.append(declared[logical])
            if header.isSectionHidden(logical):
                hidden.add(declared[logical])
        return ColumnLayout(tuple(order), frozenset(hidden))

    def arrange_columns(self, declared, layout) -> None:
        """Put the header in layout order, hiding what it hides."""
        header = self.horizontalHeader()
        logical_of = {name: index for index, name in enumerate(declared)}
        self._rearranging = True
        try:
            for target, name in enumerate(layout.order):
                logical = logical_of.get(name)
                if logical is None:
                    continue
                current = header.visualIndex(logical)
                if current != target:
                    header.moveSection(current, target)
            for logical, name in enumerate(declared):
                header.setSectionHidden(logical, layout.is_hidden(name))
        finally:
            self._rearranging = False
        self.settle_cursor()

    def first_visible_column(self):
        """Return the leftmost column on screen, or None where there is none."""
        header = self.horizontalHeader()
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if not header.isSectionHidden(logical):
                return logical
        return None

    def settle_cursor(self):
        """Move the cursor off a column that is no longer shown."""
        index = self.currentIndex()
        if not index.isValid():
            return
        if not self.horizontalHeader().isSectionHidden(index.column()):
            return
        column = self.first_visible_column()
        if column is not None:
            self._move_to(index.row(), column)

    def _column_beside(self, column, step):
        """Return the next column in visual order, or None."""
        header = self.horizontalHeader()
        visual = header.visualIndex(column) + step
        while 0 <= visual < header.count():
            logical = header.logicalIndex(visual)
            if not header.isSectionHidden(logical):
                return logical
            visual += step
        return None

    def _on_context_menu_requested(self, pos):
        self.context_menu_requested.emit(self.table_idx, pos)

    def _on_header_menu_requested(self, pos):
        header = self.horizontalHeader()
        self.header_menu_requested.emit(
            self.table_idx, self.mapFromGlobal(header.mapToGlobal(pos)))

    def _on_section_moved(self, _logical, _from_visual, _to_visual):
        if self._rearranging:
            return
        self.columns_rearranged.emit(self.table_idx)

    def focus_first_cell(self):
        """Take focus, putting the cursor on the first cell where it has none."""
        self.setFocus()
        model = self.model()
        if not self.currentIndex().isValid() and model is not None and model.rowCount() > 0:
            column = self.first_visible_column()
            self.setCurrentIndex(model.index(0, column if column is not None else 0))

    def _move_to(self, row, column):
        model = self.model()
        if model is None:
            return
        self.setCurrentIndex(model.index(row, column))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_taken.emit(self)
        self.mode_requested.emit("SHEET")

    def keyPressEvent(self, event):
        if self.state() == QAbstractItemView.State.EditingState:
            super().keyPressEvent(event)
            return

        model = self.model()
        rows = model.rowCount() if model is not None else 0

        current = self.currentIndex()
        r = max(0, current.row())
        c = max(0, current.column())

        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.clearSelection()
            self.clearFocus()
            self.mode_requested.emit("NORMAL")
            return
        elif key == self.key_down:
            if current.row() < rows - 1:
                self._move_to(r + 1, c)
            return
        elif key == self.key_up:
            if current.row() > 0:
                self._move_to(r - 1, c)
            return
        elif key == self.key_left:
            beside = self._column_beside(c, -1)
            if beside is not None:
                self._move_to(r, beside)
            return
        elif key == self.key_right:
            beside = self._column_beside(c, 1)
            if beside is not None:
                self._move_to(r, beside)
            return
        elif key == self.key_edit:
            if current.isValid() and (model.flags(current) & Qt.ItemFlag.ItemIsEditable):
                self.edit(current)
            return
        elif key == self.key_sort:
            self.sort_requested.emit(self)
            return
        elif key == Qt.Key.Key_Slash:
            self.filter_requested.emit()
            return

        super().keyPressEvent(event)
