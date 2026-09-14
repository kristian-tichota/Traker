Feature: Focus timeline drill-down

  As a user reviewing a bad day
  I want to open one day and see where the time actually went
  So that I can tell a genuinely hard day from a day I mismanaged the timer

  Background:
    Given a day with recorded focus history

  Rule: A day opens into a readable band of the whole 24 hours

    Scenario: Opening a day
      When I interact with a day on the strain calendar
      Then that day opens as a timeline covering the full 24 hours
      And the date is shown in the household's date format

    Scenario Outline: The four states are distinguishable at a glance
      Then <state> is drawn in its own colour, consistently with the rest of the app

      Examples:
        | state          |
        | focus          |
        | focus overtime |
        | rest           |
        | rest overtime  |

    Scenario: Zooming and panning
      When I zoom into part of the day
      Then the visible window narrows around the point of interest
      And the time grid grows denser as the window narrows
      And I can pan without losing the grid labels at the edges

  Rule: Manual interventions are marked on the timeline

    Scenario Outline: Event markers carry meaning
      Then a <event> is marked <appearance>

      Examples:
        | event            | appearance                    |
        | pause            | as a caution marker           |
        | skip             | as a warning marker           |
        | overridden break | as a warning marker, like a skip: both are a debt |
        | long break begun | as a distinct shape: it is the day's one decision |
        | absence          | as an ordinary marker: walking away is not an intervention |

    Scenario: A few events at the same moment stack
      Given up to four events fall on the same point of the timeline
      Then they are drawn stacked so each stays visible and identifiable

    Scenario: Many events at the same moment collapse
      Given more than four events fall on the same point of the timeline
      Then they are replaced by a single marker indicating there are more
      And that marker can be interrogated for the events it hides

  Rule: The timeline stays legible on a compositing desktop

    Scenario: Legend and background
      Then the legend is laid out over two rows rather than one crowded row
      And the popup paints an opaque background so it never renders as a dark rectangle
