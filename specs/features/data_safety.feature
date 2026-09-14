Feature: Data safety

  As the household's only administrator
  I want the data to be hard to lose and hard to corrupt
  So that years of logs survive my own mistakes

  Rule: The database is snapshotted on every launch

    Scenario: Launching the app
      When the app starts
      Then a timestamped snapshot of the live database is taken before the UI opens
      And the snapshot is a consistent copy, not a file copy of a database in use

    Scenario: Snapshots are rotated
      Given the snapshot directory holds the maximum number of snapshots
      When another is taken
      Then the oldest is removed
      And the removal is reported

    Scenario: Nothing to snapshot
      Given no database file exists yet
      Then the app reports it and starts anyway

  Rule: The store rejects impossible data rather than storing it

    Scenario: Constraints live with the data
      Then positive quantities, in-range ratings and fixed state sets are enforced by the store itself
      And a rejected write is reported to the user with the reason

    Scenario: A value of the wrong kind is refused, not stored
      Given a column that holds a number
      When I edit a cell to something that is not one
      Then the edit is refused and names the column
      And the value already stored is left as it was

    Scenario: Both write paths refuse the same values
      Given a column that holds a number
      Then defining a new item refuses text for it, exactly as editing one does
      And neither path accepts a number that is not finite

    Scenario: A request the store never saw is refused with the reason
      When a write arrives without a field it needs, or as something other than an object
      Then it is refused before it reaches the store
      And the reply names what was missing
      And the reply is machine-readable, because the app parses it

    Scenario: A value of the right kind keeps its kind
      Given a column that holds text
      When I edit a cell to something that reads as a number
      Then it is stored as the text I typed

    Scenario: Referential integrity is enforced
      Then a log row can only reference an item that exists
      And referencing a missing item is refused at the point of logging

    Scenario: Concurrent access by two members
      Then the store is configured so that one member reading does not block the other writing

  Rule: Deletion is never silent data loss

    Scenario: Deleting a catalog item
      When a catalog item is deleted
      Then log rows that referenced it survive with their reference cleared

    Scenario: Deleting a log row
      When I delete one of my log rows from its table
      Then only that row is removed
      And the catalog item it referenced is untouched

  Rule: A write that changed nothing is never reported as success

    Scenario: Removing a name no catalog holds
      When I remove an item name that does not exist
      Then the removal is refused and names what was not found
      And no catalog change is announced to the other member

    Scenario: Editing or deleting a row that is not there
      When I edit or delete a row id that does not exist
      Then it is refused rather than confirmed

    Scenario: A refused edit does not leave the rejected value on screen
      Given I typed a value the store refused
      Then the table is refreshed so the cell shows what is actually stored

  Rule: Shutdown is orderly

    Scenario: Closing the app
      When I close the application
      Then the live-update listener is stopped
      And timers and animations are stopped
      And in-flight background reads and writes are given a moment to complete
      And the tray icon is removed
