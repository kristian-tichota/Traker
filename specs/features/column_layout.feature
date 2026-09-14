@accessibility @per-user
Feature: Arranging the columns of a table

  As a member reading a ledger fifteen columns wide on one screen
  I want to switch off the columns I do not use and put the rest in my order
  So that the numbers I actually read are the ones in front of me

  A layout belongs to one member and one table, and survives the session. The
  keyboard route and the pointer route reach the same state.

  Background:
    Given the application is open
    And a tab showing a log table is visible

  Rule: A layout says which columns are shown and in what order

    Scenario: A table nobody has arranged shows what it declares
      Then every column the table declares is visible
      And they are in the order the code declares them

    Scenario: Switching a column off
      When I hide the Sugars column
      Then the table no longer has a Sugars column
      And every other column stays where it was

    Scenario: Putting a column back
      Given I have hidden the Sugars column
      When I show it again
      Then it is back in the place it held before

    Scenario: Reordering a column
      When I move the Calories column to position 2
      Then it is the second column I can see
      And positions count the columns on screen, not the ones declared

    Scenario: Starting over
      When I reset the layout
      Then the table shows what it declares, in the declared order

    Scenario: The values do not move with the headings
      When I move a column
      Then every cell still holds the value its heading names

  Rule: The last column cannot be switched off

    Scenario: Hiding the only column left is refused
      Given every column but one is hidden
      When I try to hide the last one
      Then it is refused, and the reason says so

  Rule: The keyboard route is the one that must work

    Scenario: Reading back what a table is showing
      When I run ":cols"
      Then the status bar names the table and lists its columns in order
      And it names the hidden ones after them

    Scenario Outline: Arranging from the command bar
      When I run "<command>"
      Then <outcome>

      Examples:
        | command             | outcome                                  |
        | :cols hide Sugars   | the Sugars column goes                   |
        | :cols show Sugars   | it comes back                            |
        | :cols Sugars        | it is switched to whatever it was not     |
        | :cols move 2 kcal   | Calories becomes the second column shown |
        | :cols reset         | the declared layout is restored          |

    Scenario: A column is named the way a filter names one
      Then "kcal", "cal" and "Calories" all name the calories column
      And a unique prefix is enough

    Scenario: Naming a column and nothing else toggles it
      When I run ":cols Sugars"
      Then the Sugars column is switched off if it was on, and on if it was off

    Scenario: A column that does not exist is refused, not ignored
      When I run ":cols hide Caffeine" on the Food tab
      Then it is refused, the columns that do exist are listed
      And what I typed stays in the bar to correct

    Scenario: Moving without saying where is refused
      When I run ":cols move Calories"
      Then it is refused, and the refusal shows the form with a position in it

    Scenario: It acts on the table I was last in
      Given a tab hosts a ledger, a catalog and a sets pane
      When I have been in the catalog pane and then run ":cols hide Category"
      Then the catalog pane loses that column
      And the ledger is untouched

    Scenario: The ledger is the table until I have been in another
      When I run ":cols" without having entered any table on this tab
      Then it answers for the ledger

    Scenario: A tab with no table says so
      When I run ":cols" on a chart tab
      Then it says there is nothing to arrange here

  Rule: Every cell stays reachable from the keyboard

    Scenario: Moving across the columns follows what I see
      Given I have moved the Calories column to the front
      When I move right from it
      Then the cursor lands on the column drawn next to it

    Scenario: A hidden column is stepped over
      Given the Date column is hidden
      When I move right from the column before it
      Then the cursor lands on the column after it
      And no keystroke ever leaves the cursor on a column I cannot see

    Scenario: Hiding the column the cursor is on moves the cursor
      Given the cursor is on the Sugars column
      When I hide it
      Then the cursor is on a column that is shown

    Scenario: Entering the sheet lands on a column that is shown
      Given the first declared column is hidden
      When I enter the table
      Then the cursor starts on the first column I can see

  Rule: The mouse can do everything the keyboard can

    Scenario: Dragging a heading reorders the column
      When I drag a heading somewhere else
      Then the columns are in the new order
      And it is remembered without my asking

    Scenario: The header's menu lists every column
      When I right-click the header
      Then every column the table declares is offered, in the order shown
      And the ones on screen are ticked

    Scenario: Switching a column back on with the mouse
      Given I have hidden the Sugars column
      When I right-click the header and tick Sugars
      Then it is back

    Scenario: The last visible column cannot be unticked
      Given every column but one is hidden
      When I right-click the header
      Then the remaining column's entry cannot be chosen
      And every hidden column can still be chosen

    Scenario: The menu can put the whole layout back
      When I choose "Reset Column Layout"
      Then the table shows what it declares

    Scenario: Dismissing the menu changes nothing
      When I right-click the header and dismiss the menu
      Then the layout is what it was, and nothing was stored

  Rule: A layout is this member's, and it is remembered

    Scenario: It is stored per member
      Given both members are logged into the same service
      When I arrange the Food ledger
      Then the other member's Food ledger is unchanged

    Scenario: It is stored per table
      When I arrange the catalog pane
      Then the ledger and the sets pane keep their own layouts

    Scenario: It survives a restart
      Given I have hidden the Sugars column
      When I close the application and open it again
      Then the Sugars column is still hidden

    Scenario: It is read on arrival at the tab, in one request
      When I arrive at a tab
      Then its tables' layouts are asked for together
      And they are asked for once, however often I come back to the tab

    Scenario: What I just did outranks what was stored
      Given the stored layout has not arrived yet
      When I arrange the table
      Then the answer does not undo it

    Scenario: A layout that could not be stored says so
      Given the service is unreachable
      When I arrange a table
      Then the columns move anyway and the status bar says it was not saved

  Rule: A stored layout outlives the code that wrote it

    Scenario: A column a later version added appears
      Given a stored layout written before the Fibre column existed
      When I open that tab
      Then Fibre is visible, at the end

    Scenario: A column this version no longer has is ignored
      Given a stored layout naming a column that has since been removed
      Then the rest of the layout is honoured

    Scenario: Nothing stored means the declared columns
      Given a member who has never arranged this table
      Then it shows what it declares

  Rule: What is on screen is what is summarised

    Scenario: A nutrient switched off is not totalled under the table
      Given a filter is in force and the matched-set line reports calories
      When I hide the Calories column
      Then the line no longer reports them
