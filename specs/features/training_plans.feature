@per-user
Feature: Training plans

  As someone rebuilding strength on a schedule I wrote months ago
  I want the plan and the ledger on one screen
  So that I can see what today asks for and what the last four weeks actually were

  A **cycle** is a named block of weeks — seventeen of them, say — holding one
  **planned session** per training day, each holding the **movements**
  prescribed for it: a set count, a target range, a load and an effort. It is
  private to one member, unlike a workout: two people sharing one pair of
  dumbbells are on different cycles, and a plan is a prescription rather than a
  household fact.

  A plan is not a named set. A workout's loads are fixed, and four months of
  progression would be four months of near-identical workouts; a plan carries
  its own loads week by week. See `item_sets.feature` for what a workout is.

  Background:
    Given the shared catalog describes the movements I train
    And I have a cycle whose sessions each name a day and its movements

  Rule: A cycle belongs to one member

    @per-user
    Scenario: The other member's plan is not mine
      When I list my training plans
      Then I see only the cycles I defined

    @per-user
    Scenario: The other member cannot read my sessions
      When the other member asks for the sessions of my cycle
      Then the request is refused

    @per-user
    Scenario: The other member cannot rewrite my prescription
      When the other member edits a movement of my cycle
      Then the write matches no row and is refused

    @per-user
    Scenario: We may each run a cycle of the same name
      When we both define a cycle called "Cycle 1"
      Then both are stored, because a cycle name is unique per member

  Rule: A cycle is imported whole or not at all

    Scenario: Importing a cycle with its sessions and movements
      When I import a cycle carrying every session and movement
      Then the cycle, its sessions and its movements are stored in one transaction
      And the answer says how many of each were written

    Scenario: A movement naming nothing in the catalog is refused
      When one movement names an exercise the catalog does not hold
      Then the import is refused, naming that movement

    Scenario: A refused import leaves nothing behind
      When a later session of the import is refused
      Then no part of the cycle is stored
      # A calendar missing a week reads as a plan that stops in December,
      # not as a write that failed.

    Scenario: A prescription is checked like any other write
      When I import a movement with a negative load
      Then the import is refused, naming the movement

  Rule: The calendar says what happened, the table says what was asked for

    Scenario: The whole cycle is one grid
      When I open the Plans tab
      Then I see a row per week and a column per weekday
      And each planned day is marked done, today, ahead or missed

    @exact
    Scenario Outline: What a day's mark means
      Given a session planned for "<day>"
      And the exercise ledger holds "<logged>" for that day
      Then the day is marked "<mark>"

      Examples:
        | day       | logged  | mark    |
        | in a week | nothing | ahead   |
        | today     | nothing | today   |
        | today     | a set   | done    |
        | last week | nothing | missed  |
        | last week | a set   | done    |

    Scenario: Any training that day counts as the session happening
      Given a session prescribing five movements
      And I logged three of them, having substituted the rest
      Then the day is marked done
      And the table still shows which movements were not logged
      # The plan's own rules invite substitutions; marking the day missed for
      # one would make the calendar say something untrue.

    Scenario: Adherence counts only what is due
      When some of the cycle is still ahead
      Then the tally counts sessions up to and including today only

    Scenario: Today does not break a streak until it is over
      Given every session before today was logged
      And today's is not logged yet
      Then the streak still stands

  Rule: The day on the right is the day the cursor is on

    @accessibility
    Scenario: Walking the calendar with the keyboard
      When I move over the grid with hjkl or the arrow keys
      Then the table beside it shows that day's prescription

    Scenario: Moving the cursor does not go back to the service
      When I move to another day of the same cycle
      Then the rows already held are regrouped, with no further read

    Scenario: A rest day shows nothing rather than the last day looked at
      When I move to a day with no session
      Then the table is empty and the heading says nothing is planned

    Scenario: A refresh keeps the day I was reading
      Given I am looking at last Tuesday
      When the tab refreshes because something was logged
      Then it is still showing last Tuesday
      # The tab redraws on every exercise write; a cursor that jumped back to
      # today would make logging a past session impossible.

  Rule: Each movement is shown beside what was logged against it

    Scenario: What was actually done
      Given a movement prescribing three sets of eight to twelve at 20 kg
      And the ledger holds ten, ten and nine at 22.5 kg that day
      Then the row reads "10/10/9 @ 22.5"

    @exact
    Scenario Outline: Whether the prescription was met
      Given a movement prescribing <sets> sets of <low> or more at <load> kg
      And the ledger holds "<done>" at <lifted> kg
      Then the movement reads "<verdict>"

      Examples:
        | sets | low | load | done     | lifted | verdict |
        | 3    | 8   | 20   | 8/8/8    | 20     | hit     |
        | 3    | 8   | 20   | 12/12/6  | 20     | under   |
        | 3    | 8   | 20   | 8/8      | 20     | under   |
        | 3    | 8   | 20   | 12/12/12 | 16.5   | under   |
        | 3    | 8   | 20   | 8/8/8    | 22.5   | hit     |
        | 3    | 8   | 20   | nothing  | —      |         |

    Scenario: A movement with no target range says how many sets, not "3x0"
      Given a movement prescribing three sets and no rep range
      Then the row reads "3 sets"
      # "3x0" reads as a prescription to do nothing, rather than as one that
      # never named a target.

    Scenario: A movement logged twice takes the first row
      Given I logged a movement once as prescribed and again as extra work
      Then the prescribed row is the one compared
    # The ledger's answer is not part of the prescription
    Scenario: The comparison columns cannot be typed into
      Then the load, the target and the effort are editable
      And what was logged and whether it was met are not

  Rule: The plan can be corrected where it is read

    Scenario: Changing a future week's load
      When I type a new load into a movement's row
      Then the plan is updated and the calendar is unchanged

    Scenario: Swapping a movement
      When I type another catalog movement's name into the Exercise column
      Then the prescription now names that movement

    Scenario: Deleting a session takes its movements with it
      When I delete a planned session
      Then its movements go with it and the rest of the cycle stands

  Rule: A planned session can be logged, but only on purpose

    @accessibility
    Scenario: Enter offers the command rather than running it
      When I press Enter on a planned day
      Then the command bar is filled with the command to log that day
      And nothing is written until I confirm it
      # A keystroke on a grid must not silently append eight rows to the
      # ledger. Every write in this application is something the member ran.

    Scenario: Logging a planned session
      When I confirm the command for a planned day
      Then each movement becomes one ordinary exercise log row
      And nothing downstream has to know it came from a plan

    @exact
    Scenario: The bottom of the range is what is written
      Given a movement prescribing three sets of eight to twelve at 16.5 kg
      When I log that session from the plan
      Then the row holds 8, 8, 8 at 16.5 kg with the prescribed effort
      # The number to beat, not one edited downwards on every session that
      # went to plan.

    Scenario: A hold is written in seconds
      Given a movement measured in seconds, prescribing three holds of thirty
      When I log that session from the plan
      Then the row holds 30, 30, 30

    Scenario: A day with nothing planned is refused
      When I ask to log a day the cycle does not prescribe
      Then the command is refused, naming the day

    Scenario: A movement whose exercise was deleted refuses the whole session
      When one movement's catalog item is no longer there
      Then the session is refused rather than logged short
      # A session missing two movements reads as one cut short.

    Scenario: A logged session marks its day done
      When I log a planned session
      Then that day is marked done on the calendar
      And the Exercise tab shows the same rows

  Rule: The plan is a template; the ledger is history

    Scenario: Deleting a cycle
      When I delete a cycle
      Then its sessions and movements go with it
      And the exercise rows it produced remain

    Scenario: The tab is optional
      Given my profile disables the Plans window
      Then the tab is not built and nothing else changes

    Scenario: A household with no plan says so
      When I open the Plans tab with no cycle defined
      Then it says how to import one rather than drawing an empty calendar
