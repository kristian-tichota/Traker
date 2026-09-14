import datetime
import numpy as np
from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtCore import QPoint
import matplotlib.collections as mcoll
import matplotlib.colors as mcolors
import matplotlib.patches as patches
from matplotlib.path import Path

from src.config import PALETTE
from src.domain import formulas
from src.domain.clock import ISO_DATE, as_displayed_date, minutes_of_day
from src.gui.graphs.base import BaseGraphView

SHORT_DATE = "%d.%m."


class CaffeineGraphView(BaseGraphView):
    def __init__(self, db):
        super().__init__(db)
        self.hover_data = {}
        self.hover_dates_list = []

        self.install_canvas()
        self.ax = self.fig.add_subplot(111)
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

    def reset_axes(self):
        self.ax.clear()
        self.ax.set_facecolor(PALETTE['base3'])
        self.ax.spines['bottom'].set_color(PALETTE['base01'])
        self.ax.spines['left'].set_color(PALETTE['base01'])
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.tick_params(colors=PALETTE['base00'], labelsize=8)
        self.ax.grid(True, color=PALETTE['base2'], linestyle='--')

    def read_chart_data(self):
        return self.db.get_beverage_logs(self._window_start())

    WINDOW_DAYS = 30

    def _window_start(self):
        return (datetime.date.today()
                - datetime.timedelta(days=self.WINDOW_DAYS - 1)).isoformat()

    def draw_chart(self, raw_logs):
        sleep_str = str(self.profile.get_metric("goals", "sleep_time", "23:00")).strip()
        half_life = float(self.profile.get_metric("goals", "caffeine_half_life", 5.0))
        threshold = float(self.profile.get_metric("goals", "max_sleep_caffeine", 20.0))

        sleep_mins = minutes_of_day(sleep_str, default=23 * 60)

        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=i)).isoformat()
                 for i in range(self.WINDOW_DAYS - 1, -1, -1)]
        daily_data = {d: {'total': 0.0, 'residual': 0.0, 'logs': 0} for d in dates}

        for row in raw_logs:
            log_date = row.date
            if log_date not in daily_data:
                continue

            caff_mg = row.caffeine_mg or 0.0
            log_mins = minutes_of_day(row.time, default=0)
            residual = formulas.residual_at_bedtime(caff_mg, log_mins, sleep_mins, half_life)
            daily_data[log_date]['total'] += caff_mg
            daily_data[log_date]['residual'] += residual
            daily_data[log_date]['logs'] += 1

        x_dates = np.arange(len(dates))
        y_residuals = np.array([daily_data[d]['residual'] for d in dates])

        cmap = mcolors.LinearSegmentedColormap.from_list('g2m', [PALETTE['green'], PALETTE['magenta']])
        norm = mcolors.Normalize(vmin=threshold - 0.5, vmax=threshold + 10.0)

        x_dense = np.linspace(x_dates.min(), x_dates.max(), 1000)
        y_dense = np.interp(x_dense, x_dates, y_residuals)

        points = np.array([x_dense, y_dense]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        lc = mcoll.LineCollection(segments, cmap=cmap, norm=norm, linewidth=1.5, zorder=4)
        lc.set_array(y_dense)
        self.ax.add_collection(lc)

        verts = [(x_dense[0], 0)] + list(zip(x_dense, y_dense)) + [(x_dense[-1], 0)]
        codes = [Path.MOVETO] + [Path.LINETO] * len(x_dense) + [Path.LINETO]
        path = Path(verts, codes)
        patch = patches.PathPatch(path, facecolor='none', lw=0)
        self.ax.add_patch(patch)

        y_max = max(y_dense.max(), threshold + 5.0)
        gradient = np.linspace(0, y_max, 256).reshape(-1, 1)

        im = self.ax.imshow(gradient, aspect='auto', cmap=cmap, norm=norm,
                            origin='lower', extent=[x_dates.min(), x_dates.max(), 0, y_max],
                            alpha=0.35, zorder=2)
        im.set_clip_path(patch)

        self.ax.scatter(x_dates, y_residuals, c=y_residuals, cmap=cmap, norm=norm,
                        marker='o', s=35, zorder=5)

        pad_y = max(y_residuals.max() * 1.15, threshold + 10.0)
        self.ax.set_xlim(x_dates.min() - 0.5, x_dates.max() + 0.5)
        self.ax.set_ylim(0, pad_y)

        self.ax.axhline(threshold, color=PALETTE['magenta'], linestyle=':', linewidth=1.2, alpha=0.6, zorder=5)
        self.ax.text(x_dates.min(), threshold + (pad_y * 0.02), f"Sleep Disturbance Threshold ({threshold}mg)",
                     color=PALETTE['magenta'], fontsize=8, fontname='Fira Code', alpha=0.8, zorder=6)

        self.ax.set_title("Pharmacokinetic Caffeine Residuals at Sleep Time (30-Day)",
                          color=PALETTE['base02'], fontsize=10, fontname='Fira Code', weight='bold')
        self.ax.set_ylabel("Residual Caffeine (mg)", color=PALETTE['base01'], fontname='Fira Code', fontsize=9)

        x_labels = [datetime.datetime.strptime(d, ISO_DATE).strftime(SHORT_DATE) for d in dates]
        self.ax.set_xticks(x_dates[::3])
        self.ax.set_xticklabels(x_labels[::3])

        res_color = cmap(norm(y_residuals[-1]))
        glow_res, = self.ax.plot([x_dates[-1]], [y_residuals[-1]], marker='o',
                                 color=res_color, alpha=0.6, markersize=7, zorder=6, animated=True)
        self.anim_nodes.append({'artist': glow_res, 'ax': self.ax, 'base_size': 5})

        self.hover_data = daily_data
        self.hover_dates_list = dates

    def on_hover(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            if self._last_hovered is not None:
                QToolTip.hideText()
                self._last_hovered = None
            return

        idx = int(round(event.xdata))
        if idx < 0 or idx >= len(self.hover_dates_list):
            return

        current_hover = idx
        if self._last_hovered == current_hover:
            return

        date_str = self.hover_dates_list[idx]
        data = self.hover_data.get(date_str)
        if data is None:
            return

        QToolTip.setFont(QFont("Fira Code", 10))
        QToolTip.showText(QCursor.pos() + QPoint(15, 15),
                          self.hover_text(date_str, data), self.canvas)

        self._last_hovered = current_hover

    def hover_text(self, date_str, data) -> str:
        """What one day of the window says when the cursor is on it."""
        threshold = float(self.profile.get_metric("goals", "max_sleep_caffeine", 20.0))
        breach = data['residual'] - threshold

        lines = [f"Date: {as_displayed_date(date_str)}",
                 "─" * 22,
                 f"Est. at Sleep: {data['residual']:.0f} mg",
                 f"Total Intake: {data['total']:.0f} mg ({data['logs']} drinks)"]
        if breach > 0:
            lines.append(f"Warning: +{breach:.0f} mg over threshold")
        else:
            lines.append(f"Headroom: {-breach:.0f} mg under threshold")
        return "\n".join(lines)
