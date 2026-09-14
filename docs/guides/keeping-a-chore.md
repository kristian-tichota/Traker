# Recurring chores, and what an early or late one does

A chore is a **cadence** — one known occurrence and the days between them — plus a **grace**, how far ahead of its day it may be done and still count. One board for the household. Contract: `specs/features/household_chores.feature`.

> **A completion clears every occurrence up to the last one within `grace` days after it. The next due date is the one after that.**

```
due = anchor + (k+1)·period,   k = ⌊(last_done + grace − anchor) / period⌋
due = anchor                   where nothing has been done, or k < 0
```

On a weekly chore anchored to a Friday with two days' grace: never done is that Friday and overdue after it; done Thursday, Saturday or Sunday is the following Friday, not seven days from when it was done; done Monday — four days early — is **that** Friday still; done three weeks late is the Friday after, because what was missed is dropped rather than stacked.

Two properties come free, which is why it is one expression and not a branch per case: `due > last_done + grace`, so nothing is ever asked for again the next day; and dueness is a *date*, so a fortnight away comes back as one overdue chore rather than four.

`grace` defaults to `min(period // 3, 7)`. A declared `0` is a different claim from an unanswered one — it means *only on the day*. The tab shows the effective figure either way.

## Always the same day

**A cadence in whole weeks lands on the same weekday for ever**: every occurrence is `anchor + k·period` and a completion never moves the anchor. Anything else walks through all seven. So **a monthly chore that must stay on a Friday is 28 days, not 30.**

```
:chorenew 2w Vacuum the flat       every other Friday, if today is a Friday
:chorenew 4w Descale the kettle    monthly-ish, and always the same day
:chorenew 3 Water the plants       three days; no weekday to keep, and none claimed
```

`4w` and `28` define the same chore. The confirmation names the day (`— always a Fri`) or warns that it drifts; the **Lands On** column answers the same question per row. Nothing is enforced.

## Where it stands, and a break

`OVERDUE`, `TODAY`, `OK NOW` (inside the grace window), or nothing; a break offers the first three. `src/domain/chores.py:board` is the one ordering — worst first, longest-waiting first within a group, name last so two equally late chores do not swap under the member's hand.

```
:chorenew 7 11.09.2026 1 Vacuum    anchored, one day's grace
:chore Vacuum   (or :done)         ticked off today
:rm Vacuum                         gone, and its history with it
```

`:chorenew` reads numbers-first-name-last like `:log`; the optional date between the two counts is what tells a period from a grace. On a break each due chore carries a **letter**, never a digit — `Enter` and `1`–`9` are the activity offers. A tick strikes through on the keystroke, before the store has answered, and a second press within a day is the one completion it is. `[chores] on_break = false` switches the whole thing off.

Both tables are shared and both register as catalogs, which is what keeps `user_id` out of their `WHERE` clauses. Completions **cascade** where every log→item reference is `ON DELETE SET NULL`: a completion carries only a date and a reference, so an orphan is a row nothing could ever render again.
