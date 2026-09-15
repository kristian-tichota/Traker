import pytest
from PyQt6.QtGui import QPageSize, QPainter, QPdfWriter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QLabel, QWidget

from src.desktop.activities import BreakActivity, DOCUMENT, VIDEO
from src.config import PALETTE
from src.domain import media
from src.domain.media import Place
from src.gui.components import media_progress
from src.gui.components.media_surface import (DocumentPane, MediaSurface,
                                              MpvScreen,
                                              VideoPane, build_pane)

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]

PAGES = 3


@pytest.fixture
def paper(qapp, tmp_path):
    path = str(tmp_path / "paper.pdf")
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    painter = QPainter(writer)
    for page in range(PAGES):
        painter.drawText(200, 200, f"page {page + 1}")
        if page < PAGES - 1:
            writer.newPage()
    painter.end()
    return path


@pytest.fixture
def timer_double():
    class Timer:
        time_left_ms = 125_000
        release_hold_secs = 10
        waiting_for_work_start = False
        over_by_ms = staticmethod(lambda: 83_000)

        def wall_hint(self):
            return ("PRESS ESC TO START FOCUS" if self.waiting_for_work_start
                    else "HOLD ESC 10s TO LEAVE")

    return Timer()


def failure_of(pane) -> str:
    return " ".join(label.text() for label in pane.findChildren(QLabel))


class TestReadingADocument:
    def test_the_page_is_given_the_whole_pane(self, qapp, paper):
        pane = DocumentPane(paper)

        pane.resize(1600, 900)
        pane.show()
        qapp.processEvents()

        assert pane.view.geometry() == pane.rect()
        assert pane.view.viewport().height() == pane.height()
        pane.close()
        pane.deleteLater()

    def test_it_opens_at_the_first_page(self, paper):
        pane = DocumentPane(paper)

        assert pane.document.pageCount() == PAGES
        assert pane.position() == 0

    def test_a_page_forward_and_a_page_back(self, paper):
        pane = DocumentPane(paper)

        pane.step(1)
        assert pane.position() == 1

        pane.step(-1)
        assert pane.position() == 0

    def test_the_big_key_turns_the_page(self, paper):
        pane = DocumentPane(paper)

        pane.toggle()

        assert pane.position() == 1

    def test_it_does_not_go_before_the_first_page(self, paper):
        pane = DocumentPane(paper)

        pane.step(-5)

        assert pane.position() == 0

    def test_or_past_the_last(self, paper):
        pane = DocumentPane(paper)

        pane.step(PAGES + 5)

        assert pane.position() == PAGES - 1

    def test_it_comes_back_to_the_page_it_was_left_on(self, paper):
        pane = DocumentPane(paper, start_at=2)

        assert pane.position() == 2

    def test_and_stays_on_it_once_the_screen_shows_it(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)

        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        assert pane.position() == 2
        assert pane.view.verticalScrollBar().value() > 0
        pane.close()

    def test_the_member_paging_away_from_it_settles_there(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)
        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        pane.step(-1)
        qapp.processEvents()

        assert pane.position() == 1
        pane.close()

    def test_and_neither_does_scrolling_out_of_it(self, qapp, paper):
        pane = DocumentPane(paper, start_at=2)
        pane.resize(600, 800)
        pane.show()
        qapp.processEvents()

        for _ in range(8):
            pane.nudge(1)
        qapp.processEvents()

        assert pane.position() < 2
        pane.close()

    def test_scrolling_carries_on_through_the_document(self, paper):
        pane = DocumentPane(paper)

        for _ in range(6):
            pane.nudge(-1)
        assert pane.position() > 0

        for _ in range(20):
            pane.nudge(1)
        assert pane.position() == 0

    def test_a_file_that_is_not_there_says_so_on_the_screen(self, qapp, tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))

        assert pane.view.isHidden() is True
        assert "COULD NOT READ" in failure_of(pane)

    def test_a_second_file_goes_through_the_same_pane(self, qapp, paper, tmp_path):
        pane = DocumentPane(paper)
        pane.step(2)
        assert pane.position() == PAGES - 1

        pane.open(paper)

        assert pane.document.pageCount() == PAGES
        assert pane.position() == 0

    def test_re_opening_it_carries_on_where_it_stopped(self, qapp, paper):
        pane = DocumentPane(paper)
        pane.stop()

        pane.open(paper, start_at=2)

        assert pane.position() == 2

    def test_a_file_it_could_not_read_does_not_damn_the_next_one(self, qapp, paper,
                                                                 tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))
        assert "COULD NOT READ" in failure_of(pane)

        pane.open(paper)

        assert pane.view.isHidden() is False
        assert pane.document.pageCount() == PAGES

    def test_and_takes_its_keys_without_raising(self, qapp, tmp_path):
        pane = DocumentPane(str(tmp_path / "nothing.pdf"))

        pane.toggle()
        pane.step(1)
        pane.nudge(1)
        pane.stop()

        assert pane.position() == 0


class TestPlayingAVideo:
    def test_it_is_built_and_asked_for_its_position(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.position() == 0

    def test_a_file_that_is_not_there_says_so_on_the_screen(self, qapp, tmp_path,
                                                            settled):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        pane.screen_widget.player = None
        pane._show_failure("no such file")
        settled()

        assert "COULD NOT PLAY" in failure_of(pane)

    def test_a_player_that_would_not_start_says_why_in_its_own_words(
            self, qapp, tmp_path, monkeypatch, settled):
        def refuse(screen):
            screen.player_error = "libmpv would not load: undefined symbol"
            return None
        monkeypatch.setattr(MpvScreen, "_start_mpv", refuse)

        pane = VideoPane(str(tmp_path / "talk.mkv"))
        settled()

        said = failure_of(pane)
        assert "COULD NOT PLAY" in said
        assert "undefined symbol" in said

    def test_it_takes_its_keys_without_raising(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        pane.toggle()
        pane.step(1)
        pane.step(-1)
        pane.nudge(1)
        pane.nudge(-1)
        pane.stop()

    def test_the_picture_is_libmpv_drawing_into_our_own_surface(self, qapp,
                                                                tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert isinstance(pane.screen_widget, MpvScreen)
        assert isinstance(pane.screen_widget, QOpenGLWidget)
        assert pane.screen_widget.parent() is pane

    def test_the_picture_is_given_the_whole_pane(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        pane.resize(1600, 900)
        pane.show()
        qapp.processEvents()

        assert pane.screen_widget.size() == pane.size()
        pane.close()
        pane.deleteLater()

    def test_a_second_file_goes_through_the_same_player(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        widget, player = pane.screen_widget, pane.player

        pane.open(str(tmp_path / "other.mkv"))

        assert pane.screen_widget is widget
        assert pane.player is player

    def test_nothing_is_asked_to_follow_a_file_that_ends(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.player is not None
        assert pane.player.keep_open in ("yes", True)
        assert len(pane.player.playlist) <= 1

    def test_it_takes_none_of_my_keys_and_draws_none_of_its_own_furniture(
            self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        assert pane.player.input_default_bindings is False
        assert pane.player.input_vo_keyboard is False
        assert pane.player.osc is False

    def test_the_volume_stays_inside_itself(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))

        for _ in range(20):
            pane.nudge(1)
        assert pane.player.volume == pytest.approx(100.0)

        for _ in range(30):
            pane.nudge(-1)
        assert pane.player.volume == pytest.approx(0.0)

    def test_letting_go_stops_the_player_it_started(self, qapp, tmp_path):
        pane = VideoPane(str(tmp_path / "talk.mkv"))
        assert pane.player is not None

        pane.shutdown()

        assert pane.player is None
        assert pane.screen_widget.player is None


class TestWhichPaneIsBuilt:
    def test_a_document_is_read(self, paper):
        pane = build_pane(BreakActivity("Reading", paper, DOCUMENT))

        assert isinstance(pane, DocumentPane)

    def test_anything_else_is_played(self, qapp, tmp_path):
        pane = build_pane(BreakActivity("Watching", str(tmp_path / "a.mkv"), VIDEO))

        assert isinstance(pane, VideoPane)


class Recorder(QWidget):
    def __init__(self, activity=None, start_at=0, parent=None):
        super().__init__(parent)
        self.at = 42_000
        self.of = 90_000
        self.opened = [] if activity is None else [(activity.path, start_at)]

    def open(self, path, start_at=0):
        self.opened.append((path, start_at))
        self.at = 42_000

    def position(self):
        return self.at

    def duration(self):
        return self.of

    def stop(self):
        self.at = self.of = 0

    def toggle(self):
        pass


class TestTheSurfaceAroundThem:
    @pytest.fixture
    def activity(self, tmp_path):
        return BreakActivity("Watching", str(tmp_path / "talk.mkv"), VIDEO)

    @pytest.fixture
    def paper_activity(self, paper):
        return BreakActivity("Reading", paper, DOCUMENT)

    def test_nothing_is_showing_until_it_is_asked_for(self, qapp):
        surface = MediaSurface(None, pane_factory=Recorder)

        assert surface.activity is None
        assert surface.pane is None
        assert surface.panes == {}

    def test_it_reads_the_place_before_it_stops_the_pane(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        assert surface.stop() == Place(42_000, 90_000)

    def test_stopping_puts_the_empty_page_back(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        pane = surface.open(activity)

        surface.stop()

        assert surface.activity is None
        assert surface.pane is None
        assert surface.stack.currentWidget() is not pane

    def test_closing_it_and_opening_it_again_is_the_same_pane(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        pane = surface.open(activity)
        surface.stop()

        again = surface.open(activity, start_at=90_000)

        assert again is pane
        assert pane.opened == [(activity.path, 0), (activity.path, 90_000)]
        assert surface.stack.currentWidget() is pane

    def test_a_video_and_a_document_get_a_pane_each(self, qapp, activity,
                                                    paper_activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        watching = surface.open(activity)
        reading = surface.open(paper_activity)

        assert watching is not reading
        assert set(surface.panes) == {VIDEO, DOCUMENT}
        assert surface.stack.currentWidget() is reading

    def test_the_screen_shows_the_file_and_nothing_else(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        assert surface.strip is None

    def test_a_break_with_no_other_screen_keeps_one_line(self, qapp, activity,
                                                         timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        assert "REST 02:05" in surface.strip.text()
        assert "HOLD ESC" in surface.strip.text()

    def test_that_line_says_when_the_break_has_run_out(self, qapp, activity,
                                                       timer_double):
        timer_double.waiting_for_work_start = True

        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        assert "BREAK OVER +1:23" in surface.strip.text()
        assert "PRESS ESC TO START FOCUS" in surface.strip.text()

    def test_and_how_much_of_the_exit_has_been_paid(self, qapp, activity,
                                                    timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        surface.show_hold(0.7, True)

        assert "LEAVING IN 3s" in surface.strip.text()

    def test_letting_go_puts_the_exit_back(self, qapp, activity, timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)
        surface.show_hold(0.7, True)

        surface.show_hold(0.0, False)

        assert "HOLD ESC" in surface.strip.text()

    def test_the_pane_it_was_given_is_the_pane_it_holds(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        surface.open(activity)

        assert isinstance(surface.pane, Recorder)
        assert surface.activity is activity

    def test_the_screen_showing_the_file_names_no_keys_on_it(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)

        surface.open(activity, key_hints=[("SPACE", "pause")])

        assert surface.keys.isVisibleTo(surface) is False

    def test_a_break_with_no_other_screen_keeps_the_card(self, qapp, activity,
                                                         timer_double):
        surface = MediaSurface(timer_double, pane_factory=Recorder,
                               only_screen=True)

        surface.open(activity, key_hints=[("SPACE", "pause")])
        assert surface.keys.isVisibleTo(surface) is True

        surface.stop()
        assert surface.keys.isVisibleTo(surface) is False


class TestWhereInTheFileTheMemberIs:
    @pytest.fixture
    def activity(self, tmp_path):
        return BreakActivity("Watching", str(tmp_path / "talk.mkv"), VIDEO)

    @pytest.fixture
    def alone(self, qapp, timer_double):
        built = []

        def _alone(width=1920, height=1080):
            surface = MediaSurface(timer_double, pane_factory=Recorder,
                                   only_screen=True)
            surface.resize(width, height)
            surface.show()
            qapp.processEvents()
            built.append(surface)
            return surface

        yield _alone
        for surface in built:
            surface.close()
            surface.deleteLater()
        qapp.processEvents()

    def test_the_surface_answers_where_the_pane_has_got_to(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        place, unit = surface.place()

        assert media.how_far(place, unit) == "0:42 / 1:30"
        assert media.fraction(place, unit) == pytest.approx(42 / 90)

    def test_a_document_answers_its_page_instead(self, qapp, paper):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(BreakActivity("Reading", paper, DOCUMENT))
        surface.pane.at, surface.pane.of = 41, 310

        place, unit = surface.place()

        assert media.how_far(place, unit) == "42 / 310"

    def test_nothing_showing_is_no_place_at_all(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        assert surface.place() is None

        surface.open(activity)
        surface.stop()

        assert surface.place() is None

    def test_the_player_is_asked_once_for_it(self, qapp, activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)
        asked = []
        surface.pane.position = lambda: asked.append(1) or 42_000

        surface.place()

        assert len(asked) == 1

    def test_a_break_with_another_screen_draws_none_of_it_here(self, qapp,
                                                               activity):
        surface = MediaSurface(None, pane_factory=Recorder)
        surface.open(activity)

        assert surface.progress is None

    def test_a_break_with_no_other_screen_keeps_the_row(self, qapp, alone,
                                                        activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        assert surface.progress is not None
        assert surface.progress.isVisibleTo(surface) is True

    def test_it_says_where_in_the_file_the_member_is(self, qapp, alone, activity):
        surface = alone()
        surface.open(activity)

        surface.show_progress()

        assert surface.progress.says == "0:42 / 1:30"
        assert surface.progress.fraction == pytest.approx(42 / 90)

    def test_it_takes_the_view_s_own_read_when_it_is_given_one(self, qapp,
                                                               alone, activity):
        surface = alone()
        surface.open(activity)

        surface.show_progress((media.Place(63_000, 90_000), media.TIME))

        assert surface.progress.says == "1:03 / 1:30"

    def test_it_is_a_row_under_the_picture_not_a_band_on_it(self, qapp, alone,
                                                            activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        assert surface.layout().indexOf(surface.progress) != -1
        assert not surface.progress.geometry().intersects(surface.stack.geometry())
        assert surface.progress.height() == media_progress.HEIGHT

    def test_the_row_goes_when_the_file_does(self, qapp, alone, activity):
        surface = alone()
        surface.open(activity)
        qapp.processEvents()

        surface.stop()
        qapp.processEvents()

        assert surface.progress.isVisibleTo(surface) is False

    def test_a_length_the_player_has_not_read_yet_draws_nothing(self, qapp,
                                                                alone, activity):
        surface = alone()
        surface.open(activity)
        surface.pane.of = 0

        surface.show_progress()

        assert surface.progress.says == media.UNKNOWN
        assert surface.progress.fraction == 0.0

    def test_the_member_can_actually_see_it(self, qapp, alone, activity):
        surface = alone(800, 600)
        surface.open(activity)
        surface.pane.at, surface.pane.of = 45_000, 90_000
        surface.show_progress()
        qapp.processEvents()

        shot = surface.grab().toImage()
        band = surface.progress.geometry()
        along = band.bottom()
        assert shot.pixelColor(200, along).name() == PALETTE['cyan']
        assert shot.pixelColor(600, along).name() == PALETTE['base01']
        ink = {shot.pixelColor(x, y).name()
               for y in range(band.top(), band.bottom())
               for x in range(band.width() - 140, band.width())}
        assert PALETTE['base2'] in ink
        assert surface.progress.says == "0:45 / 1:30"

    def test_a_frame_that_says_the_same_thing_is_not_repainted(self, qapp,
                                                               alone, activity):
        surface = alone()
        surface.open(activity)
        asked = []
        surface.progress.update = lambda: asked.append(1)

        for _ in range(50):
            surface.show_progress()
        assert asked == []

        surface.pane.at = 63_000
        surface.show_progress()
        assert len(asked) == 1
