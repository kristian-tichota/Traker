# Arranging a table's columns

Switch a column off, put the rest in any order. Per member, per table, kept in
the store. Contract: `specs/features/column_layout.feature`.

## For a member

```
:cols                    what this table shows, in order, then what it hides
:cols Sugars             switch a column off, or back on
:cols hide Sugars        say which, where a toggle would be ambiguous
:cols show Sugars
:cols move 2 kcal        put it second among the columns on screen
:cols reset              back to the declared columns
```

Names match the way filter fields do — `kcal`, `cal`, `Calories`, or any unique
prefix. `:cols` acts on the table last entered on the tab, and on the ledger
until one has been. With a mouse: drag a heading, or right-click the header for
a ticked list of every column — which is also how a hidden one comes back.

## For a reader of the code

A layout is a **permutation of the declared headers plus a hidden set**, and
`src/gui/columns.py` is all of it. The declared order stays `rows.py`'s, so the
header→column mapping, the editable columns, the filter's field terms and the
sort keep their logical indices; only the header's *visual* order and its hidden
sections change.

**The header is the state.** `VimTableView.column_layout()` reads the layout
back off `QHeaderView`, so the drag, the menu, `:cols` and the stored value
cannot come to disagree. `BaseManagedView.set_column_layout()` is the one
apply-and-store path; all four routes arrive there.

Stored through the existing per-member settings — no schema change, no new
route — one row per table, `columns_<table>`:

```
columns_food_logs = Est|Date|Food Name|Servings|-Sugars|…
```

Order is what is shown, a leading `-` is hidden, every declared header is named.
A header the stored value does not mention is appended, visible, so a column a
later version adds appears rather than vanishing.

Hiding the last visible column is refused, by `ColumnLayout.can_hide` — the
header row is the only route back for a member using a mouse, so there is always
a header row.
