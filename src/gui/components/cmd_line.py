import logging

from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal

from src.gui.commands import (COMMANDS, EVERY_CATALOG, candidates_for,
                              catalog_names, command_word, commands_for,
                              naming_a_command, token_position)
from src.gui.completion import best_match, completion_tail
from src.gui.components.hint_line import HintingLineEdit
from src.gui.workers import run_in_background

log = logging.getLogger(__name__)


class CommandLineEdit(HintingLineEdit):
    mode_requested = pyqtSignal(str)

    hints_changed = pyqtSignal()

    NO_MATCH_HINT = " [No match found]"
    EMPTY_NAME_HINT = " [Item Name]"

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self._names_by_catalog = {}
        self._reads_in_flight = set()
        self._threadpool = QThreadPool.globalInstance()
        self.is_fuzzy_replacement = False
        self.completing_command = False
        self.default_command = None
        self.relevant_domains = ()
        self.menu_index = 0
        self.textChanged.connect(self.update_autocomplete_hints)

        self.prefetch_catalog_names()

    def invalidate_catalog_cache(self):
        """Forget the cached names and read them again."""
        self._names_by_catalog.clear()
        self.prefetch_catalog_names()

    def prefetch_catalog_names(self):
        """Start reading every shared catalog, off the interface thread."""
        for catalog in EVERY_CATALOG:
            self._start_catalog_read(catalog)

    def _start_catalog_read(self, catalog):
        if catalog in self._names_by_catalog or catalog in self._reads_in_flight:
            return
        self._reads_in_flight.add(catalog)
        run_in_background(self._threadpool, self._read_catalog,
                          self._on_catalog_names, self._on_catalog_read_failed,
                          catalog)

    def _read_catalog(self, catalog):
        """One catalog's names, on a pool thread."""
        names = catalog_names(self.db, (catalog,))
        connection = getattr(self.db, "connection", None)
        reachable = connection.online if connection is not None else True
        return catalog, names, reachable

    def _on_catalog_names(self, outcome):
        catalog, names, reachable = outcome
        self._reads_in_flight.discard(catalog)
        if not reachable:
            return
        self._names_by_catalog[catalog] = names
        self.update_autocomplete_hints(self.text())

    def _on_catalog_read_failed(self, failure):
        error, _formatted = failure
        self._reads_in_flight.clear()
        log.warning("Reading the catalogs for completion failed: %s", error)

    def _catalog_names(self, catalogs):
        """The names catalogs offer, or None while they are being read."""
        missing = [key for key in catalogs if key not in self._names_by_catalog]
        for key in missing:
            self._start_catalog_read(key)
        if missing:
            return None

        names = []
        for key in catalogs:
            names.extend(self._names_by_catalog[key])
        return names

    def catalog_names_for_filter(self):
        """Every catalog name already cached, for the filter bar to complete."""
        names = []
        for cached in self._names_by_catalog.values():
            if cached:
                names.extend(cached)
        return names

    def set_relevant_domains(self, domains):
        """Which domains the visible tab is about, for ranking the menu."""
        self.relevant_domains = tuple(domains)
        self.menu_index = 0
        self._render_hints()

    def set_default_command(self, cmd):
        """Offer the visible tab's own command, unless the user has typed."""
        if self.default_command and self.text() == self.default_command + " ":
            self.clear()

        self.default_command = cmd

        if self.hasFocus() and not self.text().strip() and self.default_command:
            self.setText(self.default_command + " ")
            self.deselect()
            self.setCursorPosition(len(self.text()))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mode_requested.emit("COMMAND")

        if self.default_command and not self.text().strip():
            self.setText(self.default_command + " ")

        self.deselect()
        self.setCursorPosition(len(self.text()))
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.deselect()

    def accept_completion(self):
        """Write the current suggestion into the bar."""
        if not self.completion_text:
            return

        text = self.text()
        if not self.is_fuzzy_replacement:
            self.setText(text + self.completion_text)
            return

        if self.completing_command:
            self.setText(self.completion_text)
            return

        command = COMMANDS.get(text.split(maxsplit=1)[0].lower())
        if command is None:
            return

        if command.separator == ";":
            head, _, field = text.rpartition(";")
            leading = field[:len(field) - len(field.lstrip())]
            self.setText(head + ";" + leading + self.completion_text)
            return

        index = command.name_position(text)
        if index is None:
            return
        already_typed = text.split(maxsplit=index)[:index]
        self.setText(" ".join(already_typed) + " " + self.completion_text)

    def _suggest_name(self, typed, names):
        """Offer a catalog name for what has been typed in a name position."""
        if not typed:
            self.hint_text = self.EMPTY_NAME_HINT
            return

        if names is None:
            return

        match = best_match(typed, names)
        if match is None:
            self.hint_text = self.NO_MATCH_HINT
            return

        tail = completion_tail(typed, match)
        if tail is None:
            self.completion_text = match
            self.hint_text = f" -> ({match})"
            self.is_fuzzy_replacement = True
        else:
            self.completion_text = tail
            self.hint_text = tail

    def move_selection(self, step: int):
        """Move through the menu's candidates, wrapping at both ends."""
        count = len(candidates_for(self.text(), self.relevant_domains))
        if count <= 1:
            return
        self.menu_index = (self.menu_index + step) % count
        self._render_hints()

    def keyPressEvent(self, event):
        """Escape leaves, and Ctrl-N/Ctrl-P and the arrows move through the menu."""
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.clearFocus()
            self.mode_requested.emit("NORMAL")
            return

        control = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if event.key() == Qt.Key.Key_Down or (control and event.key() == Qt.Key.Key_N):
            self.move_selection(1)
            return
        if event.key() == Qt.Key.Key_Up or (control and event.key() == Qt.Key.Key_P):
            self.move_selection(-1)
            return
        super().keyPressEvent(event)

    def update_autocomplete_hints(self, text):
        self.menu_index = 0
        self._render_hints(text)

    def _render_hints(self, text=None):
        text = self.text() if text is None else text
        self.hint_text = ""
        self.completion_text = ""
        self.is_fuzzy_replacement = False
        self.completing_command = False

        if text:
            self._compute_hint(text)
        self.update()
        self.hints_changed.emit()

    def _suggest_command(self, typed):
        """Offer a command for the word being typed."""
        candidates = commands_for(typed, self.relevant_domains)
        if not candidates:
            return
        self.completing_command = True
        match = candidates[min(self.menu_index, len(candidates) - 1)]
        tail = completion_tail(typed, match.name)
        if tail is None:
            self.completion_text = match.name
            self.hint_text = f" -> ({match.name}){match.syntax_hint}"
            self.is_fuzzy_replacement = True
        else:
            self.completion_text = tail
            self.hint_text = tail + match.syntax_hint

    def _compute_hint(self, text):
        tokens = text.split(maxsplit=1)
        typed_command = command_word(text)

        if naming_a_command(text):
            self._suggest_command(typed_command)
            return

        command = COMMANDS.get(typed_command)
        if command is None:
            return

        remainder = tokens[1] if len(tokens) > 1 else ""
        if command.separator == ";":
            field = command.field_being_typed(remainder)
            if field is not None and field.catalogs:
                fragment = command.field_fragment(remainder)
                if fragment:
                    self._suggest_name(fragment, self._catalog_names(field.catalogs))
                    return
            self.hint_text = command.hint_for_fields(remainder)
            return

        position = token_position(text)
        name_starts_at = command.name_position(text)
        fragment = command.name_fragment(text) if name_starts_at is not None else ""
        if (name_starts_at is not None and position >= name_starts_at
                and (fragment or command.awaiting_name(text))):
            self._suggest_name(fragment, self._catalog_names(command.catalogs))
        else:
            self.hint_text = command.hint_for_position(position, text)

