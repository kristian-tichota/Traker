# Where Traker's own window lives

Off by default. All three empty — the shipped default — writes nothing to your compositor's
configuration and loads nothing.

```toml
[window]
desktop  = "Desktop 5"      # as the pager names it, or its position: 5
activity = "Personal"       # as the activity switcher names it
screen   = "DP-1"           # as `kscreen-doctor -o` names it
```

The window **opens** there, **cannot be dragged off** the desktop or activity, and your screen
**does not move** when Traker starts — a launch that appears to do nothing is a window on
another desktop, and the log says so. When Traker closes the rule is **gone**: KWin drops it
when the window is withdrawn, and Traker takes it out itself after a compositor restart.

## The screen is asked for differently

KDE's own **Screen** rule genuinely does not work, and it is not you. `WindowRules::checkOutput`
is `workspace()->outputs().indexOf(output)` — an index into a list whose order is the order the
compositor detected monitors *this boot* — and `outputs().value(n)` for an out-of-range index
falls back to the window's current output silently. That is why the setting appears to change
meaning between boots and to be never enforced. There is no output-*name* rule in KWin 6.

So the screen is a small KWin script instead, under its own name (`traker-window-home`) so a break cannot drop it, calling `sendClientToScreen`, which takes the output itself. It re-places when you let go of a drag, not during one. The journal says so, one line per move — `traker: window home 'Traker' dragged wanted=DP-1 on=DP-1` — where `on=` is read back after the move, so `wanted=DP-1 on=DP-2` is a placement the compositor refused. Five in a row and it stops trying and says so.

## Names, not ids

A desktop by the name on your pager or its position, an activity by the name in the switcher, a
screen by its connector name. **Not "primary"** — on this session that word means three
different monitors depending on who is asked. Case does not matter, and both are resolved again
on every launch, which is the whole reason to write names rather than the uuid the settings page
stores. A name nothing answers to costs *that* dimension and a line in the log; it is never
written as an empty value, which is KWin's own spelling of *every* desktop. Desktop names you
have never changed are not in `kwinrc` at all, so `"Desktop 5"` and `5` both work.

## Why it will not break a rest break

KWin matches a rule on the **application class**, and every window Traker opens carries the same
one — so a hand-made rule written for the window applied to a break's walls too, and a forced
`screen` un-placed one wall while the other was fine. Traker's two rules match on the *title*:
a break's walls on `Traker rest` as a **substring**, this window on `Traker` **exactly**. The
walls' rule also forces `fullscreen`, `above` and not-`minimize` — things a wall already is —
so a class-matched rule of **your** own cannot take them away. It is listed first, and the
first rule to set a value is the last word on it.

`[strict_break] media_screen` names the monitor a break plays on; empty follows `[window]
screen`. To clear anything left behind: `scripts/check_desktop_integration.py --release`
unloads both scripts and drops both rule groups, and `--screens` says what the file carries now.
