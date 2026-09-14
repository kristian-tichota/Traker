import datetime
import math
from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtCore import QPoint
import matplotlib.patches as patches
import matplotlib.colors as mcolors
from matplotlib.collections import PatchCollection

from src.config import PALETTE
from src.domain.activity import kcal_from_met_hours
from src.gui.graphs.base import BaseGraphView


def calendar_start(today: datetime.date) -> datetime.date:
    """The first day the activity calendar shows: the 1st of the month two months back."""
    month, year = today.month - 2, today.year
    if month <= 0:
        month += 12
        year -= 1
    return datetime.date(year, month, 1)

CELL = 0.85


class ActivityHeatmapView(BaseGraphView):
    PULSE_INTERVAL_MS = 30

    def __init__(self, db):
        super().__init__(db)
        self.cells = {}
        self.hover_glow = None

        self.install_canvas()
        self.ax = self.fig.add_subplot(111)
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

    def _hover_is_lit(self):
        return self.hover_glow is not None and self.hover_glow.get_visible()

    def has_animation(self):
        return bool(self.anim_nodes) or self._hover_is_lit()

    PULSE_SPEED = 3.5

    def animate_node(self, node, wave):
        """A calendar node is an outline around today, not a marker."""
        node['artist'].set_linewidth(1.0 + (wave * 2.0))
        node['artist'].set_alpha(0.5 + (wave * 0.5))

    def draw_extra_artists(self):
        if self._hover_is_lit():
            hover_wave = self.wave(7.0)
            self.hover_glow.set_linewidth(1.5 + (hover_wave * 1.5))
            self.hover_glow.set_alpha(0.6 + (hover_wave * 0.4))
            self.ax.draw_artist(self.hover_glow)

    def reset_axes(self):
        self.ax.clear()
        self.ax.set_facecolor(PALETTE['base3'])
        self.ax.axis('off')
        self.cells.clear()

        self.hover_glow = patches.Rectangle((0, 0), CELL, CELL, fill=False, edgecolor=PALETTE['blue'], linewidth=2.0, zorder=10, animated=True)
        self.hover_glow.set_visible(False)
        self.ax.add_patch(self.hover_glow)

    def read_chart_data(self):
        return self.db.get_activity_heatmap_data(
            calendar_start(datetime.date.today()).isoformat())

    def draw_chart(self, data):
        weight = float(self.profile.get_metric("biometrics", "weight_kg", 75.0))

        today = datetime.date.today()
        start_date = calendar_start(today)

        days_total = (today - start_date).days + 1
        dates = [start_date + datetime.timedelta(days=i) for i in range(days_total)]

        base2 = mcolors.to_rgb(PALETTE['base2'])
        green = mcolors.to_rgb(PALETTE['green'])

        def get_color(val):
            if val <= 0: return PALETTE['base2']
            ratio = min(val / 1000.0, 1.0)
            r = base2[0] + (green[0] - base2[0]) * ratio
            g = base2[1] + (green[1] - base2[1]) * ratio
            b = base2[2] + (green[2] - base2[2]) * ratio
            return (r, g, b)

        day_labels = {6: "Mon", 4: "Wed", 2: "Fri"}
        for y, label in day_labels.items():
            self.ax.text(-0.5, y + 0.425, label, color=PALETTE['base01'], fontsize=8, ha='right', va='center', fontname='Fira Code')

        last_month = -1
        squares = []
        for d in dates:
            d_iso = d.isoformat()
            day_data = data.get(d_iso, {"breakdown": {}})

            breakdown = day_data.get("breakdown", {})
            mob_kcal = kcal_from_met_hours(breakdown.get("Mobility", 0.0), weight)
            ex_kcal = kcal_from_met_hours(breakdown.get("Exercise_MET_hrs", 0.0), weight)

            extra_kcal = mob_kcal + ex_kcal
            day_data["extra_kcal"] = extra_kcal
            day_data["mob_kcal"] = mob_kcal
            day_data["ex_kcal"] = ex_kcal

            diff_days = (d - start_date).days
            x = (diff_days + start_date.weekday()) // 7
            y = 6 - d.weekday()

            squares.append(patches.Rectangle((x, y), CELL, CELL, facecolor=get_color(extra_kcal),
                                             edgecolor=PALETTE['base1'], linewidth=0.3))
            self.cells[(x, y)] = {'date': d_iso, 'data': day_data}

            text_color = PALETTE['base01'] if extra_kcal == 0 else PALETTE['base03']
            font_weight = 'bold' if extra_kcal > 0 else 'normal'

            if extra_kcal > 0:
                self.ax.text(x + 0.425, y + 0.55, str(d.day), color=text_color, fontsize=8, ha='center', va='center', fontname='Fira Code', weight=font_weight)
                self.ax.text(x + 0.425, y + 0.25, f"{extra_kcal:.0f} kcal", color=text_color, fontsize=5.5, ha='center', va='center', fontname='Fira Code')
            else:
                self.ax.text(x + 0.425, y + 0.425, str(d.day), color=text_color, fontsize=8, ha='center', va='center', fontname='Fira Code', weight=font_weight)

            next_day = d + datetime.timedelta(days=1)
            next_week = d + datetime.timedelta(days=7)

            if d.month != next_day.month and d.weekday() != 6:
                self.ax.plot([x - 0.075, x + 0.925], [y - 0.075, y - 0.075], color=PALETTE['base01'], linewidth=2)

            if d.month != next_week.month:
                self.ax.plot([x + 0.925, x + 0.925], [y - 0.075, y + 0.925], color=PALETTE['base01'], linewidth=2)

            if d.month != last_month and d.day <= 7:
                self.ax.text(x, 7.5, d.strftime("%b"), color=PALETTE['base00'], fontsize=10, ha='left', fontname='Fira Code', weight='bold')
                last_month = d.month

            if d == today:
                today_glow = patches.Rectangle((x, y), CELL, CELL, fill=False, edgecolor=PALETTE['cyan'], linewidth=1.5, zorder=5, animated=True)
                self.ax.add_patch(today_glow)
                self.anim_nodes.append({
                    'artist': today_glow,
                    'ax': self.ax
                })

        self.ax.add_collection(PatchCollection(squares, match_original=True),
                               autolim=False)

        self.ax.set_xlim(-1.5, (days_total + start_date.weekday()) // 7 + 1)
        self.ax.set_ylim(-0.5, 8.5)

    def cell_under(self, xdata, ydata):
        """The day whose square holds this point, or None."""
        if xdata is None or ydata is None:
            return None
        column, row = math.floor(xdata), math.floor(ydata)
        if (xdata - column) > CELL or (ydata - row) > CELL:
            return None
        return self.cells.get((column, row))

    def on_hover(self, event):
        cell = self.cell_under(event.xdata, event.ydata) if event.inaxes == self.ax else None

        if cell is None:
            if self._last_hovered is not None:
                QToolTip.hideText()
                self._last_hovered = None
                if self.hover_glow is not None:
                    self.hover_glow.set_visible(False)
            return

        date_str = cell['date']
        if self._last_hovered == date_str:
            return

        QToolTip.setFont(QFont("Fira Code", 10))
        QToolTip.showText(QCursor.pos() + QPoint(15, 15),
                          self.hover_text(date_str, cell['data']), self.canvas)

        if self.hover_glow is not None:
            column, row = math.floor(event.xdata), math.floor(event.ydata)
            self.hover_glow.set_xy((column, row))
            self.hover_glow.set_visible(True)

        self._last_hovered = date_str

    def hover_text(self, date_str, day_data) -> str:
        """What one day of the calendar says when the cursor is on it."""
        extra_kcal = day_data.get('extra_kcal', 0.0)
        if extra_kcal == 0:
            return f"Date: {date_str}\nNo Activity Logged"

        mob_kcal = day_data.get('mob_kcal', 0.0)
        ex_kcal = day_data.get('ex_kcal', 0.0)
        lines = [f"Date: {date_str}", "\u2500" * 16, f"Total Est. Burn: {extra_kcal:.0f} kcal\n"]
        if mob_kcal > 0:
            lines.append(f" \u2022 Mobility/Cardio: {mob_kcal:.0f} kcal")
        if ex_kcal > 0:
            lines.append(f" \u2022 Weight Training: {ex_kcal:.0f} kcal")
        return "\n".join(lines)
