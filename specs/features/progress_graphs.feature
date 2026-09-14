@per-user
Feature: Progress graphs

  As a household member reviewing trends rather than single days
  I want nutrition, training and activity plotted against my own goals
  So that I can see direction of travel without exporting anything

  Graph preferences are per member, although the catalog is shared.

  Rule: Drawing a chart does not take the keyboard away

    @accessibility
    Scenario: A chart is drawn while the window stays navigable
      When I open a chart tab
      Then the chart is read and drawn without blocking the interface
      And I can change tab, or type a command, before it has finished

    @accessibility
    Scenario: A chart that is not on screen is not drawn
      Given a chart tab I have not opened
      When something invalidates it
      Then no work is done for it until I open it
      And opening it draws it at the size it is shown at

    Scenario: A chart that has been superseded is discarded
      Given a chart is being drawn
      When something asks for it again before that finishes
      Then only the later answer reaches the screen
      And the earlier one is dropped without drawing over it

  Rule: A chart I am waiting for says it is being drawn

    Scenario: A chart being drawn for the first time
      Given a chart tab whose chart has never been drawn
      When I open it and the drawing takes longer than a moment
      Then a turning arc says it is being drawn
      And it stops when the chart appears

    Scenario: A chart being redrawn over one I can already read
      Given a chart is on screen
      When it is redrawn
      Then the arc does not cover the chart I am reading
      And the chart I can already read stays on screen until the new one lands

    Scenario: A drawing quick enough not to mention
      When a chart is drawn faster than the cue's grace period
      Then no arc appears at all

    Scenario: A drawing that failed
      When drawing a chart raises
      Then the arc stops
      And it does not go on claiming work that ended in an error

    Scenario: A chart I cannot see says nothing
      Given a chart tab I am not looking at
      When it is being drawn
      Then no arc is animated for it

  Rule: Nutrient trends can be smoothed

    Scenario: Daily values
      Then each tracked nutrient is plotted per day over the recorded history
      And my goal for that nutrient is drawn as a reference line and labelled

    Scenario: Weekly smoothing
      When I choose the 7-day window
      Then each point is the average of that day and the six before it
      And the series shortens accordingly rather than inventing leading values

    Scenario: A window wider than the history yields no points yet
      Given I have logged fewer days than the window is wide
      When I choose that window
      Then no averaged points are drawn
      And the chart says how many days the window still needs
      But the app keeps running

    Scenario: A one-day window is the raw series
      When I choose the 1-day window
      Then the plotted values are the recorded values, unaltered

    Scenario: The choice is remembered
      Given I chose a smoothing window
      When I reopen the app
      Then my choice is still in force
      And the other member's choice is unaffected

    Scenario: The window can be changed from the keyboard
      When I press the single-day or weekly key in NORMAL mode
      Then the graphs switch window and the status bar confirms it

  Rule: A day that was guessed rather than logged says so on the chart

    Scenario: The estimated share of each day is hatched
      Given days some of whose calories were estimated
      Then the calorie chart hatches that share of each day's column
      And it is the same figure the Food tab reports as a percentage

    Scenario: Only the calorie chart carries it
      Then the protein, fat, salt, fibre and sugar charts are unhatched

    Scenario: A stretch with no estimates in it is unhatched
      Then nothing is drawn rather than an empty hatch along the axis

    Scenario: The band is smoothed with the window it qualifies
      Given a weekly smoothing window
      Then the hatched series is averaged over the same window as the line

  Rule: Exercise graphs are pinned to the movements I care about

    Scenario: Assigning a movement to a slot
      When I pin an exercise to a numbered slot
      Then that slot plots that exercise's history
      And the assignment is remembered for me alone

    Scenario Outline: The grid can be resized
      When I choose the "<layout>" layout
      Then <count> slots are available

      Examples:
        | layout | count |
        | 2x2    | 4     |
        | 2x3    | 6     |
        | 3x3    | 9     |

    Scenario: Shrinking the grid does not lose assignments
      Given I pinned exercises to nine slots
      When I switch to a smaller layout
      Then only the visible slots are plotted
      And the hidden assignments are still there when I switch back

    Scenario: An empty slot says so
      Given a slot with no exercise pinned
      Then it renders as empty rather than as an error

    Scenario: Each plot shows progress against a target where one exists
      Given my profile declares a target weight and rep scheme for a movement
      Then that target is drawn alongside the movement's history

    Scenario: The layout can be set from the command line
      When I submit a layout command with a supported layout
      Then the grid changes and the control reflects it
      And an unsupported layout is rejected with the supported ones named

  Rule: Activity is shown as a calendar of estimated expenditure

    Scenario: The activity calendar
      Then each day is drawn as a cell carrying the day of the month
      And days with training or mobility work also show their estimated energy
      And days with nothing recorded are visibly inert

    Scenario: Energy uses my own body weight
      Then metabolic effort is converted using my weight, not a household average

    Scenario: A day can be interrogated
      When I hover a day
      Then I see the contribution of training and of mobility work separately

  Rule: The energy estimate is a stated model, not a measurement

    @exact
    Scenario: What a working set is worth
      Given a set of strength work
      Then it starts from a base of 5.0 METs
      And that is scaled by the muscle group and by the effort
      And it counts as 45 seconds of work, with rest between sets not counted

    @exact
    Scenario Outline: The muscle group scales the estimate
      Given a movement whose catalog entry names the group "<group>"
      Then the base is multiplied by <factor>

      Examples:
        | group      | factor |
        | Legs       | 1.25   |
        | Back       | 1.25   |
        | Chest      | 1.25   |
        | Biceps     | 0.80   |
        | Shoulders  | 0.80   |
        | Core       | 0.80   |

    Scenario: An unrecognised muscle group is not guessed at
      Given a movement whose group matches neither list
      Then the base is left as it is

    @exact
    Scenario: Effort scales the estimate against a reference of 7
      Then a set at RPE 7 counts as the base
      And a set at RPE 10 counts as ten sevenths of it
      And a rating outside the 1 to 10 scale is clamped to the scale
      And a row with no rating is treated as the reference effort

    @exact
    Scenario: Mobility work takes its intensity from the catalog
      Then its METs come from the routine's catalog entry, not from the log row
      And it counts for its logged duration

    @exact
    Scenario: Only effort above my own baseline counts
      Given my profile declares an activity level
      Then that level is subtracted, because my energy target already assumes it
      And work at or below it contributes nothing rather than a negative amount

    @exact
    Scenario: The compensatory movement discount
      Given my profile declares a NEAT tax percentage
      Then that share is withheld from the estimate
      And a tax of a hundred percent withholds all of it

  Rule: The graphs are an optional part of the install

    Scenario: A core install has no graph tabs
      Given the graphs extra is not installed
      Then every logging tab is present
      And the graph tabs are absent rather than broken
      And the log says which extra would bring them back

    Scenario: Opening the window costs nothing when the graphs are unused
      Then no plotting library is loaded until a graph tab is actually built
