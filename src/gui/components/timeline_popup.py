import logging
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QRect
from src.config import PALETTE
from src.domain.clock import as_displayed_date

log = logging.getLogger(__name__)


class TimelineCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(160)
        self.heartbeats = {}
        self.events = []

        self.view_start = 0.0
        self.view_end = 1440.0

        self.is_panning = False
        self.pan_last_x = 0

        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_data(self, heartbeats: dict, events: list):
        self.heartbeats = heartbeats
        self.events = events
        self.view_start = 0.0
        self.view_end = 1440.0
        self.update()

    def _time_to_x(self, minute: float) -> int:
        w = self.width() - 30
        if self.view_end <= self.view_start:
            return 15
        ratio = (minute - self.view_start) / (self.view_end - self.view_start)
        return 15 + int(ratio * w)

    def _x_to_time(self, x: int) -> float:
        w = self.width() - 30
        ratio = (x - 15) / w
        return self.view_start + (ratio * (self.view_end - self.view_start))

    def wheelEvent(self, event):
        zoom_factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        mouse_x = event.position().x()
        mouse_time = self._x_to_time(mouse_x)

        current_window = self.view_end - self.view_start
        new_window = max(10.0, min(1440.0, current_window * zoom_factor))

        ratio = (mouse_time - self.view_start) / current_window
        self.view_start = mouse_time - (ratio * new_window)
        self.view_end = mouse_time + ((1.0 - ratio) * new_window)

        if self.view_start < 0:
            self.view_end -= self.view_start
            self.view_start = 0
        if self.view_end > 1440:
            self.view_start -= (self.view_end - 1440)
            self.view_end = 1440

        self.view_start = max(0.0, self.view_start)
        self.view_end = min(1440.0, self.view_end)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = True
            self.pan_last_x = event.position().x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.is_panning:
            current_x = event.position().x()
            dx = current_x - self.pan_last_x
            self.pan_last_x = current_x

            window = self.view_end - self.view_start
            w = self.width() - 30
            dt = -(dx / w) * window

            if self.view_start + dt < 0:
                dt = -self.view_start
            elif self.view_end + dt > 1440:
                dt = 1440 - self.view_end

            self.view_start += dt
            self.view_end += dt
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.view_start = 0.0
            self.view_end = 1440.0
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_x = 15
        bar_y = 100
        bar_width = self.width() - 30
        bar_height = 8

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE['base2']))
        painter.drawRect(bar_x, bar_y, bar_width, bar_height)

        painter.setClipRect(bar_x, 0, bar_width, self.height())

        color_map = {
            'focus': QColor(PALETTE['base00']),
            'focus_overtime': QColor(PALETTE['red']),
            'rest': QColor(PALETTE['green']),
            'rest_overtime': QColor(PALETTE['cyan'])
        }

        pixels_per_minute = bar_width / (self.view_end - self.view_start) if self.view_end > self.view_start else 1
        rect_width = max(1, int(pixels_per_minute) + 1)

        sorted_heartbeats = sorted(self.heartbeats.items(), key=lambda x: x[0])

        for exact_minute, val in sorted_heartbeats:
            state = val[0] if isinstance(val, tuple) else val

            if self.view_start <= exact_minute <= self.view_end and state in color_map:
                x_pos = self._time_to_x(exact_minute)
                painter.setBrush(color_map[state])
                painter.drawRect(x_pos, bar_y, rect_width, bar_height)

        window = self.view_end - self.view_start
        if window <= 120:
            grid_interval = 15
        elif window <= 480:
            grid_interval = 60
        else:
            grid_interval = 360

        painter.setPen(QPen(QColor(PALETTE['base01']), 1, Qt.PenStyle.DotLine))
        current_grid = 0
        while current_grid <= 1440:
            if self.view_start <= current_grid <= self.view_end:
                x_line = self._time_to_x(current_grid)
                if current_grid == 1440: x_line -= 1
                painter.drawLine(x_line, bar_y - 2, x_line, bar_y + bar_height + 5)

                h, m = divmod(current_grid, 60)
                text_str = f"{int(h):02d}:{int(m):02d}"
                text_width = 34

                text_x = x_line - (text_width // 2)
                if text_x < bar_x:
                    text_x = bar_x
                elif text_x + text_width > bar_x + bar_width:
                    text_x = bar_x + bar_width - text_width

                painter.setPen(QColor(PALETTE['base01']))
                painter.drawText(int(text_x), bar_y + bar_height + 18, text_str)
                painter.setPen(QPen(QColor(PALETTE['base01']), 1, Qt.PenStyle.DotLine))

            current_grid += grid_interval

        x_to_events = {}
        for ev in self.events:
            ts, e_type, amt = ev
            try:
                time_part = ts.split("T")[1] if "T" in ts else ts
                time_elements = time_part.split(":")

                h = int(time_elements[0])
                m = int(time_elements[1])
                s = float(time_elements[2].replace("Z", "")) if len(time_elements) > 2 else 0.0

                minute_of_day = (h * 60) + m + (s / 60.0)

                if self.view_start <= minute_of_day <= self.view_end:
                    x_pos = self._time_to_x(minute_of_day)
                    if x_pos not in x_to_events:
                        x_to_events[x_pos] = []
                    x_to_events[x_pos].append(e_type)
            except (ValueError, TypeError) as e:
                log.debug("Skipping an event with an unreadable timestamp: %s", e)

        for x_pos, e_types in x_to_events.items():
            if len(e_types) <= 4:
                for stack_count, e_type in enumerate(e_types):
                    y_pos = bar_y - 12 - (stack_count * 10)

                    if "long_break" in e_type or "mode_switch" in e_type:
                        color = QColor(PALETTE['base01'])
                        painter.setBrush(color)
                        painter.setPen(QPen(QColor(PALETTE['base03']), 1))
                        painter.translate(x_pos, y_pos)
                        painter.rotate(45)
                        painter.drawRect(-4, -4, 8, 8)
                        painter.rotate(-45)
                        painter.translate(-x_pos, -y_pos)
                    else:
                        if "pause" in e_type:
                            color = QColor(PALETTE['yellow'])
                        elif "skip" in e_type or "overridden" in e_type:
                            color = QColor(PALETTE['red'])
                        else:
                            color = QColor(PALETTE['base01'])

                        painter.setBrush(color)
                        painter.setPen(QPen(QColor(PALETTE['base03']), 1))
                        painter.drawEllipse(x_pos - 4, y_pos, 8, 8)
            else:
                y_pos = bar_y - 14

                painter.setBrush(QColor(PALETTE['magenta']))
                painter.setPen(QPen(QColor(PALETTE['base03']), 1))
                painter.drawEllipse(x_pos - 6, y_pos - 6, 12, 12)

                painter.setPen(QPen(QColor(PALETTE['base03'])))
                font = painter.font()
                font.setFamily('Fira Code')
                font.setPixelSize(10)
                font.setBold(True)
                painter.setFont(font)

                text_rect = QRect(x_pos - 6, y_pos - 6, 12, 12)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "+")


class TimelinePopupWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(700, 260)
        self.setObjectName("TimelinePopup")

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        self.setStyleSheet(f"#TimelinePopup {{ background-color: {PALETTE['base3']}; border: 1px solid {PALETTE['base1']}; border-radius: 4px; }}")

        self.unpin_callback = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        header_layout.addWidget(QLabel(), 1)

        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(f"color: {PALETTE['base01']}; font-family: 'Fira Code'; font-size: 11px; font-weight: bold; border: none;")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_date, 2)

        btn_container = QHBoxLayout()
        btn_container.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(f"background: transparent; color: {PALETTE['red']}; font-weight: bold; font-size: 16px; border: none;")
        self.btn_close.clicked.connect(self.close_popup)
        btn_container.addWidget(self.btn_close)

        header_layout.addLayout(btn_container, 1)
        layout.addLayout(header_layout)

        self.canvas = TimelineCanvas()
        layout.addWidget(self.canvas)

        self.legend_container = QVBoxLayout()
        self.legend_row1 = QHBoxLayout()
        self.legend_row2 = QHBoxLayout()

        self.legend_row1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legend_row2.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.legend_row1.setSpacing(12)
        self.legend_row2.setSpacing(12)

        self.legend_container.addLayout(self.legend_row1)
        self.legend_container.addLayout(self.legend_row2)
        layout.addLayout(self.legend_container)

        instructions = QLabel("Double-click timeline to reset zoom | Scroll to zoom | Drag to pan | Thin bar indicates active Timer Mode")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet(f"color: {PALETTE['base0']}; font-family: 'Fira Code'; font-size: 9px; font-style: italic;")
        layout.addWidget(instructions)

    def close_popup(self):
        self.hide()
        if self.unpin_callback is not None:
            self.unpin_callback()

    def set_data(self, date_str: str, heartbeats: dict, events: list):
        self.lbl_date.setText(f"Timeline: {as_displayed_date(date_str)}")
        self.canvas.set_data(heartbeats, events)

        while self.legend_row1.count():
            child = self.legend_row1.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        while self.legend_row2.count():
            child = self.legend_row2.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        states = [
            ("■ Focus", PALETTE['base00']), ("■ Focus OT", PALETTE['red']),
            ("■ Rest", PALETTE['green']), ("■ Rest OT", PALETTE['cyan']),
        ]
        events = [
            ("● Pause", PALETTE['yellow']), ("● Resume", PALETTE['base01']),
            ("● Skip", PALETTE['red']), ("◆ Long break", PALETTE['base01']),
            ("● Cluster", PALETTE['magenta']),
        ]

        for row, mapping in ((self.legend_row1, states), (self.legend_row2, events)):
            for name, color in mapping:
                lbl = QLabel(name)
                lbl.setStyleSheet(f"color: {color}; font-family: 'Fira Code'; font-size: 10px; font-weight: bold; border: none;")
                row.addWidget(lbl)
