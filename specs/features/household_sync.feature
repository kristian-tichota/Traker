@shared @core
Feature: Two members, one server

  As a two-person household
  I want a small always-on service holding our shared catalog and separate logs
  So that we both track against the same data without seeing each other's diary

  The desktop app keeps no local database. It talks to a service on the home
  network that owns the data, identifies each member by their own access token,
  and pushes catalog changes to whoever is watching.

  Background:
    Given the household service is running
    And each member has their own access token

  Rule: A member sees the shared catalog and only their own records

    Scenario: Reading logs
      When I ask for my logs
      Then I receive only rows recorded under my own identity

    Scenario: Reading the catalog
      When I ask for a catalog domain
      Then I receive every entry, whoever defined it

    Scenario Outline: Personal data stays personal
      Then my <data> is scoped to me alone

      Examples:
        | data                           |
        | food, drink and training logs  |
        | focus timer history            |
        | daily stress overrides         |
        | view preferences and settings  |

    Scenario: Editing or deleting someone else's log entry is impossible
      When I try to change a log row that belongs to the other member
      Then nothing changes
      And it is refused rather than confirmed, so I am not told it worked

  Rule: Every request is authenticated

    Scenario: A request without a token
      When a request arrives carrying no token
      Then it is refused as unauthenticated

    Scenario: A request with an unrecognised token
      When a request arrives with a token that matches no member
      Then it is refused as unauthorised

    Scenario: Only known fields may be written
      When a request tries to write a column that is not on the permitted list
      Then it is refused
      And the response names the offending field

  Rule: The app degrades quietly when the service is unreachable

    Scenario: Reads while the service is down
      Given the household service is not running
      When a view refreshes
      Then it shows empty data instead of crashing
      And the failure is reported once, not as a dialog per row

    Scenario: An empty table says which kind of empty it is
      Given the household service is not running
      When a view refreshes
      Then the status line says the service is unreachable
      And it says the table may be empty for that reason rather than because nothing is logged

    Scenario: The service coming back is announced
      Given the status line reported the service unreachable
      When a read succeeds again
      Then the status line says it is reachable again
      And neither transition is announced more than once
      And the completion catalogs are read again

    Scenario: Being told no is not being offline
      Given the household service is running
      When it refuses a read
      Then the status line does not report it unreachable
      And a refused read and a refused write agree about that

    Scenario: Writes while the service is down
      Given the household service is not running
      When I submit a command
      Then the status bar reports the failure
      And my typed command is left in the bar

    Scenario: Live updates resume by themselves
      Given the app lost its connection to the update stream
      When the service becomes reachable again
      Then the app reconnects without being restarted
      And catalog changes start arriving again

    Scenario: The update stream survives an idle connection
      Given nothing has changed for a long while
      Then the stream is kept alive
      And the app does not treat the silence as a disconnection

  Rule: The service is told who its members are

    Scenario: Nothing about a household is built into the app
      Then no member name, token or service address is carried in the source

    Scenario: Starting with no members named
      When the service starts
      Then it refuses to start
      And it leaves a commented settings file saying what to add

    Scenario: A member named without a token
      When the service starts
      Then it mints one, records it beside that member, and says it once
      And a later start reuses that token rather than minting another

    Scenario Outline: Where a service setting comes from
      Given <source> supplies the address to listen on, or where the store lives
      Then the service uses it
      And ignores any source later in this order

      Examples:
        | source                            |
        | the process environment           |
        | the household settings file       |
        | the built-in default              |

    Scenario: An address given for one run stays given for one run
      Given the environment overrode a setting the settings file also carries
      When the service writes that file
      Then the file keeps its own value

    Scenario: Listening beyond this machine is asked for, never assumed
      Then the built-in default reaches only the machine the service runs on

  Rule: Where the app looks for its credentials

    Scenario Outline: Resolution order
      Given <source> supplies a service address and token
      Then the app uses them
      And ignores any source later in this order

      Examples:
        | source                            |
        | the process environment           |
        | the member's profile file         |
        | the built-in local address        |

    Scenario: A fresh install carries no token
      Given nobody has pasted a token into the profile yet
      Then the app knows an address but sends no token
      And the service answers as it does to any unauthenticated caller

    Scenario: The live-update stream uses the same address and token
      Given the app resolved a service address other than the local default
      Then it subscribes to the update stream at that address
      And it does not listen to the built-in default instead
