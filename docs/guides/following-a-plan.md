# Following a training plan

The Plans tab shows one **cycle**: a named block of weeks holding a planned session per
training day, beside what the exercise ledger actually says.
Contract: `specs/features/training_plans.feature`.

## Getting a plan in

```bash
uv run python scripts/import_training_plan.py cycle.json --help      # the JSON shape
uv run python scripts/import_training_plan.py cycle.json --dry-run   # check it
uv run python scripts/import_training_plan.py cycle.json             # write it
uv run python scripts/import_training_plan.py cycle.json --replace   # overwrite
```

Every movement must already be in the exercise catalog; a cycle is imported whole or not at all.

## Reading the tab

The calendar is a row per week and a column per weekday. Filled is settled, outline is ahead:
green where the ledger holds an exercise, blue for today with nothing logged, orange for a day
that passed empty, a dot for a rest day. The line under it is sessions done out of sessions
*due* — the future is in neither half — and the current streak.

**Any training that day counts as the session happening.** A plan's own rules invite
substitutions, so marking a day missed because one movement was swapped would make the calendar
say something untrue. Which lifts were hit is the table's job.

`hjkl` or the arrows walk the calendar; the table follows without reading again. It shows the
prescription (`Sets`, `From`, `To`, `Load`, `RPE`, `Tempo`) beside the ledger's answer:
**Logged** (`10/10/9 @ 22.5`) and **Result** — `hit` when every set reached the bottom of the
range at no less than the prescribed load, `under` otherwise, blank when nothing was logged.
Type into any prescription column to change the plan; the ledger's two answers are not
editable. Deleting a cycle takes everything except the exercise rows it produced, because a
plan is a template and the ledger is history.

## Logging a session from it

Enter on a planned day fills the bar with `:planlog DD.MM.YYYY` and does **not** run it — a
keystroke on a grid must not silently append eight rows. `:planlog` with no date means today
and works from any tab.

What it writes is the **bottom** of each range — three sets of eight to twelve becomes `8/8/8`
at the prescribed load, the number to beat. Two refusals: a day the cycle does not prescribe,
and a session holding a movement whose catalog item was deleted, which refuses whole.

## Elsewhere

Today's session is named on every screen a strict break covers, read once when the break
begins. Both go through `plans.py:prescribed_day`, so the tab and the wall cannot name
different targets for one day. "The plan" is the cycle today falls inside, otherwise the
newest — `plans.py:current_plan` for both the tab and the command line. No switcher yet.
