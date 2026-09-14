#!/usr/bin/env python3

import logging
import re
import datetime
import numpy as np
from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtCore import QPoint

from src.config import PALETTE
from src.database.rows import SupplementLogRow
from src.domain.clock import as_displayed_date
from src.gui.graphs.base import BaseGraphView

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


class SupplementGraphView(BaseGraphView):
    def __init__(self, db):
        super().__init__(db)
        self.nutrients = []
        self.hover_data = {}

        self.install_canvas()
        self.ax = self.fig.add_subplot(111)
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

    def animate_node(self, node, wave):
        """Grow a node, a tick marker growing twice as far as a dot."""
        artist = node['artist']
        growth = 4 if artist.get_marker() == '|' else 2
        artist.set_markersize(node['base_size'] + (wave * growth))
        artist.set_alpha(0.4 + (wave * 0.4))

    WINDOW_DAYS = 7

    def _window_start(self):
        return (datetime.date.today()
                - datetime.timedelta(days=self.WINDOW_DAYS - 1)).isoformat()

    def reset_axes(self):
        self.ax.clear()
        self.ax.set_facecolor(PALETTE['base3'])

        self.ax.spines['bottom'].set_color(PALETTE['base01'])
        self.ax.spines['left'].set_visible(False)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.grid(True, axis='x', color=PALETTE['base2'], linestyle='--')

    def read_chart_data(self):
        return self.db.get_supplement_logs(self._window_start())

    def draw_chart(self, raw_logs):
        col_to_log_idx = {
            name: idx for idx, name in enumerate(SupplementLogRow._fields)
            if name.endswith(("_mcg", "_mg", "_g", "_iu"))
        }
        targets = self.profile.get_supplement_targets()
        self.nutrients = []

        for t in targets:
            column = log_column_for(t, col_to_log_idx)
            if column is None:
                log.warning("No supplement log column for target %r (key %r)",
                            t.get("name"), t.get("key"))
                continue
            self.nutrients.append(
                (t["name"], col_to_log_idx[column], t["target"], _unit_of(t["name"])))

        if not self.nutrients:
            self.ax.text(0.5, 0.5, "No Supplement Targets Configured or Matched against Database Schema",
                         ha='center', va='center', color=PALETTE['base01'], fontname='Fira Code')
            return

        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=i)).isoformat()
                 for i in range(self.WINDOW_DAYS - 1, -1, -1)]
        matrix = np.zeros((len(self.nutrients), self.WINDOW_DAYS))

        for row in raw_logs:
            try:
                day_idx = dates.index(row.date)
            except ValueError:
                continue

            for i, (_, db_idx, _, _) in enumerate(self.nutrients):
                if db_idx < len(row):
                    val = row[db_idx]
                    if val is not None:
                        matrix[i, day_idx] += float(val)

        y_pos = np.arange(len(self.nutrients))
        self.ax.invert_yaxis()
        self.ax.set_xlim(-35, 160)
        self.ax.set_xticks([0, 50, 100, 150])
        self.ax.set_xticklabels(['0%', '50%', '100%\nTarget', '150%'], color=PALETTE['base01'], fontname='Fira Code', fontsize=8)
        self.ax.set_yticks(y_pos)
        self.ax.set_yticklabels([n[0] for n in self.nutrients], fontname='Fira Code', fontsize=9, color=PALETTE['base02'], weight='bold')

        self.ax.axvline(0, color=PALETTE['base01'], linewidth=1.5, zorder=2)
        self.ax.axvline(100, color=PALETTE['base00'], linestyle=':', linewidth=1.5, zorder=2)
        self.ax.text(-17.5, -0.8, "7D Streak", ha='center', color=PALETTE['base01'], fontsize=8, fontname='Fira Code', weight='bold')

        dot_x = np.linspace(-30, -5, 7)
        self.hover_data.clear()

        for i, (name, db_idx, target, unit) in enumerate(self.nutrients):
            daily_amounts = matrix[i]
            avg_intake = sum(daily_amounts) / self.WINDOW_DAYS
            today_intake = daily_amounts[-1]
            pct = (today_intake / target) * 100.0 if target > 0 else 0.0

            self.hover_data[i] = {
                "name": name, "target": target, "unit": unit,
                "daily": daily_amounts, "avg": avg_intake, "today": today_intake,
                "pct": pct, "dates": dates
            }

            for day_idx in range(7):
                amt = daily_amounts[day_idx]
                color = PALETTE['green'] if amt > 0 else PALETTE['base2']
                self.ax.scatter(dot_x[day_idx], i, color=color, s=25, zorder=5)

                if day_idx == 6 and amt > 0:
                    glow, = self.ax.plot([dot_x[6]], [i], marker='o', color=PALETTE['green'], alpha=0.6, markersize=6, zorder=4, animated=True)
                    self.anim_nodes.append({'artist': glow, 'ax': self.ax, 'base_size': 5})

            bar_width = min(pct, 155.0)

            if pct < 50: bar_color = PALETTE['red']
            elif pct < 90: bar_color = PALETTE['yellow']
            elif pct <= 120: bar_color = PALETTE['green']
            else: bar_color = PALETTE['magenta']

            self.ax.barh(i, 150, color=PALETTE['base2'], height=0.4, alpha=0.3, zorder=1)
            self.ax.barh(i, bar_width, color=bar_color, height=0.4, alpha=0.85, zorder=3)

            text_x = bar_width + 3
            self.ax.text(text_x, i, f"{today_intake:.0f} {unit} ({pct:.0f}%)", va='center', color=PALETTE['base01'], fontsize=8, fontname='Fira Code')

            if pct > 0:
                glow_edge, = self.ax.plot([bar_width], [i], marker='|', color=bar_color, alpha=0.6, markersize=12, markeredgewidth=2, zorder=4, animated=True)
                self.anim_nodes.append({'artist': glow_edge, 'ax': self.ax, 'base_size': 10})

        self.ax.set_title("Biological Saturation & Consistency Matrix (Today vs Target, 7-Day Streak)", color=PALETTE['base02'], fontsize=10, fontname='Fira Code', weight='bold', pad=15)

    def on_hover(self, event):
        if event.inaxes != self.ax or event.ydata is None:
            if self._last_hovered is not None:
                QToolTip.hideText()
                self._last_hovered = None
            return

        idx = int(round(event.ydata))
        if not hasattr(self, 'nutrients') or idx < 0 or idx >= len(self.nutrients):
            return

        if self._last_hovered == idx:
            return

        data = self.hover_data.get(idx)
        if not data:
            return

        lines = [
            f"Nutrient: {data['name']}",
            f"Optimum Target: {data['target']:.0f} {data['unit']}/day",
            f"Today: {data['today']:.1f} {data['unit']} ({data['pct']:.0f}%)",
            f"7-Day Saturation: {data['avg']:.1f} {data['unit']}/day",
            "─" * 24
        ]

        for d_str, amt in zip(data['dates'], data['daily']):
            lines.append(f"[{as_displayed_date(d_str)}]: {amt:.1f} {data['unit']}")

        text = "\n".join(lines)
        QToolTip.setFont(QFont("Fira Code", 10))
        QToolTip.showText(QCursor.pos() + QPoint(15, 15), text, self.canvas)
        self._last_hovered = idx
