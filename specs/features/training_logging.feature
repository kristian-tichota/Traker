@per-user
Feature: Training and mobility logging

  As someone managing training load rather than chasing maxima
  I want strength work and mobility work logged with their intensity
  So that the app can estimate strain as well as progress

  A named workout declares each movement's set scheme, load and effort once, and
  `:wlog` records all of them. It is the one named set whose components are not
  an amount. A mobility session may likewise be a routine set of routines and
  their minutes. See `item_sets.feature`.

  Background:
    Given the shared catalog describes the movements I train

  Rule: One row is one exercise on one day, up to five sets

    Scenario: Logging a set scheme
      When I log an exercise with a comma-separated set scheme, a weight and an RPE
      Then the row records up to five sets, the weight and the effort rating
      And unused set slots are recorded as zero

    Scenario: Effort is bounded
      When I log an RPE outside the range 0 to 10
      Then the row is rejected

    Scenario: Negative load is refused
      When I log a negative weight
      Then the row is rejected

  Rule: Progress figures are derived from the row and the movement's metric

    Scenario Outline: Movements are measured in either repetitions or seconds
      Given a movement measured in "<metric>"
      Then its logs are summarised as <summary>

      Examples:
        | metric  | summary                                   |
        | Reps    | total repetitions, volume and estimated 1RM |
        | Seconds | accumulated time, with no volume or 1RM     |

    @exact
    Scenario: Volume for repetition-based work
      Then volume is the sum of all sets multiplied by the weight

    @exact
    Scenario: Estimated one-rep maximum for repetition-based work
      Then the estimate is the weight divided by (1.0278 minus 0.0278 times the best single set)
      And it is reported as zero when no set has any repetitions

    @exact
    Scenario: The estimate has a domain and stops at its edge
      Given a set of more than 36 repetitions
      Then the divisor would be zero or negative and the estimate is not defined
      And the log reports it as not applicable rather than as a negative maximum
      And a timeline that needs a number plots the weight lifted, which is a floor on the true maximum

    Scenario: Time-based work reports no one-rep maximum
      Given a movement measured in seconds
      Then its volume reads as zero
      And its one-rep maximum reads as not applicable

  Rule: Mobility work is logged as duration against an intensity

    Scenario: Logging a mobility routine
      When I log a mobility routine with a duration in minutes
      Then the row records the date, the routine and the duration
      And the intensity comes from the catalog entry, not the log

    Scenario: A non-positive duration is refused
      When I log a routine with a duration of zero or less
      Then the row is rejected

  Rule: Training feeds the household's activity estimate

    Scenario: Strength work is weighted by muscle mass and effort
      Then a day's estimated expenditure rises with the number of working sets
      And large compound movements contribute more than small isolation work
      And a harder effort rating contributes more than an easy one

    Scenario: Only work above ordinary daily activity counts
      Then the estimate subtracts the member's baseline activity level
      And it never contributes a negative amount

    Scenario: The estimate is deliberately conservative
      Then a configurable share is withheld from the estimate
      And the app therefore under-promises rather than over-credits the day's burn

    Scenario: Expenditure is expressed in energy using the member's body weight
      Then metabolic effort is converted to energy with my own weight
      And the same day's figure feeds both the activity heatmap and my energy bar
