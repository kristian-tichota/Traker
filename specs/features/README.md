# Traker feature specifications

Behaviour in Gherkin, one file per feature. They describe **what the app must do**; implementation constraints live under `docs/`. There is no runner — treat a scenario as the contract, and change it in the same commit as the behaviour. `uv run pytest tests/unit/test_specs_parse.py` checks every file parses and is named below.

One household, two members. They share a single catalog of foods, drinks, exercises, supplements and mobility routines — a nutrition label is entered once, by whoever has the packet — while logs, targets, timer history and view preferences stay separate. That is what lets one member track a deficit and the other a surplus against the same food database.

One member has chronic finger tendinosis. This is the reason for the modal keyboard interface, the one-line command bar, the fuzzy completion and the focus timer; accessibility is the premise, not a layer. Assistive input arrives as ordinary key and pointer events, so keyboard reachability is the whole accessibility story.

## Reading order

**The interface** — `keyboard_modality.feature`, `command_line.feature`, `data_filtering.feature`, `column_layout.feature`.
**Two members, one service** — `shared_catalog.feature`, `household_sync.feature`.
**What gets logged** — `nutrition_logging.feature`, `item_sets.feature`, `training_logging.feature`, `training_plans.feature`, `supplement_logging.feature`.
**The day, and what it adds up to** — `pomodoro_timer.feature`, `household_chores.feature`, `daily_stress_index.feature`, `focus_timeline.feature`, `caffeine_forecast.feature`, `progress_graphs.feature`.
**Configuration and safety** — `user_profile.feature`, `data_safety.feature`.

## Tags

- `@exact` — the numbers and state routing *are* the specification; do not paraphrase.
- `@core` — load-bearing for daily use; a regression makes the app unusable, not degraded.
- `@accessibility` — exists because of the tendinosis constraint; never traded for polish.
- `@shared` / `@per-user` — about data both members see, or that must differ between them.
- `@gap` — a verified defect, not an aspiration.

Untagged is ordinary behaviour: keep the intent, use judgement on the details.

## Ubiquitous language

**Catalog item** — a shared definition. **Log row** — one member's private record of a date and a quantity, never a copy of the item's nutrition. **Derived value** — computed on read, never stored, so fixing a catalog entry fixes history. **Orphaned log** — its item was deleted: it keeps date and quantity, loses the name, reports zero. **Set** — a named bundle of items, expanded server-side into ordinary log rows. **Heading** — the line a ledger draws over one logged set; not a stored row, and dropped by a sort. **Amount** — servings or grams, whichever was typed. **Estimate** — eyeballed rather than read off a label. **Pending value** — a derived cell the server has not answered for yet, rendered `…`. **Matched set** — the rows a filter leaves. **Column layout** — a permutation of the header plus a hidden set.

**The four states** — every second is `focus`, `rest`, `focus_overtime` or `rest_overtime`; a **heartbeat** is one stored row per minute saying which, and **DSI** is weighted penalty over weighted recovery. **Regime** — the named block of the day the schedule is in. **Wall** — one window of a strict break, filling one output; a break *is* its walls. **Offer** — one thing a break can show, and the key that shows it. **Output** — one monitor, named as its connector; never "primary", which means three different monitors here.

## Conventions every feature assumes

`DD.MM.YYYY` everywhere a person reads or types a date; ISO is for the API and the store, and is refused in the command bar. Outcomes go to the status bar with a colour pulse — no modal dialogs, because a dialog is a keystroke the member cannot afford. Reads never block. Failure is a message, not an exception: a view with no data renders empty, and a rejected write leaves the typed input intact.
