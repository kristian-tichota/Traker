@per-user
Feature: Food and drink logging

  As one of two people with opposite calorie goals
  I want the same catalog to score my day against my own target
  So that a shared food database serves weight loss and weight gain equally

  A log row is deliberately thin: what, when, how much. Everything nutritional
  is derived from the shared catalog at read time, so correcting a food label
  once corrects every past day that used it.

  A composed meal is logged through a *meal set*, which expands into one of
  these rows per ingredient rather than becoming a row of its own — see
  `item_sets.feature`. Nothing below changes for those rows.

  Background:
    Given the shared catalog contains the items I log
    And my profile sets my own biometrics and goals

  Rule: Nutrients are derived, never stored on the log row

    Scenario: A food log row carries only what the user chose
      When I log a food
      Then the row stores the date, the meal, the item and how much of it

    Scenario: A row logged as part of a meal set also records which one
      When I log a meal set
      Then each row it writes is an ordinary food log row
      And each also records the set it came from
      And its nutrients are still derived from the catalog, not from the set

    Scenario: Per-row nutrients scale with the mass eaten
      Given a food whose catalog entry is stated per 100 g
      When I log an amount of it
      Then each nutrient is the catalog value for the grams that amount comes to
      And the same rule applies to energy, protein, carbohydrate, sugar, fat, saturated fat, salt and fibre

    Scenario: Correcting the catalog corrects history
      When I fix a wrong nutrient value on a catalog item
      Then every past log row that used it reports the corrected figures

  Rule: An amount is servings or grams, and the ledger shows both

    A serving is whatever the label said it was, and remembering that months
    later is the one thing a member cannot do. So an amount may be typed in
    either unit — a trailing `g` means grams — and **the ledger reports both**,
    side by side, right after the food's name. Checking that a row is what you
    meant is then a glance rather than an arithmetic problem.

    Scenario: A bare number is servings
      When I log "2" of a food
      Then the row records two servings
      And the ledger shows the grams that comes to

    Scenario: A trailing g is grams
      When I log "100g" of a food
      Then the row records 100 g
      And the ledger shows the servings that comes to

    Scenario: Leaving the amount out means one serving
      When I log a food without saying how much
      Then the row records one serving

    Scenario: The amount that was typed is the one stored
      Then a row logged in grams stores grams
      And a row logged in servings stores servings
      And the other reading is computed from the food's serving size on the way out

    @exact
    Scenario: Correcting a serving size moves the derived reading, never the typed one
      Given a food stated per 100 g whose serving size is 50 g
      And a row logged as 100 g of it
      When someone corrects that serving size to 25 g
      Then the row still records 100 g
      And its calories are unchanged, because energy is per 100 g and the mass is known
      And it now reads as 4 servings rather than 2

    @exact
    Scenario: The same correction moves a servings-typed row the other way
      Given a food stated per 100 g whose serving size is 50 g
      And a row logged as 2 servings of it
      When someone corrects that serving size to 25 g
      Then the row still records 2 servings
      And it now reads as 50 g, and its calories fall accordingly
      # A serving is defined by the label, so a row that named servings means
      # whatever the label now says. A row that named a mass means the mass.

    Scenario: An amount is either servings or grams, never both
      When a write carries both
      Then it is refused
      And the store refuses it too

    Scenario: Typing into one column says which unit that row is measured in
      Given a row logged in grams
      When I type a serving count into its servings column
      Then the row is measured in servings from then on
      And its grams column reads what that comes to

    Scenario: An amount of zero or less is refused
      When I log an amount that is not more than zero
      Then no row is written
      And the message says an amount has to be more than zero

    Scenario: An orphaned row keeps the amount it was given
      Given a row logged in grams whose food has since been deleted
      Then it still reports its grams
      And the reading derived from the label reports zero, like every other derived value

    Scenario Outline: Meals are a closed set
      When I log a food under the meal "<meal>"
      Then the row is accepted

      Examples:
        | meal       |
        | Breakfast  |
        | Lunch      |
        | Dinner     |
        | Supplement |

    Scenario: An unrecognised meal type is refused
      When I log a food under a meal type outside that set
      Then the row is rejected
      And it is refused before it reaches the service, naming the four meals
      # The amount before it may be left out, so an argument that took anything
      # at all would let a mistyped amount become the meal type and the meal
      # type become part of the food's name.

  Rule: A meal nobody has a label for is logged as an estimate

    Eating out was a hard stop: either type an eleven-field definition for a
    dish you will never eat again, or log something else as a proxy. The second
    is what happened, and afterwards the day looked exactly like a well-logged
    one.

    An estimate is a calorie figure and nothing else. That is *why* the day
    reads as poorly logged — the protein bar is short and the row says why —
    and it is marked at three scales: the row, the day, and the chart.

    Scenario: Logging an estimate takes calories, a meal and a description
      When I log an estimate of 550 kcal for dinner
      Then a food is written to the catalog under the category "Ad hoc"
      And its energy is that figure and every macro is zero
      And one log row is written against it, marked as an estimate

    Scenario: It is one write, not two
      Then either the food and the row are both written or neither is

    Scenario: Every log of an ad-hoc food is an estimate
      Given a food in the "Ad hoc" category
      When I log it the ordinary way
      Then that row is marked as an estimate too

    Scenario: An estimate is reusable but never silently redefined
      When I log an estimate under a name a food already holds
      Then the write is refused
      And the message says to log it the ordinary way instead
      # A food's energy is what every log of it derives its calories from, so
      # quietly moving it would rewrite meals already recorded.

    Scenario: The row says so itself
      Then the ledger marks an estimated row
      And an ordinary row carries no mark at all

    Scenario: The mark records how the row was written and is not editable
      Then it is not a column I can type into
      # Like the meal set column: both record what wrote the row rather than a
      # value to retype.

    Scenario: The day says how much of it was guessed
      Given a day with an estimate in it
      Then a line under the bars reports the estimated calories, the day's total and the share
      And it names how many rows carry no macros

    Scenario: A day with nothing estimated says nothing
      Then no such line is shown
      # A line reading "0% estimated" every day is how a cue stops being read.

    Scenario: An estimate still counts towards the day
      Then its calories are in the day's total and in the calorie bar
      # It was eaten. What is missing is the macros, not the meal.

    Scenario: The estimated rows can be filtered for
      When I filter the ledger on the estimate column
      Then only the estimated rows are shown

  Rule: The day is scored against the member's own goal

    Scenario: Today's totals are shown as progress bars
      Then I see bars for today's energy, protein and salt
      And each bar marks my target
      And each bar animates towards its new value rather than jumping

    Scenario: Energy is counted net of what I burned
      Given I logged training or mobility work today
      Then the energy bar subtracts the estimated burn from my intake
      And it shows intake, the deduction and the target together

    Scenario Outline: The target follows my declared goal
      Given my goal is "<goal>"
      And my profile sets a daily adjustment
      Then my energy target is my maintenance need <direction>

      Examples:
        | goal            | direction                     |
        | lose_weight     | reduced by that adjustment    |
        | gain_weight     | increased by that adjustment  |
        | maintain_weight | left unchanged                |

    Scenario: The adjustment's sign is taken from the goal, not from the number
      Given my goal is "lose_weight"
      And my daily adjustment is written as a positive number
      Then the target is still below maintenance

    Scenario Outline: Bar colour reads differently for each goal
      Given my goal is "<goal>"
      When my net energy is <position> my target
      Then the energy bar reads as <reading>

      Examples: losing weight tolerates a deficit
        | goal        | position               | reading |
        | lose_weight | below                  | on plan |
        | lose_weight | far above              | warning |

      Examples: gaining weight treats a deficit as a miss
        | goal        | position               | reading |
        | gain_weight | far below              | short   |
        | gain_weight | within a small band of | on plan |
        | gain_weight | far above              | warning |

    Scenario Outline: Ceiling metrics warn only upwards
      When today's <metric> exceeds my configured limit
      Then its bar warns
      And staying under the limit always reads as on plan

      Examples:
        | metric |
        | salt   |

    Scenario: Protein is a floor, not a ceiling
      When today's protein reaches my target
      Then its bar reads as satisfied
      And exceeding the target is not treated as a problem

    Scenario: A generated profile declares a goal
      Given a member whose profile was generated for them on first run
      Then it declares maintaining weight, written out rather than implied
      And changing it to a loss or gain target is editing a value, not adding a key

  Rule: Drinks are logged with a time of day, because caffeine decays

    Scenario: A beverage log row records when it was drunk
      When I log a beverage
      Then the row stores the date, the clock time, the item and the servings

    Scenario: Caffeine and antioxidants scale with servings
      Then each is the catalog value per serving times the servings logged

    Scenario: The log estimates when the dose stops mattering for sleep
      Given a drink whose caffeine is above the sleep-safe threshold
      Then the row shows how many hours must pass before it decays to that threshold
      And the estimate follows the caffeine half-life

    Scenario: A dose already below the threshold needs no wait
      Given a drink whose caffeine is at or below the sleep-safe threshold
      Then the row shows no waiting time

  Scenario: The waiting-time column honours personal caffeine settings
    Given I changed my caffeine half-life or sleep-safe threshold in my profile
    Then the caffeine graph honours my values
    And the waiting-time column in the beverage log honours the same values
