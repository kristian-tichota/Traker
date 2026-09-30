import pytest
from PyQt6.QtQml import QJSEngine

from src.desktop.kwin import home_source, release_source, script_source

pytestmark = pytest.mark.exact

HARNESS = """
function Signal() { this.handlers = []; }
Signal.prototype.connect = function (h) { this.handlers.push(h); };
Signal.prototype.emit = function (a) {
    for (var i = 0; i < this.handlers.length; i++) this.handlers[i](a);
};

function notifying(w, name, signal, initial, refused) {
    var value = initial;
    Object.defineProperty(w, name, {
        enumerable: true,
        configurable: true,
        get: function () { return value; },
        set: function (next) {
            if (refused || next === value) return;
            value = next;
            signal.emit(w);
        }
    });
}

function everywhere(w, name, allName, signal, mine, elsewhere) {
    var value = mine;
    Object.defineProperty(w, name, {
        enumerable: true,
        get: function () { return value; },
        set: function (next) {
            if (next === value) return;
            value = next;
            signal.emit(w);
        }
    });
    Object.defineProperty(w, allName, {
        enumerable: true,
        get: function () { return value.length === 0; },
        set: function (next) { w[name] = next ? [] : elsewhere(); }
    });
}

function Win(cls, opts) {
    opts = opts || {};
    this.resourceClass = cls;
    this.caption = opts.caption || cls;
    this.wantsInput = opts.wantsInput !== false;

    this.minimizedChanged = new Signal();
    this.keepAboveChanged = new Signal();
    this.desktopsChanged = new Signal();
    this.activitiesChanged = new Signal();

    everywhere(this, "desktops", "onAllDesktops", this.desktopsChanged, [one],
               function () { return [workspace.currentDesktop]; });
    if (!opts.noActivities) {
        everywhere(this, "activities", "onAllActivities", this.activitiesChanged,
                   ["uuid-one"], function () { return [workspace.currentActivity]; });
    }
    notifying(this, "minimized", this.minimizedChanged, false, opts.refused);
    notifying(this, "keepAbove", this.keepAboveChanged, false, opts.refused);
}

var one = {name: "Desktop 1"};
var wall = new Win("traker", {caption: "Traker"});
var covered = new Win("traker", {caption: "Traker rest", wantsInput: false});
var all = [wall, covered];
var raised = [];

var workspace = {
    windowAdded: new Signal(),
    windowActivated: new Signal(),
    currentDesktopChanged: new Signal(),
    currentActivityChanged: new Signal(),
    currentDesktop: one,
    currentActivity: "uuid-one",
    activeWindow: wall,
    windowList: function () { return all; },
    raiseWindow: function (w) { raised.push(w.caption); }
};

var printed = [];
function print(message) { printed.push(String(message)); }

function open_window(w) { all.push(w); workspace.windowAdded.emit(w); return w; }
"""


class Session:
    def __init__(self, setup="", source=None):
        self.engine = QJSEngine()
        self._run(HARNESS)
        if setup:
            self._run(setup)
        self._run(source if source is not None
                  else script_source("traker", focus_caption="Traker"))

    def _run(self, source):
        answer = self.engine.evaluate(source)
        assert not answer.isError(), answer.toString()
        return answer

    def __call__(self, expression):
        return self._run(expression).toVariant()


@pytest.fixture
def session(qapp):
    return Session()


class TestWhatABreakHolds:
    def test_one_the_rule_put_everywhere_is_left_everywhere(self, qapp):
        session = Session("wall.desktops = []; wall.activities = [];")
        session('workspace.currentDesktop = {name: "Desktop 4"};'
                'workspace.currentActivity = "uuid-two";'
                "workspace.currentDesktopChanged.emit();"
                "workspace.currentActivityChanged.emit();")

        assert session("wall.desktops") == [] and session("wall.activities") == []
        assert [line for line in session("printed") if "holding 'Traker'" in line
                and "everyDesktop=true everyActivity=true" in line]

    def test_they_are_above_everything(self, session):
        assert session("wall.keepAbove") is True
        assert session("covered.keepAbove") is True

    def test_one_that_maps_while_it_holds_is_held_too(self, session):
        session('var late = open_window(new Win("traker", {caption: "Traker rest 2"}));')

        assert session("late.keepAbove") is True

    def test_a_window_of_the_members_is_not_touched(self, session):
        session('var browser = open_window(new Win("firefox"));')

        assert session("browser.keepAbove") is False
        assert session("browser.desktops[0].name") == "Desktop 1"

    def test_one_that_was_already_open_is_not_touched_either(self, session):
        session('var player = new Win("mpv"); all.push(player);')

        session('workspace.currentActivity = "uuid-two";'
                "workspace.currentActivityChanged.emit();")

        assert session("player.activities") == ["uuid-one"]
        assert session("player.keepAbove") is False


class TestWhatIsNotTheBreak:
    def test_a_popup_of_ours_is_left_alone(self, qapp):
        session = Session("wall.popupWindow = false;"
                          'var tip = new Win("traker", {caption: "main.py"});'
                          "tip.popupWindow = true; all = [wall, tip];")

        assert session("tip.keepAbove") is False
        assert session("wall.keepAbove") is True

    def test_one_that_maps_while_it_holds_is_left_alone_too(self, session):
        session('var tip = new Win("traker", {caption: "main.py"});'
                "tip.popupWindow = true; open_window(tip);")
        session("workspace.windowActivated.emit(tip);")

        assert session("tip.keepAbove") is False

    def test_a_kwin_that_does_not_answer_for_popups_holds_as_before(self, session):
        assert session("wall.keepAbove") is True
        assert [line for line in session("printed") if "popup=(absent)" in line]

    def test_the_report_says_what_each_window_is(self, qapp):
        session = Session('wall.resourceName = "traker"; wall.popupWindow = false;')
        said = [line for line in session("printed") if "everyDesktop=" in line]

        assert any("class=traker" in line for line in said)
        assert any("popup=false" in line for line in said)


class TestFightingItPutsItBack:
    def test_minimising_the_wall_is_answered(self, session):
        session("wall.minimized = true;")

        assert session("wall.minimized") is False

    def test_taking_it_off_the_top_is_answered(self, session):
        session("wall.keepAbove = false;")

        assert session("wall.keepAbove") is True

    def test_sending_it_to_another_desktop_brings_it_back(self, session):
        session('wall.desktops = [{name: "Desktop 4"}];')

        assert session("wall.desktops[0].name") == "Desktop 1"

    def test_sending_it_to_another_activity_does_too(self, session):
        session('wall.activities = ["uuid-two"];')

        assert session("wall.activities") == ["uuid-one"]


class TestWhereTheFocusGoes:
    def test_something_else_taking_it_gives_it_back_to_the_wall(self, session):
        session('var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeWindow = browser;"
                "workspace.windowActivated.emit(browser);")

        assert session("workspace.activeWindow.caption") == "Traker"
        assert session("raised")[-1] == "Traker"

    def test_the_wall_is_the_named_window_not_a_readout(self, session):
        session("all = [covered, wall];"
                'var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeWindow = browser;"
                "workspace.windowActivated.emit(browser);")

        assert session("workspace.activeWindow.caption") == "Traker"

    def test_a_desktop_change_asks_for_it_again(self, session):
        session('var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeWindow = browser;")

        session('workspace.currentDesktop = {name: "Desktop 4"};'
                "workspace.currentDesktopChanged.emit();")

        assert session("workspace.activeWindow.caption") == "Traker"

    def test_an_activity_change_does_too(self, session):
        session('var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeWindow = browser;")

        session('workspace.currentActivity = "uuid-two";'
                "workspace.currentActivityChanged.emit();")

        assert session("workspace.activeWindow.caption") == "Traker"

    def test_a_window_of_ours_that_has_it_keeps_it(self, session):
        session("workspace.activeWindow = covered;"
                "workspace.windowActivated.emit(covered);")

        assert session("workspace.activeWindow.caption") == "Traker rest"

WALLS = """
var app = wall;
var front = new Win("traker", {caption: "Traker rest \u2014 DP-1"});
var other = new Win("traker", {caption: "Traker rest \u2014 HDMI-1"});
all = [app, front, other];
workspace.activeWindow = app;
"""

WALL_PREFIX = "Traker rest"
FRONT = "Traker rest \u2014 DP-1"


def walled(setup="", focus=FRONT):
    return Session(WALLS + setup,
                   source=script_source("traker", focus_caption=focus,
                                        wall_prefix=WALL_PREFIX))


class TestAWallAndTheWindowBehindIt:
    @pytest.fixture
    def session(self, qapp):
        return walled()

    def test_only_the_walls_are_kept_above_everything(self, session):
        assert session("front.keepAbove") is True
        assert session("other.keepAbove") is True
        assert session("app.keepAbove") is False

    def test_the_focus_is_taken_off_the_application_window(self, session):
        assert session("workspace.activeWindow.caption") == FRONT

    def test_activating_it_hands_the_focus_straight_back_to_a_wall(self, session):
        session("workspace.activeWindow = app;"
                "workspace.windowActivated.emit(app);")

        assert session("workspace.activeWindow.caption") == FRONT

    def test_a_wall_that_has_the_focus_keeps_it(self, session):
        session("workspace.activeWindow = other;"
                "workspace.windowActivated.emit(other);")

        assert session("workspace.activeWindow.caption") == "Traker rest \u2014 HDMI-1"

    def test_the_named_wall_is_the_one_woken(self, qapp):
        session = walled("all = [other, front, app];"
                         'var browser = new Win("firefox"); all.push(browser);'
                         "workspace.activeWindow = browser;"
                         "workspace.windowActivated.emit(browser);")

        assert session("workspace.activeWindow.caption") == FRONT

    def test_a_wall_that_maps_after_the_hold_is_held_too(self, session):
        session('var late = open_window(new Win("traker",'
                ' {caption: "Traker rest \u2014 DP-3"}));')

        assert session("late.keepAbove") is True

    def test_a_window_of_the_members_is_still_not_touched(self, session):
        session('var browser = open_window(new Win("firefox"));')

        assert session("browser.keepAbove") is False

    def test_the_journal_says_which_of_ours_are_walls(self, session):
        said = [line for line in session("printed") if "everyDesktop=" in line]

        assert len(said) == 3
        assert [line for line in said if "holding 'Traker'" in line
                and "wall=false" in line]
        assert len([line for line in said if "wall=true" in line]) == 2


class TestACompositorThatAnswersDifferently:
    def test_a_kwin_with_no_raise_of_its_own_still_activates(self, qapp):
        session = Session("delete workspace.raiseWindow;")

        session('var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeWindow = browser;"
                "workspace.windowActivated.emit(browser);")

        assert session("workspace.activeWindow.caption") == "Traker"

    def test_the_kwin_5_spellings_are_answered_too(self, qapp):
        session = Session("workspace.activeClient = workspace.activeWindow;"
                          "delete workspace.activeWindow;"
                          "workspace.clientList = workspace.windowList;"
                          "delete workspace.windowList;"
                          "workspace.clientActivated = workspace.windowActivated;")
        session('var browser = new Win("firefox"); all.push(browser);'
                "workspace.activeClient = browser;"
                "workspace.clientActivated.emit(browser);")

        assert session("wall.keepAbove") is True
        assert session("workspace.activeClient.caption") == "Traker"

    def test_a_session_with_none_of_our_windows_holds_nothing(self, qapp):
        session = Session("all = [];")

        session('var browser = open_window(new Win("firefox"));')

        assert session("browser.keepAbove") is False

TWO_OUTPUTS = """
var outputs = [
    {name: "DP-1", geometry: {x: 1920, y: 0, width: 1920, height: 1080}},
    {name: "DP-2", geometry: {x: 0, y: 0, width: 1920, height: 1080}}
];
workspace.screens = outputs;
var app = wall;
var front = new Win("traker", {caption: "Traker rest — DP-1"});
var other = new Win("traker", {caption: "Traker rest — DP-2"});
front.output = outputs[1];          // both on the left-hand screen
other.output = outputs[1];
front.fullScreen = true;
other.fullScreen = true;
front.frameGeometry = {x: 0, y: 0, width: 1920, height: 1080};
other.frameGeometry = {x: 0, y: 0, width: 1920, height: 1080};
front.outputChanged = new Signal();
other.outputChanged = new Signal();
all = [app, front, other];
var sent = [];
workspace.sendClientToScreen = function (w, output) {
    sent.push(String(w.caption) + " -> " + String(output.name));
    w.output = output;
    w.frameGeometry = {x: output.geometry.x, y: output.geometry.y,
                       width: output.geometry.width,
                       height: output.geometry.height};
};
"""

WALL_MAP = {"Traker rest — DP-1": "DP-1", "Traker rest — DP-2": "DP-2"}


def placed(setup="", walls=None, refuse=False):
    return Session(TWO_OUTPUTS + setup,
                   source=script_source("traker",
                                        focus_caption="Traker rest — DP-1",
                                        wall_prefix=WALL_PREFIX,
                                        wall_outputs=WALL_MAP if walls is None else walls,
                                        refuse_switch=refuse))


class TestPlacingEachWallOnItsOutput:
    def test_each_wall_is_sent_to_the_output_its_caption_names(self, qapp):
        session = placed()

        assert session("sent") == ["Traker rest — DP-1 -> DP-1"]
        assert session("front.output.name") == "DP-1"
        assert session("other.output.name") == "DP-2"

    def test_the_application_window_is_not_placed_anywhere(self, qapp):
        session = placed()

        assert "Traker'" not in " ".join(session("sent"))

    def test_a_caption_kwin_deduplicated_is_still_matched(self, qapp):
        session = placed('other.caption = "Traker rest — DP-2 <2>";')

        assert session("other.output.name") == "DP-2"

    def test_a_kwin_without_the_call_is_answered_by_the_property(self, qapp):
        session = placed("delete workspace.sendClientToScreen;")

        assert session("front.output.name") == "DP-1"

    DEAF = """
    delete workspace.sendClientToScreen;
    [front, other].forEach(function (w) {
        Object.defineProperty(w, "output", {
            configurable: true,
            get: function () { return undefined; },
            set: function () {}
        });
    });
    """

    def test_and_one_with_neither_is_answered_by_geometry(self, qapp):
        session = placed(self.DEAF)

        assert session("front.frameGeometry.x") == 1920
        assert session("front.fullScreen") is True

    def test_a_wall_the_compositor_moves_later_is_put_back(self, qapp):
        session = placed()
        session("""
            front.output = outputs[1];
            front.frameGeometry = {x: 0, y: 0, width: 1920, height: 1080};
            front.outputChanged.emit(front);
        """)

        assert session("front.output.name") == "DP-1"

    def test_the_journal_says_where_each_one_wanted_to_be_and_is(self, qapp):
        session = placed()
        said = [line for line in session("printed") if "everyDesktop=" in line]

        assert any("wanted=DP-1 on=DP-1" in line for line in said)
        assert any("wanted=(any)" in line for line in said)

    def test_a_break_that_named_no_outputs_places_nothing(self, qapp):
        session = placed(walls={})

        assert session("sent") == []

NOTIFYING_SWITCH = """
(function () {
    var desktop = one;
    Object.defineProperty(workspace, "currentDesktop", {
        configurable: true,
        get: function () { return desktop; },
        set: function (next) {
            if (next === desktop) return;
            desktop = next;
            workspace.currentDesktopChanged.emit();
        }
    });
    var activity = "uuid-one";
    Object.defineProperty(workspace, "currentActivity", {
        configurable: true,
        get: function () { return activity; },
        set: function (next) {
            if (next === activity) return;
            activity = next;
            workspace.currentActivityChanged.emit();
        }
    });
})();
"""

class TestRefusingTheSwitch:
    @pytest.fixture
    def refusing(self, qapp):
        return placed(NOTIFYING_SWITCH, refuse=True)

    def test_a_desktop_switch_is_put_straight_back(self, refusing):
        refusing('workspace.currentDesktop = {name: "Desktop 4"};')

        assert refusing("workspace.currentDesktop.name") == "Desktop 1"

    def test_an_activity_switch_is_too(self, refusing):
        refusing('workspace.currentActivity = "uuid-two";')

        assert refusing("workspace.currentActivity") == "uuid-one"

    def test_it_says_so_where_a_member_can_read_it(self, refusing):
        refusing('workspace.currentDesktop = {name: "Desktop 4"};')

        assert [line for line in refusing("printed")
                if "refusing currentDesktop changes" in line and "back=true" in line]

    def test_it_says_it_once_and_not_once_a_press(self, refusing):
        for desktop in ("Desktop 4", "Desktop 2", "Desktop 6"):
            refusing('workspace.currentDesktop = {name: "%s"};' % desktop)

        assert len([line for line in refusing("printed")
                    if "refusing currentDesktop" in line]) == 1

    def test_putting_it_back_does_not_re_enter_itself(self, refusing):
        refusing('workspace.currentDesktop = {name: "Desktop 4"};')
        refusing('workspace.currentActivity = "uuid-three";')

        said = [line for line in refusing("printed") if "refusing" in line]
        assert len(said) == 2
        assert refusing("workspace.currentDesktop.name") == "Desktop 1"
        assert refusing("workspace.currentActivity") == "uuid-one"

    def test_the_break_still_holds_what_it_held(self, refusing):
        assert refusing("front.keepAbove") is True

    def test_switched_off_it_follows_instead(self, qapp):
        session = placed(NOTIFYING_SWITCH, refuse=False)

        session('workspace.currentDesktop = {name: "Desktop 4"};')

        assert session("workspace.currentDesktop.name") == "Desktop 4"
        assert [line for line in session("printed") if "refusing" in line] == []


class TestEveryWallIsRaised:
    def test_both_walls_are_raised_and_the_named_one_last(self, qapp):
        session = placed()

        raised = session("raised")
        assert "Traker rest — DP-2" in raised
        assert raised[-1] == "Traker rest — DP-1"

    def test_a_desktop_change_raises_them_again(self, qapp):
        session = placed()
        session("raised = [];")

        session('workspace.currentDesktop = {name: "Desktop 4"};'
                "workspace.currentDesktopChanged.emit();")

        assert len(session("raised")) == 2

    def test_the_application_window_is_not_raised_with_them(self, qapp):
        session = placed()

        assert "Traker" not in session("raised")


class TestTheProbe:
    SCREENS = """
    workspace.screens = [
        {name: "DP-1", geometry: {x: 1920, y: 0, width: 1920, height: 1080}},
        {name: "DP-2", geometry: {x: 0, y: 0, width: 1920, height: 1080}}
    ];
    workspace.activeScreen = workspace.screens[1];
    wall.frameGeometry = {x: 1920, y: 0, width: 1920, height: 1080};
    covered.frameGeometry = {x: 0, y: 0, width: 1920, height: 1080};
    """

    @pytest.fixture
    def probed(self, qapp):
        from scripts.check_desktop_integration import PROBE

        return Session(self.SCREENS, source=PROBE.replace("__APP_ID__", "traker"))

    def test_it_names_the_outputs_and_what_kwin_answers_for(self, probed):
        said = "\n".join(probed("printed"))

        assert "screens=object" in said
        assert "sendClientToScreen=" in said
        assert 'name=DP-1' in said and 'name=DP-2' in said
        assert "activeScreen=DP-2" in said

    def test_it_says_which_output_each_of_our_windows_is_on(self, probed):
        said = [line for line in probed("printed") if "keepAbove=" in line]

        assert any("on=DP-1" in line for line in said)
        assert any("on=DP-2" in line for line in said)

    def test_it_says_it_again_when_the_desktop_changes(self, probed):
        before = len(probed("printed"))

        probed('workspace.currentDesktop = {name: "Desktop 4"};'
               "workspace.currentDesktopChanged.emit();")

        said = probed("printed")
        assert len(said) > before
        assert any("desktop changed" in line for line in said)

    def test_and_when_an_activity_changes(self, probed):
        probed('workspace.currentActivity = "uuid-two";'
               "workspace.currentActivityChanged.emit();")

        assert any("activity changed" in line for line in probed("printed"))

    def test_it_writes_nothing_at_all(self, probed):
        assert probed("wall.keepAbove") is False
        assert probed("wall.onAllDesktops") is False
        assert probed("raised") == []


class TestFollowingTheMember:
    def test_a_desktop_switch_takes_every_screen_with_it(self, session):
        session('workspace.currentDesktop = {name: "Desktop 4"};'
                "workspace.currentDesktopChanged.emit();")

        assert session("wall.desktops[0].name") == "Desktop 4"
        assert session("covered.desktops[0].name") == "Desktop 4"

    def test_an_activity_switch_does_too(self, session):
        session('workspace.currentActivity = "uuid-two";'
                "workspace.currentActivityChanged.emit();")

        assert session("wall.activities") == ["uuid-two"]
        assert session("covered.activities") == ["uuid-two"]

    def test_a_window_of_the_members_is_still_left_where_it_was(self, session):
        session('var browser = open_window(new Win("firefox"));'
                'workspace.currentDesktop = {name: "Desktop 4"};'
                "workspace.currentDesktopChanged.emit();")

        assert session("browser.desktops[0].name") == "Desktop 1"

    def test_a_session_with_no_activities_at_all_is_not_fought(self, qapp):
        session = Session("wall = new Win('traker', {caption: 'Traker',"
                          " noActivities: true});"
                          "all = [wall];")

        assert session("typeof wall.activities") == "undefined"
        assert [line for line in session("printed")
                if "everyActivity=true" in line]


class TestWhatTheJournalSays:
    def test_each_window_is_named_once_with_what_stuck(self, session):
        said = [line for line in session("printed") if "everyDesktop=" in line]

        assert len(said) == 2
        assert "holding 'Traker'" in said[0]
        assert "everyDesktop=false everyActivity=false" in said[0]

    def test_fighting_the_hold_does_not_say_it_again(self, session):
        before = len(session("printed"))

        session("wall.minimized = true; wall.minimized = true;"
                "wall.keepAbove = false;")

        assert len(session("printed")) == before

    def test_a_name_this_plasma_does_not_answer_for_is_named_absent(self, qapp):
        session = Session("wall = new Win('traker', {caption: 'Traker'});"
                          "delete wall.minimized; all = [wall];")

        assert [line for line in session("printed") if "minimized=(absent)" in line]

RELEASED = """
wall.onAllDesktops = true; wall.keepAbove = true;
wall.desktops = []; wall.activities = [];
covered.onAllDesktops = true; covered.keepAbove = true;
var player = new Win("mpv");
var browser = new Win("firefox");
all.push(player); all.push(browser);
workspace.currentDesktop = {name: "Desktop 4"};
workspace.currentActivity = "uuid-two";
"""


class TestTheUndo:
    @pytest.fixture
    def ended(self, qapp):
        return Session(RELEASED, source=release_source("traker"))

    def test_the_wall_is_an_ordinary_window_again(self, ended):
        assert ended("wall.onAllDesktops") is False
        assert ended("wall.keepAbove") is False

    def test_it_lands_where_the_member_is_now(self, ended):
        assert ended("wall.desktops[0].name") == "Desktop 4"
        assert ended("wall.activities") == ["uuid-two"]

    def test_every_window_of_ours_gets_it_back(self, ended):
        assert ended("covered.onAllDesktops") is False
        assert ended("covered.keepAbove") is False

    def test_a_window_of_the_members_is_untouched(self, ended):
        assert ended("player.desktops[0].name") == "Desktop 1"
        assert ended("player.activities") == ["uuid-one"]
        assert ended("browser.desktops[0].name") == "Desktop 1"

    def test_it_connects_to_nothing(self, ended):
        assert ended("workspace.windowAdded.handlers.length") == 0
        assert ended("workspace.currentDesktopChanged.handlers.length") == 0

    def test_the_kwin_5_spelling_is_answered_too(self, qapp):
        ended = Session(RELEASED + "workspace.currentDesktop = 3;",
                        source=release_source("traker"))

        assert ended("wall.desktop") == 3

    def test_a_wall_still_standing_keeps_the_front_it_was_given(self, qapp):
        ended = Session(RELEASED, source=release_source("traker", "Traker rest", standing=True))

        assert ended("covered.keepAbove") is True
        assert ended("wall.keepAbove") is False

AT_HOME = TWO_OUTPUTS + """
all = [app];
app.output = outputs[1];            // the far-left one, where it is not wanted
app.frameGeometry = {x: 0, y: 0, width: 1200, height: 800};
app.move = false;
app.resize = false;
app.outputChanged = new Signal();
app.frameGeometryChanged = new Signal();
app.moveResizedChanged = new Signal();
app.interactiveMoveResizeFinished = new Signal();
app.fullScreenChanged = new Signal();
workspace.screensChanged = new Signal();

function drag(w, output) {
    w.move = true;
    w.moveResizedChanged.emit(w);
    w.frameGeometry = {x: output.geometry.x + 40, y: 60,
                       width: 1200, height: 800};
    w.frameGeometryChanged.emit(w);
    w.move = false;
    w.moveResizedChanged.emit(w);
    w.interactiveMoveResizeFinished.emit(w);
}
"""


def at_home(setup="", output="DP-1", caption="Traker"):
    return Session(AT_HOME + setup,
                   source=home_source("traker", caption, output))


def landed(session):
    said = [line for line in session("printed") if "window home 'Traker'" in line]
    assert said, "the script said nothing about placing the window"
    return said[-1].rsplit("on=", 1)[1]


class TestTheWindowsOwnScreen:
    def test_it_moves_the_window_to_the_output_it_names(self, qapp):
        session = at_home()

        assert session("sent") == ["Traker -> DP-1"]
        assert landed(session) == "DP-1"

    def test_it_says_where_the_window_went(self, qapp):
        said = "\n".join(at_home()("printed"))

        assert "window home 'Traker' opened wanted=DP-1 on=DP-1" in said

    def test_a_name_this_session_does_not_have_moves_nothing(self, qapp):
        session = at_home(output="DP-9")

        assert session("sent") == []
        assert session("app.frameGeometry.x") == 0

    def test_dragging_it_to_the_other_monitor_is_undone(self, qapp):
        session = at_home()
        session("sent = []; drag(app, outputs[1]);")

        assert session("sent") == ["Traker -> DP-1"]
        assert landed(session) == "DP-1"

    def test_it_is_not_snatched_back_while_the_drag_is_still_happening(self, qapp):
        session = at_home()
        session("""
            sent = [];
            app.move = true;
            app.moveResizedChanged.emit(app);
            app.frameGeometry = {x: 40, y: 60, width: 1200, height: 800};
            app.frameGeometryChanged.emit(app);
        """)

        assert session("sent") == []

    def test_putting_it_back_does_not_recurse(self, qapp):
        session = at_home()
        session("sent = []; drag(app, outputs[1]);")

        assert landed(session) == "DP-1"
        assert len(session("sent")) == 1

    def test_a_compositor_that_will_not_move_it_is_not_argued_with(self, qapp):
        session = at_home("""
            workspace.sendClientToScreen = function (w, output) {
                sent.push('refused');
            };
            Object.defineProperty(app, 'output', {get: function () { return outputs[1]; },
                                                  set: function () {}});
            Object.defineProperty(app, 'frameGeometry', {
                get: function () { return {x: 0, y: 0, width: 1200, height: 800}; },
                set: function () { app.frameGeometryChanged.emit(app); }
            });
        """)
        before = len(session("sent"))
        for _ in range(12):
            session("app.frameGeometryChanged.emit(app);")

        assert len(session("sent")) <= before + 5
        assert any("gave up" in line for line in session("printed"))

    def test_a_monitor_coming_back_re_places_it(self, qapp):
        session = at_home()
        session("""
            sent = [];
            app.frameGeometry = {x: 0, y: 0, width: 1200, height: 800};
            workspace.screensChanged.emit();
        """)

        assert session("sent") == ["Traker -> DP-1"]

    def test_one_move_is_one_line_in_the_journal(self, qapp):
        session = at_home()
        session("printed = []; drag(app, outputs[1]);")

        assert len([l for l in session("printed") if "window home 'Traker'" in l]) == 1

    def test_a_window_already_there_says_nothing(self, qapp):
        session = at_home("app.frameGeometry = {x: 1920, y: 0, width: 1200, height: 800};")

        assert session("sent") == []
        assert [l for l in session("printed") if "window home 'Traker'" in l] == []

    def test_the_window_usually_maps_after_the_script_loads(self, qapp):
        session = at_home("all = [];")
        assert session("sent") == []

        session("var later = new Win('traker', {caption: 'Traker'});"
                "later.output = outputs[1];"
                "later.outputChanged = new Signal();"
                "open_window(later);")

        assert session("sent") == ["Traker -> DP-1"]

    def test_it_leaves_a_breaks_walls_alone(self, qapp):
        session = at_home("all = [app, front, other];")

        assert session("sent") == ["Traker -> DP-1"]

    def test_it_leaves_another_application_alone(self, qapp):
        session = at_home("""
            var theirs = new Win('konsole', {caption: 'Traker'});
            theirs.output = outputs[1];
            all = [app, theirs];
        """)

        assert session("sent") == ["Traker -> DP-1"]

    def test_a_window_titled_for_a_second_instance_is_still_ours(self, qapp):
        session = at_home("all = []; ")
        session("var second = new Win('traker', {caption: 'Traker <2>'});"
                "second.output = outputs[1];"
                "second.outputChanged = new Signal();"
                "open_window(second);")

        assert session("sent") == ["Traker <2> -> DP-1"]

    def test_a_plasma_without_sendClientToScreen_writes_the_property(self, qapp):
        session = at_home("""
            delete workspace.sendClientToScreen;
            var moved = null;
            Object.defineProperty(app, 'output', {
                get: function () { return moved || outputs[1]; },
                set: function (next) {
                    moved = next;
                    app.frameGeometry = {x: next.geometry.x, y: next.geometry.y,
                                         width: 1200, height: 800};
                }
            });
        """)

        assert landed(session) == "DP-1"

    def test_a_plasma_with_neither_gets_the_geometry(self, qapp):
        session = at_home("""
            delete workspace.sendClientToScreen;
            app.fullScreen = true;
            Object.defineProperty(app, 'output', {
                get: function () { return outputs[1]; },
                set: function () {}
            });
        """)

        assert session("app.frameGeometry.x") == 1920
        assert session("app.fullScreen") is True
