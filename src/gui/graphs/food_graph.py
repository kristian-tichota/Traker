import logging

import numpy as np
from PyQt6.QtWidgets import QComboBox, QLabel

from src.config import PALETTE
from src.gui.graphs.base import WindowedGraphView, style_trend_axes
from src.gui.workers import discard

log = logging.getLogger(__name__)


EATEN, NET_OF_TRAINING = "eaten", "net"

CALORIE_SERIES = {
    EATEN: "Eaten",
    NET_OF_TRAINING: "Net of Training",
}

CALORIE_TITLES = {
    EATEN: "Calories",
    NET_OF_TRAINING: "Net Calories",
}

SERIES_BY_LABEL = {label: key for key, label in CALORIE_SERIES.items()}


class FoodGraphView(WindowedGraphView):
    PERIOD_SETTING = "food_graph_period"

    def __init__(self, db):
        super().__init__(db)

        self.controls_layout.addWidget(QLabel("<b>Calorie Series:</b>"))
        self.series_select = QComboBox()
        self.series_select.addItems(list(CALORIE_SERIES.values()))
        self.calorie_series = EATEN
        self.series_select.currentTextChanged.connect(self.on_series_changed)
        self.controls_layout.addWidget(self.series_select)
        self.controls_layout.addStretch()

        self.fetch(self._read_preferences, self._apply_preferences)

        self.install_canvas()
        self.axes = self.fig.subplots(2, 3)

    def _read_preferences(self):
        return self.db.get_settings(
            [self.PERIOD_SETTING, "food_graph_calorie_series"],
            {self.PERIOD_SETTING: self.PERIODS[self.DEFAULT_PERIOD],
             "food_graph_calorie_series": EATEN})

    def _apply_preferences(self, saved):
        self._adopt_series(saved["food_graph_calorie_series"])
        super()._apply_preferences(saved)

    def _adopt_series(self, saved_series):
        """Show a stored calorie series on the control without writing it back."""
        self.calorie_series = (NET_OF_TRAINING
                               if str(saved_series) == NET_OF_TRAINING else EATEN)
        self.series_select.blockSignals(True)
        self.series_select.setCurrentText(CALORIE_SERIES[self.calorie_series])
        self.series_select.blockSignals(False)

    def on_series_changed(self, text):
        """Store the series picked from the combo, then draw it."""
        self.calorie_series = SERIES_BY_LABEL.get(text, EATEN)
        self.fetch(lambda: self.db.set_setting("food_graph_calorie_series",
                                               self.calorie_series), discard)
        self.refresh()

    def set_calorie_series(self, series: str):
        """Adopt a calorie series chosen elsewhere and redraw at it."""
        if series not in CALORIE_SERIES:
            log.warning("Ignoring an unsupported calorie series %r; supported: %s",
                        series, ", ".join(CALORIE_SERIES))
            return
        self._adopt_series(series)
        self.refresh()

    @property
    def nets_training(self) -> bool:
        """Report whether the calorie chart takes the training burn off."""
        return self.calorie_series == NET_OF_TRAINING

    def _hatch_estimated(self, ax, plot_dates, smoothed_estimate):
        """Hatch the part of the calorie series that was estimated."""
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
                style_trend_axes(ax)

    def read_chart_data(self):
        return self.db.get_daily_aggregates()

    def _note_training_burn(self, ax, smoothed_burn):
        """Say what training energy the calorie series has taken off."""
        if not len(smoothed_burn) or not smoothed_burn.any():
            return
        ax.text(0.02, 0.68, f"\u2212{smoothed_burn.mean():.0f} kcal/day trained off",
                transform=ax.transAxes, color=PALETTE['cyan'], fontsize=7.0,
                fontname='Fira Code', alpha=0.85,
                bbox=dict(facecolor=PALETTE['base3'], edgecolor='none',
                          pad=1.0, alpha=0.8))

    def draw_chart(self, raw_data):
        if not raw_data:
            return

        dates = [r.date for r in raw_data]
        burnt = np.array([r.burn_kcal for r in raw_data])
        calories = np.array([r.net_kcal if self.nets_training else r.energy_kcal
                             for r in raw_data])
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
            (self.axes[0, 0], calories, PALETTE['magenta'],
             f"{CALORIE_TITLES[self.calorie_series]} ({w}D Avg)", cal_target, "Goal"),
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
                if self.nets_training:
                    self._note_training_burn(
                        ax, self._compute_rolling_avg(burnt, w))

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
