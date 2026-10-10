from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE
from src.gui.animations import grey_of
from src.gui.components.key_card import KeyCard
from src.gui.components.media_progress import MediaProgress

LEGEND_SCALE = 2.2
PLAYING_PX = 15
PLAYING_TONE = grey_of(PALETTE['base01'], 0.8)
PROGRESS_PX = 420
SPACING_PX = 36


class CalmFace(QWidget):
    """What a wall beside an activity keeps: the time left, what is showing, and its keys."""

    def __init__(self, ring, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        layout.addWidget(ring)

        self.playing = QLabel()
        self.playing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playing.setStyleSheet(f"color: {PLAYING_TONE.name()}; font-size: {PLAYING_PX}px;"
                                   f" font-family: 'Fira Code';")
        self.playing.setVisible(False)
        layout.addSpacing(SPACING_PX // 2)
        layout.addWidget(self.playing)

        self.progress = MediaProgress(calm=True)
        self.progress.setFixedWidth(PROGRESS_PX)
        self.progress.setVisible(False)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.legend = KeyCard(scale=LEGEND_SCALE, calm=True)
        self.legend.setVisible(False)
        layout.addSpacing(SPACING_PX)
        layout.addWidget(self.legend, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def set_playing(self, playing):
        """Name what is showing and where it has reached, or nothing."""
        self.playing.setVisible(playing is not None)
        self.progress.setVisible(playing is not None)
        if playing is None:
            return
        name, place, unit = playing
        self.playing.setText(name)
        self.progress.show_place(place, unit)
