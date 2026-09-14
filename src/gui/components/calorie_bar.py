import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont
from PyQt6.QtCore import Qt, QTimer, QRectF
from src.config import PALETTE
from src.domain import formulas
from src.gui.animations import blend
from src.gui.lifecycle import PausesWhenHidden
from src.profile import DEFAULT_SALT_G, UserProfile

ON_TARGET_KCAL = 200.0

OVER_RAMP_KCAL = 400.0

UNDER_RAMP_MAINTAINING_KCAL = 400.0
UNDER_RAMP_GAINING_KCAL = 600.0

OVERSHOOT_RAMPS = {"salt": 3.0, "caffeine": 40.0}


class AnimatedProgressBar(PausesWhenHidden, QWidget):
    """A bar that eases towards its value at 33 Hz while visible."""

    paused_timer_attribute = "timer"
    paused_timer_interval_ms = 30

    def __init__(self, metric_type="calories", parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.profile = UserProfile()
        self.metric_type = metric_type

        self.actual_value = 0.0
        self.displayed_value = 0.0
        self.burned_value = 0.0
        self.displayed_burned_value = 0.0
        self.anim_offset = 0.0
        self.pulse_time = 0.0

        self._recalculate_targets()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)

    def set_value(self, val):
        """The measured amount."""
        self.actual_value = float(val)
        self.update()

    def reload_targets(self):
        """Recompute what this bar is aiming at, in case the profile changed."""
        self.profile = UserProfile()
        self._recalculate_targets()
        self.update()

    def set_burned_value(self, val):
        self.burned_value = float(val)
        self.update()

    def _recalculate_targets(self):
        self.max_buffer = self.profile.overflow_buffer()
        self.ticks = []

        self.target_val = 0.0
        self.max_val = 0.0
        self.unit = ""
        self.tdee = 0.0
        self.goal_type = formulas.MAINTAIN_WEIGHT

        if self.metric_type == "calories":
            self.tdee = self.profile.calculate_tdee()
            raw_adj = self.profile.daily_adjustment_kcal()
            self.goal_type = self.profile.goal_type()

            self.target_val = formulas.energy_target(self.tdee, raw_adj, self.goal_type)
            self.ticks = self.profile.tick_markers()
            highest_tick = max(self.ticks) if self.ticks else 0
            base_for_max = max(self.tdee + highest_tick, self.target_val)
            self.max_val = base_for_max + self.max_buffer
            self.unit = "kcal"

        elif self.metric_type == "protein":
            self.target_val = self.profile.calculate_target_protein()
            self.max_val = self.target_val + 100.0
            self.unit = "g prot"

        elif self.metric_type == "salt":
            self.target_val = float(self.profile.get_metric("goals", "salt_g", DEFAULT_SALT_G))
            self.max_val = self.target_val + 5.0
            self.unit = "g salt"

        elif self.metric_type == "caffeine":
            self.target_val = float(self.profile.get_metric("goals", "max_sleep_caffeine", 20.0))
            self.max_val = self.target_val + 80.0
            self.unit = "mg caff"

    def update_animation(self):
        diff = self.actual_value - self.displayed_value
        if abs(diff) > 0.1:
            self.displayed_value += diff * 0.15
        else:
            self.displayed_value = self.actual_value

        diff_burn = self.burned_value - self.displayed_burned_value
        if abs(diff_burn) > 0.1:
            self.displayed_burned_value += diff_burn * 0.15
        else:
            self.displayed_burned_value = self.burned_value

        self.anim_offset += 0.015
        if self.anim_offset > 1.0:
            self.anim_offset -= 1.0

        self.pulse_time += 0.03
        self.update()

    def _net_value(self) -> float:
        """What the bar is measuring: the calorie bar nets off the day's burn."""
        if self.metric_type == "calories":
            return max(0.0, self.displayed_value - self.displayed_burned_value)
        return self.displayed_value

    def _get_bar_color(self) -> QColor:
        """Green on target, blue short of it, magenta past it."""
        green = QColor(PALETTE['green'])
        magenta = QColor(PALETTE['magenta'])
        blue = QColor(PALETTE['blue'])

        diff = self._net_value() - self.target_val

        if self.metric_type == "calories":
            over = blend(green, magenta, (diff - ON_TARGET_KCAL) / OVER_RAMP_KCAL)
            if self.goal_type == formulas.LOSE_WEIGHT:
                return green if diff <= ON_TARGET_KCAL else over
            under_ramp = (UNDER_RAMP_GAINING_KCAL
                          if self.goal_type == formulas.GAIN_WEIGHT
                          else UNDER_RAMP_MAINTAINING_KCAL)
            if diff < -ON_TARGET_KCAL:
                return blend(blue, green,
                             (diff + ON_TARGET_KCAL + under_ramp) / under_ramp)
            return over if diff > ON_TARGET_KCAL else green

        if self.metric_type == "protein":
            if diff >= 0:
                return green
            return blend(blue, green, self.displayed_value / self.target_val)

        if self.metric_type in OVERSHOOT_RAMPS:
            if diff <= 0:
                return green
            return blend(green, magenta, diff / OVERSHOOT_RAMPS[self.metric_type])

        return green

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        text_w = 190
        bar_x = text_w
        bar_w = w - text_w

        if bar_w <= 0: return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE['base2']))
        painter.drawRoundedRect(bar_x, 0, bar_w, h, 2, 2)

        if self.max_val <= 0: return

        if self.metric_type == "calories":
            net_val = max(0.0, self.displayed_value - self.displayed_burned_value)
            net_fill_w = bar_w * min(net_val / self.max_val, 1.0)
            gross_fill_w = bar_w * min(self.displayed_value / self.max_val, 1.0)
            burn_w = max(0.0, gross_fill_w - net_fill_w)
            fill_w = net_fill_w
        else:
            fill_w = bar_w * min(self.displayed_value / self.max_val, 1.0)
            burn_w = 0.0

        base_color = self._get_bar_color()

        is_warning = False
        if self.metric_type == "calories":
            net_val = max(0.0, self.displayed_value - self.displayed_burned_value)
            if (net_val - self.target_val) > 200.0: is_warning = True
        elif self.metric_type in ["salt", "caffeine"] and self.displayed_value > self.target_val:
            is_warning = True

        pulse_speed = 1.2 if is_warning else 0.5
        pulse_intensity = math.sin(self.pulse_time * pulse_speed)

        if is_warning: alpha = int(160 + 50 * pulse_intensity)
        else: alpha = int(140 + 30 * pulse_intensity)

        base_color.setAlpha(alpha)

        if fill_w > 0:
            grad = QLinearGradient()
            grad_width = 200.0

            offset = bar_x + (self.anim_offset * grad_width)

            grad.setStart(offset, 0)
            grad.setFinalStop(offset - grad_width, 0)
            grad.setSpread(QLinearGradient.Spread.RepeatSpread)

            lighter = base_color.lighter(115)
            lighter.setAlpha(alpha)
            grad.setColorAt(0.0, base_color)
            grad.setColorAt(0.5, lighter)
            grad.setColorAt(1.0, base_color)

            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(bar_x, 0, fill_w, h), 2, 2)

        if self.metric_type == "calories" and burn_w > 0:
            burn_color = QColor(PALETTE['orange'])
            burn_alpha = int(130 + 30 * pulse_intensity)
            burn_color.setAlpha(burn_alpha)

            burn_grad = QLinearGradient()
            grad_width = 200.0
            burn_offset = (bar_x + fill_w + burn_w) - (self.anim_offset * grad_width)
            burn_grad.setStart(burn_offset, 0)
            burn_grad.setFinalStop(burn_offset + grad_width, 0)
            burn_grad.setSpread(QLinearGradient.Spread.RepeatSpread)

            burn_lighter = burn_color.lighter(125)
            burn_lighter.setAlpha(burn_alpha)
            burn_grad.setColorAt(0.0, burn_color)
            burn_grad.setColorAt(0.5, burn_lighter)
            burn_grad.setColorAt(1.0, burn_color)

            painter.setBrush(QBrush(burn_grad))
            painter.drawRoundedRect(QRectF(bar_x + fill_w, 0, burn_w, h), 2, 2)

        painter.setPen(QPen(QColor(PALETTE['base01']), 1))

        if self.metric_type == "calories":
            for tick in self.ticks:
                tick_kcal = self.tdee + tick
                if 0 < tick_kcal <= self.max_val:
                    tick_x = bar_x + (bar_w * (tick_kcal / self.max_val))
                    painter.drawLine(int(tick_x), 0, int(tick_x), h)

        if 0 < self.target_val <= self.max_val:
            target_x = bar_x + (bar_w * (self.target_val / self.max_val))
            painter.setPen(QPen(QColor(PALETTE['base01']), 2, Qt.PenStyle.SolidLine))
            painter.drawLine(int(target_x), 0, int(target_x), h)

        painter.setPen(QColor(PALETTE['base03']))
        font = QFont("Fira Code", 8, QFont.Weight.Bold)
        painter.setFont(font)

        if self.metric_type in ["salt", "caffeine"]:
            status_text = f"{self.displayed_value:.1f} / {self.target_val:.1f} {self.unit}"
        elif self.metric_type == "calories":
            status_text = f"{int(self.displayed_value)} (-{int(self.displayed_burned_value)}) / {int(self.target_val)} {self.unit}"
        else:
            status_text = f"{int(self.displayed_value)} / {int(self.target_val)} {self.unit}"

        text_rect = QRectF(0, 0, text_w - 10, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, status_text)
