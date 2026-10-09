@per-user
Feature: Supplement logging

  As a household member with a fixed micronutrient routine
  I want to log a stack in one command and see the gaps
  So that I can tell at a glance which nutrients I am still short of

  A supplement catalog entry lists a dose per serving for each tracked
  micronutrient. A log row is a quantity and a name, and the per-nutrient
  arithmetic and the comparison against targets are derived.

  The name may be a stack, meaning a named bundle of supplements and servings.
  Logging one writes an ordinary row per supplement, and those rows read as one
  line in the ledger. See `item_sets.feature`.

  Background:
    Given the shared catalog contains my supplement products
    And my profile lists a daily target per nutrient

  Rule: A dose is logged as servings of a named product, or of a stack

    Scenario: Logging a dose
      When I log a number of servings of a supplement
      Then the row records the date, the product and the servings
      And each tracked nutrient is the catalog dose times the servings

    Scenario: The serving count may be left out
      When I log a supplement or a stack by name alone
      Then one serving of it is recorded

    Scenario: Logging the day's stack
      When I log a stack
      Then one row is written per supplement in it
      And each records the servings the stack declares
      And the ledger heads them with a line totalling the doses

    Scenario: A non-positive serving count is refused
      When I log zero or fewer servings
      Then the row is rejected

    Scenario: Products may cover any subset of the tracked nutrients
      Given a product that contributes only one nutrient
      Then its other nutrient contributions read as zero

  Rule: Intake is presented against the member's own targets

    Scenario: Comparing intake with targets
      Then each tracked nutrient is plotted per day over the recorded history
      And each point is a share of my configured target, which is drawn at 100%
      And a day with nothing logged reads as zero rather than being skipped
      And a nutrient whose target is zero is not plotted

    Scenario: Supplement trends are averaged over 30 or 7 days
      Then the supplement graphs offer a 30-day and a 7-day window, and no single-day values
      And they use the 30-day window until I choose another
      And the choice is stored apart from that of the nutrient graphs

    Scenario: Targets are per member
      Given the other member has different targets
      Then their view compares the same catalog products against their own numbers

    Scenario: A member may retarget or rename the nutrient list
      Given I edited the nutrient targets in my profile
      Then the view uses my labels and my targets
      And a member who never edited them gets the built-in defaults
