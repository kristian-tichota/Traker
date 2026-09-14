import numpy as np
from PyQt6.QtWidgets import QHBoxLayout, QComboBox, QLabel

from src.config import PALETTE
from src.gui.graphs.base import BaseGraphView
from src.gui.workers import discard


class FoodGraphView(BaseGraphView):
    def __init__(self, db):
        super().__init__(db)

        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(QLabel("<b>Rolling Average Window:</b>"))
        self.period_select = QComboBox()
        self.period_select.addItems(["1 Day (Raw)", "7 Days (Weekly Average)"])

        self.rolling_period = 1
        self.period_select.currentTextChanged.connect(self.on_period_changed)
        self.fetch(lambda: self.db.get_setting("food_graph_period", "1 Day (Raw)"),
                   self._apply_saved_period)
        self.controls_layout.addWidget(self.period_select)
        self.controls_layout.addStretch()
        self.main_layout.addLayout(self.controls_layout)

        self.install_canvas()
        self.axes = self.fig.subplots(2, 3)

    def _apply_saved_period(self, saved_period):
        self.period_select.blockSignals(True)
        self.period_select.setCurrentText(saved_period)
        self.period_select.blockSignals(False)
        self.rolling_period = 7 if "7" in str(saved_period) else 1
        self.refresh()

    def _remember_period(self, text):
        self.fetch(lambda: self.db.set_setting("food_graph_period", text), discard)

    def on_period_changed(self, text):
        self.rolling_period = 7 if "7" in text else 1
        self._remember_period(text)
        self.refresh()

    def set_rolling_period(self, days: int):
        self.rolling_period = days
        text = "7 Days (Weekly Average)" if days == 7 else "1 Day (Raw)"

        self.period_select.blockSignals(True)
        self.period_select.setCurrentText(text)
        self.period_select.blockSignals(False)

        self._remember_period(text)
        self.refresh()

    def _compute_rolling_avg(self, data: np.ndarray, window: int) -> np.ndarray:
        """Each point is the mean of that day and the window - 1 before it."""
        if window <= 1:
            return data
        if len(data) < window:
            return data[:0]
        return np.convolve(data, np.ones(window)/window, mode='valid')

    def _hatch_estimated(self, ax, plot_dates, smoothed_estimate):
        """Hatch the part of the calorie series that was guessed."""
        if not len(smoothed_estimate) or not smoothed_estimate.any():
            return
        ax.fill_between(plot_dates, 0, smoothed_estimate,
                        facecolor='none', edgecolor=PALETTE['orange'],
                        hatch='///', linewidth=0.0, alpha=0.55, zorder=2)
        ax.text(0.02, 0.80, "/// estimated", transform=ax.transAxes,
                color=PALETTE['orange'], fontsize=7.0, fontname='Fira Code',
                alpha=0.85,
                bbox=dict(facecolor=PALETTE['base3'], edgecolor='none',
                          pad=1.0, alpha=0.8))

    def reset_axes(self):
        for row in self.axes:
            for ax in row:
                ax.clear()
                ax.set_facecolor(PALETTE['base3'])
                ax.spines['bottom'].set_color(PALETTE['base01'])
                ax.spines['left'].set_color(PALETTE['base01'])
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.tick_params(colors=PALETTE['base00'], labelsize=8)
                ax.grid(True, color=PALETTE['base2'], linestyle='--')

    def read_chart_data(self):
        return self.db.get_daily_aggregates()

    def draw_chart(self, raw_data):
        if not raw_data:
            return

        dates = [r.date for r in raw_data]
        calories = np.array([r.energy_kcal for r in raw_data])
        protein = np.array([r.protein_g for r in raw_data])
        fats = np.array([r.fat_g for r in raw_data])
        salt = np.array([r.salt_g for r in raw_data])
        fibre = np.array([r.fibre_g for r in raw_data])
        sugars = np.array([r.sugars_g for r in raw_data])
        estimated = np.array([r.estimated_kcal for r in raw_data])

        w = self.rolling_period
        plot_dates = dates[w-1:] if w > 1 else dates

        if not plot_dates:
            self.axes[0, 0].text(
                0.5, 0.5,
                f"{w}-day averages need {w} days;\nonly {len(dates)} recorded so far",
                ha='center', va='center', color=PALETTE['base01'], fontname='Fira Code')
            return

        cal_target = self.profile.calculate_target_calories()
        prot_target = self.profile.calculate_target_protein()
        salt_target = float(self.profile.get_metric("goals", "salt_g", 5.0))
        fibre_target = 38.0

        metrics = [
            (self.axes[0, 0], calories, PALETTE['magenta'], f"Calories ({w}D Avg)", cal_target, "Goal"),
            (self.axes[0, 1], protein, PALETTE['blue'], f"Protein ({w}D Avg)", prot_target, "Floor"),
            (self.axes[0, 2], fats, PALETTE['orange'], f"Fats ({w}D Avg)", None, None),
            (self.axes[1, 0], salt, PALETTE['red'], f"Salt ({w}D Avg)", salt_target, "Ceiling"),
            (self.axes[1, 1], fibre, PALETTE['green'], f"Fibre ({w}D Avg)", fibre_target, "Floor"),
            (self.axes[1, 2], sugars, PALETTE['yellow'], f"Sugars ({w}D Avg)", None, None)
        ]

        for ax, raw_arr, color, label, goal_val, goal_type in metrics:
            smoothed = self._compute_rolling_avg(raw_arr, w)

            ax.plot(plot_dates, smoothed, color=color, marker='o', markersize=3, linewidth=1.5, zorder=3)
            ax.set_title(label, color=PALETTE['base02'], fontsize=10, fontname='Fira Code', weight='bold')
            ax.set_xticks([])
            ax.fill_between(plot_dates, 0, smoothed, color=color, alpha=0.04, zorder=1)

            if ax is self.axes[0, 0]:
                self._hatch_estimated(ax, plot_dates,
                                      self._compute_rolling_avg(estimated, w))

            if goal_val is not None and len(plot_dates) > 0:
                ax.axhline(goal_val, color=color, linestyle=':', linewidth=1.2, alpha=0.6, zorder=2)
                ax.text(0.02, 0.92, f"{goal_type}: {goal_val:.0f}",
                        transform=ax.transAxes, color=color, fontsize=7.5,
                        fontname='Fira Code', alpha=0.7,
                        bbox=dict(facecolor=PALETTE['base3'], edgecolor='none', pad=1.0, alpha=0.8))

            if len(smoothed) > 0:
                glow_pt, = ax.plot([plot_dates[-1]], [smoothed[-1]], marker='o',
                                   color=color, alpha=0.6, markersize=7, zorder=4, animated=True)
                self.anim_nodes.append({
                    'artist': glow_pt,
                    'ax': ax,
                    'base_size': 5
                })
