@per-user
Feature: Caffeine at bedtime

  As a user whose sleep quality depends on when the last caffeine was taken
  I want to see how much caffeine will still be circulating when I go to bed
  So that I can move my last coffee earlier instead of guessing

  The view reports one metric: the caffeine still circulating at bedtime.

  Background:
    Given my profile declares my sleep time, my caffeine half-life and my sleep-safe threshold

  Rule: The residual dose is projected forward to bedtime

    @exact
    Scenario: Decay of a single drink
      Given a drink logged at a known clock time
      Then its residual at bedtime is its caffeine times one half raised to the power of (hours until bedtime divided by the half-life)

    Scenario: A day's residual is the sum of its drinks
      Given several drinks logged at different times of one day
      Then the day's figure is the sum of each drink's own projection

    Scenario: An early drink barely counts
      Given two identical drinks, one in the morning and one late in the evening
      Then the late drink contributes far more to the bedtime figure

    Scenario: My own settings drive the projection
      Given I change my sleep time or my half-life
      Then the projection changes accordingly for my whole history

  Rule: A continuous 30-day window makes streaks visible

    Scenario: Days without caffeine are plotted, not skipped
      Given a day on which I logged no caffeinated drink
      Then that day appears in the window at zero
      And the horizontal axis stays evenly spaced across all 30 days

    Scenario: The window is fixed
      Then exactly the last 30 days are shown, whether or not they contain data

  Rule: Crossing the threshold is shown as a gradient, not a switch

    Scenario: The threshold is drawn
      Then my sleep-safe threshold is marked as a reference line

    Scenario Outline: Colour follows the distance from the threshold
      Given a day whose residual is <position> the threshold
      Then that day is rendered <reading>

      Examples:
        | position       | reading                        |
        | well below     | in the safe colour             |
        | approaching    | part-way along the gradient    |
        | above          | in the danger colour           |

    Scenario: The transition is smooth
      Then colour interpolates continuously with the residual amount
      And no single step of the data produces an abrupt colour flip

    Scenario: The latest day is emphasised
      Then the most recent day is highlighted so today's standing is obvious

  Rule: A day can be interrogated

    Scenario: Hovering a day
      When I hover a day in the window
      Then I see its estimated residual at bedtime
      And how far that is above or below my threshold
      And the date in the household's date format
