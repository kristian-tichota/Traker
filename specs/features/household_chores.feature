@exact @shared @core
Feature: Household chores
  Recurring work around the flat, listed on the break that is when it gets
  done, and ticked off from there.

  A chore repeats on a cadence: one known occurrence (its anchor) and the days
  between them. What the member does is near that day rather than on it, so
  the rule that matters is what an early or a late completion does to the next
  one — and the answer is that **the cadence never drifts**. Doing it late does
  not buy a fresh full period; doing it well early does not clear the occasion
  at all, because the days will pass regardless and hygiene is the point.

  A chore is the household's, not a member's: both see the same board, and
  either one clears it.

  Background:
    Given the household service is running
    And both members are authenticated

  @exact
  Rule: A completion clears every occurrence up to the last one within grace

    The whole scheduling rule, in one sentence. Everything below follows from
    it rather than from a case in a list.

    Background:
      Given a chore "Vacuum" every 7 days anchored on Friday 11.09.2026
      And it allows 2 days of grace

    Scenario: A chore nobody has done yet is due on its anchor
      When no completion has been recorded
      Then it is next due on 11.09.2026

    Scenario: Done a day early, the weekday holds
      When it is done on Thursday 10.09.2026
      Then it is next due on Friday 18.09.2026

    Scenario: Done a day late, the weekday still holds
      The next one is not "a week from Saturday" — the schedule is the
      schedule, and the member said so by giving it one.

      When it is done on Saturday 12.09.2026
      Then it is next due on Friday 18.09.2026

    Scenario: Done two days late, the next one comes sooner in real days
      Which is the point: the gap between two doings stays bounded, so a late
      week does not become a long one.

      When it is done on Sunday 13.09.2026
      Then it is next due on Friday 18.09.2026
      And that is 5 days after it was done, not 7

    Scenario: Done four days early, it is still due on its day
      Four days of use will have passed by Friday, so Monday's effort has not
      answered Friday's occasion.

      When it is done on Monday 07.09.2026
      Then it is next due on 11.09.2026

    Scenario: Weeks late, what was missed is dropped rather than stacked
      When it is done on Wednesday 30.09.2026
      Then it is next due on Friday 09.10.2026
      And it is due once, not four times

    Scenario: A chore is never asked for again the next day
      Which follows from the rule rather than being checked for: the next due
      date is always later than the completion plus its grace.

      When it is done on any day
      Then it is next due more than "grace" days after that

  @exact
  Rule: A cadence in whole weeks lands on the same day for ever

    Not a tendency a late completion could spoil. Every occurrence is the
    anchor plus a multiple of the period and a completion never moves the
    anchor, so a period that is a multiple of seven keeps the anchor's weekday
    permanently. Anything else walks through all seven — which is why a
    monthly chore that must stay on a Friday is 28 days, not 30.

    Scenario Outline: What a cadence keeps
      Given a chore every <period> days anchored on a Friday
      Then it lands on <day>, whenever it is done

      Examples:
        | period | day    |
        | 7      | Fri    |
        | 14     | Fri    |
        | 28     | Fri    |
        | 364    | Fri    |
        | 3      | drifts |
        | 30     | drifts |
        | 31     | drifts |

    Scenario: Doing it late does not move the day
      Given a chore every 14 days anchored on a Friday
      When it is done on a Sunday, three weeks late
      Then it is next due on a Friday

    Scenario: The board says which day each chore keeps
      Then the Chores tab has a Lands On column
      And it reads the weekday for a cadence in whole weeks
      And it reads "drifts" for one that is not

    Scenario: A cadence may be typed in weeks
      When the member types ":chorenew 4w Descale the kettle"
      Then a chore recurring every 28 days is defined
      And ":chorenew 28 Descale the kettle" defines the same thing

    Scenario: Defining one says which day it will keep
      The member's one moment to notice before it walks off the day.

      When the member types ":chorenew 2w 11.09.2026 Vacuum"
      Then the confirmation says it is always a Fri

    Scenario: Defining one that drifts says so
      When the member types ":chorenew 30 11.09.2026 Descale"
      Then the confirmation says the day drifts

    Scenario: A chore due more often than weekly says nothing about a weekday
      It never had one, and "the day drifts" there is noise.

      When the member types ":chorenew 3 Water the plants"
      Then the confirmation mentions no weekday

    Scenario: A cadence of less than a day is refused
      When the member types ":chorenew 0w Vacuum"
      Then the refusal says a cadence is at least one day

  Rule: Grace is derived from the cadence unless the member pins it

    Two days is generous on a daily chore and mean on a monthly one.

    Scenario Outline: What a cadence implies
      Given a chore every <period> days with no grace declared
      Then it allows <grace> days of grace

      Examples:
        | period | grace |
        | 1      | 0     |
        | 3      | 1     |
        | 7      | 2     |
        | 14     | 4     |
        | 30     | 7     |
        | 90     | 7     |

    Scenario: A weekly default separates the two cases the member described
      Given a chore every 7 days with no grace declared
      Then doing it one day early clears the occasion
      And doing it four days early does not

    Scenario: A declared zero means only on the day
      Given a chore every 7 days allowing 0 days of grace
      When it is done one day early
      Then it is still due on its day

    Scenario: The board shows the grace a chore actually allows
      A member should not need to know the rule to read what it permits.

      Given a chore every 7 days with no grace declared
      Then the Chores tab shows 2 days of grace for it

  Rule: The board says where every chore stands today

    Scenario Outline: Standings
      Given a chore next due <when>
      Then it stands as <standing>

      Examples:
        | when                     | standing |
        | three days ago           | OVERDUE  |
        | today                    | TODAY    |
        | inside its grace window  | OK NOW   |
        | after its grace window   |          |

    Scenario: The worst one is first
      Given chores overdue, due today, and doable early
      Then the board lists them in that order
      And two equally late chores keep a stable order between refreshes

    Scenario: A paused chore is off the board entirely
      Given a chore that is not active
      Then it is neither listed nor offered
      And its definition and history are kept

  @shared
  Rule: One board, either member

    Scenario: Both members see the same chores
      When one member defines "Take out the bins"
      Then the other member's board lists it

    Scenario: Either member clears it
      Given a chore "Take out the bins" due today
      When one member ticks it off
      Then the other member is no longer asked for it

    Scenario: The history says who did it
      When a member ticks a chore off
      Then the shared history records their name against that date

    Scenario: Deleting a chore takes its history with it
      A completion carries a date and a reference and nothing else, so an
      orphan is a row that could never be read again.

      Given a chore with completions recorded against it
      When the chore is deleted
      Then its completions are gone too

  @accessibility @core
  Rule: A break lists what is due, and takes the tick

    A strict break is when the chores get done. A break that lists them and
    cannot record one is a break the member works around.

    Scenario: A covered screen lists what is due
      Given a strict break has taken the screens
      Then every covered screen lists what is overdue, due today or doable early
      And each says how late or early it is
      And each carries the letter that ticks it

    Scenario: What is weeks away is left off
      Given a chore next due in three weeks
      When a strict break begins
      Then that chore is not listed

    Scenario: A day with nothing due shows no panel at all
      Congratulating the member every break is how a panel stops being read.

      Given nothing is due, overdue, or doable early
      When a strict break begins
      Then the break surface says nothing about chores

    Scenario: A letter ticks the chore beside it
      Given a strict break listing "Vacuum" against the letter "a"
      When the member presses "a"
      Then "Vacuum" is recorded as done today

    Scenario: Clicking the line ticks it too
      Given a strict break listing "Vacuum"
      When the member clicks that line
      Then "Vacuum" is recorded as done today

    Scenario: The row is struck through on the keystroke
      A covered screen cannot answer inside the time a member takes to decide
      they were not heard.

      When the member ticks a chore
      Then that row is struck through at once, before the store has answered
      And every covered screen strikes the same row through

    Scenario: A second press within a day records one completion
      When the member ticks the same chore twice
      Then the store holds one completion for that day

    Scenario: A refused tick says so and does not claim the chore is done
      Given the household service refuses the write
      When the member ticks a chore
      Then the status line says it was not recorded
      And the row is no longer struck through

    Scenario: The letters and the activity keys never collide
      A day with four chores on it must not move the key that opens the video
      queued this morning.

      Given a strict break offering both activities and chores
      Then Enter and 1-9 open activities only
      And a-z tick chores only
      And a key with nothing behind it is left alone

    Scenario: A letter typed into a field is left alone
      The command bar stays reachable behind the wall.

      Given the member is typing into the command bar during a break
      When they type a letter
      Then no chore is ticked

    Scenario: What is due is read once per break, never per frame
      The countdown redraws on every engine tick.

      When a strict break begins
      Then the board is read once
      And redrawing the countdown reads nothing

    Scenario: A chore ticked behind the wall leaves the panel
      When the member runs ":chore Vacuum" in the command bar during a break
      Then the panel in front of them stops offering it

    Scenario: A re-read never blanks the panel it is replacing
      When the board is read again during a break
      Then what is on screen stays until the answer arrives

    Scenario: A read that did not arrive shows nothing
      Given the household service is unreachable
      When a strict break begins
      Then the break surface lists no chores rather than yesterday's

    Scenario: Chores on a break are optional
      Given the profile sets "[chores] on_break = false"
      When a strict break begins
      Then the break surface says nothing about chores
      And the Chores tab is unaffected

  Rule: Chores are defined and corrected in the GUI

    Scenario: The tab is the definition
      Then the Chores tab lists every chore with its cadence, grace, anchor, last completion, next due date and standing

    Scenario: What may be typed into
      Then the name, the cadence, the grace, the anchor, the notes and whether it is active may be edited in place
      And nothing derived may be

    Scenario: Dates read and are typed in Czech
      Then the anchor, the last completion and the next due date are shown as DD.MM.YYYY
      And an anchor typed as DD.MM.YYYY reaches the store as ISO

    Scenario: A sort on a date column is chronological
      The dates are held as ISO and rendered as Czech, so the sort reads the
      value rather than the text: "01.10.2026" sorts before "11.09.2026".

      When the member sorts by Next Due
      Then the chores are in date order

    Scenario: A completion may be corrected, but not re-pointed
      Moving a completion to another chore is two edits pretending to be one.

      Then the date of a completion may be edited
      And the chore it belongs to may not

    Scenario: One due date, two surfaces
      The Chores tab and the break panel show the same figure, so one
      function computes it.

      Then the next due date on the tab equals the one on the break panel, for every chore

  Rule: The command line reaches both

    Scenario: Ticking one off
      When the member types ":chore Vacuum"
      Then "Vacuum" is recorded as done today
      And ":done Vacuum" does the same

    Scenario: The name is completed from the household's chores
      When the member types ":chore " and presses Tab
      Then the chore names are offered

    Scenario: Defining one
      When the member types ":chorenew 7 Vacuum the flat"
      Then a chore recurring every 7 days from today is defined
      And the confirmation names the grace it will allow
      And "2w" in place of "7" would have meant 14 days

    Scenario: Naming its first occurrence and its grace
      When the member types ":chorenew 7 11.09.2026 1 Vacuum"
      Then the chore is anchored on 11.09.2026 with one day of grace

    Scenario: Ticking a chore nobody defined is refused by name
      When the member types ":chore Hoover"
      Then the refusal names "Hoover"

  Rule: The store has the last word

    Scenario: A cadence of less than a day is refused
      When a chore is defined with a period of 0 days
      Then the write is refused

    Scenario: An anchor that is not a date is refused
      An unreadable anchor is not a chore due on the wrong day — it is one
      that is never due at all, and says nothing about why.

      When a chore is defined with an anchor of "Friday"
      Then the write is refused

    Scenario: Text in the cadence is refused rather than stored
      SQLite would keep "7d" in an INTEGER column.

      When a chore is defined with a period of "7d"
      Then the write is refused

    Scenario: A name is one identity however it is capitalised
      Given a chore "Vacuum"
      When a chore "VACUUM" is defined
      Then the write is refused
      And ":chore vacuum" reaches the existing one
