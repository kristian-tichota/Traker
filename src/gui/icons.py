import logging
import os

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from src.config import PALETTE

log = logging.getLogger(__name__)

ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons")

TINT_ANCHOR = "currentColor"

ICON_PX = 16

RENDER_PX = ICON_PX * 2

TAB_ICONS = {
    "pomodoro": ("clock-hour-4", "cyan"),
    "food": ("apple", "yellow"),
    "beverages": ("cup", "orange"),
    "exercise": ("barbell", "green"),
    "supplements": ("pill", "violet"),
    "mobility": ("stretching", "blue"),
    "food_graphs": ("chart-line", "yellow"),
    "exercise_graphs": ("chart-bar", "green"),
    "heatmap": ("layout-grid", "green"),
    "caffeine_graph": ("chart-area-line", "orange"),
    "supplement_graphs": ("chart-histogram", "violet"),
    "plans": ("calendar-event", "magenta"),
    "chores": ("checklist", "red"),
}

_BUILT = {}


def tab_icon(registry_key: str) -> QIcon:
    """The icon for a tab, or an empty one for a tab with none declared."""
    entry = TAB_ICONS.get(registry_key)
    if entry is None:
        return QIcon()
    return coloured_icon(*entry)


def coloured_icon(name: str, accent: str) -> QIcon:
    """One vendored glyph, stroked in PALETTE[accent]."""
    key = (name, accent)
    if key in _BUILT:
        return _BUILT[key]

    icon = QIcon()
    markup = _read(name)
    if markup:
        colour = PALETTE.get(accent, PALETTE["base00"])
        icon = _rendered(markup.replace(TINT_ANCHOR, colour), name)
    _BUILT[key] = icon
    return icon


def _read(name: str) -> str:
    path = os.path.join(ICON_DIR, f"{name}.svg")
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as unreadable:
        log.warning("No tab icon %r (%s); that tab keeps its label alone.",
                    name, unreadable)
        return ""


def _rendered(markup: str, name: str) -> QIcon:
    """The tinted markup as an icon, or an empty one if it will not parse."""
    renderer = QSvgRenderer(QByteArray(markup.encode("utf-8")))
    if not renderer.isValid():
        log.warning("Tab icon %r is not valid SVG; leaving that tab bare.", name)
        return QIcon()

    pixmap = QPixmap(RENDER_PX, RENDER_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, RENDER_PX, RENDER_PX))
    painter.end()
    return QIcon(pixmap)
