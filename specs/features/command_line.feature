@accessibility @core
Feature: Command line logging

  As a user who wants to log a meal in one line
  I want a command bar that completes item names for me
  So that I type a few characters instead of filling in a form

  The command bar is the primary way data enters the app. It is optimised for the
  fewest possible keystrokes: the visible tab pre-fills the command you most
  likely want, hints show the remaining arguments as you type, and item names
  complete from the shared catalog.

  Background:
    Given the application is open
    And COMMAND mode is active

  Rule: Commands are either "log" commands or "define" commands

    Scenario Outline: Logging reads as quantity first, name last
      When I submit "<command>"
      Then a <record> is recorded against today
      And the visible tab reflects the new record

      Examples:
        | command                        | record             |
        | log 1.5 Breakfast Rolled Oats  | food log           |
        | bevlog 1 08:30 Black Coffee    | beverage log       |
        | exlog 7,7,7 30 8 Overhead Press| exercise log       |
        | supplog 1 Morning Stack        | supplement log     |
        | moblog 20 Hip Opener           | mobility log       |

    Scenario: An item name may contain spaces
      When I submit a log command whose trailing name has several words
      Then the whole trailing remainder is treated as the item name
      And that holds whether or not the optional arguments before it were given

    Scenario Outline: Meal types have single-letter shortcuts
      When I submit "log 1 <shortcut> Rolled Oats"
      Then the food log records the meal type "<meal>"

      Examples:
        | shortcut | meal       |
        | b        | Breakfast  |
        | l        | Lunch      |
        | d        | Dinner     |
        | s        | Supplement |

    Scenario: Defining a catalog item uses semicolon-separated fields
      When I submit a define command with its fields separated by ";"
      Then a new catalog item is created for every household member
      And the fields are read positionally in the documented order

    Scenario Outline: Definitions are rejected when the field count is wrong
      When I submit "<command>" with too few or too many fields
      Then no item is created
      And the status bar explains the expected syntax, field by field

      Examples:
        | command    |
        | define     |
        | bevdefine  |
        | exdefine   |
        | suppdefine |
        | mobdefine  |

  Rule: A command may be carried out by the window instead of by a write

    Scenario: A command whose subject is the tab in front of me
      When I submit ":cols hide Sugars"
      Then the visible tab's table loses that column
      And nothing is written to the household's data
      # What ":cols" names is a column of *this* table, which only the window
      # can resolve — so the window carries it out and the view stores the
      # preference. See column_layout.feature.

    Scenario: A command whose subject is this machine
      When I submit ":rest ~/Videos/talk.mkv" or ":break long"
      Then the queue file on this machine is written, or the next break changes
      And nothing is written to the household's data
      # A path on this machine and a break not yet begun. The other member's
      # client could use neither, so neither is theirs to hear about.

    Scenario: Naming nothing reads the state back
      When I submit ":cols", ":rest" or ":break" with no argument
      Then the status bar reports what it would otherwise have changed
      # The cheapest thing to type is the commonest thing meant, and with
      # nothing to change there is nothing left to mean but a readout.

    Scenario: It reports through the same line as every other command
      When such a command is refused
      Then the status bar shows the reason and what I typed stays in the bar

  Rule: An argument a member would always type the same way may be left out

    The arguments omitted are the ones that would otherwise be retyped every
    single time: one serving, and the time it is now. This is the tendinosis
    constraint applied to the grammar rather than to the keys.

    Two things keep it unambiguous rather than positional guesswork: each
    optional argument declares what it means when absent, and what a value for
    it could look like. A serving count and a clock time cannot be mistaken for
    each other, so the arguments are read left to right and each steps aside for
    a token it could not be.

    @accessibility
    Scenario Outline: One drink log, four ways of typing it
      When I submit "<command>"
      Then the beverage log records <servings> and <time>

      Examples:
        | command                     | servings | time      |
        | bevlog 2 14:30 Black Coffee | 2        | 14:30     |
        | bevlog 2 Black Coffee       | 2        | right now |
        | bevlog 14:30 Black Coffee   | 1        | 14:30     |
        | bevlog Black Coffee         | 1        | right now |

    @accessibility
    Scenario: An amount left out of a food log means one serving
      When I submit "log b Rolled Oats"
      Then one serving of it is logged against breakfast

    Scenario: A stack is logged by name alone
      When I submit "supplog Morning"
      Then one of that stack is logged

    Scenario: A time is defaulted to now rather than to a fixed hour
      Then the clock is read at the moment the command is submitted
      # The caffeine forecast is built on when a drink was actually drunk, so a
      # wrong-but-plausible default would be worse than none.

    Scenario: A value of the wrong shape is reported rather than shifted along
      When I submit "log x b Rolled Oats"
      Then the amount is reported as unreadable
      And nothing is sent to the service
      # If the argument after it took whatever was in front of it, a typo would
      # become the meal type and the meal type would become part of the name.

    Scenario: A malformed value of the right shape is still taken and refused
      When I submit "bevlog 25:99 Black Coffee"
      Then it is refused as a bad time
      # It has the shape of a time, so the time argument takes it rather than
      # stepping aside and leaving "25:99 Black Coffee" to be looked up.

  Rule: The bar tells the user what to type next

    Scenario: Completing a command name
      When I have typed a prefix of a known command
      Then the rest of the command name is offered as a hint
      And the hint continues with that command's argument list

    Scenario: Advertising the next argument
      Given I have typed a command and some of its arguments
      Then the hint shows only the arguments I have not supplied yet
      And an argument whose label reads as several words is shown whole

    Scenario: An argument that may be left out is still advertised
      When I have typed a command and nothing else
      Then the hint lists its optional arguments along with the rest
      # The whole of what they save is knowing that they are there.

    Scenario: An argument passed over is no longer advertised
      Given I typed a value that only a later argument could be
      Then the one it stepped past is not offered again

    Scenario: The bare prompt for a name waits until the name is all that is left
      Then a command with optional arguments still available shows its argument list

    Scenario: The visible tab pre-fills its own command
      Given a tab with an obvious logging command
      When I enter COMMAND mode from that tab
      Then the command bar already contains that command and a trailing space
      And the caret sits at the end with nothing selected

    Scenario: Switching tabs replaces an untouched pre-filled command
      Given the command bar holds only a pre-filled command
      When I switch to a tab with a different command
      Then the pre-filled command is replaced rather than appended to

    Scenario: A half-typed command survives losing focus
      Given I have typed a partial command
      When focus leaves the command bar without Escape or Enter
      Then the text is preserved
      And COMMAND mode is still active

    Scenario: Tab is the completion key and nothing else
      When I press Tab in the command bar
      Then the command bar keeps keyboard focus
      And it keeps it whether or not a suggestion was showing

  Rule: The bar lists what could be typed here, before anything is typed

    A hint is a *continuation* of what has been typed, so it can only describe
    the command already being typed. A member who does not know a command
    exists has no way to be told that it does — which is how a household kept a
    supplement stack in its head rather than in the catalog. So the bar is
    headed by a menu of what is possible, and the visible tab decides what
    comes first.

    @accessibility
    Scenario: Entering COMMAND mode says what can be typed
      When I enter COMMAND mode
      Then the commands are listed above the bar
      And each is shown with the arguments it takes

    Scenario: The visible tab's own commands come first
      Given I am on a tab that logs one subject
      Then that subject's commands head the list
      And they are marked as belonging to it
      And the rest follow in the order they are declared

    Scenario: A tab reading more than it is about is listed by what it is about
      Given the Food tab, which also reads exercise and mobility for the burn
      Then only the food commands head its list
      # What a tab reads and what it is about are different questions. Offering
      # ":exlog" as a food command is an answer to the wrong one.

    Scenario: A tab with no logging command of its own
      Given a chart tab or the focus timer
      Then the list is headed by the commands for what that tab shows

    Scenario: Typing narrows the list
      When I type a fragment of a command name
      Then only the commands it could become are listed
      And the same match quality that ranks item names ranks these

    Scenario: What was typed decides first, and the tab settles the draws
      Given several commands match what I typed equally well
      Then the visible tab's own come first among them
      And a better match outranks the visible tab

    Scenario: A fragment that is not a command's opening still finds it
      When I type letters that appear in a command name in order
      Then that command is offered
      And Tab writes the whole name rather than appending to what I typed

    Scenario: Moving through the candidates
      When I press Ctrl-N or Ctrl-P
      Then the selection moves to the next or previous candidate and wraps
      And Tab writes the one that is selected
      And the next keystroke returns the selection to the best match

    Scenario: A list too long for the menu
      Then at most seven candidates are shown
      And the line beneath says how many did not fit
      And the selection scrolls the list rather than stopping at the last row

    Scenario: A word that matches no command
      Then the menu says so rather than listing every command

    Scenario: The menu belongs to COMMAND mode
      When I leave COMMAND mode
      Then the menu is not shown
      And the table gets its space back

  Rule: Once the command is known, the menu describes what it takes

    Scenario: Each argument is listed with what it expects
      When I have typed a command and a space
      Then each of its arguments is listed
      And each says what sort of value it expects
      And the argument the bar is waiting for is marked

    Scenario: An argument that may be left out says so
      Then it is listed like the rest and marked as omittable
      # A member who does not know it can be left out types it every time.

    Scenario: A definition's separator is shown alongside its fields
      Given a command whose fields are separated by ";"
      Then the heading line shows the fields separated the way they are typed

    @accessibility
    Scenario: Defining a set is readable off the menu
      Given I am on a domain's tab and have typed its set command
      Then the menu names the set command and its two fields
      And the components field says which unit its amounts are in
      And it shows an example component of that domain
      # Which is the whole of what a member needs to define one: nothing else
      # on screen has ever said that a stack's amounts are servings and a
      # recipe's are grams.

    Scenario: A definition with more fields than the menu can show
      Given a command with eleven fields
      Then the fields around the one being typed are shown
      And the heading line stays visible

    Scenario: A word that is finished but is not a command
      When I type an unknown word and a space
      Then the menu lists the commands that word could have been
      # By the time the status bar says "unknown command" the whole line has
      # been typed.

  Rule: The bar checks what it can before the service does

    Scenario: A time that is not a time
      When I give a beverage log a time that is not a 24-hour HH:MM
      Then the command is refused and says what a time looks like

    Scenario: A quantity that is not a finite number
      When I give a numeric field a value like "1e400"
      Then the command is refused rather than stored as an infinity

    Scenario: A field with a closed set of values
      When I give a definition a value outside that set
      Then the command is refused and lists what is allowed

  Rule: Completion never reads the catalog on the interface thread

    The bar exists to save keystrokes, and the catalog lives on the service —
    so re-reading it on every character turned each keystroke into a network
    round trip the interface waited for. The catalogs are read once, up front
    and off that thread, and typing costs nothing at all.

    Scenario: Typing an item name
      When I type an item name a character at a time
      Then no keystroke reads a catalog from the service

    Scenario: A suggestion that is not ready yet
      Given the catalog names have not arrived
      When I type an item name fragment
      Then the bar offers nothing rather than claiming there is no match
      And the suggestion appears as soon as the names land

    Scenario: A catalog that changed
      Given either member defined or removed an item
      Then the next completion reads the catalog again

    Scenario: A catalog read that failed is not remembered as an empty catalog
      Given the household service was down when the names were read
      Then nothing is cached for that catalog
      And the names are read again when the service is reachable

  Rule: Item names complete from the shared catalog by fuzzy match

    Scenario Outline: Match quality decides the suggestion
      Given the catalog contains "Rolled Oats"
      When I type "<typed>" where an item name is expected
      Then "Rolled Oats" is suggested because it matched by <kind>

      Examples:
        | typed | kind        |
        | rol   | prefix      |
        | oats  | substring   |
        | rlo   | subsequence |

    Scenario: Prefix matches win over weaker matches
      Given several catalog items match what I typed
      Then a prefix match is preferred over a substring match
      And a substring match is preferred over a subsequence match
      And the shortest name wins among equally good matches

    Scenario: Accents and letter case are ignored
      Given the catalog contains an item whose name carries diacritics
      When I type the same letters without diacritics or capitals
      Then the item is still suggested

    Scenario: Accepting a suggestion
      When I press Tab with a suggestion showing
      Then the item name is completed in place
      And arguments I already typed before the name are left untouched
      And what is left in the bar is a name the catalog can resolve

    Scenario: A completion never leaves a spelling the catalog cannot resolve
      Given the catalog contains an item whose name carries diacritics
      When I type its opening letters without the diacritics and press Tab
      Then the catalog's own spelling replaces what I typed
      And the accents I skipped are restored rather than left out

    Scenario: Letter case is the one difference a completion may leave behind
      Given I typed an item's opening letters in the wrong case
      When I press Tab
      Then only the missing tail is appended
      And the item still resolves, because the catalog ignores letter case

    Scenario: Nothing matches
      When I type an item name fragment that matches no catalog item
      Then the hint says so
      And Tab changes nothing

  Rule: Outcomes are reported without a modal dialog

    Scenario: A command succeeds
      When a command completes
      Then the command bar clears and returns me to NORMAL mode
      And every tab is marked stale so it reloads when next shown
      And the status bar pulses to acknowledge the write
      And the status bar names what was written, not the mode I returned to

    Scenario: A command fails
      When a command is rejected, by bad syntax or by the server
      Then the status bar shows the reason and pulses a warning
      And the command text stays in the bar so I can correct it
      And no partial record is created

    Scenario: The bar does not wait for the service
      When I submit a command
      Then the write is made without blocking the interface
      And the window stays responsive while the service answers

    Scenario: Enter pressed twice before the first write answers
      Given a command is still being written
      When I submit it again
      Then it is written once
      And the bar accepts a new command once the first has landed

    Scenario Outline: A refusal is reported whichever command was refused
      Given the service refuses the write
      When I submit a "<command>" command
      Then the status bar shows the service's own reason

      Examples: logging
        | command |
        | log     |
        | bevlog  |
        | exlog   |
        | supplog |
        | moblog  |

      Examples: defining
        | command    |
        | define     |
        | bevdefine  |
        | exdefine   |
        | suppdefine |
        | mobdefine  |

      Examples: catalog and view commands
        | command     |
        | rm          |
        | track       |
        | graphlayout |
        | setdsi      |

    Scenario: An unknown command
      When I submit a word that is not a command
      Then the status bar reports the unknown command
