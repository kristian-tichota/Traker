from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenu
from PyQt6.QtCore import QThreadPool, pyqtSignal
from src.config import PALETTE
from src.domain.clock import as_displayed_date, as_stored_date
from src.gui.animations import ChangeGlow
from src.gui.columns import ColumnLayout, setting_key
from src.gui.components.vim_table_view import VimTableView
from src.gui.domains import domain_of_table
from src.gui.lifecycle import ShutdownMixin
from src.database.rows import MatchedTotals
from src.gui.models.filter_proxy import FilterProxyModel
from src.gui.models.log_table import (DATE_HEADERS, LogTableModel,
                                      editable_columns)
from src.gui.workers import run_in_background

SUMMARY_PARTS = (
    ("servings", "Servings", "{:g} servings"),
    ("grams", "Grams", "{:,.0f} g"),
    ("energy_kcal", "Calories", "{:,.0f} kcal"),
    ("protein_g", "Protein", "{:,.0f} g protein"),
    ("carbs_g", "Carbs", "{:,.0f} g carbs"),
    ("fat_g", "Fats", "{:,.0f} g fat"),
)

ESTIMATE_PART = ("estimated_rows", "Est", "{:,.0f} estimated")

LEDGER_STRETCH, RIGHT_COLUMN_STRETCH = 6, 4
CATALOG_STRETCH, SETS_STRETCH = 6, 4


def lay_out_tables(into, ledger, catalog, sets_pane):
    """Place a domain tab's three panes at the stretches above."""
    right_column = QVBoxLayout()
    right_column.addLayout(catalog, CATALOG_STRETCH)
    right_column.addLayout(sets_pane, SETS_STRETCH)
    into.addLayout(ledger, LEDGER_STRETCH)
    into.addLayout(right_column, RIGHT_COLUMN_STRETCH)
    return into


def summary_line(totals, headers) -> str:
    """Build the line under a filtered table: how much of what, over what span."""
    parts = [f"{totals.rows:,} row" + ("" if totals.rows == 1 else "s")]
    present = set(headers)
    for field, header, template in SUMMARY_PARTS:
        if header in present:
            parts.append(template.format(getattr(totals, field)))
    field, header, template = ESTIMATE_PART
    if header in present and getattr(totals, field):
        parts.append(template.format(getattr(totals, field)))
    if totals.first_date and totals.last_date:
        first = as_displayed_date(totals.first_date)
        last = as_displayed_date(totals.last_date)
        parts.append(first if first == last else f"{first} → {last}")
    return " · ".join(parts)


class BaseManagedView(ShutdownMixin, QWidget):
    """A tab of one or two editable tables."""

    DATE_HEADERS = DATE_HEADERS

    data_changed = pyqtSignal(str)

    status_message = pyqtSignal(str)

    command_requested = pyqtSignal(str)

    def __init__(self, db, tables, headers, mappings):
        """Build one entry per table this view hosts, indexed by table_idx."""
        super().__init__()
        self.db = db
        self.tables = tables
        self.headers = headers
        self.mappings = mappings
        self.threadpool = QThreadPool.globalInstance()
        self._table_widgets = {}
        self._table_models = {}
        self._table_proxies = {}
        self._table_glows = {}
        self.summary_label = None
        self._table_titles = {}
        self._layouts_loaded = False
        self._arranged = set()
        self._fold_wanted = set()

    def fetch(self, fn, on_result, *args, **kwargs):
        """Read or write through the thread pool, with both outcomes wired."""
        return run_in_background(
            self.threadpool, fn, on_result, self._report_background_failure, *args, **kwargs)

    def fetch_table(self, table_idx, fn, *args, **kwargs):
        """Read rows off-thread and put them in table table_idx."""
        receivers = (self._populate_first_table, self._populate_second_table,
                     self._populate_third_table)
        return self.fetch(fn, receivers[table_idx], *args, **kwargs)

    def _populate_first_table(self, data):
        self.set_rows(0, data)

    def _populate_second_table(self, data):
        self.set_rows(1, data)

    def _populate_third_table(self, data):
        self.set_rows(2, data)

    def _report_background_failure(self, failure):
        error, _formatted = failure
        self.status_message.emit(f" Background call failed: {error}")

    def editable_columns(self, table_idx=0):
        """Return the column indices that may be typed into, from the mapping."""
        return editable_columns(self.headers[table_idx], self.mappings[table_idx])

    def build_table_layout(self, title: str, headers: list, table_idx: int):
        layout = QVBoxLayout()
        self._table_titles[table_idx] = title
        if title:
            layout.addWidget(QLabel(f"<b>{title}</b>"))

        table = VimTableView(table_idx)
        model = LogTableModel(headers, self.mappings[table_idx], table_idx,
                              parent=table, date_headers=self.DATE_HEADERS)
        proxy = FilterProxyModel(table)
        proxy.setSourceModel(model)
        table.setModel(proxy)
        self._table_widgets[table_idx] = table
        self._table_models[table_idx] = model
        self._table_proxies[table_idx] = proxy
        self._table_glows[table_idx] = ChangeGlow(model, parent=table)

        model.edit_requested.connect(self.on_cell_edited)
        table.context_menu_requested.connect(self.on_context_menu_requested)
        table.header_menu_requested.connect(self.on_header_menu_requested)
        table.columns_rearranged.connect(self.on_columns_rearranged)

        layout.addWidget(table)
        if table_idx == 0:
            self.summary_label = QLabel("")
            self.summary_label.setStyleSheet(
                f"color: {PALETTE['base01']}; padding: 2px 4px;")
            self.summary_label.hide()
            layout.addWidget(self.summary_label)
        return layout, table

    def model_for(self, table_idx=0):
        return self._table_models[table_idx]

    def glow_for(self, table_idx=0):
        return self._table_glows[table_idx]

    def show_pending_row(self, row, table_idx=0):
        """Show a row the store has confirmed but not yet described."""
        position = self._table_models[table_idx].insert_pending_row(row)
        self._table_glows[table_idx].start()
        return position

    def showEvent(self, event):
        """Read this member's column layouts on arrival at the tab."""
        super().showEvent(event)
        self.load_column_layouts()

    def shutdown(self):
        """Stop the row washes before the timers, then hand on up the MRO."""
        for glow in self._table_glows.values():
            glow.stop()
        super().shutdown()

    def set_rows(self, table_idx, data):
        """Put data in table table_idx."""
        model = self._table_models[table_idx]
        widget = self._table_widgets[table_idx]
        keep = self._cursor_identity(widget)
        model.set_rows(data)
        widget.measure_columns_once()
        self._restore_cursor(widget, keep)
        self._table_glows[table_idx].start()
        self._update_summary(table_idx)
        if table_idx in self._fold_wanted:
            self._warm_fold(table_idx)

    def _cursor_identity(self, widget):
        """Return (row id, column) under the cursor, or None where it has none."""
        index = widget.currentIndex()
        if not index.isValid():
            return None
        proxy = widget.model()
        source = proxy.mapToSource(index) if hasattr(proxy, "mapToSource") else index
        model = self._table_models[widget.table_idx]
        return model.row_id(source), index.column()

    def _restore_cursor(self, widget, keep):
        """Put the cursor back on its row, where that row is still here."""
        if keep is None:
            return
        row_id, column = keep
        if row_id is None:
            return
        model = self._table_models[widget.table_idx]
        for position, row in enumerate(model.rows):
            if len(row) and row[0] == row_id:
                index = model.index(position, column)
                proxy = widget.model()
                if hasattr(proxy, "mapFromSource"):
                    index = proxy.mapFromSource(index)
                if index.isValid():
                    widget.setCurrentIndex(index)
                return

    def warm_fold(self, table_idx=0):
        """Fold the rows for matching, off the interface thread."""
        self._fold_wanted.add(table_idx)
        self._warm_fold(table_idx)

    def _warm_fold(self, table_idx):
        if not self._table_models[table_idx].rows:
            return
        self.fetch(self._fold_rows, self._adopt_fold, table_idx)

    def _fold_rows(self, table_idx):
        model = self._table_models[table_idx]
        rows = model.rows
        return table_idx, rows, model.fold_all(rows)

    def _adopt_fold(self, payload):
        """Adopt a fold for the table the payload names."""
        table_idx, rows, prebuilt = payload
        self._table_models[table_idx].adopt_fold(prebuilt, rows)

    def fold_is_warm(self, table_idx=0) -> bool:
        model = self._table_models[table_idx]
        return len(model._folded) >= model.rowCount()

    def populate_table(self, table, data, table_idx=0):
        """Put data in table table_idx, under the alternative name."""
        self.set_rows(table_idx, data)

    def table_title(self, table_idx=0) -> str:
        """Return what the heading over this table calls it, for a status line."""
        return self._table_titles.get(table_idx) or self.tables[table_idx]

    def column_layout(self, table_idx=0) -> ColumnLayout:
        """Return what table table_idx is showing, in the order it shows it."""
        return self._table_widgets[table_idx].column_layout(self.headers[table_idx])

    def apply_column_layout(self, table_idx, layout) -> None:
        """Show layout without storing it."""
        self._table_widgets[table_idx].arrange_columns(self.headers[table_idx], layout)
        self._update_summary(table_idx)

    def set_column_layout(self, table_idx, layout) -> None:
        """Show layout and remember it for this member."""
        self.apply_column_layout(table_idx, layout)
        self._store_column_layout(table_idx, layout)

    def load_column_layouts(self) -> None:
        """Read this member's stored layouts and apply them, once per view."""
        if self._layouts_loaded or self.is_shut_down():
            return
        self._layouts_loaded = True
        self.fetch(self._read_column_layouts, self._adopt_column_layouts)

    def _read_column_layouts(self):
        """Read the stored layouts on the pool thread."""
        keys = [setting_key(self.tables[table_idx])
                for table_idx in sorted(self._table_widgets)]
        return self.db.get_settings(keys, {key: "" for key in keys})

    def _adopt_column_layouts(self, answered):
        for table_idx in sorted(self._table_widgets):
            if table_idx in self._arranged:
                continue
            stored = answered.get(setting_key(self.tables[table_idx]), "")
            if not stored:
                continue
            self.apply_column_layout(
                table_idx, ColumnLayout.parse(stored, self.headers[table_idx]))

    def _store_column_layout(self, table_idx, layout):
        self._arranged.add(table_idx)
        self.fetch(self._write_column_layout, self._on_column_layout_stored,
                   self.tables[table_idx], layout.encoded)

    def _write_column_layout(self, table, encoded):
        """Write one column layout on the pool thread."""
        return self.db.set_setting(setting_key(table), encoded)

    def _on_column_layout_stored(self, outcome):
        """Report a refusal, the columns being on screen already."""
        success, message = outcome
        if not success:
            self.status_message.emit(f" Column layout not saved: {message}")

    def on_columns_rearranged(self, table_index):
        """Store where a dragged heading landed."""
        self._store_column_layout(table_index, self.column_layout(table_index))

    def on_header_menu_requested(self, table_index, pos):
        """Offer the columns this table shows, from the header menu."""
        table_widget = self._table_widgets[table_index]
        layout = self.column_layout(table_index)
        menu = QMenu()
        columns = {}
        for name in layout.order:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(not layout.is_hidden(name))
            action.setEnabled(layout.is_hidden(name) or layout.can_hide(name))
            columns[action] = name
        menu.addSeparator()
        reset = menu.addAction("Reset Column Layout")

        chosen = menu.exec(table_widget.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is reset:
            self.set_column_layout(
                table_index, ColumnLayout.declared(self.headers[table_index]))
            return
        if chosen in columns:
            self.set_column_layout(table_index, layout.toggled(columns[chosen]))

    def proxy_for(self, table_idx=0):
        return self._table_proxies[table_idx]

    def apply_filter(self, query, table_idx=0):
        """Show only the rows matching query, and describe what is left."""
        self._table_proxies[table_idx].set_query(query)
        self._update_summary(table_idx)

    def clear_filter(self, table_idx=0):
        self._table_proxies[table_idx].clear_query()
        self._update_summary(table_idx)

    def sort_by(self, column, order, table_idx=0):
        self._table_proxies[table_idx].sort(column, order)

    def clear_sort(self, table_idx=0):
        """Return to the order the service answered in."""
        from PyQt6.QtCore import Qt as _Qt

        self._table_proxies[table_idx].sort(-1, _Qt.SortOrder.AscendingOrder)

    def matched_totals(self, table_idx=0):
        return MatchedTotals.of(self._table_proxies[table_idx].matched_rows())

    def _update_summary(self, table_idx=0):
        """Update the line under the table with what the matched set comes to."""
        if self.summary_label is None or table_idx != 0:
            return
        proxy = self._table_proxies[table_idx]
        if not proxy.is_filtered():
            self.summary_label.hide()
            return
        self.summary_label.setText(summary_line(self.matched_totals(table_idx),
                                                self.column_layout(table_idx).visible))
        self.summary_label.show()

    def on_context_menu_requested(self, table_index, pos):
        self.show_context_menu(self._table_widgets[table_index], table_index, pos)

    def show_context_menu(self, table_widget, table_index, pos):
        index = table_widget.indexAt(pos)
        if not index.isValid():
            return
        index = self._table_proxies[table_index].mapToSource(index)
        row_id = self._table_models[table_index].row_id(index)
        if row_id is None:
            return

        menu = QMenu()
        delete_action = menu.addAction("Delete Selected Record")
        action = menu.exec(table_widget.mapToGlobal(pos))

        if action == delete_action:
            self.fetch(self._delete_row, self._on_delete_finished,
                       self.tables[table_index], row_id)

    def domain_of(self, table_idx=0):
        """Return the household subject this view's table belongs to."""
        return domain_of_table(self.tables[table_idx]) or ""

    def _delete_row(self, table, row_id):
        """Delete on the pool thread, carrying the table name back out."""
        success, msg = self.db.delete_record(table, row_id)
        return table, success, msg

    def _on_delete_finished(self, outcome):
        table, success, msg = outcome
        if not success:
            self.status_message.emit(f" Deletion refused: {msg}")
            return
        self.status_message.emit(f" Deleted one row from '{table}'.")
        self.data_changed.emit(domain_of_table(table) or "")

    def on_cell_edited(self, table_target, row_id, col_name, new_val):
        """Send an edited cell to the store, off the interface thread."""
        if col_name in self.DATE_HEADERS:
            new_val = as_stored_date(new_val)

        self.fetch(
            self._write_edit, self._on_edit_finished,
            self.tables[table_target], row_id, col_name, new_val, self.mappings[table_target],
        )

    def _write_edit(self, table, row_id, col_name, new_val, mapping):
        """PATCH on the pool thread, carrying the table name back out."""
        success, msg = self.db.update_record(table, row_id, col_name, new_val, mapping)
        return table, success, msg

    def _on_edit_finished(self, outcome):
        table, success, msg = outcome
        self.status_message.emit(" Saved." if success else f" Edit refused: {msg}")
        self.data_changed.emit(domain_of_table(table) or "")
