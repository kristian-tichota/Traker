# The four modes

Which keys mean what, and how the window keeps its readout honest. Contract:
`specs/features/keyboard_modality.feature`.

## For a member

The status row's left half always names the mode and lists its keys, in your own
bindings from `[keybinds]`. It is coloured too: grey NORMAL, green COMMAND, blue
SHEET, violet FILTER. The right half carries the last message — a sort, a filter
count, a refused write — and never takes the mode away.

| Mode | Enter with | Keys | Leave with |
| --- | --- | --- | --- |
| NORMAL | Escape, from anywhere | `0`–`9`, `A`–`Z` select a tab; `D`/`W` switch the nutrient window | — |
| COMMAND | `i` or `:` | Tab completes, Ctrl-N/Ctrl-P pick | Escape, or running the line |
| SHEET | `s`, or clicking a cell | `hjkl` move, `e` edits, `o` sorts | Escape |
| FILTER | `/`, from NORMAL or a sheet | type to narrow, Enter drops into the rows | Escape, which also clears |

Switching tabs returns you to NORMAL, because the table or bar the mode named is
no longer in front of you. A half-typed command stays in the bar.

## For a reader of the code

`MainWindow.set_mode` is the only way in, and module-level `MODES` is the only
list of them — a name absent from it is refused rather than left naming the mode
the member has just left.

**A mode is entered by the transition, not by a focus event.** `enter_command`,
`enter_sheet`, `open_filter` and `_commit_filter` each name their mode; focus
delivery is the window manager's business and the readout is not. A table's
`focusInEvent` still announces SHEET — a table clicked into really is in SHEET —
and `set_mode` absorbs the repeat.

**`mode_label` is the readout; `status_bar` is the message line.** Fourteen
things write the message line and none of them puts a mode back, so a mode named
there survived only until the next sort, filter count, refused write or tab
switch — in NORMAL, until a transition that never comes.

**Leaving a mode takes the keyboard back too** (`return_to_normal`). All three
modal surfaces leave the same way — clear, `clearFocus`, emit
`mode_requested("NORMAL")` — and `_on_mode_requested` is the one place that
decides what that does with the focus. It has to: `clearFocus` alone leaves the
window with no focus widget, and `MainWindow.keyPressEvent` is what reads the
tab keys, so NORMAL without focus advertises keys that do nothing.

**A mode does not outlive its tab.** `_on_tab_changed` returns to NORMAL.

Tests: `tests/gui/test_modality.py`, plus the modality section of
`scripts/walk_the_app.py`, which drives it through Qt's own event dispatch.
