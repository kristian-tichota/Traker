from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QVBoxLayout, QWidget)

from src.config import PALETTE

TITLE = "SOUND"
COLUMNS = 5
PLAY, STOP = "▶  PLAY", "■  STOP"

FONT = "font-family: 'Fira Code';"
BUTTON = f"""
    QPushButton {{
        background-color: {PALETTE['base3']}; color: {PALETTE['base01']};
        padding: 4px 10px; font-size: 11px; {FONT}
        border: 1px solid transparent; border-radius: 2px;
    }}
    QPushButton:hover {{ background-color: {PALETTE['base2']}; color: {PALETTE['base03']}; }}
    QPushButton:checked {{
        background-color: {PALETTE['base2']}; color: {PALETTE['base03']};
        border: 1px solid {{edge}};
    }}
"""
SLIDER = f"""
    QSlider::groove:horizontal {{ height: 4px; background: {PALETTE['base2']}; }}
    QSlider::sub-page:horizontal {{ background: {PALETTE['base1']}; }}
    QSlider::handle:horizontal {{
        width: 12px; margin: -5px 0; border-radius: 6px; background: {PALETTE['base01']};
    }}
"""


class SoundPanel(QWidget):
    """The ambience by mouse: on or off, which scene, and how loud."""

    switched = pyqtSignal(bool)
    scene_chosen = pyqtSignal(str)
    volume_chosen = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playing = False
        self.scenes = []
        self._edge = PALETTE['base1']
        self._buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(6)

        title = QLabel(TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {PALETTE['base00']}; font-size: 11px; font-weight: bold; "
                            f"letter-spacing: 2px; {FONT}")
        layout.addWidget(title)

        self.toggle = self._button(PLAY)
        self.toggle.clicked.connect(lambda: self.switched.emit(not self.playing))
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.toggle)
        layout.addLayout(row)

        self._grid = QGridLayout()
        self._grid.setSpacing(4)
        grid_row = QHBoxLayout()
        grid_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid_row.addLayout(self._grid)
        layout.addLayout(grid_row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setSingleStep(10)
        self.slider.setPageStep(10)
        self.slider.setFixedWidth(220)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.setStyleSheet(SLIDER)
        self.slider.valueChanged.connect(lambda value: self.volume_chosen.emit(value / 100))
        self.lbl_volume = QLabel()
        self.lbl_volume.setFixedWidth(48)
        self.lbl_volume.setStyleSheet(f"color: {PALETTE['base01']}; font-size: 11px; {FONT}")
        volume_row = QHBoxLayout()
        volume_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        volume_row.addWidget(self.slider)
        volume_row.addWidget(self.lbl_volume)
        layout.addLayout(volume_row)

        self.lbl_note = QLabel()
        self.lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_note.setStyleSheet(f"color: {PALETTE['orange']}; font-size: 10px; {FONT}")
        self.lbl_note.setVisible(False)
        layout.addWidget(self.lbl_note)

    def show_state(self, scenes, chosen, volume, playing):
        """Show scenes as (name, shown) pairs, the chosen one marked, without signalling."""
        self.playing = playing
        if scenes != self.scenes:
            self._lay_out(scenes)
        edge = PALETTE['blue'] if playing else PALETTE['base1']
        if edge != self._edge:
            self._edge = edge
            for button in [self.toggle, *self._buttons.values()]:
                button.setStyleSheet(BUTTON.replace("{edge}", edge))
        for name, button in self._buttons.items():
            button.setChecked(name == chosen)
        self.toggle.setText(STOP if playing else PLAY)
        self.toggle.setChecked(playing)
        self.slider.blockSignals(True)
        self.slider.setValue(round(volume * 100))
        self.slider.blockSignals(False)
        self.lbl_volume.setText(f"{round(volume * 100)} %")

    def set_note(self, note):
        """Show a warning under the controls, or none."""
        self.lbl_note.setText(note)
        self.lbl_note.setVisible(bool(note))

    def chosen(self) -> str:
        """Return the name of the scene marked, or ""."""
        return next((name for name, button in self._buttons.items() if button.isChecked()), "")

    def _lay_out(self, scenes):
        for button in self._buttons.values():
            self._grid.removeWidget(button)
            button.deleteLater()
        self.scenes = list(scenes)
        self._buttons = {}
        for index, (name, shown) in enumerate(self.scenes):
            button = self._button(shown)
            button.clicked.connect(lambda _, name=name: self.scene_chosen.emit(name))
            self._grid.addWidget(button, index // COLUMNS, index % COLUMNS)
            self._buttons[name] = button

    def _button(self, text) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet(BUTTON.replace("{edge}", self._edge))
        return button
