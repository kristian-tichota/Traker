@accessibility @core
Feature: Filtering and sorting what a table shows

  As a user whose ledger holds several thousand rows
  I want to ask "show me every time I ate X" without leaving the keyboard
  So that my own history is something I can question, not only scroll

  A filter narrows the ledger and a sort orders the result. The shortest filter
  is a bare word.

  Background:
    Given the application is open
    And a tab showing a log table is visible

  Rule: A bare word is the fast path

    Scenario: One word searches every column
      When I filter on "oats"
      Then only rows with "oats" somewhere in them remain
      And the match ignores letter case

    Scenario: Accents are ignored while matching
      Given the catalog holds "Řízek s bramborem"
      When I filter on "rizek"
      Then that item's rows remain
      And the folding is the one the command bar already uses for completion

    Scenario: A bare word matches a name, a meal or a date alike
      When I filter on "breakfast"
      Then rows whose meal type is Breakfast remain
      And nothing else has to be typed to say which column was meant

  Rule: A field term narrows to one column

    Scenario Outline: Naming a column
      When I filter on "<term>"
      Then only rows whose <column> satisfies it remain

      Examples:
        | term             | column        |
        | meal:b           | meal type     |
        | food:oats        | food name     |
        | kcal>300         | calories      |
        | prot>=20         | protein       |
        | date>01.08.2026  | date          |
        | g>90             | grams         |
        | est:1            | estimate mark |

    Scenario: A column may be named by an alias or by a prefix
      Then "kcal", "cal" and "Calories" all name the calories column
      And "caf" names the caffeine column without its units being typed

    Scenario: One shorthand names the set column on every tab
      Then "set" names the meal set on the Food tab and the stack on Supplements
      And it resolves to whichever set column the table in front of me has

    Scenario: The estimate mark is a flag, so it compares as one
      When I filter on "est:1"
      Then only the estimated rows remain
      And "est:0" leaves only the rows read off a label

    Scenario: Meal shortcuts read the way the log command's do
      When I filter on "meal:b"
      Then rows whose meal type is Breakfast remain
      And the shortcuts are the ones ":log" already accepts

    Scenario: Dates are typed the way they are read
      When I filter on "date>01.08.2026"
      Then rows after the first of August remain
      And typing the stored ISO form works too

    Scenario: Comparisons run against the stored value, not the rendered text
      Given a row showing "9.00" calories and a row showing "312.40"
      When I filter on "kcal>300"
      Then only the row with 312.40 remains
      And the comparison is numeric, so "9.00" is not treated as the larger

  Rule: Terms combine, and a bad one is refused

    Scenario: Two terms both have to match
      When I filter on "oats meal:b"
      Then only breakfast rows mentioning oats remain

    Scenario: A bare word mixes with a field term
      When I filter on "oats date>01.08.2026"
      Then only rows mentioning oats after that date remain

    Scenario: A column that does not exist is reported
      When I filter on "nonsense:x"
      Then the status bar says no such column exists
      And it lists the columns that do
      And the table is not narrowed, because a filter that silently matches everything looks exactly like one that worked

    Scenario: A comparison that cannot be made is reported
      When I filter on "kcal>abc"
      Then the status bar says it is not a number or a date
      And the previous filter stays in force

    Scenario: A term with no value is reported
      When I filter on "kcal>"
      Then the status bar says the value is missing

  Rule: FILTER is a mode, with the guarantees every mode carries

    Scenario: The filter key opens the bar
      When I press the filter key in NORMAL mode
      Then FILTER mode is active
      And the status bar names it
      And the filter bar holds keyboard focus

    Scenario: The sheet can be filtered without leaving it
      Given SHEET mode is active
      When I press the filter key
      Then FILTER mode is active

    Scenario: Escape clears the filter and leaves the mode
      Given a filter is in force
      When I press Escape
      Then NORMAL mode is active
      And every row is visible again
      And the filter bar is hidden

    Scenario: Enter keeps the filter and moves to the rows
      Given a filter is in force
      When I press Enter
      Then SHEET mode is active
      And the cursor is on the first matching row
      And the filter is still in force

    Scenario: A tab with no table says so
      Given a chart tab is visible
      When I press the filter key
      Then the status bar says there is nothing to filter
      And no filter bar opens

  Rule: One prompt is on screen at a time

    Scenario: The command bar makes way for the filter bar
      When I press the filter key
      Then the command bar is hidden
      And only the "/" prompt is under the table

    Scenario: The command bar comes back when the filter closes
      Given a filter is in force
      When I press Escape
      Then the command bar is visible again
      And it holds whatever the visible tab pre-fills

    Scenario: An empty filter bar says what to type, once
      When I press the filter key
      Then the bar shows examples of each form it accepts
      And no second string is painted over them

  Rule: The member is told what the matched set comes to

    Scenario: A summary line under the table
      Given a filter is in force
      Then a line under the table reports how many rows matched
      And the totals of the columns that table has
      And the first and last date in the matched set
      And those dates are written the way the household reads them

    Scenario: Estimated rows are counted only when there are some
      Given a matched set containing estimates
      Then the summary says how many of its rows are estimates
      And a matched set with none says nothing about them

    Scenario: The summary agrees with the day's own totals
      Then the matched set's totals and the daily totals are computed by one function, and a test asserts they agree

    Scenario: The progress bars keep meaning today
      Given a filter spanning several weeks is in force
      Then the calorie, protein and salt bars still show today against my goal
      And the matched set's totals are in the summary line, labelled as such

    Scenario: The summary disappears with the filter
      When I clear the filter
      Then the summary line is hidden

  Rule: A row I just logged is never hidden by a filter

    Scenario: An optimistic row stays visible
      Given a filter is in force
      When I log a row whose derived columns are not known yet
      Then that row is shown regardless of the filter
      And hiding it would look exactly like the write having failed

    Scenario: My own write does not throw the filter away
      Given a filter is in force
      When I log a row
      Then the filter is still in force
      And FILTER mode is still active
      And the filter bar still holds what I typed

    Scenario: Changing tabs still drops it
      Given a filter is in force
      When I switch to another tab
      Then the filter is cleared
      And its field terms were resolved against the columns of the table I left

  Rule: Sorting orders the answer, and can be undone

    Scenario: The sort key sorts by the column under the cursor
      Given SHEET mode is active
      When I press the sort key
      Then the table is sorted by that column, ascending
      And the status bar names the column and the direction

    Scenario: Pressing it again reverses the order
      When I press the sort key twice
      Then the table is sorted by that column, descending

    Scenario: Pressing it a third time restores the stored order
      When I press the sort key three times
      Then the table is back in the order the ledger is stored in
      And that matters because the service answers newest first

    Scenario: Sorting compares values, not their renderings
      Given a column holding 9 and 312
      When I sort by it ascending
      Then 9 comes before 312

    Scenario: An orphaned row sorts last either way
      Given a row whose catalog item was deleted, so the sorted value is absent
      When I sort by that column
      Then that row is last, ascending or descending

    Scenario: Clicking a column heading sorts it the same way
      When I click a column heading
      Then the table is sorted by that column, ascending
      And a second click reverses it, and a third restores the stored order

    Scenario: The heading carries an arrow for the sort in force
      When a column is sorted
      Then its heading shows an arrow for the direction
      And restoring the stored order takes the arrow away

    Scenario: A filter and a sort hold together
      Given a filter is in force
      When I sort by a column
      Then only matching rows are shown, in the sorted order

  Rule: A filter survives what happens under it

    Scenario: A refresh re-evaluates the filter
      Given a filter is in force
      When the table is refreshed
      Then the filter is applied to the new rows
      And the summary line reports the new matched set

    Scenario: Switching tabs closes the filter
      Given a filter is in force
      When I switch to another tab
      Then that tab shows all of its rows
      And the filter bar is not carried over
