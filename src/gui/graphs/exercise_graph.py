import logging

import numpy as np
from PyQt6.QtWidgets import QHBoxLayout, QComboBox, QLabel, QToolTip
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtCore import QPoint

from src.config import PALETTE
from src.domain import formulas
from src.gui.graphs.base import BaseGraphView
from src.gui.workers import discard

log = logging.getLogger(__name__)


def timelines_by_name(rows, names):
    """One timeline per requested movement, from a single read of the log."""
    wanted = {str(name).lower(): str(name) for name in names if name}
    timelines = {name: [] for name in wanted.values()}
    for row in rows:
        if not row.name:
            continue
        requested = wanted.get(row.name.lower())
        if requested is None:
            continue
        timelines[requested].append((row.date, row.volume, row.one_rep_max,
                                     row.sets_display, row.weight_kg, row.rpe))
    for timeline in timelines.values():
        timeline.sort(key=lambda point: point[0])
    return timelines


class ExerciseGraphView(BaseGraphView):
    CONTENT_MARGINS = (4, 4, 4, 4)

    LAYOUTS = ("2x2", "2x3", "3x3")

    def __init__(self, db):
        super().__init__(db)
        self.hover_nodes = {}
        self.hover_lines = []
        self.flat_axes = []

        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(QLabel("<b>Grid Form Factor:</b>"))
        self.grid_select = QComboBox()
        self.grid_select.addItems(self.LAYOUTS)
        self.grid_select.currentTextChanged.connect(self.on_layout_changed)
        self._dims = self.LAYOUTS[0]
        self.controls_layout.addWidget(self.grid_select)

        self.controls_layout.addWidget(QLabel("<b>Configure Slot:</b>"))
        self.slot_select = QComboBox()
        self.controls_layout.addWidget(self.slot_select)

        self.controls_layout.addWidget(QLabel("<b>Exercise Target:</b>"))
        self.exercise_select = QComboBox()
        self.controls_layout.addWidget(self.exercise_select)

        self.controls_layout.addSpacing(25)
        legend_1rm = QLabel("<b>──● 1RM Strength (Left Axis)</b>")
        legend_1rm.setStyleSheet(f"color: {PALETTE['blue']}; font-family: 'Fira Code'; font-size: 11px;")
        self.controls_layout.addWidget(legend_1rm)

        self.controls_layout.addSpacing(15)
        legend_vol = QLabel("<b>- - ✖ Total Volume (Right Axis)</b>")
        legend_vol.setStyleSheet(f"color: {PALETTE['violet']}; font-family: 'Fira Code'; font-size: 11px;")
        self.controls_layout.addWidget(legend_vol)

        self.controls_layout.addStretch()
        self.main_layout.addLayout(self.controls_layout)

        self.install_canvas()

        self.signals_blocked = False
        self.slot_select.currentIndexChanged.connect(self.on_slot_selection_changed)
        self.exercise_select.currentIndexChanged.connect(self.on_exercise_assignment_changed)

        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

        self.fetch(lambda: self.db.get_setting("ex_graph_layout_dims", self._dims),
                   self.set_grid_dims)

    def set_grid_dims(self, dims):
        """Adopt a layout that has already been stored, and redraw at it."""
        if dims not in self.LAYOUTS:
            log.warning("Ignoring an unsupported grid layout %r; supported: %s",
                        dims, ", ".join(self.LAYOUTS))
            return
        self._dims = dims
        self.grid_select.blockSignals(True)
        self.grid_select.setCurrentText(dims)
        self.grid_select.blockSignals(False)
        self.refresh()

    def has_animation(self):
        return bool(self.anim_nodes) or any(h.get_visible() for h in self.hover_nodes.values())

    def animate_node(self, node, wave):
        """Each slot carries its own speed, so nine charts do not pulse as one block."""
        node['artist'].set_markersize(node['base_size'] + (wave * 6))
        node['artist'].set_alpha(0.2 + (wave * 0.4))

    def draw_extra_artists(self):
        hover_wave = self.wave(6.0)
        for ax, hover_artist in self.hover_nodes.items():
            if hover_artist.get_visible():
                hover_artist.set_markersize(12 + (hover_wave * 8))
                hover_artist.set_alpha(0.3 + (hover_wave * 0.5))
                ax.draw_artist(hover_artist)

    def update_selectors_list(self):
        """Refill the slot and exercise pickers."""
        self.fetch(self.db.get_all_exercise_names, self._fill_selectors)

    def _fill_selectors(self, exercise_names):
        self.signals_blocked = True
        previous_slot = max(0, self.slot_select.currentIndex())

        self.slot_select.clear()
        rows, cols = self._grid_shape()
        for i in range(1, (rows * cols) + 1):
            self.slot_select.addItem(f"Slot {i}")
        self.slot_select.setCurrentIndex(min(previous_slot, self.slot_select.count() - 1))

        self.exercise_select.clear()
        self.exercise_select.addItem("None")
        self.exercise_select.addItems(exercise_names)

        self.signals_blocked = False
        self.on_slot_selection_changed()

    def _grid_shape(self):
        return int(self._dims[0]), int(self._dims[2])

    def on_slot_selection_changed(self):
        if self.signals_blocked: return
        slot_idx = self.slot_select.currentIndex() + 1
        self.fetch(lambda: self.db.get_setting(f"ex_graph_slot_{slot_idx}", "None"),
                   self._show_slot_assignment)

    def _show_slot_assignment(self, current_assigned):
        self.signals_blocked = True
        idx = self.exercise_select.findText(current_assigned)
        self.exercise_select.setCurrentIndex(idx if idx >= 0 else 0)
        self.signals_blocked = False

    def on_exercise_assignment_changed(self):
        if self.signals_blocked: return
        slot_idx = self.slot_select.currentIndex() + 1
        selected_ex = self.exercise_select.currentText()

        self.fetch(lambda: self.db.set_setting(f"ex_graph_slot_{slot_idx}", selected_ex),
                   self._on_slot_assignment_stored)

    def _on_slot_assignment_stored(self, _outcome):
        """The new pin is in the store; redraw the grid off the back of it."""
        self.refresh()

    def on_layout_changed(self, text):
        """The member picked a layout from the combo: store it, then draw it."""
        self._dims = text
        self.fetch(lambda: self.db.set_setting("ex_graph_layout_dims", text), discard)
        self.refresh()

    def read_chart_data(self):
        """Every slot's pinned exercise and its timeline, on one worker thread."""
        rows, cols = self._grid_shape()
        return self._pinned_timelines(rows * cols)

    def _pinned_timelines(self, total_slots):
        keys = [f"ex_graph_slot_{slot + 1}" for slot in range(total_slots)]
        settings = self.db.get_settings(keys, {key: "None" for key in keys})
        pinned = [settings[key] or "None" for key in keys]
        wanted = [name for name in pinned if name != "None"]
        timelines = timelines_by_name(self.db.get_exercise_logs(), wanted) if wanted else {}
        return [(name, timelines.get(name) if name != "None" else None)
                for name in pinned]

    def prepare_refresh(self):
        self.update_selectors_list()

    def reset_axes(self):
        self.fig.clear()
        self.fig.set_layout_engine('constrained')
        self.hover_nodes.clear()
        self.hover_lines = []

        rows, cols = self._grid_shape()
        total_slots = rows * cols
        self.flat_axes = (self.fig.subplots(rows, cols).flatten() if total_slots > 1
                          else [self.fig.subplots(rows, cols)])

    def draw_chart(self, slot_data_list):
        """Draw one pinned movement per slot."""
        for slot_idx, (exercise_pinned, history) in enumerate(slot_data_list):
            ax = self.flat_axes[slot_idx]
            ax.set_facecolor(PALETTE['base3'])

            if not history:
                ax.spines['bottom'].set_color(PALETTE['base2'])
                ax.spines['left'].set_color(PALETTE['base2'])
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)

                title_text = f"Slot {slot_idx + 1}: [Unassigned]" if exercise_pinned == "None" else f"{exercise_pinned} (No Data)"
                ax.set_title(title_text, color=PALETTE['base1'], fontsize=9, fontname='Fira Code')

                ax.set_xticks([])
                ax.set_yticks([])
                continue

            dates = [h[0] for h in history]
            volumes = [h[1] for h in history]
            intensities = [h[2] for h in history]

            ax.spines['bottom'].set_color(PALETTE['base01'])
            ax.spines['left'].set_color(PALETTE['blue'])
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            ax.tick_params(axis='y', colors=PALETTE['blue'], labelsize=7)
            ax.tick_params(axis='x', colors=PALETTE['base00'])
            ax.grid(True, color=PALETTE['base2'], linestyle='--')

            line, = ax.plot(dates, intensities, color=PALETTE['blue'], marker='o', markersize=4, linewidth=1.2, zorder=3)
            ax.set_title(exercise_pinned, color=PALETTE['base02'], fontsize=9, fontname='Fira Code', weight='bold')
            ax.set_xticks([])

            ax2 = ax.twinx()
            ax2.plot(dates, volumes, color=PALETTE['violet'], marker='x', markersize=2, linewidth=0.8, linestyle='--', alpha=0.7, zorder=2)
            ax2.fill_between(dates, 0, volumes, color=PALETTE['violet'], alpha=0.08, zorder=1)

            ax2.spines['top'].set_visible(False)
            ax2.spines['left'].set_visible(False)
            ax2.spines['bottom'].set_visible(False)
            ax2.spines['right'].set_color(PALETTE['violet'])
            ax2.tick_params(axis='y', colors=PALETTE['violet'], labelsize=6)

            goal_meta = None
            try:
                goals_sec = self.profile.data.get("exercise_goals", {})
                ex_goal = None
                normalized_pinned = exercise_pinned.lower().replace("_", " ").replace("-", " ").strip()

                for k, v in goals_sec.items():
                    if k.lower().replace("_", " ").replace("-", " ").strip() == normalized_pinned:
                        ex_goal = v
                        break

                if ex_goal:
                    raw_wt = ex_goal.get("target_weight")
                    raw_reps = ex_goal.get("target_reps")

                    if raw_wt is not None and raw_reps is not None:
                        t_wt = float(raw_wt)

                        if isinstance(raw_reps, str):
                            reps_list = [float(x.strip()) for x in raw_reps.split(",") if x.strip()]
                            sets_str = ",".join(str(int(x)) if x == int(x) else str(x) for x in reps_list)
                        elif isinstance(raw_reps, (int, float)):
                            reps_list = [float(raw_reps)]
                            sets_str = str(int(raw_reps)) if raw_reps == int(raw_reps) else str(raw_reps)
                        else:
                            reps_list = []
                            sets_str = ""

                        if t_wt > 0 and reps_list:
                            total_reps = sum(reps_list)
                            max_reps = max(reps_list)

                            target_vol = formulas.training_volume(total_reps, t_wt)
                            target_1rm = formulas.one_rep_max_or_weight(t_wt, max_reps)

                            goal_dates = [dates[-1], "Goal"]

                            ax.plot(goal_dates, [intensities[-1], target_1rm], color=PALETTE['blue'], linestyle=':', alpha=0.30, linewidth=1.2, zorder=2)
                            ax.plot(["Goal"], [target_1rm], marker='o', color=PALETTE['blue'], markersize=5, alpha=0.35, zorder=3)

                            ax2.plot(goal_dates, [volumes[-1], target_vol], color=PALETTE['violet'], linestyle=':', alpha=0.30, linewidth=1.0, zorder=1)
                            ax2.plot(["Goal"], [target_vol], marker='x', color=PALETTE['violet'], markersize=4, alpha=0.35, zorder=2)
                            ax2.fill_between(goal_dates, [0, 0], [volumes[-1], target_vol], color=PALETTE['violet'], alpha=0.02, zorder=1)

                            goal_meta = {
                                'onerm': target_1rm,
                                'weight': t_wt,
                                'sets_str': sets_str
                            }
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                log.warning("Could not compute the goal projection for %s: %s", exercise_pinned, e)

            hover_glow, = ax.plot([], [], marker='o', color=PALETTE['cyan'], markersize=10, alpha=0, zorder=5, animated=True)
            hover_glow.set_visible(False)
            self.hover_nodes[ax] = hover_glow

            max_1rm = max(intensities)
            latest_1rm = intensities[-1]
            is_pr = (latest_1rm >= max_1rm) and (len(intensities) > 1)

            pulse_color = PALETTE['magenta'] if is_pr else PALETTE['blue']
            pulse_speed = 4.5 if is_pr else 2.25

            glow_pt, = ax.plot([dates[-1]], [latest_1rm], marker='o', color=pulse_color, alpha=0.5, markersize=8, zorder=4, animated=True)
            self.anim_nodes.append({
                'artist': glow_pt,
                'ax': ax,
                'speed': pulse_speed,
                'base_size': 6
            })

            self.hover_lines.append({
                'line': line,
                'history': history,
                'axes': [ax, ax2],
                'goal': goal_meta
            })

    def on_hover(self, event):
        if event.inaxes is None or event.x is None or event.y is None:
            if self._last_hovered is not None:
                for node in self.hover_nodes.values():
                    node.set_visible(False)
                QToolTip.hideText()
                self._last_hovered = None
            return

        hit_found = False
        for item in self.hover_lines:
            line = item['line']
            allowed_axes = item.get('axes', [line.axes])

            if event.inaxes in allowed_axes:
                xy_data = line.get_xydata()
                xy_pixels = line.axes.transData.transform(xy_data)
                dx = xy_pixels[:, 0] - event.x
                dy = xy_pixels[:, 1] - event.y
                distances = np.hypot(dx, dy)

                min_idx = np.argmin(distances) if len(distances) > 0 else -1
                min_dist = distances[min_idx] if min_idx != -1 else float('inf')

                goal_dist = float('inf')
                if item.get('goal'):
                    goal_x_idx = len(item['history'])
                    goal_pixel = line.axes.transData.transform((goal_x_idx, item['goal']['onerm']))
                    goal_dist = np.hypot(goal_pixel[0] - event.x, goal_pixel[1] - event.y)

                if goal_dist < min_dist and goal_dist <= 10:
                    current_hover = (id(line), "goal")
                    if self._last_hovered == current_hover:
                        hit_found = True
                        break

                    for node in self.hover_nodes.values():
                        node.set_visible(False)

                    hover_node = self.hover_nodes.get(line.axes)
                    if hover_node:
                        hover_node.set_data(["Goal"], [item['goal']['onerm']])
                        hover_node.set_visible(True)

                    g = item['goal']
                    text = f"Target Milestone Goal\nWeight: {g['weight']:.1f} kg\nSets: [{g['sets_str']}]"
                    QToolTip.setFont(QFont("Fira Code", 10))
                    QToolTip.showText(QCursor.pos() + QPoint(15, 15), text, self.canvas)

                    self._last_hovered = current_hover
                    hit_found = True
                    break

                elif min_dist <= 10:
                    idx = min_idx
                    current_hover = (id(line), idx)
                    if self._last_hovered == current_hover:
                        hit_found = True
                        break

                    dt = item['history'][idx][0]
                    onerm = item['history'][idx][2]

                    for node in self.hover_nodes.values():
                        node.set_visible(False)

                    hover_node = self.hover_nodes.get(line.axes)
                    if hover_node:
                        hover_node.set_data([dt], [onerm])
                        hover_node.set_visible(True)

                    sets_str = item['history'][idx][3]
                    wt = item['history'][idx][4]
                    rpe = item['history'][idx][5]

                    text = f"Date: {dt}\nSets: [{sets_str}]\nWeight: {wt:.1f} kg\nRPE: {rpe:.1f}"
                    QToolTip.setFont(QFont("Fira Code", 10))
                    QToolTip.showText(QCursor.pos() + QPoint(15, 15), text, self.canvas)

                    self._last_hovered = current_hover
                    hit_found = True
                    break

        if not hit_found:
            if self._last_hovered is not None:
                for node in self.hover_nodes.values():
                    node.set_visible(False)
                QToolTip.hideText()
                self._last_hovered = None
