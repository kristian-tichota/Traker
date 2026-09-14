import logging
import os
from importlib import import_module

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
                             QLabel, QSizePolicy, QSystemTrayIcon)
from PyQt6.QtCore import Qt, QSize, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QFont

from src.gui.views.food_views import FoodView
from src.gui.views.beverage_view import BeveragesView
from src.gui.views.exercise_view import ExerciseView
from src.gui.views.supplement_view import SupplementsView
from src.gui.views.mobility_view import MobilityView
from src.gui.views.pomodoro_view import PomodoroView
from src.gui.views.plan_view import PlanView
from src.gui.views.chore_view import ChoreView
from src.gui.icons import ICON_PX, tab_icon

from src.gui.animations import TabFadeManager, StatusBarPulser
from src.desktop.kwin import WindowScreen, default_app_id
from src.desktop.kwin_rules import WindowHome
from src.desktop.night_filter import NightFilter
from src.gui.components.cmd_line import CommandLineEdit
from src.gui.components.command_menu import CommandMenu
from src.gui.components.filter_line import FilterLineEdit
from src.gui.components.vim_table_view import VimTableView
from src.gui.domains import domain_of_table, domains_for_tab, tabs_reading
from src.gui.sync_listener import SyncListener
from src.gui.columns import ColumnError, describe, rearranged
from src.desktop import rest_queue
from src.gui.commands import (BREAK_LONG, COMMANDS, QUEUE_ADD, QUEUE_CLEAR,
                              QUEUE_REMOVE, RESET, CommandError, resolve)
from src.gui.filtering import FilterError
from src.gui.workers import run_in_background
from src.database import REQUEST_TIMEOUT_S
from src.config import PALETTE
from src.profile import UserProfile, get_qt_key

log = logging.getLogger(__name__)


def _graph(module: str, view: str):
    """Build a graph tab, importing matplotlib only where that tab is wanted."""
    def build(window):
        return getattr(import_module(f"src.gui.graphs.{module}"), view)(window.db)
    return build


TAB_SHORTCUT_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

NUTRIENT_WINDOW_KEYS = "DW"

MODES = {
    "NORMAL": "base01",
    "COMMAND": "green",
    "SHEET": "blue",
    "FILTER": "violet",
}


def tab_shortcut_keys(also_reserved: str = "") -> str:
    """Return the keys that select a tab, in order, less the reserved ones."""
    blocked = {character.upper() for character in NUTRIENT_WINDOW_KEYS + also_reserved}
    return "".join(c for c in TAB_SHORTCUT_ALPHABET if c not in blocked)


def resolve_app_icon() -> QIcon:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate_paths = [
        os.path.join(base_dir, "assets", "icon.svg"),
        os.path.join(base_dir, "assets", "icon.png"),
        os.path.join(os.getcwd(), "assets", "icon.svg"),
        os.path.join(os.getcwd(), "assets", "icon.png"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(PALETTE.get("base02", "#073642")))
    painter.setPen(QPen(QColor(PALETTE.get("green", "#859900")), 3))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor(PALETTE.get("green", "#859900")))
    font = QFont("Fira Code", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    connection_changed = pyqtSignal(bool, str)

    TAB_REGISTRY = (
        ("pomodoro", "Focus Timer", lambda w: PomodoroView(w.db, w.tray_icon), None),
        ("food", "Food", lambda w: FoodView(w.db), "log"),
        ("beverages", "Beverages", lambda w: BeveragesView(w.db), "bevlog"),
        ("exercise", "Exercise", lambda w: ExerciseView(w.db), "exlog"),
        ("supplements", "Supplements", lambda w: SupplementsView(w.db), "supplog"),
        ("mobility", "Mobility", lambda w: MobilityView(w.db), "moblog"),
        ("food_graphs", "Nutrient Graphs", _graph("food_graph", "FoodGraphView"), None),
        ("exercise_graphs", "Exercise Graphs", _graph("exercise_graph", "ExerciseGraphView"), None),
        ("heatmap", "Heatmap", _graph("heatmap", "ActivityHeatmapView"), None),
        ("caffeine_graph", "Caffeine Graph", _graph("caffeine_graph", "CaffeineGraphView"), None),
        ("supplement_graphs", "Supplement Graphs",
         _graph("supplement_graph", "SupplementGraphView"), None),
        ("plans", "Plans", lambda w: PlanView(w.db), "planlog"),
        ("chores", "Chores", lambda w: ChoreView(w.db), "chore"),
    )

    def __init__(self, db):
        """Build the window, in the order the pieces depend on each other."""
        super().__init__()
        self.db = db
        self.setWindowTitle("Traker")
        self.resize(1350, 780)
        self.current_mode = "NORMAL"
        self._sheet_table = None
        self._command_in_flight = False

        self.profile = UserProfile()

        self.window_home = self._claim_a_desktop()

        self.night_filter = NightFilter()
        self.night_filter.begin()

        self._read_keybinds()
        self._build_tray_icon()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        self._build_tabs(main_layout)
        self._build_command_menu(main_layout)
        self._build_command_bar(main_layout)
        self._build_filter_bar(main_layout)
        self._build_status_row(main_layout)

        for view in self.views.values():
            self._connect_view(view)

        self.dirty_tabs = set(range(self.tabs.count()))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        if self.tabs.count() > 0:
            self._on_tab_changed(0)

        self._wire_input()
        self.set_mode("NORMAL")
        self._watch_the_connection()

        self.sync_listener = SyncListener(self.db)
        self.sync_listener.catalog_updated.connect(self._on_remote_catalog_update)
        self.sync_listener.start()

    def _claim_a_desktop(self):
        """Put this window where [window] says it belongs, or nowhere."""
        home = WindowHome(self.windowTitle(),
                          desktop=self.profile.get_metric("window", "desktop", ""),
                          activity=self.profile.get_metric("window", "activity", ""))
        home.hold()

        self.window_screen = WindowScreen(
            default_app_id(), self.windowTitle(),
            self.profile.get_metric("window", "screen", ""))
        self.window_screen.engage()
        return home

    def _read_keybinds(self):
        """Return the keys NORMAL mode answers to, from [keybinds]."""
        keybind = self.profile.get_metric
        self.key_cmd = get_qt_key(keybind("keybinds", "command_mode", "i"), Qt.Key.Key_I)
        self.key_sheet = get_qt_key(keybind("keybinds", "sheet_mode", "s"), Qt.Key.Key_S)
        self.key_filter = get_qt_key(keybind("keybinds", "filter", "/"), Qt.Key.Key_Slash)
        self.key_sort = get_qt_key(keybind("keybinds", "sort", "o"), Qt.Key.Key_O)

        reserved = (str(keybind("keybinds", "command_mode", "i"))
                    + str(keybind("keybinds", "sheet_mode", "s")))
        self.tab_keys = tab_shortcut_keys(reserved)
        self._tab_key_index = {
            get_qt_key(character, None): position
            for position, character in enumerate(self.tab_keys)
        }

    def _build_tray_icon(self):
        app_icon = resolve_app_icon()
        self.setWindowIcon(app_icon)
        self.tray_icon = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(app_icon)
            self.tray_icon.show()

    def _build_tabs(self, main_layout):
        """Build the enabled tabs, each labelled with the key that selects it."""
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(ICON_PX, ICON_PX))
        self.tab_default_commands = {}
        self.views = {}
        self.tab_indices = {}

        for key, label, build, default_cmd in self.TAB_REGISTRY:
            if not self.profile.is_window_enabled(key, default=True):
                continue
            try:
                widget = build(self)
            except ImportError as error:
                log.warning("No %s tab: %s. Install it with: uv sync --extra graphs",
                            key, error)
                continue
            self.views[key] = widget

            index = self.tabs.count()
            self.tab_indices[key] = index
            prefix = self.tab_keys[index] if index < len(self.tab_keys) else str(index)
            self.tabs.addTab(widget, tab_icon(key), f"{prefix}: {label}")
            if default_cmd:
                self.tab_default_commands[index] = default_cmd

        if self.tabs.count() == 0:
            empty = QLabel("No active views configured in "
                           "~/.config/traker/user_profile.toml")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabs.addTab(empty, "Empty")

        main_layout.addWidget(self.tabs)

    def _build_command_menu(self, main_layout):
        """Build the menu of what can be typed, hidden until COMMAND mode."""
        self.command_menu = CommandMenu()
        main_layout.addWidget(self.command_menu)
        self.command_menu.hide()

    def _build_command_bar(self, main_layout):
        self.command_layout = QHBoxLayout()
        self.command_prefix = QLabel(":")
        self.command_prefix.setStyleSheet(
            f"color: {PALETTE['green']}; font-weight: bold; font-size: 14px;")
        self.command_line = CommandLineEdit(self.db)
        self.command_layout.addWidget(self.command_prefix)
        self.command_layout.addWidget(self.command_line)
        main_layout.addLayout(self.command_layout)

    def _build_filter_bar(self, main_layout):
        """Build the filter bar, under the command bar and hidden until "/"."""
        self.filter_layout = QHBoxLayout()
        self.filter_prefix = QLabel("/")
        self.filter_prefix.setStyleSheet(
            f"color: {PALETTE['violet']}; font-weight: bold; font-size: 14px;")
        self.filter_line = FilterLineEdit()
        self.filter_layout.addWidget(self.filter_prefix)
        self.filter_layout.addWidget(self.filter_line)
        main_layout.addLayout(self.filter_layout)
        self.filter_prefix.hide()
        self.filter_line.hide()
        self._filter_open = False
        self._filtered_view = None

    def _build_status_row(self, main_layout):
        """Build the status row: the mode on the left, the last message on the right."""
        self.status_row = QHBoxLayout()
        self.status_row.setContentsMargins(0, 0, 0, 0)
        self.status_row.setSpacing(0)

        self.mode_label = QLabel()
        self.status_bar = QLabel()
        for label in (self.mode_label, self.status_bar):
            label.setStyleSheet(
                f"background-color: {PALETTE['base2']}; "
                f"color: {PALETTE['base01']}; padding: 3px;")
        self.status_bar.setSizePolicy(QSizePolicy.Policy.Ignored,
                                      QSizePolicy.Policy.Preferred)
        self.status_row.addWidget(self.mode_label)
        self.status_row.addWidget(self.status_bar, 1)
        main_layout.addLayout(self.status_row)

        self.tab_animator = TabFadeManager(self.tabs, duration=180)
        self._reveal_poll = QTimer(self)
        self._reveal_poll.timeout.connect(self._on_reveal_poll)
        self.status_pulser = StatusBarPulser(
            status_bar=self.status_bar,
            base_bg_hex=PALETTE['base2'],
            text_color_hex=PALETTE['base01'],
        )

    def _wire_input(self):
        """Connect the two bars and every table to the window's own handlers."""
        self.command_line.returnPressed.connect(self.execute_command)
        self.command_line.mode_requested.connect(self._on_mode_requested)
        self.command_line.hints_changed.connect(self._refresh_command_menu)

        self.filter_line.mode_requested.connect(self._on_filter_mode_requested)
        self.filter_line.query_changed.connect(self._on_filter_changed)
        self.filter_line.filter_refused.connect(self.status_bar.setText)
        self.filter_line.committed.connect(self._commit_filter)

        for table in self.findChildren(VimTableView):
            table.focus_taken.connect(self._remember_sheet_table)
            table.mode_requested.connect(self._on_mode_requested)
            table.filter_requested.connect(self.open_filter)
            table.sort_requested.connect(self.sort_visible_table)

    def _watch_the_connection(self):
        """Report whether an empty table is no rows or a service that is down."""
        self.connection_changed.connect(self._on_connection_changed)
        connection = getattr(self.db, "connection", None)
        if connection is None:
            return
        connection.on_change = self.connection_changed.emit
        if not connection.online:
            self._on_connection_changed(False, connection.last_error or "")

    def _connect_view(self, widget):
        """Listen to what a view reports."""
        if hasattr(widget, "data_changed"):
            widget.data_changed.connect(self._on_view_data_changed)
        if hasattr(widget, "status_message"):
            widget.status_message.connect(self.status_bar.setText)
        if hasattr(widget, "command_requested"):
            widget.command_requested.connect(self.offer_command)

    def _on_view_data_changed(self, domain):
        """Handle a view reporting a write."""
        if domain:
            self.mark_domains_stale((domain,))
        else:
            self.mark_all_tabs_stale()

    def _invalidate_reads(self, domains):
        """Drop the client's cached reads for these domains, or all of them."""
        invalidate = getattr(self.db, "invalidate", None)
        if invalidate is not None:
            invalidate(domains)

    def mark_domains_stale(self, domains):
        """Mark the tabs reading domains out of date and redraw the visible one."""
        keys = tabs_reading(domains)
        indices = {self.tab_indices[key] for key in keys if key in self.tab_indices}
        if not indices:
            return
        self.dirty_tabs |= indices
        self._refresh_visible_tab()

    def mark_all_tabs_stale(self):
        """Mark every tab out of date and redraw the visible one now."""
        self.dirty_tabs = set(range(self.tabs.count()))
        self._refresh_visible_tab()

    def _on_connection_changed(self, online, reason):
        if online:
            self.command_line.invalidate_catalog_cache()
            self._invalidate_reads(None)
            self.mark_all_tabs_stale()
            self.status_bar.setText(" Household service reachable again.")
            self.status_pulser.pulse(PALETTE.get('green', '#859900'))
        else:
            self.status_bar.setText(
                f" Household service unreachable — tables may be empty for that reason, "
                f"not because there is nothing logged. ({reason})"
            )
            self.status_pulser.pulse(PALETTE.get('red', '#dc322f'))

    def _on_remote_catalog_update(self, data):
        self.command_line.invalidate_catalog_cache()
        domain = domain_of_table((data or {}).get("table", "")) if isinstance(data, dict) else None
        if domain:
            self._invalidate_reads((domain,))
            self.mark_domains_stale((domain,))
        else:
            self._invalidate_reads(None)
            self.mark_all_tabs_stale()
        self.status_pulser.pulse(PALETTE['cyan'])
        self.status_bar.setText(" Real-time sync: Catalog definitions updated.")

    REVEAL_POLL_MS = 16

    SHUTDOWN_GRACE_MS = (REQUEST_TIMEOUT_S * 1000) + 500

    def closeEvent(self, event):
        """Shut the client down, unless a strict break is holding the screens."""
        timer = self.views.get("pomodoro")
        holding = getattr(timer, "holds_the_screens", None)
        if callable(holding) and holding():
            log.info("Refusing to quit: a strict break is holding the screens.")
            event.ignore()
            return

        connection = getattr(self.db, "connection", None)
        if connection is not None:
            connection.on_change = None

        if hasattr(self, 'sync_listener') and self.sync_listener:
            self.sync_listener.stop()
            self.sync_listener = None

        for view in self.views.values():
            shutdown = getattr(view, "shutdown", None)
            if callable(shutdown):
                shutdown()

        if self.tray_icon:
            self.tray_icon.hide()

        self.window_home.release()
        self.window_screen.release()

        self.night_filter.stop()

        if not QThreadPool.globalInstance().waitForDone(self.SHUTDOWN_GRACE_MS):
            log.warning(
                "Closing with background work still running after %d ms",
                self.SHUTDOWN_GRACE_MS)
        event.accept()

    def _bound_key(self, binding, fallback) -> str:
        """Return the key bound to binding, for a readout to name."""
        return str(self.profile.get_metric("keybinds", binding, fallback)).lower()

    def _mode_hint(self, mode_name) -> str:
        """Return the keys that work in mode_name, in the configured bindings."""
        key = self._bound_key
        if mode_name == "NORMAL":
            return (f"Hotkeys: Keys->Tabs | {key('sheet_mode', 's')}->Enter Sheet"
                    f" | {key('command_mode', 'i')}->Focus Command Bar")
        if mode_name == "COMMAND":
            return "Tab->Complete | Ctrl-n/Ctrl-p->Pick | Esc->Normal Mode"
        if mode_name == "SHEET":
            return (f"{key('left', 'h')},{key('down', 'j')},{key('up', 'k')},"
                    f"{key('right', 'l')}->Move | {key('edit', 'e')}->Edit"
                    f" | {key('sort', 'o')}->Sort | Esc->Normal Mode")
        return "Type to narrow | Tab->Complete | Enter->Sheet | Esc->Clear"

    def set_mode(self, mode_name):
        """Enter mode_name and name it, whatever else the status line holds."""
        if mode_name not in MODES:
            log.warning("Refusing to enter unknown mode %r", mode_name)
            return

        self.current_mode = mode_name
        self.command_menu.setVisible(mode_name == "COMMAND")
        if mode_name == "COMMAND":
            self._refresh_command_menu()

        self.mode_label.setText(f" Mode: {mode_name} | {self._mode_hint(mode_name)} ")
        self.mode_label.setStyleSheet(
            f"background-color: {PALETTE['base2']}; "
            f"color: {PALETTE[MODES[mode_name]]}; "
            f"padding: 3px; font-weight: bold;")

    def return_to_normal(self):
        """Leave whatever mode is active and take the keyboard back."""
        self.setFocus()
        self.set_mode("NORMAL")

    def _on_mode_requested(self, mode):
        """Handle a bar or a table asking for a mode."""
        if mode == "NORMAL":
            self.return_to_normal()
            return
        self.set_mode(mode)

    def _refresh_command_menu(self):
        """Re-render the menu from what the bar is currently offering."""
        self.command_menu.render_for(self.command_line.text(),
                                     self.command_line.relevant_domains,
                                     self.command_line.menu_index)

    def _tab_subject(self, index) -> tuple:
        """Return the domains the tab at index is about, for ranking the menu."""
        default = self.tab_default_commands.get(index)
        if default:
            return COMMANDS[default].domains
        for key, position in self.tab_indices.items():
            if position == index:
                return domains_for_tab(key)
        return ()

    def enter_command(self):
        """Put the keyboard in the command bar and name the mode."""
        self.command_line.setFocus()
        self.set_mode("COMMAND")

    def offer_command(self, text: str):
        """Write a command into the bar without running it."""
        self.command_line.setText(text)
        self.command_line.setFocus()
        self.command_line.deselect()
        self.command_line.setCursorPosition(len(text))
        self.set_mode("COMMAND")

    def enter_sheet(self):
        """Put the keyboard on the visible tab's first table and name the mode."""
        widget = self.tabs.currentWidget()
        tables = widget.findChildren(VimTableView) if widget else []
        if not tables:
            return
        tables[0].focus_first_cell()
        self.set_mode("SHEET")

    def filterable_view(self):
        """Return the visible tab, where it has a table to filter."""
        widget = self.tabs.currentWidget()
        return widget if hasattr(widget, "apply_filter") else None

    def open_filter(self):
        """Show the filter bar for the visible table and take focus."""
        view = self.filterable_view()
        if view is None:
            self.status_bar.setText(" Nothing to filter on this tab.")
            return
        self.command_prefix.hide()
        self.command_line.hide()
        self.filter_prefix.show()
        self.filter_line.show()
        self._filter_open = True
        self._filtered_view = view
        view.warm_fold(0)
        self.filter_line.open_for(view.headers[0],
                                  self.command_line.catalog_names_for_filter())
        self.filter_line.setFocus()
        self.set_mode("FILTER")

    def close_filter(self):
        """Hide the bar and drop any filter it had in force."""
        if self._filtered_view is not None:
            self._filtered_view.clear_filter()
            self._filtered_view = None
        self.filter_line.blockSignals(True)
        self.filter_line.clear()
        self.filter_line.blockSignals(False)
        self.filter_prefix.hide()
        self.filter_line.hide()
        self.command_prefix.show()
        self.command_line.show()
        self._filter_open = False

    def _on_filter_mode_requested(self, mode):
        """Handle Escape from the filter bar: drop the filter and leave the mode."""
        if mode != "FILTER":
            self.close_filter()
        self._on_mode_requested(mode)

    def _on_filter_changed(self, query):
        view = self._filtered_view
        if view is None:
            return
        view.apply_filter(query)
        if query:
            self.status_bar.setText(
                f" Filter: {view.matched_totals().rows:,} of "
                f"{view.model_for(0).rowCount():,} rows.")

    def _commit_filter(self):
        """Keep the filter and drop into the sheet on the first match."""
        view = self._filtered_view
        if view is None:
            return
        tables = view.findChildren(VimTableView)
        if tables:
            tables[0].focus_first_cell()
        self.set_mode("SHEET")

    def _remember_sheet_table(self, table):
        """Record the current table, for a command typed after leaving it."""
        self._sheet_table = table

    def _arrangeable_table(self, view) -> int:
        """Return which of a tab's tables :cols acts on."""
        table = self._sheet_table
        if table is not None and table in view.findChildren(VimTableView):
            return table.table_idx
        return 0

    def arrange_columns(self, payload):
        """Carry out :cols against the visible table."""
        view = self.filterable_view()
        if view is None:
            raise ColumnError("No table to arrange on this tab.")
        table_idx = self._arrangeable_table(view)
        layout = view.column_layout(table_idx)
        title = view.table_title(table_idx)

        if payload["action"] != RESET and not payload["column"]:
            return f" {title}: {describe(layout)}"

        settled, said = rearranged(layout, view.headers[table_idx],
                                   payload["action"], payload["column"],
                                   payload["position"])
        view.set_column_layout(table_idx, settled)
        return f" {title}: {said}."

    def queue_long_break(self, payload):
        """Carry out :break, setting whether the next break is the long one."""
        view = self.views.get("pomodoro")
        if view is None:
            raise CommandError("The Focus Timer is switched off in the profile.")
        if not payload["action"]:
            return view.long_break_state()
        return view.set_long_break_queued(payload["action"] == BREAK_LONG)

    def queue_rest(self, payload):
        """Carry out :rest, setting what to open on the next break."""
        path = rest_queue.path_for(self.profile)
        action, position = payload["action"], payload["position"]
        entry = (payload["entry"] or "").strip()

        if action == QUEUE_REMOVE and position is None:
            raise CommandError("Say which one: rest rm 2.")

        if action == QUEUE_ADD and not entry:
            return f" Break queue: {rest_queue.describe(rest_queue.read(path))}"

        try:
            if action == QUEUE_CLEAR:
                rest_queue.clear(path)
                return " Break queue emptied."
            if action == QUEUE_REMOVE:
                left = rest_queue.remove(position, path)
                return f" Dropped {position} from the break queue; {len(left)} left."
            queued = rest_queue.append(entry, path)
        except ValueError as e:
            raise CommandError(str(e)) from e

        return f" Queued for a break: {rest_queue.label(entry)} ({len(queued)} waiting)."

    def sort_visible_table(self, table):
        """Cycle the column under the cursor: ascending, descending, as stored."""
        column = table.currentIndex().column()
        if column < 0:
            return
        view = self.filterable_view()
        if view is None:
            return
        proxy = view.proxy_for(table.table_idx)
        current_column = proxy.sortColumn()
        order = proxy.sortOrder()

        if current_column != column:
            proxy.sort(column, Qt.SortOrder.AscendingOrder)
            direction = "ascending"
        elif order == Qt.SortOrder.AscendingOrder:
            proxy.sort(column, Qt.SortOrder.DescendingOrder)
            direction = "descending"
        else:
            proxy.sort(-1, Qt.SortOrder.AscendingOrder)
            direction = "the order the ledger is stored in"

        header = view.headers[table.table_idx][column]
        self.status_bar.setText(f" Sorted by {header}, {direction}.")

    def _on_tab_changed(self, index):
        """Handle arrival at a tab."""
        self.command_line.set_relevant_domains(self._tab_subject(index))
        default_cmd = self.tab_default_commands.get(index, None)
        self.command_line.set_default_command(default_cmd)

        if self._filter_open:
            self.close_filter()

        if self.current_mode != "NORMAL":
            self.return_to_normal()

        if index not in self.dirty_tabs:
            return
        self._refresh_tab(index, veil=True)

    def _refresh_visible_tab(self):
        """Refresh the visible tab after a data change."""
        index = self.tabs.currentIndex()
        if index not in self.dirty_tabs:
            return
        self._refresh_tab(index, veil=False)

    def _refresh_tab(self, index, veil: bool):
        """Dispatch the refresh of tab index, veiled or in place."""
        widget = self.tabs.widget(index)
        self.dirty_tabs.discard(index)
        if not hasattr(widget, "refresh"):
            return

        if veil:
            self.tab_animator.cover(index)
            self.status_bar.setText(" Reading…")
        widget.refresh()
        if veil:
            self._settle_tab_when_read(index, widget)

    def _settle_tab_when_read(self, index, widget):
        """Reveal the tab once its refresh has landed."""
        self._reveal_poll.start(self.REVEAL_POLL_MS)

    def _on_reveal_poll(self):
        """Uncover the visible tab once nothing is still being read for it."""
        if QThreadPool.globalInstance().activeThreadCount() > 0:
            return
        self._reveal_poll.stop()
        self.tab_animator.reveal()
        if self.status_bar.text() == " Reading…":
            self.status_bar.setText("")

    def keyPressEvent(self, event):
        k = event.key()

        if self.current_mode == "NORMAL":
            target_idx = self._tab_key_index.get(k)
            if target_idx is not None:
                if target_idx < self.tabs.count():
                    self.tabs.setCurrentIndex(target_idx)
            elif k == self.key_cmd or k == Qt.Key.Key_Colon:
                self.enter_command()
            elif k == self.key_sheet:
                self.enter_sheet()
            elif k == self.key_filter or k == Qt.Key.Key_Slash:
                self.open_filter()
            elif k == Qt.Key.Key_D:
                self._set_nutrient_window(1, " Graphs: 1-Day Baseline Views.")
            elif k == Qt.Key.Key_W:
                self._set_nutrient_window(7, " Graphs: 7-Day Windowed Averages.")
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _set_nutrient_window(self, days, message):
        graphs = self.views.get('food_graphs')
        if not graphs:
            return
        graphs.set_rolling_period(days)
        self.status_bar.setText(message)
        self.status_pulser.pulse(PALETTE['base1'])

    def _report_failure(self, reason):
        self.status_bar.setText(f" Execution Fail: {reason}")
        self.status_pulser.pulse(PALETTE.get('red', '#dc322f'))

    def _show_optimistically(self, command, payload):
        """Put the row just written on screen, at once."""
        row = command.pending_row(payload)
        if row is None:
            return
        view = self.views.get(command.optimistic.view)
        show = getattr(view, "show_pending_row", None)
        if show is None:
            return
        show(row)

    def _apply_view_effect(self, command, payload):
        """Mirror the result of the one command a view must reflect at once."""
        effect = command.view_effect
        if effect is None:
            return
        view = self.views.get(effect.view)
        if view is None:
            return
        getattr(view, effect.method)(payload[effect.field])

    def execute_command(self):
        """Run whatever is in the command bar."""
        text = self.command_line.text().strip()
        if not text:
            self.return_to_normal()
            return

        if self._command_in_flight:
            return

        try:
            command, remainder = resolve(text)
            payload = command.parse(remainder)
        except Exception as e:  # broad: whatever a parser raised is still the status bar's answer
            self._report_failure(e)
            return

        if command.window_effect is not None:
            self._run_window_command(command, payload)
            return

        self._command_in_flight = True
        run_in_background(QThreadPool.globalInstance(), self._invoke_command,
                          self._on_command_finished, self._on_command_raised,
                          command, payload)

    def _run_window_command(self, command, payload):
        """Carry out a window command against the visible tab."""
        try:
            message = getattr(self, command.window_effect)(payload)
        except (CommandError, ColumnError, FilterError) as e:
            self._report_failure(e)
            return

        self.command_line.clear()
        self.return_to_normal()
        self.status_bar.setText(message or command.confirm(payload))
        self.status_pulser.pulse(PALETTE.get('blue', '#268bd2'))

    def _invoke_command(self, command, payload):
        """Perform the write on a pool thread."""
        success, message = command.invoke(self.db, payload)
        return command, payload, success, message

    def _on_command_finished(self, outcome):
        command, payload, success, message = outcome
        self._command_in_flight = False
        if not success:
            self._report_failure(message)
            return

        self.command_line.clear()
        self.return_to_normal()

        self.command_line.invalidate_catalog_cache()
        self._show_optimistically(command, payload)
        self.mark_domains_stale(command.domains)
        self._apply_view_effect(command, payload)

        self.status_bar.setText(
            message if command.reports_result else command.confirm(payload))
        self.status_pulser.pulse(PALETTE.get('blue', '#268bd2'))

    def _on_command_raised(self, failure):
        """Handle a client method that raised instead of returning a refusal."""
        error, _formatted = failure
        self._command_in_flight = False
        self._report_failure(error)
