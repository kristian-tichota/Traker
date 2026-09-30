from PyQt6.QtCore import Qt, pyqtSignal

from src.gui.completion import best_match, completion_tail
from src.gui.components.hint_line import HintingLineEdit
from src.gui.filtering import FilterError, parse


class FilterLineEdit(HintingLineEdit):
    """One line of filter text, parsed on every keystroke."""

    query_changed = pyqtSignal(object)

    filter_refused = pyqtSignal(str)

    mode_requested = pyqtSignal(str)

    committed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("filter: oats  ·  meal:b  ·  kcal>300  ·  date>01.08.2026")
        self.headers = []
        self.completion_names = []
        self.textChanged.connect(self._on_text_changed)

    def open_for(self, headers, names=()):
        """Point the bar at a table: its headers and the names worth completing."""
        self.headers = list(headers)
        self.completion_names = list(names)
        self._on_text_changed(self.text())

    def _on_text_changed(self, text):
        self._update_hint(text)
        try:
            query = parse(text, self.headers)
        except FilterError as refused:
            self.filter_refused.emit(f" Filter: {refused}")
            return
        self.query_changed.emit(query)

    def _update_hint(self, text):
        """Suggest a catalog name for a trailing bare word."""
        self.completion_text = self.hint_text = ""
        last = "" if text.endswith(" ") else (text.split() or [""])[-1]
        if not any(sign in last for sign in ":=<>"):
            match = best_match(last, self.completion_names)
            tail = None if match is None else completion_tail(last, match)
            self.completion_text = tail or ""
            self.hint_text = f"  → {match}" if match and tail is None else self.completion_text
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.clearFocus()
            self.mode_requested.emit("NORMAL")
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mode_requested.emit("FILTER")
        self.deselect()
        self.setCursorPosition(len(self.text()))
        self.update()
