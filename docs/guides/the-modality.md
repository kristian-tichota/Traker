# The four modes

Which keys act in each mode, and how the window keeps its readout accurate. Contract:
`specs/features/keyboard_modality.feature`.

## Modes

The left half of the status row always names the mode and lists its keys, in the bindings declared in
`[keybinds]`. It is also coloured: grey for NORMAL, green for COMMAND, blue for SHEET, violet for
FILTER. The right half carries the last message, such as a sort, a filter count or a refused write,
and never replaces the mode.

| Mode | Entered with | Keys | Left with |
| --- | --- | --- | --- |
| NORMAL | Escape, from anywhere | `0`–`9`, `A`–`Z` select a tab; `D`/`W` switch the nutrient window | — |
| COMMAND | `i` or `:` | Tab completes, Ctrl-N/Ctrl-P pick | Escape, or running the line |
| SHEET | `s`, or clicking a cell | `hjkl` move, `e` edits, `o` sorts | Escape |
| FILTER | `/`, from NORMAL or a sheet | type to narrow, Enter drops into the rows | Escape, which also clears |

Switching tabs returns the window to NORMAL, because the table or bar the mode named is no longer
displayed. A half-typed command remains in the bar.

## Implementation

`MainWindow.set_mode` is the only entry, and module-level `MODES` is the only list of modes. A name
absent from that list is refused rather than left naming the mode just left.

A mode is entered by the transition, not by a focus event. `enter_command`, `enter_sheet`,
`open_filter` and `_commit_filter` each name their mode; focus delivery belongs to the window manager
and the readout does not depend on it. A table's `focusInEvent` still announces SHEET, because a table
clicked into is in SHEET, and `set_mode` absorbs the repeat.

`mode_label` is the readout and `status_bar` is the message line. Fourteen callers write the message
line and none of them restores a mode, so a mode named there would survive only until the next sort,
filter count, refused write or tab switch, and in NORMAL until a transition that never arrives.

Leaving a mode also releases the keyboard, through `return_to_normal`. All three modal surfaces leave
the same way, by clearing, calling `clearFocus` and emitting `mode_requested("NORMAL")`, and
`_on_mode_requested` is the one place that decides what happens to the focus. It has to, because
`clearFocus` alone leaves the window with no focus widget while `MainWindow.keyPressEvent` reads the
tab keys, so NORMAL without focus would advertise keys that do nothing.

A mode does not outlive its tab, because `_on_tab_changed` returns to NORMAL.

Tests are in `tests/gui/test_modality.py`, together with the modality section of
`scripts/walk_the_app.py`, which drives it through Qt's own event dispatch.
