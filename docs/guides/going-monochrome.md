# Taking the colour out of the evening

Off by default. Contract: `specs/features/user_profile.feature`.

```toml
[grayscale]
enabled = false
from = "20:00"
to = "06:00"
intensity = 1.0         # 0.05 to 1.0, and never 0
```

Switched on, **every screen loses its colour between those hours** — every application, every
monitor. It is KWin's own filter rather than a window of Traker's, because a sheet we drew
would be grey over Traker and colour everywhere else.

## A schedule, not a hold

Nothing is enforced: change `enabled` to `false` while Traker runs and the colour is back
within the minute, because the profile is re-read each tick.

It is **not undone when Traker closes**: an evening you asked to be grey does not stop being one
because a tracker is shut, and a KWin that restarts underneath comes back grey by itself. The
`[Plugins]` key its effect loader reads at startup is why the hours are written into `kwinrc`
as well as asked for over D-Bus.

The corollary: switch `enabled` to `false` **while Traker is closed** and the screens stay as
they are. Traker will not unload an effect it did not itself load this session, because that
effect is somebody's colour-blindness correction before it is ever our evening. Untick it in
System Settings → Accessibility, or turn it back on and let an evening end. The hours may wrap
past midnight, by the same rule the schedule's regimes wrap by (`clock.py:within_window`).

## Plasma 6.6 or newer

That is where KWin's colour-blindness effect gained the monochrome mode this uses. **Nothing
checks the version**: the mode is a bare `UInt` with no maximum, so an older KWin reads the
number back unchanged and falls through to the red-green filter — screens going pink.

`intensity` is how far towards grey, and **0 is not off** — KWin rolls a zero over to full,
which is why its own slider will not reach it. Off is `enabled = false`.

## If it does not happen

```bash
journalctl --user -b -g 'grayscale'
kreadconfig6 --file kwinrc --group Plugins --key colorblindnesscorrectionEnabled
kreadconfig6 --file kwinrc --group Effect-colorblindnesscorrection --key Mode
```

One journal line per boundary; nothing at all means the section is off or the hour has not
come, and "No KWin" means no compositor is answering, which the next minute asks again.
`Mode` is `3`. Both keys are edited in place, so anything else in either group is left alone.
