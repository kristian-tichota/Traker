import re

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.config import PALETTE
from src.gui.animations import grey_of

BACKGROUND_ALPHA = 205

PAD_X = 11
PAD_Y = 8
GAP = 14
ROW_HEIGHT = 18
FONT_PX = 10

MARGIN = 20

RADIUS = 4.0

SIGN_PX = 15
SIDE_PX = 7
PEDAL_PX = (17, 10)
MARK_GAP = 7
RING_PX = 1.6
OUTLINE_PX = 2
FRAME_MS = 16

CALM_INPUTS, CALM_SAYS, CALM_KEY = (grey_of(PALETTE['base0']), grey_of(PALETTE['base01']),
                                     grey_of(PALETTE['base01'], 0.75))
CALM_HOLD = grey_of(PALETTE['base1'])

LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
RIGHT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
BOTTOM_LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

SIGNS = {
    "fist": '<path d="M6 10.2a1.7 1.7 0 0 1 3.4 0 1.7 1.7 0 0 1 3.4 0 1.7 1.7 0 0 1 3.4 0 1.7 1.7 0 0 1 3.4 0V15a5.5 5.5 0 0 1-5.5 5.5h-2.6A5.5 5.5 0 0 1 6 15z M9.4 10.2v2 M12.8 10.2v2 M16.2 10.2v2 M6 13.6h6.3a1.6 1.6 0 0 1 0 3.2H8.5"/>',
    "pinch": '<path d="M12.5 11.5V5a1.25 1.25 0 0 1 2.5 0v6 M15 10.5V4.2a1.25 1.25 0 0 1 2.5 0v6.8 M17.5 11V6.5a1.25 1.25 0 0 1 2.5 0v7.5a7 7 0 0 1-7 7h-.6a6 6 0 0 1-5.6-3.8 M12 12.3v1.2"/><circle cx="8.7" cy="12.3" r="3.3"/>',
    "thumbs_up": '<path d="M9.5 11 12.3 4.3a1.5 1.5 0 0 1 2.9.6V9.5h3.6a1.8 1.8 0 0 1 1.8 2.1l-1.1 6.8a2 2 0 0 1-2 1.6H9.5z M5 11h4.5v9H5z"/>',
    "brow_raise": '<circle cx="12" cy="13" r="8.5"/><path d="M7.6 8.6q1.6-1.6 3.2 0 M13.2 8.6q1.6-1.6 3.2 0 M12 1.2v2.2 M10.6 2.6 12 1.2l1.4 1.4 M9.2 11.6v.4 M14.8 11.6v.4 M10 16.6h4"/>',
    "pucker_frown": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="16" r="1.3"/><path d="M7.6 8.4l3.1 1.4 M16.4 8.4l-3.1 1.4 M9.2 11.8v.4 M14.8 11.8v.4"/>',
    "open": '<path d="M8.2 12.2V5.6a1.25 1.25 0 0 1 2.5 0V11 M10.7 10.6V4.1a1.25 1.25 0 0 1 2.5 0v6.5 M13.2 10.6V4.9a1.25 1.25 0 0 1 2.5 0v6 M15.7 11.4V7.3a1.25 1.25 0 0 1 2.5 0V15a6.5 6.5 0 0 1-6.5 6.5h-.9a6 6 0 0 1-4.7-2.3l-3.3-4.1a1.35 1.35 0 0 1 2-1.8l2.4 2.1v-3.2"/>',
}

PEDALS = ("left", "middle", "right")
PEDAL = re.compile(r"(left|middle|right) pedal")
GESTURE = re.compile(r"(?:(left|right)_)?(\w+)")

_RENDERERS = {}


def mark_of(name) -> tuple:
    """Return how an input is drawn: ("sign", shape, side), ("pedal", index) or ("text", words)."""
    pedal = PEDAL.fullmatch(name)
    if pedal:
        return "pedal", PEDALS.index(pedal[1])
    gesture = GESTURE.fullmatch(name)
    if gesture is None:
        return "text", name
    side, shape = gesture.groups()
    if shape in SIGNS:
        return "sign", shape, side or ""
    return "text", name.replace("_", " ")


def _renderer(shape, side, colour) -> QSvgRenderer:
    key = (shape, side, colour.name())
    if key not in _RENDERERS:
        art = SIGNS[shape]
        if side == "left":
            art = f'<g transform="matrix(-1 0 0 1 24 0)">{art}</g>'
        markup = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
                  f' stroke="{colour.name()}" stroke-width="1.5" stroke-linecap="round"'
                  f' stroke-linejoin="round">{art}</svg>')
        _RENDERERS[key] = QSvgRenderer(QByteArray(markup.encode()))
    return _RENDERERS[key]


class Marks:
    """The inputs of a row: a sign per gesture, a glyph per pedal, and words for the rest."""

    def __init__(self, font, scale):
        self.scale = float(scale)
        self.font = font
        self.side_font = QFont(font)
        self.side_font.setPixelSize(max(1, round(SIDE_PX * self.scale)))

    def _px(self, length) -> float:
        return length * self.scale

    def _width(self, mark) -> float:
        if mark[0] == "sign":
            side = QFontMetrics(self.side_font).horizontalAdvance("L") if mark[2] else 0
            return self._px(SIGN_PX) + side
        if mark[0] == "pedal":
            return self._px(PEDAL_PX[0])
        return QFontMetrics(self.font).horizontalAdvance(mark[1])

    def width(self, names) -> float:
        """Return the width the inputs take side by side."""
        marks = [mark_of(name) for name in names]
        if not marks:
            return 0.0
        return sum(self._width(mark) for mark in marks) + self._px(MARK_GAP) * (len(marks) - 1)

    def paint(self, painter, right, middle, names, ink, hold, gate=None):
        """Paint the inputs to end at right, the held gesture ringed by how much of it is served."""
        x = right - self.width(names)
        for name in names:
            mark = mark_of(name)
            width = self._width(mark)
            if mark[0] == "sign":
                size = self._px(SIGN_PX)
                box = QRectF(x, middle - size / 2, size, size)
                _renderer(mark[1], mark[2], ink).render(painter, box)
                if mark[2]:
                    painter.setFont(self.side_font)
                    painter.setPen(ink)
                    painter.drawText(QRectF(box.right(), box.top(), width - size, size),
                                     BOTTOM_LEFT, mark[2][0].upper())
                if gate is not None and gate.name == name:
                    self._ring(painter, box, hold, gate.fraction())
            elif mark[0] == "pedal":
                height = self._px(PEDAL_PX[1])
                self._pedal(painter, QRectF(x, middle - height / 2, width, height), mark[1], ink)
            else:
                painter.setFont(self.font)
                painter.setPen(ink)
                painter.drawText(QRectF(x, middle - self._px(ROW_HEIGHT) / 2, width + 1,
                                        self._px(ROW_HEIGHT)), LEFT, mark[1])
            x += width + self._px(MARK_GAP)

    def _pedal(self, painter, box, index, ink):
        unit = box.width() / 20
        painter.setPen(QPen(ink, max(1.0, 1.3 * unit)))
        for key in range(3):
            painter.setBrush(ink if key == index else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(box.left() + (1 + key * 7) * unit, box.top() + unit,
                                           5 * unit, box.height() - 2 * unit),
                                    1.6 * unit, 1.6 * unit)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _ring(self, painter, box, colour, fraction):
        radius = box.width() * 12.4 / 24
        centre = box.center()
        around = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
        track = QColor(colour)
        track.setAlphaF(0.25)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(track, self._px(RING_PX)))
        painter.drawEllipse(around)
        pen = QPen(colour, self._px(RING_PX))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawArc(around, 90 * 16, -round(fraction * 360 * 16))


class Ticker:
    """Repaints a widget every frame while a gesture it shows serves its hold."""

    def __init__(self, widget):
        self.gate = None
        self._widget = widget
        self._timer = QTimer(widget)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def follow(self, gate, shown):
        """Keep gate where it is shown, repainting until its hold is served."""
        self.gate = gate if shown else None
        if self.gate is None:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()
        self._widget.update()

    def _tick(self):
        self._widget.update()
        if self.gate is None or self.gate.fraction() >= 1.0:
            self._timer.stop()


class KeyCard(QWidget):
    """One key per row, what that key does, and the inputs that send it."""

    def __init__(self, hints=(), parent=None, scale=1.0, calm=False, held_only=False):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.scale = float(scale)
        self.calm = bool(calm)
        self.held_only = bool(held_only)
        self._font = QFont("Fira Code")
        self._font.setPixelSize(round(FONT_PX * self.scale))
        self._marks = Marks(self._font, self.scale)
        self._ticker = Ticker(self)
        self._gate = None
        self._rows = []
        self.light = False
        self.set_hints(hints)

    def set_hints(self, hints):
        """Show (key, effect) or (key, effect, input names) rows."""
        self._rows = [(str(key), str(says), tuple(str(name) for name in (rest[0] if rest else ())))
                      for key, says, *rest in hints]
        self._follow_the_gate()

    def set_gate(self, gate):
        """Outline the rows the gesture serving its hold drives, its sign ringed, or none."""
        self._gate = gate
        self._follow_the_gate()

    def _follow_the_gate(self):
        self._ticker.follow(self._gate, bool(self.held_rows))
        self.resize(self.sizeHint())
        self.updateGeometry()

    def set_light(self, light):
        """Paint the card for a light surface behind it, or a dark one."""
        self.light = bool(light)
        self.update()

    @property
    def hints(self) -> tuple:
        """Return what the card says, as (key, effect) pairs."""
        return tuple((key, says) for key, says, _ in self._rows)

    @property
    def inputs(self) -> tuple:
        """Return the input names each row carries, in row order."""
        return tuple(names for _, _, names in self._rows)

    @property
    def held_rows(self) -> tuple:
        """Return the (key, effect) of every row the gesture serving its hold drives."""
        if self._gate is None:
            return ()
        return tuple((key, says) for key, says, names in self._rows if self._gate.name in names)

    def _shown(self) -> list:
        if not self.held_only:
            return self._rows
        held = set(self.held_rows)
        return [row for row in self._rows if row[:2] in held]

    def _px(self, length) -> int:
        return round(length * self.scale)

    def _columns(self) -> tuple:
        """Return the widths of the inputs, effect and key columns, inputs 0 where none."""
        rows, metrics = self._shown(), QFontMetrics(self._font)
        inputs = max(round(self._marks.width(names)) for _, _, names in rows)
        says = max(metrics.horizontalAdvance(says) for _, says, _ in rows)
        keys = max(metrics.horizontalAdvance(key) for key, _, _ in rows)
        return inputs, says, keys

    def sizeHint(self) -> QSize:
        """Size the card to its widest row."""
        rows = self._shown()
        if not rows:
            return QSize(0, 0)
        inputs, says, keys = self._columns()
        gaps = (2 if inputs else 1) * self._px(GAP)
        return QSize(inputs + says + keys + gaps + 2 * self._px(PAD_X),
                     self._px(ROW_HEIGHT) * len(rows) + 2 * self._px(PAD_Y))

    def place_top_right(self, within):
        """Place the card in the top-right corner of within, in parent coordinates."""
        size = self.sizeHint()
        self.setGeometry(within.right() - size.width() - MARGIN,
                         within.top() + MARGIN, size.width(), size.height())

    def _tones(self) -> tuple:
        """Return the bright, effect, faint and hold colours."""
        if self.calm:
            return CALM_INPUTS, CALM_SAYS, CALM_KEY, CALM_HOLD
        return (QColor(PALETTE['base01' if self.light else 'base1']), QColor(PALETTE['base00']),
                QColor(PALETTE['base1' if self.light else 'base01']), QColor(PALETTE['blue']))

    def paintEvent(self, event):
        rows = self._shown()
        if not rows:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.calm:
            behind = QColor(PALETTE['base2' if self.light else 'base03'])
            behind.setAlpha(BACKGROUND_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(behind)
            painter.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)

        inputs, says, keys = self._columns()
        bright, said, faint, hold = self._tones()
        gap, row_height = self._px(GAP), self._px(ROW_HEIGHT)
        left = self._px(PAD_X)
        gate = self._ticker.gate

        top = self._px(PAD_Y)
        for key, effect, names in rows:
            if gate is not None and gate.name in names:
                width = self._px(OUTLINE_PX)
                painter.setPen(QPen(hold, width))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QRectF(width, top, self.width() - 2 * width, row_height),
                                        RADIUS, RADIUS)
            painter.setFont(self._font)
            if inputs:
                self._marks.paint(painter, left + inputs, top + row_height / 2, names,
                                  bright, hold, gate)
                painter.setFont(self._font)
                painter.setPen(said)
                painter.drawText(QRectF(left + inputs + gap, top, says, row_height), LEFT, effect)
                painter.setPen(faint)
                painter.drawText(QRectF(left + inputs + says + 2 * gap, top, keys, row_height),
                                 LEFT, key)
            else:
                painter.setPen(bright)
                painter.drawText(QRectF(left, top, keys, row_height), RIGHT, key)
                painter.setPen(said)
                painter.drawText(QRectF(left + keys + gap, top, says, row_height), LEFT, effect)
            top += row_height


class InputMarks(QWidget):
    """The inputs that act on one line, the held gesture ringed by how much of it is served."""

    def __init__(self, names=(), scale=1.0, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scale = float(scale)
        self._font = QFont("Fira Code")
        self._font.setPixelSize(round(FONT_PX * self.scale))
        self._marks = Marks(self._font, self.scale)
        self._ticker = Ticker(self)
        self._gate = None
        self.names = ()
        self.set_names(names)

    def set_names(self, names):
        """Mark the line with these inputs, or with none."""
        self.names = tuple(str(name) for name in names)
        self._ticker.follow(self._gate, self.held)
        self.updateGeometry()

    def set_gate(self, gate):
        """Ring the gesture serving its hold where it is one of these inputs."""
        self._gate = gate
        self._ticker.follow(gate, self.held)

    @property
    def held(self) -> bool:
        """Report whether the gesture serving its hold is one of these inputs."""
        return self._gate is not None and self._gate.name in self.names

    def width_wanted(self) -> int:
        return round(self._marks.width(self.names))

    def sizeHint(self) -> QSize:
        return QSize(self.width_wanted(), round(ROW_HEIGHT * self.scale))

    def paintEvent(self, event):
        if not self.names:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = QColor(PALETTE['base1'])
        self._marks.paint(painter, self.width(), self.height() / 2, self.names, ink,
                          QColor(PALETTE['blue']), self._ticker.gate)


class MarkedLine(QWidget):
    """A line with the inputs that act on it before it, outlined while one of them is held."""

    pressed = pyqtSignal()

    def __init__(self, label, scale=1.0, parent=None):
        super().__init__(parent)
        self.label = label
        self.marks = InputMarks(scale=scale)
        self.scale = float(scale)
        layout = QHBoxLayout(self)
        pad = round(OUTLINE_PX * 3 * self.scale)
        layout.setContentsMargins(pad, pad // 2, pad, pad // 2)
        layout.setSpacing(round(GAP * self.scale))
        layout.addStretch()
        layout.addWidget(self.marks)
        layout.addWidget(label)
        layout.addStretch()

    def set_names(self, names, width=None):
        """Mark the line with these inputs, in a column width wide where one is given."""
        names = tuple(str(name) for name in names)
        if names == self.marks.names and width is None and self.marks.isVisible() == bool(names):
            return
        self.marks.set_names(names)
        self.marks.setFixedWidth(self.marks.width_wanted() if width is None else width)
        self.marks.setVisible(bool(width) or bool(self.marks.names))
        self.update()

    def set_gate(self, gate):
        """Outline the line while a gesture that acts on it serves its hold."""
        self.marks.set_gate(gate)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if not self.marks.held:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = round(OUTLINE_PX * self.scale)
        painter.setPen(QPen(QColor(PALETTE['blue']), width))
        box = self.marks.geometry().united(self.label.geometry())
        pad = 2 * width
        painter.drawRoundedRect(QRectF(box).adjusted(-pad, -width, pad, width).intersected(
            QRectF(self.rect()).adjusted(width / 2, width / 2, -width / 2, -width / 2)),
            RADIUS, RADIUS)
