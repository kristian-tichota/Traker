@per-user @core
Feature: Personal profile

  As two people with different bodies and different goals
  I want all of my personal settings in one file I can edit
  So that the app can be shared without either of us compromising

  The profile is the only place where the two members' use of the app diverges:
  biometrics, goals, which views they want, which keys they use, their timer
  split, their schedule and where their window belongs in their own desktop
  session. Everything in it has a working default, so an unedited profile is a
  usable profile.

  Rule: A usable profile exists from the first launch

    Scenario: First run
      Given a member with no profile file
      When they start the app
      Then a complete, commented profile is written for them
      And they are told where it was written
      And the app starts normally with those defaults

    Scenario: A partial profile keeps working
      Given a profile that omits some keys
      Then the missing keys fall back to their defaults
      And no error is shown for the omissions

    Scenario: A malformed profile does not prevent startup
      Given a profile file that cannot be parsed
      Then the failure is reported on the console
      And the app starts with defaults throughout

  Rule: Views can be turned off

    Scenario: A generated profile carries the everyday views only
      Given a member with no profile file
      When they start the app
      Then the food, drink, exercise and mobility views are enabled
      And the graphs reading those views are enabled
      And every other view is written down as disabled rather than omitted

    Scenario: Disabling views
      Given I disabled some views in my profile
      Then only the views I kept appear as tabs
      And their keyboard shortcuts are renumbered without gaps

    Scenario: Disabling everything
      Given I disabled every view
      Then the app opens with a placeholder telling me where to re-enable them

    Scenario: A profile predating a tab merge still switches the tab off
      Given my profile disables the separate food log and food database views
      And it names no key for the merged food view
      Then the merged food view does not appear as a tab

    Scenario: A tab merge does not switch a tab off by itself
      Given my profile enables only one half of a since-merged pair
      Then the merged view appears as a tab

  Rule: Energy targets are derived from biometrics

    @exact
    Scenario Outline: Basal metabolic rate
      Given biometrics of <weight> kg, <height> cm, <age> years and gender "<gender>"
      Then my basal rate is <bmr> kcal

      Examples:
        | weight | height | age | gender | bmr    |
        | 75.0   | 180.0  | 30  | M      | 1730.0 |
        | 65.0   | 160.0  | 25  | F      | 1364.0 |

    Scenario: Maintenance need
      Then my maintenance need is my basal rate times my activity level

    Scenario: Energy target
      Then my energy target is my maintenance need adjusted in the direction of my goal

    Scenario: Protein target scales with body weight
      Given a protein multiplier in my profile
      Then my protein target is my weight times that multiplier

    Scenario: An older profile stating protein as a flat figure still works
      Given a profile that declares a fixed protein target and no multiplier
      Then that fixed figure is used

  Rule: Keys are remappable

    Scenario: Remapping navigation
      Given I rebound the navigation, edit, command or sheet keys
      Then the app responds to my keys
      And the status bar hints name my keys

    Scenario: An unrecognised key name falls back
      Given I bound a key to a name the app does not recognise
      Then the built-in default for that action stays in force

  Rule: The day is divided into named regimes

    Scenario: The current regime
      Given a schedule mapping time ranges to regime names
      Then the timer view names the regime I am currently in
      And the tray icon carries that regime's colour

    Scenario: A range crossing midnight
      Given a regime whose range starts in the evening and ends after midnight
      Then it is in force on both sides of midnight

    Scenario: Time outside any range
      Given a moment covered by no range
      Then the regime reads as unscheduled

    Scenario: A weekday may override the default schedule
      Given a schedule declared for today's weekday
      Then it takes precedence over the default schedule

  Rule: The screens lose their colour for the hours I name

    Colour at night is the part of screen hygiene a break cannot answer,
    because a break ends. So this is a schedule and not a hold: it converges
    on what the clock says, and nothing about it is enforced or hard to leave.

    Scenario: Naming the hours
      Given a [grayscale] section I have switched on
      When the clock reaches the hour it starts at
      Then every screen loses its colour, in every application
      And it has its colour back at the hour it ends at
      # The compositor's own filter, not a window of ours: a sheet Traker drew
      # would be grey over Traker and colour everywhere else.

    Scenario: Starting the app inside those hours
      Given the clock is already inside them
      When I start Traker
      Then the screens go monochrome without waiting for the next boundary

    Scenario: The hours wrap past midnight
      Given hours that start in the evening and end in the morning
      Then they are in force on both sides of midnight
      # The same rule the schedule's regimes wrap by, computed once so the
      # two cannot disagree.

    Scenario: Off is the default
      Given a profile I have not edited
      Then the hours are named but nothing is applied
      And my compositor's configuration says nothing about Traker
      # Every setting here that reaches the session is opt-in. The other
      # member of this household does not want their screens touched.

    Scenario: A session with no compositor to ask
      Given a session that is not this desktop at all
      Then the screens are left in colour and the log says so
      And the next minute asks again, for the session whose KWin was not up yet

    Scenario: Closing Traker inside those hours
      Given the screens are monochrome and the hour has not passed
      When I close Traker
      Then they stay that way
      # Unlike the window rule above, which exists only while the window does.
      # The request is for grey evenings, not for grey evenings while Traker runs.

  Rule: The timer's split is declared per member

    Scenario: What it declares
      Given a [timer] section
      Then it names a focus length, a break length, the long break and how many a day holds
      And whether a break takes every screen

    Scenario: The wall is opt-in
      Given a generated profile
      Then breaks do not take the screens until I say so
      # One of the household's two members does not want them taken, and
      # meeting that unasked on a first launch is not a default.

    Scenario: Nothing declared
      Given a profile with no [timer] section
      Then the shipped split applies

    Scenario: A profile written before the split
      Given a profile still declaring the old timer modes
      Then none of that section is read, and the app says so once

  Rule: The window has a desktop and an activity of its own, if I say so

    A KDE session is only deterministic if a virtual desktop and an activity
    always mean the same application. The compositor can be told that, and its
    own settings page is the awkward way to say it: the value it stores is a
    uuid, and one rule matched on the application class caught windows I did
    not mean — a break's walls carry the same class as the window.

    Scenario: Naming where the window belongs
      Given a [window] section naming a virtual desktop and an activity
      When I start Traker
      Then its window is put on that desktop and that activity
      And it cannot be dragged off either of them
      And my screen does not move, and the log says where the window went
      # Being taken to another desktop by a launch is worse than a window the
      # member has to go and find, and the log is what makes the second one
      # explicable rather than a launch that seems to do nothing.

    Scenario: Forcing nothing is the default
      Given a generated profile
      Then nothing of Traker's is written to the compositor's configuration
      # A member who has not asked for this should not find Traker in the list
      # of their own window rules.

    Scenario: And a monitor, which has to be asked for differently
      Given a [window] section naming a screen by its connector name
      When I start Traker
      Then its window is moved to that monitor, by name
      And it is put back there when I let go of it somewhere else
      And it is not snatched back while I am still dragging it
      And the log says which monitor it went to, and what prompted the move
      # KWin's own setting for this is a *number*: an index into a list it
      # rebuilds every boot, so it means a different monitor each time, and an
      # index past the end of the list does nothing and says nothing. Asking
      # for the output by name is the form of the request KWin honours.

    Scenario: Named the way they are shown
      Given a [window] section
      Then a desktop may be named as it appears on the pager, or as its position
      And an activity may be named as it appears in the switcher
      And a screen is named as its connector, never as "primary"
      And all of them are resolved afresh on every launch
      # So renaming or rebuilding one does not leave something stale behind in
      # the member's configuration, which is what a stored uuid does.

    Scenario: A name this session does not have
      Given a [window] section naming a desktop or activity that is not there
      Then that one is left alone, the other still applies, and the log says which
      # And specifically *not* forced to "everywhere", which is what an empty
      # value means to the compositor — the opposite of what was asked for.

    Scenario: A monitor name this session does not have
      Given a [window] section naming a screen that is not there
      When I start Traker
      Then the window is left where the compositor put it, and nothing is moved
      # An unplugged monitor must not send the window somewhere arbitrary.

    Scenario: A compositor that will not move the window
      Given a [window] section naming a screen
      And a compositor that refuses to move the window there
      When it has refused several times in a row
      Then it stops asking, and says so once
      # It watches the window's geometry and moving the window writes its
      # geometry, so a refusal it kept retrying would be an argument on every
      # frame rather than a line in a log.

    Scenario: A session that is not this desktop at all
      Given a [window] section and a session with no compositor to tell
      When I start Traker
      Then nothing is written, and no file is left behind that was not there
      # Including the compositor's own rules file: a member on another desktop
      # environment should not acquire one because Traker looked for it.

    Scenario: Moving it for real means saying so
      Given a [window] section naming a desktop, an activity and a screen
      When I want the window somewhere else
      Then I edit the profile and restart, and there is no command for it
      # Forced is the point. A way to move it for one session would be a way
      # to end up not knowing where it is, which is the thing being fixed.

    Scenario: What a break shows follows the window, unless I say otherwise
      Given a [window] section naming a screen
      And no screen named for what a break shows
      When a break shows me a file
      Then it goes to the monitor the window was forced onto
      And naming one for the break still overrides it
      # The window is on that monitor because that is where the member looks.
      # Falling back to "primary" instead means the first output the compositor
      # announced, which is not necessarily the one in front of them.

    Scenario: It cannot take a break with it
      Given a [window] section naming a desktop and an activity
      When a break takes the screens
      Then the walls are still on every desktop and every activity
      And the window's placement is untouched by the break beginning or ending
      # The two are matched differently on purpose: the walls by a title
      # prefix, the window by its exact title, which no wall's title is. A
      # rule matched on the application class alone reached both, and it
      # un-placed a wall — one screen of a break stopped being covered.

    Scenario: Traker stops being in my configuration when it stops running
      Given a [window] section and a running Traker
      When I close it
      Then the rule that placed its window is gone
      And so is what was holding it to one monitor
      # The compositor drops it when the window goes, and Traker takes it out
      # itself for the session where the compositor restarted underneath.
