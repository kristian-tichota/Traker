@shared @core
Feature: Shared item catalog

  As two people tracking in the same household
  I want one catalog of foods, drinks, exercises, supplements and routines
  So that neither of us re-enters nutrition labels the other already typed

  The catalog is the household's single source of truth and is entered once.
  Logs stay private per member, so one catalog serves opposite targets.

  Background:
    Given both household members use the same catalog
    And each member keeps their own logs

  Rule: Catalog entries describe an item once, per unit

    Scenario Outline: Each domain stores the attributes its logs need
      Given a "<domain>" catalog entry
      Then it records <attributes>

      Examples:
        | domain     | attributes                                                    |
        | food       | macronutrients per 100 g and a serving size                   |
        | beverage   | caffeine and antioxidants per serving                         |
        | exercise   | how the movement is measured, plus kinesiology metadata       |
        | supplement | a dose per serving for each tracked micronutrient             |
        | mobility   | a metabolic intensity and free-text notes                     |

    Scenario: Item names are unique within a domain
      When I define an item whose name already exists in that domain
      Then the definition is rejected
      And the status bar reports the conflict
      And the existing item is left untouched

    Scenario: Implausible values are refused at the boundary
      When I define an item with a negative nutrient or a non-positive serving size
      Then the definition is rejected
      And nothing is written

    Scenario: Logging finds items regardless of capitalisation
      Given the catalog contains "Rolled Oats"
      When I log against "rolled oats"
      Then the log is attached to "Rolled Oats"

    Scenario: Logging against an unknown item is refused
      When I log against a name that is in no catalog
      Then no log is created
      And the message names the item and the catalog it was missing from

  Rule: Catalog edits are visible to both members immediately

    Scenario: A definition reaches the other member's open app
      Given the other member has the app open
      When I define a new catalog item
      Then their app is told the catalog changed
      And the view they are looking at reloads
      And their remaining tabs are marked stale
      And their status bar tells them a sync arrived

    Scenario: Personal logs are not broadcast
      When I record a log entry
      Then the other member's app is not disturbed

  Rule: Deleting an item never destroys history

    Scenario: Removing an item keeps the logs that referenced it
      Given I logged an item several times
      When I remove that item from the catalog
      Then my log rows still exist with their dates and quantities
      And each of them shows no item name
      And their derived nutrient values read as zero

    Scenario: Removal is by name and spans every domain
      When I remove an item by name
      Then any catalog entry with that name is removed from all five domains
      And the removal is broadcast to the other member

    Scenario: A removed name may be defined again
      Given I removed an item from the catalog
      When I define a new item with the same name
      Then the definition succeeds
      And the old orphaned log rows stay orphaned rather than reattaching
