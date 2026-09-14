# Scheduled monochrome

Disabled by default, and configured under `[grayscale]` in the member profile, where every key is
documented. Contract: `specs/features/user_profile.feature`.

When enabled, every screen loses its colour between those hours, across every application and every
monitor. KWin's own filter performs this rather than a window of the application's, because an
application-drawn overlay would be grey over the application and coloured everywhere else.

## Schedule

Nothing is enforced. Setting `enabled` to `false` while the application runs restores colour within
the minute, because the profile is re-read on each tick.

The filter is not undone when the application closes, because the schedule is a property of the
session rather than of the application, and a KWin that restarts underneath returns to grey by itself.
The `[Plugins]` key its effect loader reads at startup is why the hours are written into `kwinrc` as
well as requested over D-Bus.

The corollary is that setting `enabled` to `false` while the application is closed leaves the screens
as they are. The application MUST NOT unload an effect it did not itself load in the current session,
because that effect may be an accessibility correction rather than this schedule. Disable it in
System Settings, under Accessibility, or re-enable the schedule and let an evening end. The hours may
wrap past midnight, by the same rule the schedule's regimes wrap by (`clock.py:within_window`).

## Version requirement

Plasma 6.6 or newer is REQUIRED, because that is where KWin's colour-blindness effect gained the
monochrome mode this uses. Nothing checks the version: the mode is a bare `UInt` with no maximum, so
an older KWin reads the number back unchanged and falls through to the red-green filter, which tints
the screens rather than desaturating them.

`intensity` is the distance towards grey, and `0` is not off, because KWin rolls a zero over to full,
which is why its own slider does not reach it. Off is `enabled = false`.

## Diagnostics

```bash
journalctl --user -b -g 'grayscale'
kreadconfig6 --file kwinrc --group Plugins --key colorblindnesscorrectionEnabled
kreadconfig6 --file kwinrc --group Effect-colorblindnesscorrection --key Mode
```

The journal carries one line per boundary. No output at all means the section is disabled or the hour
has not arrived, and `No KWin` means no compositor is answering, which the next minute retries.
`Mode` is `3`. Both keys are edited in place, so anything else in either group is left unchanged.
