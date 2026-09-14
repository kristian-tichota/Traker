@shared
Feature: Named sets of catalog items

  As someone who eats, drinks, takes and trains the same things week after week
  I want to name a bundle of catalog items once
  So that logging a six-ingredient breakfast, or a nine-supplement stack, is one
  line, spelled the same way every time

  A **set** is a named list of catalog items and how much of each. It is shared
  across the household like the catalogs, and separate from them: it has no
  values of its own, only the items it composes.

  Every domain has them, and each calls them by its own word:

  | Domain     | What a member calls one | What a component carries |
  | food       | meal set                | grams                    |
  | beverage   | drink set               | servings                 |
  | supplement | stack                   | servings                 |
  | mobility   | routine set             | minutes                  |
  | exercise   | workout                 | a set scheme, load, effort |

  Logging one expands it, on the server, into one ordinary log row per
  component — each carrying the set it came from. Nothing downstream learns a
  second kind of row: the derived values, the day's bars, the charts and the
  filter all read the same log rows they always did.

  A set's name is unique **within its domain**, not household-wide: each log
  command resolves one namespace, its own, so a "Morning" stack and a "Morning"
  drink set can both exist.

  Background:
    Given the shared catalog contains the items I use
    And both household members see the same sets

  Rule: A set is a list of catalog items, each measured in its domain's unit

    Scenario: Defining a set from items already in the catalog
      When I define a set naming several catalog items and an amount of each
      Then the set is stored with one component per item
      And the whole household can log it

    Scenario: A meal set's amounts are grams
      Given a food whose catalog serving size is 50 g
      And a meal set that uses 100 g of it
      When I log that set
      Then the row for that food records 100 g
      And it reads as 2 servings

    Scenario: Correcting a serving size leaves the recipe meaning the same food
      Given a meal set that uses 100 g of a food
      When I correct that food's serving size in the catalog
      Then the set still means 100 g of it
      And the rows it has already written still mean 100 g of it
      And what that amount comes to in servings is what changes

    Scenario: A stack's and a drink set's amounts are servings
      When I define a stack of supplements or a set of drinks
      Then each component's amount is a number of servings of that item

    Scenario: A routine set's amounts are minutes
      When I define a routine set
      Then each component's amount is how long that routine is done for

    Scenario: A component that is not in the catalog is refused
      When I define a set naming an item the catalog does not hold
      Then the definition is rejected
      And the message names the item
      And no part of the set is stored

    Scenario: An amount that is not a positive number is refused
      When I define a set with a negative, zero or unreadable amount
      Then the definition is rejected
      And nothing is written

    Scenario: The same item twice in one set is refused
      When I list one item twice in the same definition
      Then the definition is rejected
      And the message says to give one amount per component

    Scenario: A set is a flat list of items
      Then a set's components are catalog items and never other sets

    Scenario: A set draws only on its own domain's catalog
      Then a stack composes supplements and a meal set composes foods
      And a domain with no sets refuses to define one

  Rule: A set's name is its own within its domain

    Scenario: A set may not take an item's name
      When I define a set whose name an item of that domain already holds
      Then the definition is rejected
      And the message says logging it would be ambiguous

    Scenario: A set name is unique however it is capitalised
      When I define a set whose name an existing set of that domain already holds
      Then the definition is rejected
      And the existing set is left untouched

    Scenario: Two domains may use the same name
      Given a supplement stack called "Morning"
      When I define a drink set called "Morning"
      Then both exist
      And each log command reaches the one belonging to its own domain

    Scenario: Logging finds a set regardless of capitalisation
      Given a set called "Blue Oatmeal"
      When I log "blue oatmeal"
      Then the set is logged

  Rule: A domain's own log command takes an item or a set

    Scenario: The logging command takes either
      When I log a name
      Then it is resolved against that domain's catalog first and its sets second
      And completion offers both

    Scenario: A name in neither is refused
      When I log a name that is in neither
      Then no row is written
      And the message names the catalog and the sets it looked in

    Scenario: The leading quantity multiplies every component
      Given a set of several items
      When I log two of it
      Then every component's amount is doubled

    Scenario: For a routine set the leading number is a multiple, not a duration
      Given a routine set whose components carry their own minutes
      When I log one of it
      Then each routine is logged for the minutes the set declares

    Scenario: A meal set cannot be logged in grams
      When I log a meal set with an amount in grams
      Then the write is refused
      And the message says to log it as a multiple
      # Its ingredients are already in grams and it declares no total mass, so a
      # mass here could only be read as a proportion of one. Guessing which
      # reading was meant is worse than refusing.

    Scenario: A workout is logged by its own command
      Given a workout, whose components carry their own sets, load and effort
      When I log it
      Then each movement is recorded as the workout describes it
      And nothing about it was typed but its name

    Scenario: The ordinary training command refuses a workout's name
      When I log a workout's name as though it were an exercise
      Then the write is refused
      And the message names the command that logs a workout
      # A workout carries its own loads, so there is nothing for the sets,
      # weight and effort typed with it to apply to. Ignoring them silently is
      # what refusing avoids.

    Scenario: A set with no components cannot be logged
      Given a set whose components have all been deleted
      When I log it
      Then the write is refused
      And the message says it has no components

    Scenario: The expansion is one write
      When I log a set
      Then either every component row is written or none is

  Rule: The ledger says which set a row came from

    Scenario: Each expanded row names its set
      When I log a set
      Then each row it wrote carries the set's name in its own column
      And an item logged on its own carries none

    Scenario: A logged set is headed by a line totalling it
      Given I logged a set
      Then the rows it wrote are headed by a line naming the set
      And that line reports the sum of the figures it can honestly add
      And it reports no serving count of its own

    Scenario: A heading adds up only what a sum of means something
      Then a meal set's heading totals the grams and the nutrients
      And a stack's heading totals the doses
      And a routine set's heading totals the minutes and not the intensity
      And a workout's heading totals the volume and not the loads
      # Servings across different foods, or reps across a squat and a plank,
      # are not quantities. The set's own multiplier is not stored, so the only
      # honest figures are the ones that add up.

    Scenario: Two logs of one set at one meal read as one meal
      When I log the same set twice at the same meal on the same day
      Then one heading covers all the rows
      And it totals all of them

    Scenario: What makes one logging of a set differs by domain
      Then a meal set is one logging per day and meal
      And a drink set is one logging per day and time
      And every other set is one logging per day

    Scenario: The heading is not a row I can edit or delete
      Then the heading has no database id
      And typing into it is refused

    Scenario: Sorting drops the headings
      When I sort the ledger by any column
      Then the headings are not shown
      And every row still names its set in the meal set column

    Scenario: Filtering drops the headings
      When I narrow the ledger with a filter
      Then the headings are not shown
      And the matched set's totals count the rows, not the headings

    Scenario: The set name is a filterable column
      When I filter on the set column
      Then only the rows logged as part of a matching set are shown
      And the same shorthand names it on every tab

    Scenario: Clearing the sort brings the headings back
      When I return the ledger to its stored order
      Then the headings are shown again

  Rule: Deleting an item a set needs is refused

    Scenario: Removing a component's item
      Given an item that a set uses
      When I remove that item from the catalog
      Then the removal is rejected
      And the message names the sets that use it, in that domain's words
      And the item is still in the catalog

    Scenario: Every domain is asked, not just the one being looked at
      Given a supplement that a stack uses
      When I remove that supplement
      Then the removal is rejected naming the stack
      # A stack missing a supplement under-reports a dose exactly the way a
      # recipe missing an ingredient under-reports a meal.

    Scenario: Removing the set first
      When I remove a set
      Then its components go with it
      And the items it used can then be removed

    Scenario: Rows already logged from a set are history and stay
      Given I logged a set
      When that set is removed
      Then the rows it wrote remain in my log
      And they no longer name a set

  Rule: A set can be read, repaired and pruned from its own tab

    Scenario: Each domain's tab lists its sets
      Then the sets pane sits beside that domain's catalog
      And a set is built out of the items directly above it

    Scenario: A set whose last component was deleted is still shown
      Then it appears with its item and amount empty
      # A set the member cannot see is one they cannot repair or remove.

    Scenario: A component's amount can be corrected in place
      When I type a new amount into a component's row
      Then the set means that amount from then on
      And the rows it has already written are unchanged

    Scenario: A set's own name is not editable from the pane
      Then the pane's rows are the set's components
      And renaming the set is a write to another table
