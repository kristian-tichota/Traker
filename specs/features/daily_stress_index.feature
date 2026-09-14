@exact @per-user
Feature: Daily Stress Index

  As a user managing how much of the day is spent at a keyboard
  I want one number per day expressing strain against recovery
  So that I can see whether a day was sustainable without reading a timeline

  The index is a ratio of penalty to recovery. Above 1.0 the day cost more than
  it gave back, below 1.0 it was restorative, and a day of the prescribed split
  is exactly 1.0. The presentation around the index is not specified.

  Background:
    Given the day's seconds are accumulated into the four states

  Rule: The index is an unweighted ratio of accumulated seconds

    @exact
    Scenario: The formula
      Then penalty is focus seconds plus focus overtime seconds
      And recovery is rest seconds plus rest overtime seconds
      And the index is penalty divided by recovery

    @exact
    Scenario: A second of one state costs a second of any other
      Then no state is worth more or less than the seconds it holds

    @exact
    Scenario: A day of the prescribed split
      Given I focused for as long as I rested
      Then the index is 1.0, which is the line the colours turn on

    Scenario: A day with no recovery at all
      Given I accumulated penalty but no recovery whatsoever
      Then the index is the penalty total rather than a division by zero

    Scenario: A day with nothing logged
      Then the index is zero
      And the day is not drawn as an active day

    Scenario: Nothing about the app changes the arithmetic
      Then two days holding the same seconds score the same
      And history already recorded keeps its stored seconds, which are recomputed on display

    Scenario: The live index includes time not yet stored
      Then the displayed index combines today's stored minutes with the current sub-minute counters
      And it agrees with the four live totals shown beside it

  Rule: Thirty days are shown at a glance

    Scenario: The strain calendar
      Then the last 30 days are drawn as one cell per day
      And each cell is coloured by that day's index
      And the numeric index is written into cells that have data

    Scenario Outline: Colour bands
      Given a day whose index is <index>
      Then the cell reads as <reading>

      Examples:
        | index                     | reading      |
        | at or below 1.0           | sustainable  |
        | above 1.0 up to 1.5       | borderline   |
        | above 1.5                 | overloaded   |

    Scenario: Today keeps updating
      Given the timer is running
      Then today's cell tracks the live index without waiting for a refresh

  Rule: A day's score can be overridden by hand

    Scenario: Why overrides exist
      Given a day where the timer was not running while I was in fact resting or working
      Then I can pin that day's displayed index to a value I choose
      And the calendar then reflects reality rather than the timer's blind spots

    Scenario: Setting an override
      When I set an override for a date
      Then the calendar shows my value in place of the computed one
      And the day is marked as overridden rather than silently replaced

    Scenario: Overriding a day that has no recorded time
      When I set an override for a date with no history
      Then the day appears on the calendar as active with my value

    Scenario: Clearing an override
      When I clear the override for a date
      Then the calendar returns to the computed index for that day

    Scenario: Overrides are personal
      Then my overrides never affect the other member's calendar

    Scenario: Overrides do not rewrite history
      Then the stored minute-by-minute history is left untouched by an override
