#!/usr/bin/env python3

import datetime
import logging
import math
import re
from typing import NamedTuple

import numpy as np
from matplotlib.ticker import PercentFormatter

from src.config import PALETTE
from src.database.rows import SupplementLogRow
from src.domain.clock import as_displayed_date
from src.gui.graphs.base import WindowedGraphView, style_trend_axes

log = logging.getLogger(__name__)


def _unit_of(display_name: str) -> str:
    """Return the unit a target label carries: "mcg" in "B12 (mcg)"."""
    match = re.search(r'\((.*?)\)', display_name)
    return match.group(1).strip() if match else "units"


def _column_from_display_name(display_name: str) -> str:
    """Return the log column a target label spells out."""
    col_name = str(display_name).lower().strip()
    col_name = col_name.replace("(", "").replace(")", "").strip()
    return col_name.replace(" ", "_").replace("-", "_")


def log_column_for(target: dict, columns) -> str:
    """Return the supplement-log column this target measures, or None."""
    key = str(target.get("key") or "").strip().lower()
    if key:
        prefix = f"{key}_"
        for column in columns:
            if column.startswith(prefix):
                return column

    from_label = _column_from_display_name(target.get("name", ""))
    return from_label if from_label in columns else None


COLOURS = ('blue', 'cyan', 'green', 'yellow', 'orange', 'red', 'magenta', 'violet')

LABEL = {"fontname": "Fira Code"}


class Nutrient(NamedTuple):
    name: str
    column: str
    target: float
    unit: str


def _parsed(text):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def daily_amounts(raw_logs, columns, today: datetime.date):
    """Return each day from the first log to today, and every column's total per day."""
    logged = [(day, row) for day, row in ((_parsed(row.date), row) for row in raw_logs)
              if day is not None and day <= today]
    if not logged:
        return [], np.zeros((len(columns), 0))

    first = min(day for day, _ in logged)
    span = (today - first).days + 1
    matrix = np.zeros((len(columns), span))
    for day, row in logged:
        for i, column in enumerate(columns):
            matrix[i, (day - first).days] += float(getattr(row, column) or 0.0)
    dates = [(first + datetime.timedelta(days=offset)).isoformat() for offset in range(span)]
    return dates, matrix


class SupplementGraphView(WindowedGraphView):
    PERIOD_SETTING = "supplement_graph_period"

    DEFAULT_PERIOD = 7

    COLUMNS = 3

    def __init__(self, db):
        super().__init__(db)
        self.controls_layout.addStretch()
        self.axes = []
        self.hover_data = {}

        self.fetch(self._read_preferences, self._apply_preferences)

        self.install_canvas()
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

    def read_chart_data(self):
        return self.db.get_supplement_logs()

    def _tracked_nutrients(self) -> list:
        """Return the profile's targets that name a log column and a positive amount."""
        columns = [name for name in SupplementLogRow._fields
                   if name.endswith(("_mcg", "_mg", "_g", "_iu"))]
        nutrients = []
        for target in self.profile.get_supplement_targets():
            column = log_column_for(target, columns)
            if column is None:
                log.warning("No supplement log column for target %r (key %r)",
                            target.get("name"), target.get("key"))
            elif target["target"] > 0:
                nutrients.append(Nutrient(target["name"], column, target["target"],
                                          _unit_of(target["name"])))
        return nutrients

    def _say(self, message):
        """Replace every panel with one centred message."""
        self.fig.clear()
        self.axes = []
        self.fig.text(0.5, 0.5, message, ha='center', va='center',
                      color=PALETTE['base01'], **LABEL)

    def _grid(self, count):
        """Lay out count cleared panels, reusing the axes of a layout of the same size."""
        if len(self.axes) != count:
            self.fig.clear()
            columns = min(count, self.COLUMNS)
            grid = self.fig.subplots(math.ceil(count / columns), columns, squeeze=False).ravel()
            for spare in grid[count:]:
                self.fig.delaxes(spare)
            self.axes = list(grid[:count])
        for ax in self.axes:
            ax.clear()
            style_trend_axes(ax)

    def draw_chart(self, raw_logs):
        self.hover_data.clear()
        nutrients = self._tracked_nutrients()
        if not nutrients:
            self._say("No supplement targets above zero in the profile")
            return

        dates, amounts = daily_amounts(raw_logs or [], [n.column for n in nutrients],
                                       datetime.date.today())
        w = self.rolling_period
        if not dates:
            self._say("No supplements logged yet")
            return
        if len(dates) < w:
            self._say(f"{w}-day averages need {w} days;\nonly {len(dates)} recorded so far")
            return

        plot_dates = dates[w - 1:]
        x = np.arange(len(plot_dates))
        self._grid(len(nutrients))

        for index, (ax, nutrient, daily) in enumerate(zip(self.axes, nutrients, amounts)):
            colour = PALETTE[COLOURS[index % len(COLOURS)]]
            smoothed = self._compute_rolling_avg(daily, w)
            share = smoothed / nutrient.target * 100.0

            ax.plot(x, share, color=colour, marker='o', markersize=3, linewidth=1.5, zorder=3)
            ax.fill_between(x, 0, share, color=colour, alpha=0.04, zorder=1)
            ax.axhline(100, color=colour, linestyle=':', linewidth=1.2, alpha=0.6, zorder=2)
            ax.set_title(f"{nutrient.name} ({w}D Avg)", color=PALETTE['base02'], fontsize=10,
                         weight='bold', **LABEL)
            ax.set_xticks([])
            ax.set_ylim(bottom=0)
            ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
            ax.text(0.02, 0.92, f"Target: {nutrient.target:g} {nutrient.unit}",
                    transform=ax.transAxes, color=colour, fontsize=7.5, alpha=0.7,
                    bbox=dict(facecolor=PALETTE['base3'], edgecolor='none', pad=1.0, alpha=0.8),
                    **LABEL)

            glow, = ax.plot([x[-1]], [share[-1]], marker='o', color=colour, alpha=0.6,
                            markersize=7, zorder=4, animated=True)
            self.anim_nodes.append({'artist': glow, 'ax': ax, 'base_size': 5})
            self.hover_data[index] = {
                "name": nutrient.name, "target": nutrient.target, "unit": nutrient.unit,
                "window": w, "dates": plot_dates, "amounts": smoothed,
            }

    def on_hover(self, event):
        index = next((i for i, ax in enumerate(self.axes) if ax is event.inaxes), None)
        data = self.hover_data.get(index)
        if data is None or event.xdata is None:
            self.clear_hover()
            return
        day = min(max(int(round(event.xdata)), 0), len(data["dates"]) - 1)
        self.show_hover((index, day), self.hover_text(data, day))

    @staticmethod
    def hover_text(data, day: int) -> str:
        """Return what one nutrient's panel says for one day under the cursor."""
        amount, unit = data["amounts"][day], data["unit"]
        heading = (data["name"] if data["window"] <= 1
                   else f"{data['name']}, {data['window']}-day average")
        return "\n".join([
            heading,
            f"Target: {data['target']:g} {unit}/day",
            "\u2500" * 24,
            f"[{as_displayed_date(data['dates'][day])}]: {amount:.1f} {unit} "
            f"({amount / data['target'] * 100.0:.0f}%)",
        ])
