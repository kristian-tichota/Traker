# Chore scheduling

A chore is a cadence, meaning one known occurrence and the number of days between occurrences, plus a grace, meaning how far ahead of its day it may be done and still count. There is one board for the household. Contract: `specs/features/household_chores.feature`.

A completion clears every occurrence up to the last one within `grace` days after it, and the next due date is the one after that.

```
due = anchor + (k+1)·period,   k = ⌊(last_done + grace − anchor) / period⌋
due = anchor                   where nothing has been done, or k < 0
```

On a weekly chore anchored to a Friday with two days of grace: never done is that Friday and overdue after it; done on Thursday, Saturday or Sunday is the following Friday rather than seven days from the completion; done on Monday, four days early, is that same Friday; and done three weeks late is the Friday after, because missed occurrences are dropped rather than accumulated.

Two properties follow from the single expression, which is why it is not a branch per case: `due > last_done + grace`, so nothing is asked for again the next day; and dueness is a date, so a fortnight of absence returns one overdue chore rather than four.

`grace` defaults to `min(period // 3, 7)`. A declared `0` is a different claim from an absent one, because it means only on the day. The tab shows the effective figure in both cases.

## Weekday stability

A cadence in whole weeks lands on the same weekday indefinitely, because every occurrence is `anchor + k·period` and a completion never moves the anchor. Any other period walks through all seven weekdays. A monthly chore that must stay on a Friday is therefore 28 days rather than 30.

```
:chorenew 2w Vacuum the flat       every second Friday, where today is a Friday
:chorenew 4w Descale the kettle    four weeks, and always the same day
:chorenew 3 Water the plants       three days; no weekday is kept, and none is claimed
```

`4w` and `28` define the same chore. The confirmation names the day (`— always a Fri`) or warns that it drifts, and the **Lands On** column answers the same question per row. Nothing is enforced.

## Status and breaks

A chore reads `OVERDUE`, `TODAY`, `OK NOW` (inside the grace window), or nothing, and a break offers the first three. `src/domain/chores.py:board` is the one ordering: worst first, longest-waiting first within a group, and name last, so that two equally late chores do not exchange places under the pointer.

```
:chorenew 7 11.09.2026 1 Vacuum    anchored, one day of grace
:chore Vacuum   (or :done)         ticked off today
:rm Vacuum                         removed, with its history
```

`:chorenew` reads numbers first and name last, as `:log` does, and the optional date between the two counts is what distinguishes a period from a grace. On a break each due chore carries a letter rather than a digit, because `Enter` and `1`-`9` are the activity offers. A tick strikes the entry through on the keystroke, before the store has answered, and a second press within a day is the one completion it is. `[chores] on_break = false` disables the whole feature.

Both tables are shared and both register as catalogs, which keeps `user_id` out of their `WHERE` clauses. Completions cascade, where every other log-to-item reference is `ON DELETE SET NULL`, because a completion carries only a date and a reference, so an orphan would be a row nothing could render.
