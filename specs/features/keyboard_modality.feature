@accessibility @core
Feature: Modal keyboard navigation

  As a household member who cannot type comfortably
  I want every routine action to be a couple of keystrokes away
  So that logging a day costs me almost no finger movement

  This application is used by members who cannot type comfortably. Assistive
  input (voice control, head tracking) reaches the app as ordinary key and
  pointer events, so
  anything reachable from the keyboard is reachable by those too. The cost of a
  mistake must stay low: no interaction may trap the user in a mode they cannot
  leave, and Escape always means "back to NORMAL".

  Background:
    Given the application is open
    And NORMAL mode is active

  Rule: Exactly one of NORMAL, COMMAND, SHEET or FILTER is active, and the status bar names it

    A mode named on screen that the keyboard is not in is worse than no name at
    all: every key it advertises does nothing. So the mode has a readout of its
    own, separate from the line that carries messages. Sharing one line meant
    the first sort, filter count, refused write or tab switch replaced the mode
    with a message, and nothing ever put it back — for as long as the member
    stayed in that mode.

    Scenario: The status bar teaches the current mode
      Then the status bar names the active mode
      And it lists the keys that leave it
      And the keys it lists are the user's own remapped keys, not hardcoded ones
      And the mode is coloured as well as named

    Scenario: A message does not take the mode away
      When something else is reported to the status bar
      Then the message and the active mode are both readable

    Scenario: Switching tabs does not take the mode away
      Given the tab I am switching to holds data that is out of date
      When I switch to it
      And its rows arrive
      Then the status bar still names the active mode

    Scenario: A name that is not one of the four is refused
      Given SHEET mode is active
      When something asks for a mode that does not exist
      Then SHEET mode is still active

    Scenario: Entering the command line
      When I press the command-mode key
      Then COMMAND mode is active
      And the command line holds keyboard focus

    Scenario: Entering a data sheet
      When I press the sheet-mode key
      Then SHEET mode is active
      And the first table on the visible tab holds keyboard focus
      And a cell is selected even if I had never selected one before

    Scenario: A tab with no table refuses the sheet key
      Given the visible tab holds no table
      When I press the sheet-mode key
      Then NORMAL mode is still active

    Scenario: Entering the filter bar
      When I press the filter key
      Then FILTER mode is active
      And the filter bar holds keyboard focus
      And the table narrows as I type

    Scenario Outline: Escape always returns to NORMAL
      Given <mode> mode is active
      When I press Escape
      Then NORMAL mode is active
      And the main window holds keyboard focus
      And a tab key selects its tab again

      Examples:
        | mode    |
        | COMMAND |
        | SHEET   |
        | FILTER  |

  Rule: A mode belongs to the surface it was entered from

    SHEET names a table, COMMAND and FILTER name a bar. Leaving the tab leaves
    all three behind — the table is off screen, and the bar has lost the
    keyboard to whatever was clicked. The tab keys are read in NORMAL only, so a
    mode that outlives its surface is a keyboard that stops answering.

    Scenario Outline: Switching tabs returns to NORMAL
      Given <mode> mode is active
      When I switch to another tab
      Then NORMAL mode is active
      And a tab key selects its tab again

      Examples:
        | mode    |
        | COMMAND |
        | SHEET   |
        | FILTER  |

    Scenario: A half-typed command survives losing the mode
      Given COMMAND mode is active with text I have not run
      When I switch to another tab
      Then NORMAL mode is active
      And the text is still in the command bar

    Scenario: The focus timer taking the screen leaves the sheet too
      Given SHEET mode is active
      When the focus timer fills the screen
      Then NORMAL mode is active

  Rule: Tabs are reachable by a single labelled keystroke

    Scenario: Tab labels advertise their own shortcut
      Then each tab label is prefixed with the key that selects it

    Scenario Outline: One keystroke selects a tab
      When I press "<key>" in NORMAL mode
      Then the tab at position <position> becomes visible

      Examples: digits address the first ten tabs
        | key | position |
        | 0   | 1st      |
        | 3   | 4th      |

      Examples: letters continue past the tenth tab
        | key | position |
        | A   | 11th     |
        | B   | 12th     |

    Scenario: A key beyond the last tab does nothing
      When I press a tab key with no tab behind it
      Then the visible tab does not change
      And no error is reported

    Scenario: Tabs the user disabled are skipped entirely
      Given I disabled some views in my profile
      Then the remaining tabs are renumbered without gaps
      And every one of them is still reachable by a single keystroke

  Rule: Sheets are navigated and edited without leaving the home row

    Scenario: Moving between cells
      Given SHEET mode is active
      When I press the left, down, up or right key
      Then the selection moves one cell in that direction
      And the selection never leaves the table

    Scenario: Editing the selected cell
      Given SHEET mode is active
      And the selected cell is editable
      When I press the edit key
      Then the cell enters inline editing
      And navigation keys type into the cell instead of moving the selection

    Scenario: Read-only cells refuse the edit key
      Given SHEET mode is active
      And the selected cell holds a derived value
      When I press the edit key
      Then nothing happens

  Rule: Data arriving does not take the surface away from me

    A refresh is not an arrival. Arriving at a tab whose rows are about to be
    replaced may fade the page in — the content is new to the eye anyway. Data
    changing under a tab I am already reading may not: it is one row out of
    thousands, and blanking the page to say so also hides the row I just wrote,
    loses the cell my cursor was on, and reads as the application restarting.

    Scenario: A tab I switch to fades its rows in
      Given the tab I am switching to holds data that is out of date
      When I switch to it
      Then its rows fade in when they arrive rather than when I pressed the key
      And the status bar says it is reading

    Scenario: A tab whose data is already current is instant
      When I switch to a tab whose data is current
      Then it appears with no fade at all

    Scenario: My own write does not blank the tab I am reading
      Given a log table is visible
      When I log a row
      Then the rest of the tab is undisturbed
      And only the rows the write changed are highlighted
      And the highlight fades

    Scenario: The other member's write does not blank it either
      Given a log table is visible
      When the other member changes the shared catalog
      Then only the rows that changed are highlighted

    Scenario: A refresh that changed nothing shows nothing
      Given a log table is visible
      When a refresh returns the rows it already had
      Then nothing on the tab moves

    Scenario: A refresh keeps my place in the sheet
      Given SHEET mode is active with the cursor on a row
      When that table is refreshed
      Then the cursor is on the same row
      And it follows the row rather than the position it held

    Scenario: A refresh does not put a cursor where I had none
      Given I have not entered the sheet
      When the table is refreshed
      Then no cell is selected

    Scenario: A tab I am waiting for says so
      Given the tab I am switching to holds data that is out of date
      When the read takes longer than a moment
      Then a turning arc says the tab is being read
      And the status bar says it is reading
      And the arc stops when the rows arrive

    Scenario: A tab that arrives at once says nothing
      When a tab's rows arrive faster than the cue's grace period
      Then no arc appears at all
      And a cue too brief to read would be noise rather than feedback

  Rule: A few NORMAL-mode keys are reserved for view options

    Scenario Outline: Switching the nutrient graph window
      When I press "<key>" in NORMAL mode
      Then the nutrient graphs switch to <window>
      And the status bar confirms the change

      Examples:
        | key | window                |
        | D   | single-day values     |
        | W   | 7-day rolling average |
