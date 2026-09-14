# Application window placement

Placement is disabled by default. With all three keys empty, which is the shipped default, nothing is
written to the compositor configuration and no script is loaded. `[window] desktop`, `activity` and
`screen` name the three.

The window opens there, cannot be dragged off the desktop or activity, and the current screen does not
change when the application starts, because a launch that appears to do nothing is a window on another
desktop, and the log records this. When the application closes the rule is gone: KWin drops it when
the window is withdrawn, and the application removes it itself after a compositor restart.

## Output selection

KDE's own Screen rule does not work. `WindowRules::checkOutput` is
`workspace()->outputs().indexOf(output)`, an index into a list ordered by the sequence in which the
compositor detected monitors during the current boot, and `outputs().value(n)` for an out-of-range
index falls back silently to the window's current output. The setting therefore changes meaning
between boots and is never enforced. KWin 6 offers no output-name rule.

The output is selected by a small KWin script instead, under its own name (`traker-window-home`) so
that a break cannot drop it, calling `sendClientToScreen`, which takes the output itself. It re-places
when a drag ends rather than during one. The journal records one line per move, for example
`traker: window home 'Traker' dragged wanted=DP-1 on=DP-1`, where `on=` is read back after the move,
so `wanted=DP-1 on=DP-2` is a placement the compositor refused. After five consecutive refusals the
script stops trying and reports this.

## Naming

A desktop is named as the pager names it or by its position, an activity as the switcher names it, and
a screen by its connector name. The word `primary` MUST NOT be used, because on this session it
denotes three different monitors depending on which subsystem answers. Case is not significant, and
both names are resolved again on every launch, which is why names rather than the UUID the settings
page stores are written. A name nothing answers to costs that dimension and a line in the log, and it
is never written as an empty value, which is KWin's own spelling of every desktop. Desktop names that
have never been changed are absent from `kwinrc`, so `"Desktop 5"` and `5` both resolve.

## Interaction with a strict break

KWin matches a rule on the application class, and every window this application opens carries the same
class, so a class-matched rule written for the main window also reaches a break's walls, where a
forced `screen` displaces one wall. Both rules therefore match on the title: a break's wall on
`Traker rest` as a substring, and the main window on `Traker` exactly. The wall rule also forces
`fullscreen`, `above` and not-`minimize`, which a wall already is, so a member's own class-matched
rule cannot remove them. It is listed first, because the first rule to set a value decides it.

`[strict_break] media_screen` names the monitor a break plays on, and empty follows `[window] screen`.
`scripts/check_desktop_integration.py --release` unloads both scripts and drops both rule groups, and
`--screens` reports what the file currently carries.
