import datetime
import logging
import math
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QStackedWidget,
                             QApplication)
from PyQt6.QtCore import (Qt, QTimer, pyqtProperty, QPropertyAnimation, QDateTime,
                          QEvent, QRect, QThreadPool, pyqtSignal)
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QIcon, QPainterPath
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from src.config import PALETTE
from src.desktop import activities as break_activities
from src.desktop import notify as notify_service
from src.desktop import rest_positions
from src.desktop import rest_queue
from src.desktop.idle import idle_ms as session_idle_ms
from src.desktop.kwin import KWinPin, default_app_id
from src.desktop.kwin_rules import REST_GROUP, RestRule, prune
from src.desktop.switch_guard import SwitchGuard
from src.domain import chores, formulas, media, plans
from src.domain.clock import as_displayed_date, minutes_covered
from src.profile import (DEFAULT_IDLE_PAUSE_SECS, DEFAULT_STOP_HOLD_SECS,
                         UserProfile)
from src.gui.components.chore_panel import KEYS as CHORE_KEYS, ChorePanel
from src.gui.components.key_card import KeyCard
from src.gui.components.media_progress import MediaProgress
from src.gui.components.media_surface import MediaSurface
from src.gui.components.timeline_popup import TimelinePopupWidget
from src.gui.components.upcoming_panel import UpcomingPanel
from src.gui.lifecycle import PausesWhenHidden, ShutdownMixin
from src.gui.domains import CHORE
from src.gui.workers import discard, run_in_background

log = logging.getLogger(__name__)

MS_PER_MINUTE = 60_000

RELEASE_KEY = Qt.Key.Key_Escape
RELEASE_KEY_NAME = "ESC"

LONG_BREAK_EVENT = "long_break_started"

HOLD_TICK_MS = 50

HOLD_RELEASE = "release"
HOLD_STOP = "stop"

IDLE_POLL_MS = 1000

SCREENS_SETTLE_MS = 400

PROMPT_BORDER_PX = 16

PLAYING_TITLE = "NOW PLAYING"
PROGRESS_PX = 420

WALL_NAME = "strictWall"


def read_day(db):
    """Read the day summary and this member's stress overrides, in one call."""
    summary = db.get_pomodoro_daily_summary()
    overrides = getattr(db, "get_pomodoro_dsi_overrides", dict)()
    return summary, overrides


def read_upcoming(db) -> list:
    """Read today's planned session, as a break surface states it."""
    plan = plans.current_plan(db.get_training_plans())
    if plan is None:
        return []

    today = plans.today_iso()
    session, movements = plans.prescribed_day(
        db.get_plan_sessions(plan.id), db.get_plan_movements(plan.id), today)
    if session is None:
        return [(as_displayed_date(today), ["nothing planned"])]

    title = f"{as_displayed_date(today)} · {session.name}"
    if session.week:
        title = f"{title} · W{session.week}"
    lines = [plans.movement_text(movement) for movement in movements]
    return [(title, lines or ["no movements prescribed"])]


def read_chores(db) -> list:
    """Read what the household owes today, worst first."""
    return chores.due_now(db.get_chores())


def complete_chore(db, chore_id: int, name: str) -> tuple:
    """Tick one chore, carrying back which one."""
    success, message = db.complete_chore(
        {"name": name, "date": chores.today_iso()})
    return chore_id, success, message


def is_typing_into(watched) -> bool:
    """Report whether this key was delivered to a text field."""
    return isinstance(watched, QLineEdit)


def read_long_breaks_spent(db) -> tuple:
    """Read (date, count) for the long breaks today has already spent."""
    today = datetime.date.today().isoformat()
    events = db.get_pomodoro_events_for_day(today)
    return today, sum(1 for event in events
                      if len(event) > 1 and event[1] == LONG_BREAK_EVENT)


def rewrite_as_rest(db, minutes) -> tuple:
    """Store each of those minutes as rest overtime, replacing what stands."""
    written = 0
    for date_iso, minute_of_day in minutes:
        stored, _ = db.log_pomodoro_heartbeat(
            {"date": date_iso, "minute_of_day": minute_of_day, "second": 0,
             "state": "rest_overtime"})
        written += bool(stored)
    return written, len(minutes)


def read_was_answered(db) -> bool:
    """Report whether the last read reached the household service."""
    connection = getattr(db, "connection", None)
    return connection is None or connection.online


class LongBreakDots(QWidget):
    """The day's long breaks: one dot each, filled as they are spent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.spent = 0
        self.available = 0

    def set_spent(self, spent, available):
        self.spent = max(0, int(spent))
        self.available = max(0, int(available))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        circle_size = 8
        spacing = 12
        total_width = (self.available * circle_size) + ((self.available - 1) * spacing)
        start_x = (self.width() - total_width) // 2
        start_y = (self.height() - circle_size) // 2

        for i in range(self.available):
            x = start_x + i * (circle_size + spacing)
            painter.setPen(Qt.PenStyle.NoPen)
            if i < self.spent:
                painter.setBrush(QColor(PALETTE['violet']))
            else:
                painter.setBrush(QColor(PALETTE['base2']))
            painter.drawEllipse(x, start_y, circle_size, circle_size)


class AnimatedPlayPauseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self._morph_factor = 0.0
        self.is_playing = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.animation = QPropertyAnimation(self, b"morph_factor")
        self.animation.setDuration(120)

    @pyqtProperty(float)
    def morph_factor(self):
        return self._morph_factor

    @morph_factor.setter
    def morph_factor(self, value):
        self._morph_factor = value
        self.update()

    def set_playing(self, playing: bool):
        self.is_playing = playing
        self.animation.stop()
        self.animation.setStartValue(self._morph_factor)
        self.animation.setEndValue(1.0 if playing else 0.0)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(PALETTE['base2']) if self.underMouse() else QColor(PALETTE['base3'])
        painter.setPen(QPen(QColor(PALETTE['base1']), 1))
        painter.setBrush(bg_color)
        painter.drawEllipse(2, 2, self.width() - 4, self.height() - 4)

        box_size = 12
        cx, cy = self.width() / 2, self.height() / 2
        x0, y0 = cx - box_size / 2, cy - box_size / 2
        f = self._morph_factor

        p1_x, p1_y = x0 + (2 * f), y0
        p2_x, p2_y = x0 + (2 * f), y0 + box_size
        p3_x, p3_y = x0 + box_size, (y0 + box_size / 2) + ((box_size / 2) * f)
        p4_x, p4_y = x0 + box_size, (y0 + box_size / 2) - ((box_size / 2) * f)

        path = QPainterPath()
        path.moveTo(p1_x, p1_y)
        path.lineTo(p2_x, p2_y)
        path.lineTo(p3_x, p3_y)
        path.lineTo(p4_x, p4_y)
        path.closeSubpath()

        if self.isEnabled():
            fill_color = QColor(PALETTE['magenta']) if self.is_playing else QColor(PALETTE['blue'])
        else:
            fill_color = QColor(PALETTE['base1'])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawPath(path)


class HoldRing(QWidget):
    """What leaving a break, or stopping focus, costs — drawn as it is paid."""

    SIDE = 38

    def __init__(self, hold_secs, parent=None):
        super().__init__(parent)
        self.hold_secs = float(hold_secs)
        self.fraction = 0.0
        self.setFixedHeight(self.SIDE + 8)

    def set_hold_secs(self, secs):
        self.hold_secs = float(secs)

    def set_fraction(self, fraction):
        self.fraction = max(0.0, min(1.0, float(fraction)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = self.SIDE
        box = QRect((self.width() - side) // 2, 4, side, side)

        painter.setPen(QPen(QColor(PALETTE['base1']), 3))
        painter.drawArc(box, 0, 360 * 16)

        painter.setPen(QPen(QColor(PALETTE['magenta']), 3))
        painter.drawArc(box, 90 * 16, -int(360 * 16 * self.fraction))

        left = max(0, math.ceil(self.hold_secs * (1.0 - self.fraction)))
        painter.setPen(QColor(PALETTE['base01']))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, str(left))

WALL_CAPTION = "Traker rest"


def wall_caption(screen) -> str:
    """Return what to call the wall on screen."""
    name = screen.name() if screen is not None else ""
    return f"{WALL_CAPTION} \u2014 {name}" if name else WALL_CAPTION


class StrictOverlay(QWidget):
    """One screen of a break: its readouts, or what the break is showing."""

    FLAGS = (Qt.WindowType.Window |
             Qt.WindowType.FramelessWindowHint |
             Qt.WindowType.WindowStaysOnTopHint)

    def __init__(self, timer_ref, screen, parent=None):
        super().__init__(parent)
        self.timer_ref = timer_ref
        self.screen_covered = screen
        self.output_name = screen.name() if screen is not None else ""
        self.stands_corrected = False
        self.let_go = False
        self._playing_name = None
        self._prompting = None
        self._dressed = None
        self.setWindowFlags(self.FLAGS)
        self.setWindowTitle(wall_caption(screen))
        self.setObjectName(WALL_NAME)
        self.setStyleSheet(
            f"#{WALL_NAME} {{ background-color: {PALETTE['base03']}; }}")

        self.keys = KeyCard(parent=self)
        self.keys.setVisible(False)

        # Qt rebuilds a mapped window the first time a GL child reaches it: this one is first.
        self.texture_page = QOpenGLWidget(self)
        self.texture_page.hide()

        self.frame = QVBoxLayout(self)
        self.frame.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(self)
        self.frame.addWidget(self.stack)
        self.readouts = QWidget(self.stack)
        self.stack.addWidget(self.readouts)
        self.media = None

        self._build_body(QVBoxLayout(self.readouts))
        self.setGeometry(screen.geometry())
        self.update_display()

    def closeEvent(self, event):
        """Refuse to close while the break still holds."""
        if not self.let_go and self.timer_ref.holds_the_screens():
            event.ignore()
            return
        super().closeEvent(event)

    def forget_screen(self):
        """Release the output this wall covers."""
        self.screen_covered = None

    def dismiss(self):
        """Close the wall at the end of the break."""
        self.let_go = True
        self.close()

    def media_parent(self):
        """Return the widget to build the media surface under."""
        return self.stack

    def host_media(self, surface):
        """Take the surface this break shows files on."""
        self.media = surface
        self.stack.addWidget(surface)

    def show_media(self) -> bool:
        """Show the file instead of the readouts."""
        if self.media is None:
            return False
        self.stack.setCurrentWidget(self.media)
        return True

    def hide_media(self):
        """Show the readouts again."""
        self.stack.setCurrentWidget(self.readouts)

    def is_showing_media(self) -> bool:
        return self.media is not None and self.stack.currentWidget() is self.media

    def set_keys(self, hints):
        """Name the keys that drive what is showing, or none of them."""
        self.keys.set_hints(hints)
        self.keys.setVisible(bool(hints))
        self.keys.place_top_right(self.rect())
        self.keys.raise_()

    def resizeEvent(self, event):
        """Keep the card in its corner and the sign at the screen's scale."""
        super().resizeEvent(event)
        self.keys.place_top_right(self.rect())
        self.keys.raise_()
        self._dress_for_the_state()

    def covers_its_own_screen(self) -> bool:
        """Report whether the compositor put this wall on its intended output."""
        handle = self.windowHandle()
        if handle is None or self.screen_covered is None:
            return True
        return handle.screen() is self.screen_covered

    def take_its_screen_again(self):
        """Name the output once more and fill it again."""
        if self.screen_covered is None:
            return
        self.stands_corrected = True
        self.setScreen(self.screen_covered)
        self.setGeometry(self.screen_covered.geometry())
        self.showFullScreen()
        self.raise_()

    def _build_body(self, layout):
        """Build the countdown, and what it costs to leave it."""
        layout.addStretch()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.hold_ring = HoldRing(self.timer_ref.release_hold_secs)
        self.hold_ring.setVisible(False)
        layout.addWidget(self.hold_ring)

        self.lbl_hint = QLabel(self.timer_ref.wall_hint())
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_hint)
        self._dress_for_the_state()

        self.upcoming = UpcomingPanel()
        layout.addWidget(self.upcoming)

        self.playing = UpcomingPanel()
        layout.addWidget(self.playing)
        self.progress = MediaProgress()
        self.progress.setFixedWidth(PROGRESS_PX)
        self.progress.setVisible(False)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.chores = ChorePanel()
        self.chores.chore_ticked.connect(self.timer_ref.tick_chore)
        layout.addWidget(self.chores)

        layout.addStretch()

    def set_upcoming(self, sections):
        """Show what the view read when the break began."""
        self.upcoming.set_sections(sections)

    def set_chores(self, entries):
        """Show what is due, as the view read it when the break began."""
        self.chores.set_entries(entries)

    def set_offers_note(self, note):
        """State how long the offers are still held back, or nothing."""
        self.upcoming.set_note(self.timer_ref.OFFERS_TITLE, note)

    def set_playing(self, playing):
        """Name what is on the screen beside this one, and where it has reached."""
        self.progress.setVisible(playing is not None)
        if playing is None:
            self._playing_name = None
            self.playing.set_sections([])
            return
        name, place, unit = playing
        if name != self._playing_name:
            self._playing_name = name
            self.playing.set_sections([(PLAYING_TITLE, [name])])
        self.progress.show_place(place, unit)

    def update_display(self):
        """Update the countdown and the way on, both on every tick."""
        if self.timer_ref.waiting_for_work_start:
            self.label.setText(
                f"BREAK OVER\n+{media.as_elapsed(self.timer_ref.over_by_ms())}")
        else:
            mins, secs = divmod(int(self.timer_ref.time_left_ms // 1000), 60)
            self.label.setText(f"REST INTERVAL\n{mins:02d}:{secs:02d}")
        self.lbl_hint.setText(self.timer_ref.wall_hint())
        self._dress_for_the_state()

    def _dress_for_the_state(self):
        """Dress the wall as a desk countdown or as a sign read from the door."""
        prompting = self.timer_ref.prompts_for_focus()
        dressed = (prompting, self.height())
        if dressed == self._dressed:
            return
        self._dressed = dressed
        self._prompting = prompting

        inset = PROMPT_BORDER_PX if prompting else 0
        self.frame.setContentsMargins(inset, inset, inset, inset)

        if prompting:
            headline = max(28, self.height() // 16)
            instruction = max(11, self.height() // 48)
            self.label.setStyleSheet(f"color: {PALETTE['blue']};"
                                     f" font-size: {headline}px;"
                                     f" font-family: 'Fira Code';")
            self.lbl_hint.setStyleSheet(f"color: {PALETTE['base2']};"
                                        f" font-size: {instruction}px;"
                                        f" font-family: 'Fira Code';"
                                        f" letter-spacing: {max(2, instruction // 6)}px;")
            self.update()
            return

        self.label.setStyleSheet(f"color: {PALETTE['base01']}; font-size: 28px;"
                                 f" font-family: 'Fira Code';")
        self.lbl_hint.setStyleSheet(f"color: {PALETTE['base01']}; font-size: 11px;"
                                    f" font-family: 'Fira Code'; letter-spacing: 2px;")
        self.update()

    def paintEvent(self, event):
        """Paint the frame around a wall whose break has run out."""
        super().paintEvent(event)
        if not self._prompting:
            return
        painter = QPainter(self)
        pen = QPen(QColor(PALETTE['blue']), PROMPT_BORDER_PX)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        inset = PROMPT_BORDER_PX // 2
        painter.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))

    def show_hold(self, fraction, visible):
        self.hold_ring.set_fraction(fraction)
        self.hold_ring.setVisible(visible)

    def changeEvent(self, event):
        """Return to the front a moment after something else takes the focus."""
        if event.type() == event.Type.ActivationChange and not self.isActiveWindow() \
                and self.timer_ref.holds_the_screens():
            active_win = QApplication.activeWindow()
            if not self.timer_ref.owns_window(active_win):
                QTimer.singleShot(10, self._take_the_screen_back)
        super().changeEvent(event)

    def _take_the_screen_back(self):
        """Return to the front, a moment after something else took the focus."""
        if not self.timer_ref.owns_window(self) or not self.timer_ref.holds_the_screens():
            return
        self.raise_()
        self.activateWindow()


class StressCalendar(PausesWhenHidden, QWidget):
    """The last 30 days of the Daily Stress Index, one breathing cell per day."""

    paused_timer_attribute = "anim_timer"
    paused_timer_interval_ms = 30

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setFixedHeight(80)
        self.data_map = {}
        self.clock = 0.0

        self.setMouseTracking(True)
        self.hovered_date = None
        self.pinned_date = None
        self.rect_map = []

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate)

    def refresh(self):
        """Read the day summary for this calendar alone."""
        run_in_background(
            QThreadPool.globalInstance(), read_day, self._on_summary_read,
            None, self.db)

    def _on_summary_read(self, payload):
        if not read_was_answered(self.db):
            log.warning("Keeping the strain calendar: its read did not reach the service.")
            return
        self.apply_summary_data(payload)

    def apply_summary_data(self, payload):
        raw, overrides = payload
        self.data_map.clear()

        for row in raw:
            date_str = row.date
            focus_mins, rest_mins = row.focus_mins, row.rest_mins
            focus_ot, rest_ot = row.focus_overtime_mins, row.rest_overtime_mins
            dsi = formulas.daily_stress_index(
                focus_mins * 60, focus_ot * 60, rest_mins * 60, rest_ot * 60)

            self.data_map[date_str] = {
                "dsi": dsi,
                "active": focus_mins > 0 or rest_mins > 0 or focus_ot > 0 or rest_ot > 0,
                "focus_mins": focus_mins,
                "focus_ot": focus_ot
            }

        for override_date, val in overrides.items():
            try:
                pinned = float(val)
            except (TypeError, ValueError):
                log.warning("Ignoring a stored stress override that is not a number: %r", val)
                continue
            if not math.isfinite(pinned):
                log.warning("Ignoring a stored stress override that is not finite: %r", val)
                continue

            if override_date in self.data_map:
                self.data_map[override_date]["override_dsi"] = pinned
                self.data_map[override_date]["is_overridden"] = True
            else:
                self.data_map[override_date] = {
                    "dsi": 0.0,
                    "active": True,
                    "override_dsi": pinned,
                    "is_overridden": True,
                    "focus_mins": 0,
                    "focus_ot": 0
                }
        self.update()

    def _animate(self):
        self.clock += 0.06
        self.update()

    def _fetch_day_detail(self, date_iso):
        return (date_iso,
                self.db.get_pomodoro_heartbeats_for_day(date_iso),
                self.db.get_pomodoro_events_for_day(date_iso))

    def _load_day_into_popup(self, date_iso, show_close):
        def apply(payload):
            day, heartbeats, events = payload
            if day not in (self.hovered_date, self.pinned_date):
                return
            popup = self._get_popup()
            popup.set_data(day, heartbeats, events)
            popup.btn_close.setVisible(show_close)

        run_in_background(
            QThreadPool.globalInstance(), self._fetch_day_detail, apply, None, date_iso)

    def _get_popup(self):
        if not hasattr(self, '_popup') or self._popup is None:
            self._popup = TimelinePopupWidget(self.parentWidget())
            self._popup.unpin_callback = self._on_popup_unpinned
            self._popup.hide()
        return self._popup

    def _on_popup_unpinned(self):
        self.pinned_date = None
        self.hovered_date = None

    POPUP_OFFSET_PX = 20
    POPUP_FLIP_GAP_PX = 15
    POPUP_MARGIN_PX = 10

    def _day_at(self, pos):
        """Return the day whose square is under pos, or None."""
        for rect, date_iso in self.rect_map:
            if rect.contains(pos):
                return date_iso
        return None

    def _place_popup(self, popup, pos):
        """Put the popup beside pos, flipped where it would fall off."""
        parent_view = self.parentWidget()
        local = parent_view.mapFromGlobal(self.mapToGlobal(pos))

        x = local.x() + self.POPUP_OFFSET_PX
        y = local.y() + self.POPUP_OFFSET_PX
        if x + popup.width() > parent_view.width():
            x = local.x() - popup.width() - self.POPUP_FLIP_GAP_PX
        if y + popup.height() > parent_view.height():
            y = local.y() - popup.height() - self.POPUP_FLIP_GAP_PX

        popup.move(max(self.POPUP_MARGIN_PX, x), max(self.POPUP_MARGIN_PX, y))
        popup.raise_()
        popup.show()

    def mouseMoveEvent(self, event):
        if self.pinned_date is not None:
            return

        hit = self._day_at(event.pos())
        popup = self._get_popup()
        if not hit:
            self.hovered_date = None
            popup.hide()
            return

        if self.hovered_date != hit:
            self.hovered_date = hit
            self._load_day_into_popup(hit, show_close=False)

        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._place_popup(popup, event.pos())

    def mousePressEvent(self, event):
        hit = self._day_at(event.pos())
        popup = self._get_popup()
        if not hit:
            if self.pinned_date:
                self.pinned_date = None
                self.hovered_date = None
                popup.hide()
            return

        self.pinned_date = hit
        self.hovered_date = hit
        self._load_day_into_popup(hit, show_close=True)
        self._place_popup(popup, event.pos())

    def leaveEvent(self, event):
        if not self.pinned_date:
            self.hovered_date = None
            if hasattr(self, '_popup') and self._popup is not None:
                self._popup.hide()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=29)
        cell_size, spacing, cols = 28, 6, 15

        start_x = (self.width() - (cols * (cell_size + spacing))) // 2
        start_y = (self.height() - (2 * (cell_size + spacing))) // 2
        self.rect_map.clear()

        for i in range(30):
            d = start_date + datetime.timedelta(days=i)
            d_iso = d.isoformat()
            stats = self.data_map.get(d_iso, {"dsi": 0, "active": False})
            x = start_x + (i % cols) * (cell_size + spacing)
            y = start_y + (i // cols) * (cell_size + spacing)

            rect = QRect(x, y, cell_size, cell_size)
            self.rect_map.append((rect, d_iso))

            is_overridden = stats.get("is_overridden", False)
            display_dsi = stats.get("override_dsi", stats.get("dsi", 0.0)) if is_overridden else stats.get("dsi", 0.0)

            if not stats["active"]:
                base_color = QColor(PALETTE['base2'])
                alpha = 255
            else:
                if display_dsi <= 1.0: base_color = QColor(PALETTE['green'])
                elif display_dsi <= 1.5: base_color = QColor(PALETTE['yellow'])
                else: base_color = QColor(PALETTE['orange'])
                wave = (math.sin(self.clock * 2.0 + i * 0.5) + 1) / 2
                alpha = int(160 + (95 * wave))

            base_color.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(base_color)
            painter.drawRoundedRect(x, y, cell_size, cell_size, 2, 2)

            if stats["active"]:
                text_color = QColor(PALETTE['base03'])
                painter.setPen(QPen(text_color))
                font = painter.font()
                font.setFamily('Fira Code')
                font.setPixelSize(10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{display_dsi:.1f}")

                if is_overridden:
                    path = QPainterPath()
                    path.moveTo(x + cell_size - 6, y)
                    path.lineTo(x + cell_size, y)
                    path.lineTo(x + cell_size, y + 6)
                    path.closeSubpath()

                    subtle_color = QColor(PALETTE['base01'])
                    subtle_color.setAlpha(180)
                    painter.setBrush(subtle_color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPath(path)


class PomodoroView(ShutdownMixin, QWidget):
    data_changed = pyqtSignal(str)

    status_message = pyqtSignal(str)

    def __init__(self, db, tray_icon):
        super().__init__()
        self.db = db
        self.tray_icon = tray_icon
        self.threadpool = QThreadPool.globalInstance()
        self.profile = UserProfile()

        split = self.profile.timer_split()
        self.work_ms = split["focus_mins"] * MS_PER_MINUTE
        self.break_ms = split["break_mins"] * MS_PER_MINUTE
        self.long_break_ms = split["long_break_mins"] * MS_PER_MINUTE
        self.long_breaks_per_day = split["long_breaks_per_day"]
        self.strict_mode = split["strict"]
        self.stop_hold_secs = self.profile.number(
            "timer", "stop_hold_secs", DEFAULT_STOP_HOLD_SECS, low=1.0, high=60.0)
        self.idle_pause_ms = int(self.profile.number(
            "timer", "idle_pause_secs", DEFAULT_IDLE_PAUSE_SECS, low=0.0) * 1000)

        self.current_phase = "work"
        self.current_regime_str = ""

        self.time_left_ms = 0
        self.is_running = False

        self._long_break_queued = False
        self._long_breaks_used = 0
        self._long_break_day = datetime.date.today().isoformat()

        self.live_focus_ms = 0
        self.live_rest_ms = 0
        self.live_focus_ot_ms = 0
        self.live_rest_ot_ms = 0

        self.intra_minute_focus_ms = 0
        self.intra_minute_rest_ms = 0
        self.intra_minute_focus_ot_ms = 0
        self.intra_minute_rest_ot_ms = 0

        self.waiting_for_work_start = True
        self.waiting_for_break_start = False
        self._over_since_ms = 0

        self._handing_over = False

        self.last_frame_timestamp = 0
        self.last_tray_second = -1
        self.last_logged_minute = -1
        self.overlays = []

        self._strict_engaged = False
        self._media_host = None
        self._screen_taken = None
        self._filtering_keys = False
        self._watching_outputs = False
        self._screens_settling = QTimer(self)
        self._screens_settling.setSingleShot(True)
        self._screens_settling.timeout.connect(self._rewall_for_the_outputs)

        self._upcoming = []
        self._chores = []
        self._media_screen_name = str(self.profile.get_metric(
            "strict_break", "media_screen", "") or "").strip()
        self._window_screen_name = str(self.profile.get_metric(
            "window", "screen", "") or "").strip()
        self._refuse_switch = self.profile.get_metric(
            "strict_break", "refuse_switch", True) is not False
        self._chores_on_break = self.profile.get_metric(
            "chores", "on_break", True) is not False
        self.media_surface = None
        self._showing = None

        self.release_hold_secs = self.profile.number(
            "strict_break", "release_hold_secs", 10, low=1.0, high=60.0)
        self.warn_secs = self.profile.number(
            "strict_break", "warn_secs", 60, low=0.0)
        self.away_secs = self.profile.number(
            "strict_break", "away_secs", 300, low=0.0)
        self._warn_sound = str(self.profile.get_metric(
            "strict_break", "sound_name", "dialog-warning"))
        self._warn_sound_file = str(self.profile.get_metric(
            "strict_break", "sound_file", ""))

        self.activities = break_activities.read(
            self.profile.get_metric("strict_break", "activities", ()) or ())
        self._queue_path = rest_queue.path_for(self.profile)
        self._positions_path = rest_positions.beside(self._queue_path)
        self._offers = list(self.activities)
        self.media_pane_factory = None

        self.kwin_pin = None
        if self.profile.get_metric("strict_break", "follow_across_desktops", True):
            self.kwin_pin = KWinPin(
                self.profile.get_metric("strict_break", "app_id", "") or default_app_id(),
                wall_prefix=WALL_CAPTION,
                refuse_switch=self._refuse_switch)

        self.switch_guard = SwitchGuard() if self._refuse_switch else None

        prune((REST_GROUP,))
        self.rest_rule = None
        if self.profile.get_metric("strict_break", "pin_with_rule", True):
            self.rest_rule = RestRule(WALL_CAPTION)

        self._hold_timer = QTimer(self)
        self._hold_timer.timeout.connect(self._hold_tick)
        self._hold_started_ms = 0
        self._hold_for = None
        self._paid_stop_hold = False

        self.idle_source = session_idle_ms
        self._idled = False
        self._idle_watch = QTimer(self)
        self._idle_watch.timeout.connect(self._watch_for_the_member)
        self._warned_of_break = False
        self._said_the_offers_are_open = False

        self.setup_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._engine_loop)
        self.refresh_timer.start(self.visible_interval_ms())
        self._idle_watch.start(IDLE_POLL_MS)

    HIDDEN_INTERVAL_MS = 1000

    COVERED_INTERVAL_MS = 100

    FALLBACK_REFRESH_HZ = 180.0

    def visible_interval_ms(self):
        """Return one frame at the screen's refresh rate."""
        screen = QApplication.primaryScreen()
        rate = screen.refreshRate() if (screen and screen.refreshRate() > 0) \
            else self.FALLBACK_REFRESH_HZ
        return max(1, int(math.floor(1000.0 / rate)))

    def engine_interval_ms(self):
        """Return the cadence the engine should be running at now."""
        if not self.isVisible():
            return self.HIDDEN_INTERVAL_MS
        return self.COVERED_INTERVAL_MS if self._strict_engaged \
            else self.visible_interval_ms()

    def _apply_engine_cadence(self):
        if self.is_shut_down() or getattr(self, "refresh_timer", None) is None:
            return
        wanted = self.engine_interval_ms()
        if self.refresh_timer.interval() != wanted or not self.refresh_timer.isActive():
            self.refresh_timer.start(wanted)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_engine_cadence()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._apply_engine_cadence()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(12)

        self.lbl_split = QLabel(self.split_text())
        self.lbl_split.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_split.setStyleSheet(f"color: {PALETTE['base01']}; font-family: 'Fira Code'; font-size: 10px; font-weight: bold; letter-spacing: 2px;")
        layout.addWidget(self.lbl_split)

        self.lbl_phase = QLabel("FOCUS INTERVAL")
        self.lbl_phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_phase.setStyleSheet(f"color: {PALETTE['blue']}; font-size: 10px; font-weight: bold; font-family: 'Fira Code'; letter-spacing: 2px;")
        layout.addWidget(self.lbl_phase)

        self.lbl_regime = QLabel("REGIME: UNKNOWN")
        self.lbl_regime.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_regime.setStyleSheet(f"color: {PALETTE['base01']}; font-size: 11px; font-family: 'Fira Code'; font-style: italic;")
        layout.addWidget(self.lbl_regime)

        self.progress_dots = LongBreakDots()
        layout.addWidget(self.progress_dots)

        self.lbl_timer = QLabel(self._format_high_precision(0))
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer.setStyleSheet(f"color: {PALETTE['base03']}; font-size: 72px; font-family: 'Fira Code'; font-weight: 300;")
        layout.addWidget(self.lbl_timer)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.setSpacing(20)

        self.btn_play = AnimatedPlayPauseButton()
        self.btn_play.clicked.connect(self._toggle_timer)
        self.btn_play.pressed.connect(self._begin_stop_hold)
        self.btn_play.released.connect(self.cancel_hold)

        self.btn_skip = QPushButton("Skip Interval")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['base3']}; color: {PALETTE['base00']};
                padding: 6px 14px; font-size: 10px; font-family: 'Fira Code';
                border: 1px solid {PALETTE['base1']}; border-radius: 2px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['base2']}; color: {PALETTE['base03']};
            }}
        """)
        self.btn_skip.clicked.connect(self._skip_phase)

        self.btn_long = QPushButton()
        self.btn_long.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_long.setStyleSheet(self.btn_skip.styleSheet())
        self.btn_long.clicked.connect(self.toggle_long_break)

        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_skip)
        btn_layout.addWidget(self.btn_long)
        layout.addLayout(btn_layout)

        self.hold_ring = HoldRing(self.release_hold_secs)
        self.hold_ring.setVisible(False)
        layout.addWidget(self.hold_ring)

        self.lbl_release_hint = QLabel(self.release_hint())
        self.lbl_release_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_release_hint.setStyleSheet(f"color: {PALETTE['base01']}; font-size: 10px; font-family: 'Fira Code'; letter-spacing: 2px;")
        self.lbl_release_hint.setVisible(False)
        layout.addWidget(self.lbl_release_hint)

        self.upcoming = UpcomingPanel()
        layout.addWidget(self.upcoming)

        self.chores_panel = ChorePanel()
        self.chores_panel.chore_ticked.connect(self.tick_chore)
        layout.addWidget(self.chores_panel)

        self.panel_metrics = QWidget()
        self.panel_metrics.setFixedWidth(500)
        self.panel_metrics.setStyleSheet(f"background-color: {PALETTE['base3']}; border: none; font-family: 'Fira Code'; font-size: 11px;")

        metrics_layout = QVBoxLayout(self.panel_metrics)
        metrics_layout.setContentsMargins(10, 10, 10, 10)
        metrics_layout.setSpacing(8)

        self.rows_val_labels = []
        labels_text = [
            "Focus Accumulation",
            "Rest Accumulation",
            "Focus Overtime (Deep Flow)",
            "Rest Overtime (Delay Threshold)",
            "Live DSI Ratio"
        ]

        for text in labels_text:
            row_layout = QHBoxLayout()
            lbl_name = QLabel(text)
            lbl_name.setStyleSheet(f"color: {PALETTE['base01']};")
            lbl_val = QLabel("00:00.00" if "Ratio" not in text else "0.00")
            lbl_val.setStyleSheet(f"color: {PALETTE['base03']}; font-weight: bold;")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight)

            row_layout.addWidget(lbl_name)
            row_layout.addWidget(lbl_val)
            metrics_layout.addLayout(row_layout)
            self.rows_val_labels.append(lbl_val)

        metrics_container = QHBoxLayout()
        metrics_container.addStretch()
        metrics_container.addWidget(self.panel_metrics)
        metrics_container.addStretch()
        layout.addLayout(metrics_container)

        self.stress_calendar = StressCalendar(self.db, self)
        layout.addWidget(self.stress_calendar)
        layout.addStretch()

        self._start_waiting()

    def _record(self, event_type: str, amount_ms: int = 0):
        """Append one telemetry event off-thread, reporting any failure."""
        run_in_background(
            self.threadpool, self.db.log_pomodoro_event, discard, None,
            {
                "timestamp": datetime.datetime.now().isoformat(),
                "event_type": event_type,
                "amount_ms": amount_ms,
            },
        )

    def _get_current_state(self):
        """Return which of the four states this second accrues to."""
        if self.is_running:
            return 'focus' if self.current_phase == 'work' else 'rest'
        if self._idled or self.waiting_for_work_start:
            return 'rest_overtime'
        return 'focus_overtime'

    def split_text(self) -> str:
        """Return the schedule, stated once on the view."""
        return (f"{self.work_ms // MS_PER_MINUTE} / "
                f"{self.break_ms // MS_PER_MINUTE}"
                f"   ·   {self.long_break_ms // MS_PER_MINUTE} LONG "
                f"x{self.long_breaks_per_day}")

    def long_breaks_left(self) -> int:
        """Return how many long breaks today still holds."""
        self._roll_the_day()
        return max(0, self.long_breaks_per_day - self._long_breaks_used)

    def _roll_the_day(self):
        """Give the long breaks back at midnight."""
        today = datetime.date.today().isoformat()
        if today != self._long_break_day:
            self._long_break_day = today
            self._long_breaks_used = 0

    def toggle_long_break(self) -> str:
        """Toggle the queued long break and return the new state."""
        return self.set_long_break_queued(not self._long_break_queued)

    def set_long_break_queued(self, wanted: bool) -> str:
        """Set whether the next break is the long one."""
        if not wanted:
            was = self._long_break_queued
            self._long_break_queued = False
            self._apply_long_break_controls()
            return (" The next break is the ordinary one again." if was
                    else self.long_break_state())

        if self._long_break_queued:
            return self.long_break_state()

        if self.long_breaks_left() <= 0:
            self._apply_long_break_controls()
            if not self.long_breaks_per_day:
                return " No long breaks are configured."
            return (f" Both of today's {self.long_break_ms // MS_PER_MINUTE}"
                    f"-minute breaks are spent.")

        self._long_break_queued = True
        self._apply_long_break_controls()
        return (f" The next break is {self.long_break_ms // MS_PER_MINUTE}"
                f" minutes. {self.long_breaks_left()} of"
                f" {self.long_breaks_per_day} left today.")

    def long_break_state(self) -> str:
        """Return the line that answers a query about the long break."""
        queued = "queued" if self._long_break_queued else "not queued"
        return (f" Long break {queued}"
                f" · {self.long_break_ms // MS_PER_MINUTE} min"
                f" · {self.long_breaks_left()} of {self.long_breaks_per_day}"
                f" left today.")

    def _apply_long_break_controls(self):
        """Apply the button text and the dots for the current state."""
        minutes = self.long_break_ms // MS_PER_MINUTE
        self.btn_long.setText(f"{minutes}m Break Queued" if self._long_break_queued
                              else f"Queue {minutes}m Break")
        self.btn_long.setEnabled(
            bool(self._long_break_queued or self.long_breaks_left()))
        self.progress_dots.set_spent(self._long_breaks_used,
                                     self.long_breaks_per_day)

    def _spend_long_break(self):
        """Spend the queued long break."""
        self._long_break_queued = False
        self._long_breaks_used += 1
        self._record(LONG_BREAK_EVENT)

    def _read_long_breaks_spent(self):
        """Seed today's spend from the store."""
        run_in_background(self.threadpool, read_long_breaks_spent,
                          self._apply_long_breaks_spent, None, self.db)

    def _apply_long_breaks_spent(self, payload):
        """Apply the long breaks already spent today."""
        if not read_was_answered(self.db):
            log.warning("Not seeding today's long breaks: the read did not "
                        "reach the service.")
            return
        self._long_break_day, self._long_breaks_used = payload
        self._apply_long_break_controls()

    def _start_waiting(self):
        """Put focus on the clock, stopped, waiting for a start."""
        self.current_phase = "work"
        self.time_left_ms = self.work_ms
        self.is_running = False
        self.btn_play.set_playing(False)
        self.waiting_for_work_start = True
        self.waiting_for_break_start = False
        self._warned_of_break = False
        self._clear_overlays()

        self.lbl_phase.setText("READY - PRESS PLAY")
        self.lbl_phase.setStyleSheet(f"color: {PALETTE['blue']}; font-size: 10px; font-weight: bold; font-family: 'Fira Code'; letter-spacing: 2px;")
        self._apply_long_break_controls()
        self.lbl_timer.setText(self._format_high_precision(self.time_left_ms))

        self._update_tray()
        self._read_long_breaks_spent()
        self.refresh()

    def refresh(self):
        """Read the day's telemetry and, during a break, what is still due."""
        self._reload_day()
        self._update_tray()
        if self._strict_break_is_holding():
            self._read_chores()

    def _format_high_precision(self, ms: float) -> str:
        total_seconds = max(0.0, ms / 1000.0)
        mins, secs = divmod(int(total_seconds), 60)
        hundredths = int((total_seconds - int(total_seconds)) * 100)
        return f"{mins:02d}:{secs:02d}.{hundredths:02d}"

    def _reload_day(self, handing_over=False):
        """Read today once and feed both readouts of it."""
        self._handing_over = handing_over
        run_in_background(self.threadpool, read_day, self._apply_day, None, self.db)

    def _apply_day(self, payload):
        handing_over, self._handing_over = self._handing_over, False
        if not read_was_answered(self.db):
            log.warning("Keeping today's totals: the summary read did not reach the service.")
            return

        summary, _overrides = payload
        self._on_historical_aggregates_loaded(summary)

        if handing_over:
            self.intra_minute_focus_ms = 0
            self.intra_minute_rest_ms = 0
            self.intra_minute_focus_ot_ms = 0
            self.intra_minute_rest_ot_ms = 0

        self.stress_calendar.apply_summary_data(payload)

    def _on_historical_aggregates_loaded(self, daily_summary):
        today_str = datetime.date.today().isoformat()
        self.live_focus_ms = 0
        self.live_rest_ms = 0
        self.live_focus_ot_ms = 0
        self.live_rest_ot_ms = 0

        for row in daily_summary:
            if row.date == today_str:
                self.live_focus_ms = row.focus_mins * MS_PER_MINUTE
                self.live_rest_ms = row.rest_mins * MS_PER_MINUTE
                self.live_focus_ot_ms = row.focus_overtime_mins * MS_PER_MINUTE
                self.live_rest_ot_ms = row.rest_overtime_mins * MS_PER_MINUTE

    def _engine_loop(self):
        now = QDateTime.currentMSecsSinceEpoch()
        if self.last_frame_timestamp == 0:
            self.last_frame_timestamp = now
            return

        delta_ms = now - self.last_frame_timestamp
        self.last_frame_timestamp = now

        current_state = self._get_current_state()
        if current_state == 'focus':
            self.intra_minute_focus_ms += delta_ms
        elif current_state == 'rest':
            self.intra_minute_rest_ms += delta_ms
        elif current_state == 'focus_overtime':
            self.intra_minute_focus_ot_ms += delta_ms
        elif current_state == 'rest_overtime':
            self.intra_minute_rest_ot_ms += delta_ms

        dt_now = datetime.datetime.now()
        current_minute = dt_now.hour * 60 + dt_now.minute

        if current_minute != self.last_logged_minute and self.last_logged_minute != -1:
            heartbeat_data = {
                "date": dt_now.date().isoformat(),
                "minute_of_day": current_minute,
                "second": 0,
                "state": self._get_current_state(),
            }
            run_in_background(
                self.threadpool, self.db.log_pomodoro_heartbeat,
                discard, None, heartbeat_data)
            self._reload_day(handing_over=True)

        self.last_logged_minute = current_minute

        if self.is_running:
            self.time_left_ms -= delta_ms
            if (self.strict_mode and self.warn_secs and not self._warned_of_break
                    and self.current_phase == "work"
                    and self.time_left_ms <= self.warn_secs * 1000):
                self._warn_of_coming_break()
            if (not self._said_the_offers_are_open and self._offers
                    and self._strict_break_is_holding() and self.away_ms() > 0
                    and self.opens_in_ms() <= 0):
                self._say_the_offers_are_open()
            if self.time_left_ms <= 0:
                self.time_left_ms = 0
                if self.current_phase == "work" and not self.strict_mode:
                    self.is_running = False
                    self.btn_play.set_playing(False)
                    self.waiting_for_break_start = True
                    self.lbl_phase.setText("FOCUS OVER - PRESS PLAY")
                    self._update_tray()
                    return
                self._next_phase()
                return

        self.lbl_timer.setText(self._format_high_precision(self.time_left_ms))

        tot_f = self.live_focus_ms + self.intra_minute_focus_ms
        tot_r = self.live_rest_ms + self.intra_minute_rest_ms
        tot_f_ot = self.live_focus_ot_ms + self.intra_minute_focus_ot_ms
        tot_r_ot = self.live_rest_ot_ms + self.intra_minute_rest_ot_ms

        self.rows_val_labels[0].setText(self._format_high_precision(tot_f))
        self.rows_val_labels[1].setText(self._format_high_precision(tot_r))
        self.rows_val_labels[2].setText(self._format_high_precision(tot_f_ot))
        self.rows_val_labels[3].setText(self._format_high_precision(tot_r_ot))

        dsi = formulas.daily_stress_index(
            tot_f / 1000.0, tot_f_ot / 1000.0, tot_r / 1000.0, tot_r_ot / 1000.0)
        self.rows_val_labels[4].setText(f"{dsi:.2f}")

        current_sec = int(self.time_left_ms // 1000)
        if current_sec != self.last_tray_second:
            self.last_tray_second = current_sec
            new_regime = self.profile.get_current_regime()
            if new_regime != self.current_regime_str:
                self.current_regime_str = new_regime
                self.lbl_regime.setText(f"REGIME: {new_regime.upper()}")
            self._update_tray()

        self._redraw_break_surfaces()

    def _toggle_timer(self):
        if self._strict_break_is_holding():
            log.debug("Pause refused: a strict break is holding the screens.")
            return

        if self._paid_stop_hold:
            self._paid_stop_hold = False
            return

        if self._focus_is_running():
            log.debug("Stop refused: a running focus interval is held, not clicked.")
            return

        if self.waiting_for_break_start:
            self._record("resumed_break")
            self.waiting_for_break_start = False
            self._next_phase()
            return

        if self.waiting_for_work_start:
            self._record("resumed_focus")
            self.waiting_for_work_start = False
            self.is_running = True
            self.btn_play.set_playing(True)
            self._say_phase("FOCUS INTERVAL", PALETTE['blue'])
            self._clear_overlays()
            self._apply_exit_controls()
            self._update_tray()
            return

        self.is_running = not self.is_running
        self.btn_play.set_playing(self.is_running)

        if self.is_running:
            self._idled = False
            event_type = "resumed_focus" if self.current_phase == "work" else "resumed_break"
            if self.current_phase == "work":
                self._say_phase("FOCUS INTERVAL", PALETTE['blue'])
            else:
                self._say_phase(
                    self.current_phase.upper().replace("_", " "),
                    PALETTE['violet'] if "long" in self.current_phase else PALETTE['green'])
        else:
            event_type = "paused_focus" if self.current_phase == "work" else "paused_break"

        self._record(event_type)

        if "break" in self.current_phase and self.strict_mode:
            if self.is_running:
                self._enforce_strict_mode()
            else:
                self._clear_overlays()
        self._apply_exit_controls()
        self._update_tray()

    def _focus_is_running(self) -> bool:
        """Report whether a focus interval is on the clock now."""
        return self.is_running and self.current_phase == "work"

    def _say_phase(self, text, colour):
        """Set the phase line, in the colour of the state it names."""
        self.lbl_phase.setText(text)
        self.lbl_phase.setStyleSheet(
            f"color: {colour}; font-size: 10px; font-weight: bold; "
            f"font-family: 'Fira Code'; letter-spacing: 2px;")

    def _begin_stop_hold(self):
        """Begin the stop hold, the play button being the stop while running."""
        self._paid_stop_hold = False
        self.begin_hold(HOLD_STOP)

    def _stop_focus(self):
        """Stop the clock once the hold is paid, the waiting being focus overtime."""
        self._paid_stop_hold = True
        self.is_running = False
        self.btn_play.set_playing(False)
        self._record("paused_focus")
        self._say_phase("FOCUS STOPPED - PRESS PLAY", PALETTE['magenta'])
        self._apply_exit_controls()
        self._update_tray()

    def _watch_for_the_member(self):
        """Stop the clock for an absence, and start it again on any input."""
        if not self.idle_pause_ms or not (self._idled or self._focus_is_running()):
            return

        away = self.idle_source()
        if away is None:
            return

        if self._idled:
            if away < self.idle_pause_ms:
                self._came_back()
        elif away >= self.idle_pause_ms:
            self._walked_away()

    def _walked_away(self):
        """Stop the interval for a proven absence."""
        self.cancel_hold()
        self._idled = True
        self.is_running = False
        self.btn_play.set_playing(False)
        self._record("idled_focus", int(max(0, self.time_left_ms)))
        self._reattribute_the_inactivity()
        self._say_phase("AWAY - TIMER PAUSED", PALETTE['green'])
        self._apply_exit_controls()
        self._update_tray()

    def _reattribute_the_inactivity(self):
        """Reclassify the inactivity that proved the absence as rest."""
        moved = min(self.intra_minute_focus_ms, self.idle_pause_ms)
        self.intra_minute_focus_ms -= moved
        self.intra_minute_rest_ot_ms += moved

        ended = datetime.datetime.now()
        minutes = minutes_covered(
            ended - datetime.timedelta(milliseconds=self.idle_pause_ms), ended)
        if not minutes:
            return

        stored = len(minutes) * MS_PER_MINUTE
        self.live_focus_ms = max(0, self.live_focus_ms - stored)
        self.live_rest_ot_ms += stored
        run_in_background(self.threadpool, rewrite_as_rest,
                          self._absence_rewritten, None, self.db, minutes)

    def _absence_rewritten(self, payload):
        """Apply the long breaks already spent today."""
        written, asked = payload
        if written < asked:
            log.warning("Today still counts %d minute(s) of an absence as focus: "
                        "the service stored %d of %d.", asked - written, written, asked)
        self._reload_day()

    def _came_back(self):
        """Carry the interval on from where the absence stopped it."""
        self._idled = False
        self.is_running = True
        self.btn_play.set_playing(True)
        self._record("resumed_focus")
        self._say_phase("FOCUS INTERVAL", PALETTE['blue'])
        self._apply_exit_controls()
        self._update_tray()

    def _skip_phase(self):
        if self._strict_break_is_holding():
            log.debug("Skip refused: a strict break is holding the screens.")
            return

        event_type = "skipped_focus" if self.current_phase == "work" else "skipped_break"
        self._record(event_type, int(max(0, self.time_left_ms)))

        self.waiting_for_work_start = False
        self.waiting_for_break_start = False
        self._next_phase()

    def _next_phase(self):
        self.last_tray_second = -1
        self.cancel_hold()
        self._warned_of_break = False
        self._said_the_offers_are_open = False

        if self.current_phase == "work":
            if self._long_break_queued and self.long_breaks_left() > 0:
                self.current_phase = "long_break"
                self.time_left_ms = self.long_break_ms
                self._spend_long_break()
            else:
                self.current_phase = "break"
                self.time_left_ms = self.break_ms
            self._apply_long_break_controls()

            self.lbl_phase.setText(self.current_phase.upper().replace("_", " "))
            self.lbl_phase.setStyleSheet(f"color: {PALETTE['violet'] if 'long' in self.current_phase else PALETTE['green']}; font-size: 10px; font-weight: bold; font-family: 'Fira Code'; letter-spacing: 2px;")
            self.waiting_for_break_start = False
            self.waiting_for_work_start = False
            self.is_running = True
            self.btn_play.set_playing(True)

            if self.strict_mode:
                self._enforce_strict_mode()
        else:
            self.current_phase = "work"
            self.time_left_ms = self.work_ms
            self.lbl_phase.setText("REST OVER - PRESS PLAY")
            self.lbl_phase.setStyleSheet(f"color: {PALETTE['blue']}; font-size: 10px; font-weight: bold; font-family: 'Fira Code'; letter-spacing: 2px;")

            self.waiting_for_work_start = True
            self.waiting_for_break_start = False
            self._over_since_ms = QDateTime.currentMSecsSinceEpoch()
            self.is_running = False
            self.btn_play.set_playing(False)

            if self._strict_engaged:
                self._stand_down_enforcement()
                self._say_which_keys_drive_it()

        self.lbl_timer.setText(self._format_high_precision(self.time_left_ms))
        self._update_tray()
        self._apply_exit_controls()
        self._redraw_break_surfaces()
        self.refresh()

    def over_by_ms(self) -> int:
        """Return how long the wall has stood past the end of its break."""
        if not self.waiting_for_work_start or not self._over_since_ms:
            return 0
        return max(0, QDateTime.currentMSecsSinceEpoch() - self._over_since_ms)

    def release_hint(self) -> str:
        """Return what to hold, and for how long."""
        return f"HOLD {RELEASE_KEY_NAME} {self.release_hold_secs:.0f}s TO LEAVE"

    def wall_hint(self) -> str:
        """Return the way on, for the state the break is in."""
        if self.prompts_for_focus():
            return f"PRESS {RELEASE_KEY_NAME} TO START FOCUS"
        return self.release_hint()

    def media_key_hints(self, kind) -> list:
        """Return every key that drives what is showing, in reading order."""
        paging = kind == break_activities.DOCUMENT
        hints = [
            ("SPACE", "turn the page" if paging else "pause"),
            ("\u2190 \u2192", "page" if paging else "seek 30 s"),
            ("\u2191 \u2193", "scroll" if paging else "volume"),
            ("0", "back to Traker"),
        ]
        if len(self._offers) > 1:
            hints.append((f"1-{min(len(self._offers), 9)}", "another offer"))
        if self.prompts_for_focus():
            hints.append((RELEASE_KEY_NAME, "start focus"))
        else:
            hints.append((f"{RELEASE_KEY_NAME} {self.release_hold_secs:.0f}s",
                          "leave the break"))
        return hints

    def take_offers(self) -> list:
        """Return what this break may be handed to, in key order."""
        self._offers = (break_activities.queued(rest_queue.read(self._queue_path))
                        + list(self.activities))
        return self._offers

    OFFERS_TITLE = "SOMETHING TO DO"

    def away_ms(self) -> int:
        """Return how long this break holds its offers back."""
        return media.away_ms(self.away_secs, self.phase_length_ms(), self.break_ms)

    def opens_in_ms(self) -> int:
        """Return what is left of that wait, or nothing outside a held break."""
        if not self._strict_break_is_holding():
            return 0
        return media.opens_in(self.away_ms(), self.phase_length_ms(),
                              self.time_left_ms)

    def offers_note(self) -> str:
        """Return the title the offers carry while they are still held back."""
        left = self.opens_in_ms()
        return f"OPENS IN {media.as_elapsed(left)}" if left > 0 else ""

    def _say_when_the_offers_open(self):
        """Put the countdown note on every panel listing the offers."""
        note = self.offers_note()
        self.upcoming.set_note(self.OFFERS_TITLE, note)
        for overlay in self.overlays:
            overlay.set_offers_note(note)

    def _say_the_offers_are_open(self):
        """Announce that the wait is up, as a coming break is announced."""
        self._said_the_offers_are_open = True
        notify_service.notify(
            "The break can show something now",
            f"{media.as_elapsed(self.away_ms())} away from the screen is up. "
            f"{self.offer_key(0)} shows “{self._offers[0].name}”.",
            sound_name=self._warn_sound,
            sound_file=self._warn_sound_file,
        )

    def offer_section(self) -> list:
        """Return the offers as a panel section, or nothing where there are none."""
        if not self._offers:
            return []
        places = rest_positions.read(self._positions_path)
        return [(self.OFFERS_TITLE, self._offer_lines(places))]

    def _offer_lines(self, places) -> list:
        """Build one line per offer: its key, its name, and how far in it is."""
        said = [media.how_far(places.get(offer.path, media.Place()),
                              break_activities.readout_of(offer.kind))
                for offer in self._offers]
        keys = [self.offer_key(index) for index in range(len(self._offers))]
        if all(how == media.UNKNOWN for how in said):
            return [f"{key}  {offer.name}"
                    for key, offer in zip(keys, self._offers)]
        key_width = max(len(key) for key in keys)
        name_width = max(len(offer.name) for offer in self._offers)
        how_width = max(len(how) for how in said)
        return [f"{key:>{key_width}}  {offer.name:<{name_width}}  {how:>{how_width}}".rstrip()
                for key, offer, how in zip(keys, self._offers, said)]

    offer_key = staticmethod(break_activities.offer_key)

    def _break_surfaces(self) -> list:
        """Return every surface a break draws besides the timer view itself."""
        surfaces = list(self.overlays)
        if self.media_surface is not None:
            surfaces.append(self.media_surface)
        return surfaces

    def _redraw_break_surfaces(self):
        """Put the phase back on every surface the break draws."""
        playing = self._playing()
        for surface in self._break_surfaces():
            surface.update_display()
        for wall in self.overlays:
            wall.set_playing(playing)
        if self.media_surface is not None:
            self.media_surface.show_progress(playing[1:] if playing else None)
        self._say_when_the_offers_open()
        self._keep_the_walls_on_their_screens()

    def _playing(self) -> tuple:
        """Return what is showing and where it has reached: (name, place, unit)."""
        if self._showing is None or self.media_surface is None:
            return None
        place = self.media_surface.place()
        return ((self._showing.name,) + place) if place else None

    def _keep_the_walls_on_their_screens(self):
        """Report or correct a wall the compositor placed on another output."""
        placing = self.kwin_pin is not None and self.kwin_pin.engaged
        for overlay in self.overlays:
            if overlay.stands_corrected or overlay.covers_its_own_screen():
                continue
            if placing:
                overlay.stands_corrected = True
                log.warning("A break's wall for %s was placed elsewhere; KWin "
                            "was asked to move it there.", overlay.output_name)
                continue
            log.warning("A break's wall for %s was placed elsewhere and there "
                        "is no compositor script; naming that output again.",
                        overlay.output_name)
            overlay.take_its_screen_again()

    def owns_window(self, window) -> bool:
        """Report whether the window that took the focus is one of the walls."""
        return window is not None and window in self.overlays

    def holds_the_screens(self) -> bool:
        """Report whether a strict break owns the screens now."""
        return self._strict_break_is_holding()

    def _strict_break_is_holding(self) -> bool:
        """Report whether a running strict break owns the screens now."""
        return (self._strict_engaged and self.is_running
                and "break" in self.current_phase)

    def prompts_for_focus(self) -> bool:
        """Report whether the walls are up only to state that the break is over."""
        return self._strict_engaged and not self._strict_break_is_holding()

    def stop_hint(self) -> str:
        """Return what stopping a running interval costs, stated beside the ring."""
        return f"HOLD TO STOP · {self.stop_hold_secs:.0f}s"

    def _apply_exit_controls(self):
        """Refuse pause and skip while the screens are held, and price a stop."""
        holding = self._strict_break_is_holding()
        self.btn_play.setEnabled(not holding)
        self.btn_skip.setEnabled(not holding)
        self.lbl_release_hint.setText(
            self.release_hint() if holding else self.stop_hint())
        self.lbl_release_hint.setVisible(holding or self._focus_is_running())

    def eventFilter(self, watched, event):
        """Handle every key a break answers, wherever the focus is."""
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return super().eventFilter(watched, event)

        if self.prompts_for_focus():
            if event.type() == QEvent.Type.KeyPress \
                    and event.key() == RELEASE_KEY and not event.isAutoRepeat() \
                    and not is_typing_into(watched):
                self._toggle_timer()
                return True

        if self._strict_break_is_holding() \
                and event.key() == RELEASE_KEY and not event.isAutoRepeat():
            if event.type() == QEvent.Type.KeyPress:
                self.begin_hold()
            else:
                self.cancel_hold()
            return True

        if self._strict_engaged:
            if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat() \
                    and not is_typing_into(watched):
                activity = self._activity_for(event.key())
                if activity is not None:
                    self._show_activity(activity)
                    return True
                if self._drive_media(event.key()):
                    return True
                chore = self._chore_for(event.key())
                if chore is not None:
                    self.tick_chore(chore.id)
                    return True
        return super().eventFilter(watched, event)

    def _activity_for(self, key):
        """Return the offer a key opens, or None for a key left alone."""
        if not self._offers:
            return None
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return self._offers[0]
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_1
            if index < len(self._offers):
                return self._offers[index]
        return None

    def _drive_media(self, key) -> bool:
        """Apply one key to what the break is showing."""
        pane = self.media_surface.pane if self.media_surface is not None else None
        if self._showing is None or pane is None:
            return False

        if key == Qt.Key.Key_Space:
            pane.toggle()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            pane.step(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            pane.step(-1)
        elif key == Qt.Key.Key_Up:
            pane.nudge(1)
        elif key == Qt.Key.Key_Down:
            pane.nudge(-1)
        elif key == Qt.Key.Key_0:
            self._stop_showing()
        else:
            return False
        return True

    def hold_secs(self, purpose) -> float:
        """Return how long this hold must be paid for."""
        return (self.release_hold_secs if purpose == HOLD_RELEASE
                else self.stop_hold_secs)

    def _hold_is_live(self, purpose) -> bool:
        """Report whether what the hold would pay for is still the case."""
        if purpose == HOLD_RELEASE:
            return self._strict_break_is_holding()
        return self._focus_is_running()

    def begin_hold(self, purpose=HOLD_RELEASE):
        """Start charging for what the hold buys."""
        if self._hold_timer.isActive() or not self._hold_is_live(purpose):
            return
        self._hold_for = purpose
        self._hold_started_ms = QDateTime.currentMSecsSinceEpoch()
        self.hold_ring.set_hold_secs(self.hold_secs(purpose))
        self._show_hold(0.0, True)
        self._hold_timer.start(HOLD_TICK_MS)

    def cancel_hold(self):
        """Cancel a hold released early, with nothing paid and nothing owed."""
        if not self._hold_timer.isActive():
            return
        self._hold_timer.stop()
        self._hold_for = None
        self._show_hold(0.0, False)

    def _hold_tick(self):
        """Advance the hold, measured against the wall clock rather than ticks."""
        purpose = self._hold_for
        if not self._hold_is_live(purpose):
            self.cancel_hold()
            return

        hold_ms = self.hold_secs(purpose) * 1000.0
        elapsed = QDateTime.currentMSecsSinceEpoch() - self._hold_started_ms
        if elapsed >= hold_ms:
            self.cancel_hold()
            if purpose == HOLD_RELEASE:
                self._release_strict_break()
            else:
                self._stop_focus()
            return
        self._show_hold(elapsed / hold_ms, True)

    def _show_hold(self, fraction, visible):
        self.hold_ring.set_fraction(fraction)
        self.hold_ring.setVisible(visible)
        for surface in self._break_surfaces():
            surface.show_hold(fraction, visible)

    def _release_strict_break(self):
        """Give the screens back once the hold is paid, and record the cost."""
        self._record("overridden_break", int(max(0, self.time_left_ms)))
        self._clear_overlays()
        self._next_phase()

    def _warn_of_coming_break(self):
        """Announce a coming strict break while there is still time to leave."""
        self._warned_of_break = True
        coming = self.long_break_ms if self._long_break_queued else self.break_ms
        notify_service.notify(
            f"Strict break in {self.warn_secs:.0f} s",
            f"A {coming // MS_PER_MINUTE}-minute break takes every screen when "
            f"focus ends. Hold {RELEASE_KEY_NAME} for "
            f"{self.release_hold_secs:.0f} s to leave one.",
            sound_name=self._warn_sound,
            sound_file=self._warn_sound_file,
        )

    def _show_activity(self, activity) -> bool:
        """Show activity on the primary screen's wall."""
        if not self._strict_engaged:
            return False

        if self.opens_in_ms() > 0:
            log.debug("%r is held back for another %d ms: away from the screen.",
                      activity.name, self.opens_in_ms())
            return False

        surface = self.media_surface
        if surface is None or self._media_host is None:
            log.warning("Nothing to show %r on: this break covers no screen.",
                        activity.name)
            return False

        if self._showing is activity:
            return True

        self._remember_where_it_stopped()

        surface.open(
            activity,
            start_at=rest_positions.position_for(activity.path, self._positions_path))
        self._showing = activity
        self._media_host.show_media()
        self._media_host.raise_()
        self._media_host.activateWindow()
        self._say_which_keys_drive_it()
        self._redraw_break_surfaces()
        return True

    def _say_which_keys_drive_it(self):
        """Name the keys that drive what is showing, on every surface showing it."""
        if self._showing is None:
            return
        hints = self.media_key_hints(self._showing.kind)
        if self.media_surface is not None:
            self.media_surface.set_keys(hints)
        for wall in self.overlays:
            if wall is not self._media_host:
                wall.set_keys(hints)

    def _remember_where_it_stopped(self):
        """Stop what is showing and keep the position."""
        if self._showing is None or self.media_surface is None:
            return
        where = self.media_surface.stop()
        rest_positions.remember(self._showing.path, where.at,
                                self._positions_path, where.of)
        self._showing = None
        self._show_upcoming()

    def _stop_showing(self):
        """Take what is showing away, remembering where it reached."""
        self._remember_where_it_stopped()
        for wall in self.overlays:
            wall.set_keys([])
        if self.media_surface is not None:
            self.media_surface.set_keys([])
        if self._media_host is not None:
            self._media_host.hide_media()
        self._redraw_break_surfaces()

    def _engage_kwin(self, caption="", wall_outputs=None) -> bool:
        """Ask KWin to hold this break's windows across every desktop."""
        if self.kwin_pin is None:
            return False
        return self.kwin_pin.engage(focus_caption=caption,
                                    wall_outputs=wall_outputs or {})

    def _read_upcoming(self):
        """Read what is coming, once, as the break begins."""
        self._upcoming = []
        self._show_upcoming()
        run_in_background(self.threadpool, read_upcoming, self._apply_upcoming,
                          None, self.db)

    def _apply_upcoming(self, sections):
        if not read_was_answered(self.db):
            log.warning("Showing nothing coming: its read did not reach the service.")
            return
        self._upcoming = list(sections)
        self._show_upcoming()

    def _read_chores(self):
        """Read what is due, as the break begins and after one is ticked."""
        if not self._chores_on_break:
            return
        run_in_background(self.threadpool, read_chores, self._apply_chores,
                          None, self.db)

    def _apply_chores(self, entries):
        if not read_was_answered(self.db):
            log.warning("Showing no chores: their read did not reach the service.")
            return
        self._chores = list(entries)
        self._show_chores()

    def _show_chores(self):
        """Hand what is due to every surface with room for it."""
        entries = self._chores if self._strict_engaged else []
        self.chores_panel.set_entries(entries)
        for overlay in self.overlays:
            overlay.set_chores(entries)

    def tick_chore(self, chore_id: int):
        """Mark one chore done today, from a key or a click on the wall."""
        entry = next((e for e in self._chores if e.id == chore_id), None)
        if entry is None:
            return
        for surface in self._chore_surfaces():
            surface.mark_done(chore_id)
        run_in_background(self.threadpool, complete_chore, self._chore_ticked,
                          None, self.db, chore_id, entry.name)

    def _chore_ticked(self, answer):
        """Apply the answer to a chore tick."""
        chore_id, success, message = answer
        if not success:
            log.warning("Chore %s was not ticked: %s", chore_id, message)
            self.status_message.emit(f" Chore not recorded: {message}")
            self._read_chores()
            return
        self.data_changed.emit(CHORE)

    def _chore_surfaces(self) -> list:
        """Return every chore panel a break is drawing, the timer view's included."""
        return [self.chores_panel] + [o.chores for o in self.overlays]

    def _chore_for(self, key):
        """Return the chore a key ticks, or None for a key left alone."""
        if not self._chores or not Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return None
        index = CHORE_KEYS.find(chr(key).lower())
        return self._chores[index] if 0 <= index < len(self._chores) else None

    def _show_upcoming(self):
        """Hand what is coming to every surface with room for it."""
        sections = (self._upcoming + self.offer_section()
                    if self._strict_engaged else [])
        self.upcoming.set_sections(sections)
        for overlay in self.overlays:
            overlay.set_upcoming(sections)
        self._say_when_the_offers_open()

    def _member_screen(self):
        """Return the screen the break's focus starts on, being this window's."""
        main_win = self.window()
        handle = main_win.windowHandle() if main_win is not None else None
        screen = handle.screen() if handle is not None else None
        return screen or QApplication.primaryScreen()

    def _media_screen(self):
        """Return the screen that shows what the break was asked for."""
        for wanted in (self._media_screen_name, self._window_screen_name):
            if not wanted:
                continue
            for screen in self.screens_to_cover():
                if screen is not None and screen.name() == wanted:
                    return screen
            log.warning("No output is called %r: showing what a break plays "
                        "elsewhere.", wanted)
        return QApplication.primaryScreen() or self._member_screen()

    def screens_to_cover(self) -> list:
        """Return every output a break walls, which is all of them."""
        return list(QApplication.screens())

    def wall_outputs(self) -> dict:
        """Return which output each wall belongs on, keyed by its title."""
        return {wall.windowTitle(): wall.output_name
                for wall in self.overlays
                if wall.screen_covered is not None and wall.output_name}

    def _wall_for(self, screen):
        """Return the wall covering screen, or the first one there is."""
        for wall in self.overlays:
            if wall.screen_covered is screen:
                return wall
        return self.overlays[0] if self.overlays else None

    def _build_wall(self, screen):
        """Build one output's wall, mapped onto the output it names."""
        wall = StrictOverlay(self, screen)
        wall.setScreen(screen)
        wall.showFullScreen()
        wall.raise_()
        return wall

    def _host_the_media(self):
        """Build the surface files are shown on, inside the wall that shows them."""
        self._media_host = self._wall_for(self._media_screen())
        if self._media_host is None:
            return
        self.media_surface = MediaSurface(
            self, pane_factory=self.media_pane_factory,
            only_screen=len(self.overlays) == 1,
            parent=self._media_host.media_parent())
        self._media_host.host_media(self.media_surface)

    def _watch_the_outputs(self):
        """Watch for a monitor going away and coming back, for the break's length."""
        app = QApplication.instance()
        if app is None or self._watching_outputs:
            return
        app.screenAdded.connect(self._an_output_arrived)
        app.screenRemoved.connect(self._an_output_went)
        self._watching_outputs = True

    def _stop_watching_the_outputs(self):
        """Stop watching the outputs, and drop a pending rebuild."""
        self._screens_settling.stop()
        app = QApplication.instance()
        if app is not None and self._watching_outputs:
            app.screenAdded.disconnect(self._an_output_arrived)
            app.screenRemoved.disconnect(self._an_output_went)
        self._watching_outputs = False

    def _an_output_arrived(self, screen):
        """Handle a monitor coming back."""
        log.info("Output %r appeared; the break's walls will be rebuilt to "
                 "match.", screen.name() if screen is not None else "")
        self._screens_settling.start(SCREENS_SETTLE_MS)

    def _an_output_went(self, screen):
        """Handle a monitor going away."""
        log.info("Output %r went away; the break's wall for it is standing "
                 "down.", screen.name() if screen is not None else "")
        for wall in self.overlays:
            if wall.screen_covered is screen:
                wall.forget_screen()
                wall.hide()
        if self._screen_taken is screen:
            self._screen_taken = None
        self._screens_settling.start(SCREENS_SETTLE_MS)

    def _rewall_for_the_outputs(self):
        """Make the walls match the outputs that exist now."""
        if not self._strict_engaged or self.is_shut_down():
            return

        wanted = self.screens_to_cover()
        spare = list(self.overlays)
        kept = []
        for screen in wanted:
            match = next((w for w in spare if w.screen_covered is screen), None)
            if match is not None:
                spare.remove(match)
            kept.append(match)

        if not spare and all(wall is not None for wall in kept):
            return

        for wall in kept:
            if wall is not None:
                wall.stands_corrected = False

        log.info("A break's walls are being rebuilt for %d output(s): %d kept, "
                 "%d dropped.", len(wanted),
                 sum(wall is not None for wall in kept), len(spare))

        losing_media = any(wall is self._media_host for wall in spare)
        showing = self._showing if losing_media else None
        if losing_media:
            self._remember_where_it_stopped()
            if self.media_surface is not None:
                self.media_surface.shutdown()
            self.media_surface = None
            self._media_host = None

        for wall in spare:
            wall.dismiss()
            wall.setParent(None)
            wall.deleteLater()

        self.overlays = [wall if wall is not None else self._build_wall(screen)
                         for screen, wall in zip(wanted, kept)]

        if self._screen_taken is None:
            self._screen_taken = self._member_screen()
        if self.media_surface is None:
            self._host_the_media()
        if showing is not None:
            self._show_activity(showing)

        front = self._media_host or self._wall_for(self._screen_taken)
        self._engage_kwin(front.windowTitle() if front is not None else "",
                          self.wall_outputs())
        if front is not None:
            front.raise_()
            front.activateWindow()

        self._show_upcoming()
        self._show_chores()
        self._redraw_break_surfaces()

    def _enforce_strict_mode(self):
        """Take every screen for the length of a strict break."""
        self._clear_overlays()

        self.take_offers()

        self._screen_taken = self._member_screen()

        if self.rest_rule is not None:
            self.rest_rule.hold()

        for screen in self.screens_to_cover():
            self.overlays.append(self._build_wall(screen))

        self._host_the_media()

        if self.switch_guard is not None:
            self.switch_guard.hold()

        front = self._media_host or self._wall_for(self._screen_taken)
        self._engage_kwin(front.windowTitle() if front is not None else "",
                          self.wall_outputs())
        if front is not None:
            front.raise_()
            front.activateWindow()

        app = QApplication.instance()
        if app is not None and not self._filtering_keys:
            app.installEventFilter(self)
            self._filtering_keys = True

        self._watch_the_outputs()

        self._strict_engaged = True
        self._apply_engine_cadence()
        self._apply_exit_controls()
        self._read_upcoming()
        self._read_chores()

    def _stand_down_enforcement(self):
        """Stop enforcing, with the walls still up and still in front."""
        self._show_upcoming()
        self._show_chores()

        standing = bool(self.overlays)

        if self.switch_guard is not None:
            self.switch_guard.release()

        if self.kwin_pin is not None and self.kwin_pin.engaged:
            self.kwin_pin.release(standing=standing)

        if self.rest_rule is not None:
            if standing:
                self.rest_rule.stand_down()
            else:
                self.rest_rule.release()

    def _clear_overlays(self):
        """Give the screens back: the hold, what was showing, the walls, KWin."""
        self.cancel_hold()

        self._stop_showing()

        if self.media_surface is not None:
            self.media_surface.shutdown()

        for o in self.overlays:
            o.dismiss()
            o.setParent(None)
            o.deleteLater()
        self.overlays.clear()
        self.media_surface = None
        self._media_host = None

        self._screen_taken = None
        self._upcoming = []
        self._chores = []

        app = QApplication.instance()
        if app is not None and self._filtering_keys:
            app.removeEventFilter(self)
        self._filtering_keys = False

        self._stop_watching_the_outputs()

        self._stand_down_enforcement()

        self._strict_engaged = False
        self._apply_engine_cadence()
        self._apply_exit_controls()
        self._show_upcoming()
        self._show_chores()

    def shutdown(self):
        """Stop the timers, then drop the strict-mode overlays."""
        self._shut_down = True
        super().shutdown()
        self._clear_overlays()

    def phase_length_ms(self) -> int:
        """Return how long the interval now running was given."""
        if self.current_phase == "work":
            return self.work_ms
        return self.long_break_ms if self.current_phase == "long_break" else self.break_ms

    def _update_tray(self):
        if not self.tray_icon: return

        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = self.phase_length_ms()
        fraction = max(0.0, min(1.0, self.time_left_ms / total)) if total > 0 else 0

        painter.setPen(QPen(QColor(PALETTE['base2']), 5))
        painter.drawEllipse(6, 6, size - 12, size - 12)

        color = QColor(PALETTE['blue']) if self.current_phase == "work" else (QColor(PALETTE['violet']) if self.current_phase == "long_break" else QColor(PALETTE['green']))
        pen_arc = QPen(color, 5)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)

        start_angle = 90 * 16
        span_angle = int(-360 * fraction * 16)
        painter.drawArc(6, 6, size - 12, size - 12, start_angle, span_angle)

        regime = self.current_regime_str
        raw_color = self.profile.get_regime_color(regime, PALETTE['base01'])
        regime_color = QColor(PALETTE[raw_color]) if raw_color in PALETTE else QColor(raw_color)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(regime_color)
        painter.drawEllipse((size - 10) // 2, (size - 10) // 2, 10, 10)

        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
