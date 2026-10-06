# Eye rest

Disabled by default, and configured under `[eye_rest]` in the member profile, where every key is
documented. The Focus Timer tab MUST be enabled, because the timer owns the walls the veil is also
drawn on. Contract: `specs/features/pomodoro_timer.feature`.

## Routines

| Routine | Steps | When |
| --- | --- | --- |
| Rest | close gently 2 s, open 1 s, close gently 2 s, squeeze 2 s, open 1 s, gaze `gaze_secs` | after `every_mins` of screen time |
| Blink set | 15 × (close 2 s, squeeze 2 s, open 1 s), 75 s | at the start of the first `blink_sets_per_day` breaks |

Each step sounds the cue of its motion, so that the routine can be followed with the eyes closed.

| Motion | Cue |
| --- | --- |
| Close | Two falling notes |
| Open | Two rising notes |
| Squeeze | Three low pulses |
| Look away | One bell |
| End | A three-note chord |

The cues are WAV files generated into `~/.cache/traker/` and played through QtMultimedia. A finished blink set is stored as a `blink_set` timer event, which seeds the count on
the next start.

## Surfaces

While a break's walls stand, the veil is a child widget of each wall, drawn over the activity it
shows. Otherwise it is one frameless window per output, captioned `Traker eyes — <output>`, which is
transparent for input. The `[traker-eyes]` group in `kwinrulesrc` forces those windows above other
windows and onto every desktop and activity, and keeps them out of the focus, the task bar, the pager
and the switcher. The group is written when the timer starts and removed when it shuts down.
`check_desktop_integration.py` reports it as `eye veils rule`.

A window that is both fullscreen and active is in a KWin layer above every keep-above window, so it
covers the veil.

## Default Sources

| Default | Source |
| --- | --- |
| Blink cycle every 20 min | Kim et al. 2021, Cont Lens Anterior Eye 44:101329 |
| 15 repetitions, three sets a day | Wolffsohn et al. 2025, Cont Lens Anterior Eye 48:102453 |
| 20 s gaze at 6 m | The 20-20-20 convention; Talens-Estarelles et al. 2023, Cont Lens Anterior Eye 46:101744 |
| Management beyond breaks | TFOS Lifestyle report, Wolffsohn et al. 2023, Ocul Surf 28:213 |
