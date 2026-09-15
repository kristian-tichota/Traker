# Table column layout

A column may be switched off and the remainder placed in any order. A layout is held per member and
per table, in the store. Contract: `specs/features/column_layout.feature`.

## Commands

```
:cols                    what this table shows, in order, then what it hides
:cols Sugars             switch a column off, or back on
:cols hide Sugars        say which, where a toggle would be ambiguous
:cols show Sugars
:cols move 2 kcal        put it second among the columns on screen
:cols reset              back to the declared columns
```

Names match as filter fields do, so `kcal`, `cal`, `Calories` or any unique prefix resolves. `:cols`
acts on the table last entered on the tab, and on the ledger until one has been entered. With a
pointer, a heading may be dragged, or the header right-clicked for a ticked list of every column,
which is also how a hidden column returns. A left click on a heading sorts by that column and cycles
ascending, descending, then the stored order, as the sort key does; an arrow on the heading names the
sort in force.

## Implementation

A layout is a permutation of the declared headers plus a hidden set, and `src/gui/columns.py` is all
of it. The declared order remains the one in `rows.py`, so the header-to-column mapping, the editable
columns, the filter's field terms and the sort keep their logical indices, and only the header's
visual order and its hidden sections change.

The header is the state. `VimTableView.column_layout()` reads the layout back off `QHeaderView`, so
the drag, the menu, `:cols` and the stored value cannot disagree. `BaseManagedView.set_column_layout()`
is the one apply-and-store path, and all four routes arrive there.

Layouts are stored through the existing per-member settings, with no schema change and no new route,
as one row per table named `columns_<table>`:

```
columns_food_logs = Est|Date|Food Name|Servings|-Sugars|…
```

The order is what is shown, a leading `-` marks a hidden column, and every declared header is named. A
header the stored value does not mention is appended and visible, so a column added by a later version
appears rather than vanishing.

Hiding the last visible column is refused by `ColumnLayout.can_hide`, because the header row is the
only route back for a member using a pointer, so there MUST always be a header row.
