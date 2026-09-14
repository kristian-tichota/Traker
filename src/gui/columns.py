from dataclasses import dataclass, replace

from src.gui.commands import HIDE, MOVE, RESET, SHOW
from src.gui.filtering import FilterError, resolve_field

SEPARATOR = "|"

HIDDEN_MARK = "-"


class ColumnError(ValueError):
    """A rearrangement the member must correct."""


def setting_key(table: str) -> str:
    """Return the user_settings key holding one table's layout."""
    return f"columns_{table}"


@dataclass(frozen=True)
class ColumnLayout:
    """One table's columns, in the order shown, and which of them are hidden."""

    order: tuple
    hidden: frozenset = frozenset()

    @classmethod
    def declared(cls, headers) -> "ColumnLayout":
        """Return the layout a table has before it is arranged."""
        return cls(tuple(headers))

    @classmethod
    def parse(cls, stored: str, declared) -> "ColumnLayout":
        """Read a stored value against the columns this table has."""
        declared = tuple(declared)
        order, hidden = [], set()
        for token in (stored or "").split(SEPARATOR):
            name = token.strip()
            switched_off = name.startswith(HIDDEN_MARK)
            if switched_off:
                name = name[len(HIDDEN_MARK):].strip()
            if name not in declared or name in order:
                continue
            order.append(name)
            if switched_off:
                hidden.add(name)
        order.extend(name for name in declared if name not in order)
        return cls(tuple(order), frozenset(hidden))

    @property
    def encoded(self) -> str:
        """Return the stored form."""
        return SEPARATOR.join(
            (HIDDEN_MARK + name) if name in self.hidden else name
            for name in self.order)

    @property
    def visible(self) -> tuple:
        """Return the columns on screen, in the order they are on screen."""
        return tuple(name for name in self.order if name not in self.hidden)

    def is_default(self, declared) -> bool:
        """Report whether this is what the table declares, so nothing needs storing."""
        return self.order == tuple(declared) and not self.hidden

    def is_hidden(self, header: str) -> bool:
        return header in self.hidden

    def can_hide(self, header: str) -> bool:
        """Report whether hiding header would leave a table to read."""
        return header in self.order and not self.is_hidden(header) and len(self.visible) > 1

    def hide(self, header: str) -> "ColumnLayout":
        self._must_hold(header)
        if self.is_hidden(header):
            return self
        if not self.can_hide(header):
            raise ColumnError(f"'{header}' is the only column left; "
                              "show another one before hiding it.")
        return replace(self, hidden=self.hidden | {header})

    def show(self, header: str) -> "ColumnLayout":
        self._must_hold(header)
        return replace(self, hidden=self.hidden - {header})

    def toggled(self, header: str) -> "ColumnLayout":
        """Return this layout with one column's visibility flipped."""
        return self.show(header) if self.is_hidden(header) else self.hide(header)

    def move(self, header: str, position: int) -> "ColumnLayout":
        """Put header at position, counting visible columns from 1."""
        self._must_hold(header)
        if self.is_hidden(header):
            raise ColumnError(f"'{header}' is hidden here; show it before moving it.")
        if not 1 <= position <= len(self.visible):
            raise ColumnError(f"This table shows {len(self.visible)} columns, "
                              f"so there is no position {position}.")
        remaining = [name for name in self.order if name != header]
        elsewhere = [name for name in self.visible if name != header]
        if position > len(elsewhere):
            index = len(remaining)
        else:
            index = remaining.index(elsewhere[position - 1])
        return replace(self, order=(*remaining[:index], header, *remaining[index:]))

    def _must_hold(self, header: str):
        if header not in self.order:
            raise ColumnError(f"This table has no column called '{header}'.")


def resolve_column(token: str, layout: ColumnLayout) -> str:
    """Return the header a typed word names, or raise ColumnError."""
    try:
        return resolve_field(token, layout.order)
    except FilterError as exc:
        raise ColumnError(str(exc)) from exc


def rearranged(layout: ColumnLayout, declared, action: str, column: str,
               position: int | None):
    """Return the layout :cols asks for, and the line that reports it."""
    if action == RESET:
        return ColumnLayout.declared(declared), "back to the columns it declares"

    header = resolve_column(column, layout)
    if action == MOVE:
        if position is None:
            raise ColumnError(f"Which position? Say ':cols move 2 {header}'.")
        return layout.move(header, position), f"'{header}' moved to {position}"
    if action == HIDE:
        return layout.hide(header), f"'{header}' hidden"
    if action == SHOW:
        return layout.show(header), f"'{header}' shown"

    settled = layout.toggled(header)
    return settled, f"'{header}' " + ("hidden" if settled.is_hidden(header) else "shown")


def describe(layout: ColumnLayout) -> str:
    """Format the layout as one status-bar line: what is shown, then what is not."""
    shown = ", ".join(layout.visible)
    if not layout.hidden:
        return shown
    off = ", ".join(name for name in layout.order if layout.is_hidden(name))
    return f"{shown} · hidden: {off}"
