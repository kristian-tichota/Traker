import logging

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel, QTreeWidget,
                             QVBoxLayout, QWidget)

from src.config import PALETTE
from src.domain.hints import LETTERS, labels

log = logging.getLogger(__name__)

LIST_INDENT_PX = 28
LIST_FONT_PX = 20
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
UNMARKED = Qt.ItemDataRole.UserRole


class BreakPane(QWidget):
    """What a break shows, or one line in its place saying why nothing is shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = None
        self._message = QLabel(self)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._message)

    def position(self) -> int:
        return 0

    def duration(self) -> int:
        return 0

    def stop(self):
        """Leave what is shown as it is, there being no place in it to keep."""

    def still(self, held):
        """Hold what plays still while the eyes rest, there being nothing playing here."""

    def shutdown(self):
        """Let go of what is shown, once, at the end of the break."""
        self.stop()

    def _shown(self):
        """Return the widget shown while there is no message."""
        return self.view

    def _show_message(self, text, colour='red'):
        self._message.setText(text)
        self._message.setStyleSheet(f"color: {PALETTE[colour]}; font-size: 16px; "
                                    f"font-family: 'Fira Code'; letter-spacing: 2px;")
        self._show_only(self._message)

    def _clear_message(self):
        self._message.clear()
        self._show_only(self._shown())

    def _show_only(self, shown):
        layout = self.layout()
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            widget.setVisible(widget is shown)


class WebPane(BreakPane):
    """A pane a web view draws on paper, destroyed as soon as the break ends."""

    def __init__(self, refused, parent=None, quiet=True, alignment=Qt.AlignmentFlag(0)):
        super().__init__(parent)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as error:
            log.warning("No web engine for a break: %s", error)
            self._show_message(f"{refused}\n{error}")
            return
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(PALETTE['base3']))
        if quiet:
            self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.view.page().setAudioMuted(True)
        self.layout().addWidget(self.view, alignment=alignment)

    def shutdown(self):
        """Let go of what is shown and destroy the web view at once."""
        self.stop()
        if self.view is not None:
            sip.delete(self.view)
            self.view = None


def key_list(parent, columns) -> QTreeWidget:
    """Build a list driven by keys or a pointer, in Solarized light, each row's hint in front."""
    tree = QTreeWidget(parent)
    tree.setColumnCount(len(columns) + 1)
    tree.setHeaderLabels((*columns, ""))
    tree.header().moveSection(len(columns), 0)
    tree.header().setSectionResizeMode(len(columns), QHeaderView.ResizeMode.ResizeToContents)
    tree.setRootIsDecorated(False)
    tree.setItemsExpandable(False)
    tree.setIndentation(LIST_INDENT_PX)
    tree.setUniformRowHeights(True)
    tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setFrameShape(QFrame.Shape.NoFrame)
    tree.setStyleSheet(
        f"QTreeWidget {{ background-color: {PALETTE['base3']}; border: none;"
        f" font-family: 'Fira Code'; font-size: {LIST_FONT_PX}px; padding: 20px; }}"
        f" QTreeWidget::item {{ padding: 4px 16px; }}"
        f" QHeaderView::section {{ background-color: {PALETTE['base3']};"
        f" color: {PALETTE['base1']}; border: none; font-family: 'Fira Code';"
        f" font-size: 11px; letter-spacing: 2px; padding: 4px 16px; }}")
    return tree


def named_list(parent) -> QTreeWidget:
    """Build a list of names, each with a note to its right."""
    tree = key_list(parent, ("", ""))
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    tree.headerItem().setTextAlignment(1, RIGHT)
    return tree


def ink(row, colour):
    """Colour a row's name, kept for when the row is no longer marked."""
    row.setForeground(0, colour)
    row.setData(0, UNMARKED, colour)


class MarkedList:
    """A pane choosing one row of its chooser, by the mark or by a hint."""

    marked = 0
    typed = ""
    letters = LETTERS
    _rows = ()
    _labels = ()

    def set_letters(self, letters):
        """Build the hints from letters, the rows listed included."""
        self.letters = str(letters)
        self._label()

    def hint(self, letter) -> bool:
        """Open the row whose hint the letters typed spell, reporting whether letter was taken."""
        typed = self.typed + letter
        if not any(label.startswith(typed) for label in self._labels):
            typed = letter
        if not any(label.startswith(typed) for label in self._labels):
            self._narrow("")
            return False
        if typed not in self._labels:
            self._narrow(typed)
            return True
        self._narrow("")
        self._mark(self._labels.index(typed))
        self.toggle()
        return True

    def pick(self, row):
        """Open the row a pointer pressed, as its hint would."""
        if row in self._rows:
            self._mark(self._rows.index(row))
            self.toggle()

    def forget_hint(self) -> bool:
        """Drop the letters typed towards a hint, reporting whether there were any."""
        if not self.typed:
            return False
        self._narrow("")
        return True

    def _label(self):
        """Give every row listed its hint, in list order."""
        self._labels = labels(len(self._rows), self.letters)
        self._narrow("")

    def _narrow(self, typed):
        """Show the hints that begin with typed, and blank the rest."""
        self.typed = typed
        if not self._rows:
            return
        column = self.chooser.columnCount() - 1
        for index, row in enumerate(self._rows):
            label = self._labels[index] if index < len(self._labels) else ""
            row.setText(column, label if label.startswith(typed) else "")
            row.setForeground(column, QColor(PALETTE['orange']))

    def _mark(self, index):
        """Mark the row at index, within the list, and keep it in view."""
        if not self._rows:
            return
        if self.typed:
            self._narrow("")
        self._paint_row(False)
        self.marked = max(0, min(len(self._rows) - 1, int(index)))
        self._paint_row(True)
        self.chooser.scrollToItem(self._rows[self.marked],
                                  QAbstractItemView.ScrollHint.PositionAtCenter)

    def _paint_row(self, marked):
        """Paint the marked row as marked, or as it reads once it is not."""
        if not 0 <= self.marked < len(self._rows):
            return
        row = self._rows[self.marked]
        row.setForeground(0, QColor(PALETTE['base02']) if marked else row.data(0, UNMARKED))
        for column in range(self.chooser.columnCount()):
            row.setData(column, Qt.ItemDataRole.BackgroundRole,
                        QColor(PALETTE['base2']) if marked else None)
