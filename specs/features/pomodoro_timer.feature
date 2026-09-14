@exact @accessibility @core
Feature: Focus timer

  As a user limiting uninterrupted time at a computer
  I want a timer that enforces breaks and records what actually happened
  So that rest is measured rather than assumed

  Every second of the day falls into exactly one of four states, and the stored
  history MUST agree with the live display. The state routing and the two-tier
  timing below MUST NOT be collapsed.

  Background:
    Given one split declared in my profile: a focus length and a break length
    And a longer break I may queue in place of one, and how many of those a day holds
    And whether a break takes every screen, which is my profile's to say
    And a strict break declares how long its release key must be held, and how long before it lands I am warned
    And how long stopping a running focus interval must be held for, and how long away from my desk stops it for me

  Rule: There is one split, not a menu of them

    Scenario: The shipped split
      Then focus is 30 minutes and a break is 30
      And the queued break is 60, twice a day
      And the view says what the split is rather than offering me others

    Scenario: My own split
      Given I wrote different durations in my profile
      Then the timer runs those instead
      And a duration that could not run — zero, or not a number — is refused in favour of the shipped one

    Scenario: A profile written before the split
      Given my profile still declares the old timer modes
      Then none of it is read
      And the app says so once, rather than ignoring it silently
      And the wall stays off until I ask for it, because a mode I had to select was never one

  Rule: The break after focus is the ordinary one unless I queued the long one

    Scenario: Queuing it
      When I queue the long break, from the command bar or the button
      Then the next break is the long one
      And the break already running is unchanged, whatever it is
      And I may take it back before that break begins

    Scenario: Spending it
      When the long break begins
      Then it is recorded as begun, so a restart today cannot hand me another
      And one fewer is left for the day
      And the break after it is the ordinary one again

    Scenario: Leaving one early still spends it
      Given I left a long break by holding the release key
      Then it stays spent, because it happened

    Scenario: The third of a day
      When I have spent both and ask for another
      Then it is refused in words, and the control that offers it is visibly spent

    Scenario: Tomorrow
      Then the day's long breaks are back

    Scenario: Reading it back
      When I ask about the next break rather than telling it
      Then I am told whether the long one is queued and how many are left today

  Rule: Every second is accounted to exactly one of four states

    Scenario Outline: State routing
      Given the timer is <condition>
      Then elapsed time accrues to "<state>"

      Examples:
        | condition                                        | state          |
        | running in a focus interval                      | focus          |
        | running in a short or long break                 | rest           |
        | waiting for me to start focus                    | rest_overtime  |
        | waiting for me to start a break after focus ended| focus_overtime |
        | paused during a focus interval by my own hand    | focus_overtime |
        | paused during a focus interval by my absence     | rest_overtime  |
        | paused during a break                            | focus_overtime |

    Scenario: A fresh timer waits in rest overtime
      When the timer is first shown
      Then the phase is focus with the full focus duration on the clock
      And the timer is not running
      And it displays that it is ready and waiting for me to press play
      And the waiting time accrues to rest overtime

  Rule: Timing is two-tiered, so the live display and the stored history agree

    Scenario: The live engine measures in fractions of a second
      Then the display advances at the screen's refresh rate
      And it shows minutes, seconds and hundredths
      And elapsed time is measured from the wall clock between frames, not by counting ticks

    Scenario: A display nobody can see advances no faster than it needs to
      Given the focus timer tab is not the visible tab
      Then the engine runs about once a second instead of at the screen's refresh rate
      And it still crosses every minute boundary, so the stored history is unchanged
      And the four state totals are the same as they would be at the full cadence
      And the full cadence resumes the moment the tab is shown again

    Scenario: A display behind a break's own walls is one nobody can see either
      Given a strict break is holding the screens
      Then the engine runs about ten times a second, not at the screen's refresh rate
      And everything I can actually read then is in whole seconds anyway
      And the ring filling as I hold the exit is unaffected, having its own timer
      And the full cadence resumes when the screens are given back

    Scenario: The stored history has one row per minute of the day
      When the system clock crosses into a new minute
      Then exactly one heartbeat is stored for that minute, holding the state at the crossing
      And re-crossing a minute already stored replaces that row rather than adding another

    Scenario: The two tiers hand over without double counting
      When a heartbeat is stored
      Then today's totals are re-read from the stored history
      And the in-memory sub-minute counters reset to zero
      And the displayed totals do not jump or stall across the handover

    Scenario: Manual actions never force a heartbeat
      When I pause, resume or skip
      Then a timeline event is recorded with the moment it happened
      But no heartbeat is written outside the ordinary minute rollover

    Scenario: Totals survive a restart
      Given I already accumulated time today
      When the app is restarted
      Then today's totals continue from the stored history

  Rule: Focus ends differently depending on whether breaks are enforced

    Scenario: Strict mode starts the break for me
      Given my profile says breaks take the screens
      When the focus interval reaches zero
      Then the break begins immediately and runs
      And it is the long break if I queued one, otherwise the ordinary one

    Scenario: Without strict mode the timer waits at zero
      Given my profile says breaks do not take the screens
      When the focus interval reaches zero
      Then the clock holds at zero and stops running
      And it displays that focus is over and asks me to press play
      And the waiting time accrues to focus overtime

    Scenario: Starting the break by hand
      Given focus has ended and the timer is waiting for me
      When I press play
      Then a resumed-break event is recorded
      And the break begins and runs

  Rule: Focus is never resumed automatically

    Scenario: The end of a break always waits for me
      When a break reaches zero, whether or not it held the screens
      Then the phase becomes focus with the full focus duration on the clock
      And the timer does not run
      And it displays that rest is over and asks me to press play
      And the waiting time accrues to rest overtime

    Scenario: Starting focus by hand
      Given a break has ended and the timer is waiting for me
      When I press play — or the release key, where walls are still standing
      Then a resumed-focus event is recorded
      And the focus interval begins and runs

  Rule: A focus interval I walked away from is not focus

    Scenario: Walking away
      Given a focus interval is running
      When the session has seen neither a key nor the mouse for the configured inactivity
      Then the clock stops
      And an event is recorded naming the focus time that was left on it
      And the waiting accrues to rest overtime
      And the phase says I am away rather than that I stopped

    Scenario: The silence that proved it was rest as well
      Given the timer stopped itself for my absence
      Then every whole minute of that inactivity is stored again as rest overtime
      And the part-minute since the last stored one moves with them
      And the live readouts move by what was moved, so the two still agree
      And today's stress index falls, those seconds having gone from penalty to recovery

    Scenario: Only the minutes it can vouch for
      Given the timer stopped itself for my absence
      Then nothing before that inactivity is touched, however long I had been sitting there
      And a rewrite that did not reach the service leaves the totals as the store has them, and says so in the log

    Scenario: Nothing lands while I am gone
      Given the timer stopped itself for my absence
      Then no break begins, however long I am away
      And what was left of the interval is still left of it

    Scenario: Coming back
      Given the timer stopped itself for my absence
      When the session sees a key or the mouse again
      Then the interval carries on from where the absence stopped it
      And a resumed-focus event is recorded
      And the break lands after the focus time that was left, as it would have

    Scenario: Coming back to the window rather than the keyboard
      Given the timer stopped itself for my absence
      When I press play
      Then the interval carries on the same way

    Scenario: A break is not watched for my absence
      Given a break is running
      Then being away from the keyboard changes nothing

    Scenario: Inactivity I turned off
      Given the inactivity in my profile is zero
      Then the clock runs whether I am at the desk or not

    Scenario: A session that will not say how long I have been idle
      Given the desktop does not answer how long the session has been idle
      Then the timer runs as it would without the feature, and says so once in the log

  Rule: Stopping a running focus interval is held for, not clicked

    Scenario: A click leaves it running
      Given a focus interval is running
      When I click stop
      Then the clock is still running
      And the view says how long the stop has to be held for

    Scenario: Paying the hold
      Given a focus interval is running
      When I hold the stop for as long as it asks
      Then the clock stops
      And a paused-focus event is recorded
      And the waiting accrues to focus overtime

    Scenario: Letting go early
      Given I began the hold on a running focus interval
      When I let go before it is paid
      Then the clock is still running and nothing is recorded

    Scenario: The click that ends the hold is not also a start
      Given I paid the hold with the button
      Then letting go of it leaves the clock stopped

    Scenario: Starting it again is one press
      Given I stopped a focus interval by hand
      When I press play
      Then focus carries on from where I stopped it

    Scenario: A break is not held to it
      Given a break that does not take the screens is running
      When I click stop
      Then it stops on the click

  Rule: An enforced break occupies every screen until focus resumes

    Scenario: Enforcing a break
      Given breaks take the screens
      When a break begins
      Then every screen is covered by a wall of its own, in front of other windows
      And each wall is a window naming the output it fills, apart from Traker's own
      And my own Traker window is left exactly where I had it, behind them
      And the compositor is asked to keep all of it on every virtual desktop and activity
      And it is told which output each wall belongs on, because Qt cannot ask for one
      And the keyboard is put on the wall that shows me a file

    Scenario: What the break shows is on the screen I named
      Given breaks take the screens and I have more than one screen
      And my profile names the output a break shows a file on
      When a break begins
      Then the wall covering that output is the one that shows me a file
      And the countdown, what is coming and the chores are on the walls beside it
      And it keeps that screen for the length of the break

    Scenario: A screen name nothing answers to
      Given my profile names an output this session does not have
      When a break begins
      Then the file goes to the primary screen and the log says why

    Scenario: Every wall is put on its own output by the compositor
      Given breaks take the screens and I have more than one screen
      When a break begins
      Then each wall is on the output it was built for
      And it is the compositor that was asked to put it there, by name

    Scenario: A monitor switched off and back on
      Given breaks take the screens and one is running
      When I switch a monitor off and on again
      Then the monitor that came back is covered by a wall of its own
      And the wall on the monitor I did not touch is the one that was there
      And what was showing on the one that went dark comes back where it stopped
      And every screen dark at once is still a break, and still costs the hold

    Scenario: Somewhere else to be is not a way out
      Given breaks take the screens and one is running
      When I switch to another virtual desktop or another activity
      Then I am put straight back, however I tried to leave
      And that does not depend on the compositor having taken a script
      And the break is there too — every screen of it, not only the one in front

    Scenario: Letting it follow me instead
      Given breaks take the screens
      And my profile says a switch is not put back
      When I switch to another virtual desktop or another activity
      Then the break comes with me, as far as the compositor will carry it

    Scenario: Closing the wall is not a way out either
      Given breaks take the screens and one is running
      When I close a wall, or quit the application from outside it
      Then nothing closes and nothing quits

    Scenario: A compositor that will not pin a window is asked to follow me
      Given breaks take the screens and one is running
      And the compositor will move a window but will not keep one everywhere
      When I switch to another virtual desktop or another activity
      Then every window of the break is moved to the one I switched to
      And what it would and would not do is said where I can read it back

    Scenario: Asking for every desktop the one way the compositor cannot refuse
      Given breaks take the screens
      And my compositor silently refuses every way of writing "keep this window everywhere"
      When a break begins
      Then it asks with a window rule instead, before the first wall opens
      And the rule matches the walls by their title and nothing else of mine
      And it expires when the wall closes, so the compositor removes it itself
      And my own window rules are all still there afterwards
      And it is asked for ahead of mine, so a rule of mine cannot outrank it

    Scenario: A rule of my own cannot un-place a wall
      Given breaks take the screens
      And a window rule of my own that matches this application
      When a break begins
      Then each wall still fills its own screen, in front of everything
      And it still cannot be minimised or taken out of fullscreen

    Scenario: A rule that outlived the break it was written for
      Given a break was holding and my compositor restarted under it
      When I next start Traker, or ask it what this session answers for
      Then the rule that kept the walls everywhere is taken back out

    Scenario: Leaving the desktops to the compositor
      Given breaks take the screens
      And my profile says the walls are not pinned with a rule
      When a break begins
      Then the walls are wherever the compositor put them
      And a switch is still refused, and the break still follows me

    Scenario: A wall the compositor put on the wrong screen
      Given breaks take the screens and I have more than one screen
      When a wall ends up on an output it was not built for
      Then it names that output and fills it again
      And it does that once, not on every frame

    Scenario: A session whose compositor does not answer
      Given breaks take the screens
      And the session has no compositor that takes the request
      When a break begins
      Then it holds every screen it can reach on its own
      And nothing is refused or reported to me for the part that could not be asked for

    Scenario: The walls outlive the break, and the enforcement does not
      Given breaks take the screens
      When the break reaches zero
      Then the walls stay in place while the timer waits for me
      And each one is still in front of the screen it covers, every screen
      And each one says the break is over and to press the release key once
      And it says it at the scale of the screen it is on, inside a frame
      And that one press starts focus and takes them away
      And the controls that start focus are mine to use again
      But nothing is held any longer: the compositor has its desktops back
      And a switch is no longer put straight back
      And no wall takes the focus off what I reach for any more
      And what is coming and what is due go off them, with their keys

  Rule: A strict break has one exit, and it costs seconds

    Scenario: Pausing is refused while the screens are held
      Given breaks take the screens and one is running
      When I pause
      Then the break keeps running and the screens stay held
      And the controls that would have ended it show that they are refused

    Scenario: Skipping is refused while the screens are held
      Given breaks take the screens and one is running
      When I skip the current interval
      Then nothing is recorded and the break keeps running

    Scenario: Leaving a break by holding the release key
      Given breaks take the screens and one is running
      When I hold the release key for the configured hold
      Then the screens are given back
      And an event is recorded naming the break as overridden, carrying the time left on it
      And the phase becomes focus with the full focus duration on the clock, waiting for me

    Scenario: The hold is shown while it is being paid
      Given I am holding the release key
      Then every screen the break covers shows how much of the hold is done
      And letting go before it completes records nothing and changes nothing

    Scenario: A break I left does not come back
      Given I left a break by holding the release key
      Then that break is not resumed
      And the next break is the one that follows the next focus interval
      And it is the ordinary one, whatever the one I left was

    Scenario: The exit is named where the break is read
      Given breaks take the screens and one is running
      Then every screen the break covers names the key to hold and for how long

    Scenario: Leaving while something is playing
      Given a break is showing me a video or a document
      When I hold the release key
      Then the hold is paid exactly as it is on a bare wall, and what was playing stops

    Scenario: A hold I wrote wrong costs the shipped one, not the timer
      Given I wrote something that is not a number as the hold or the warning
      Then the shipped figure is used and the app says so once
      And the tab is still built

  Rule: A held break shows me something I named

    Scenario: What can be shown, and what shows it
      Given my profile names activities, each with a name and a file
      And a queue of paths I asked for since
      Then the offers are the queue first and my standing entries after it
      And the first is on Enter and the rest are on the digits, in that order
      And every screen the break covers lists them with the key for each
      And a key with no offer behind it is left alone
      And a key delivered to a field I am typing into is left to that field

    Scenario: A PDF is read and anything else is played
      Given a queue with a video and a document in it
      Then neither needs anything declared for it
      And the one that is a PDF is read, a page at a time

    Scenario: Nothing runs unasked
      Given breaks take the screens and one begins
      Then nothing is shown until I press the key for it

    Scenario: The first minutes of a break are away from the screen
      Given breaks take the screens and one begins
      Then nothing can be shown for the first five minutes of it
      And an offer's key does nothing at all until they are up
      And the offers are listed the whole time, titled with how long is left
      And what is due and what is coming are on the wall as they always are
      And a chore still takes its tick, because that is what being away is for

    Scenario: A longer break is longer away from the screen
      Given the wait is five minutes of an ordinary break
      When a long break of twice the length holds the screens
      Then the wait is twice as long as well
      And a wait longer than the break itself is simply the whole break

    Scenario: I hear when the wait is up
      Given a break is holding the screens and I am away from them
      When the wait runs out and something can be shown
      Then I am told so through the session's notification, with its sound
      And it names the key and what is behind it
      And I am told once in a break, not once a frame
      But a break with nothing written down for it says nothing at all

    Scenario: The wait is mine to set, or to switch off
      Given my profile sets the seconds a break waits before it shows anything
      Then a break waits that long, in proportion to its own length
      And zero opens the offers the moment it lands
      And a value that is not a number costs one line in the log, not the tab

    Scenario: The queue is what is available, not a playlist
      Given a queue with several videos in it
      When one of them reaches its end
      Then nothing else starts, and the wall is what I am left looking at
      And the next thing shown is whichever one I press a key for

    Scenario: Showing one
      When I press an offer's key while the break holds
      Then it is shown on the primary screen, inside that wall's own window
      And that screen shows it and nothing else
      And no screen is given back, and pause and skip stay refused
      And nothing is launched, and no window of anybody else's is involved
      And the wall it opens in is never taken away and put back to open it

    Scenario: A document is read edge to edge
      Given a break is showing me a PDF
      Then the page fills the screen it is on, to every edge of it

    Scenario: What the other screens are for
      Given a break is showing me something and I have another screen
      Then the countdown, what is coming and the chores are on that one
      And the offers are there too, so I can ask for something else

    Scenario: A break with only one screen
      Given a break is showing me something and there is no other screen
      Then one thin line says how long is left and what leaving costs
      And the position and the card of the keys are on that screen after all
      And they are rows under the picture, because nothing may be drawn on it

    Scenario: What each key does is written down
      Given a break is showing me something
      Then a small card in the corner names every key that drives it
      And it names them for what is showing: SPACE pauses a video, and turns a page
      And it names what leaving costs
      And every wall beside the one showing it carries that card
      But the screen showing it does not, because that would be over the film
      And a screen with nothing showing on it names none of those keys

    Scenario: The five keys
      Given a break is showing me something
      Then SPACE pauses a video, or turns the page of a document
      And left and right — and PgUp and PgDn — seek 30 seconds, or turn pages
      And up and down are the volume, or scroll inside the page
      And 0 puts the wall back
      And another offer's key shows that one instead

    Scenario: Closing it is not a way out
      Given a break is showing me something
      When I ask for the wall back
      Then what is underneath is the break, still holding every screen

    Scenario: Closing it and opening it again costs nothing
      Given a break is showing me something
      When I ask for the wall back and then press its key again
      Then it is showing again, on the same screen, where it had got to
      And the walls, the hold and the compositor's part of it never moved

    Scenario: A second offer does not stack on the first
      When I press another offer's key during the same break
      Then the first stops and the second is what is showing
      And where the first got to is remembered

    Scenario: Its own key again is not a second opening
      Given a break is showing me something
      When I press the key it is already showing
      Then nothing happens at all

    Scenario: A forty-minute video spans three breaks
      Given a break was showing me something and stopped
      Then where it got to is remembered — a position, or a page
      And how long the file is is remembered with it
      And the next break that shows it carries on from there
      And a document opens *on* that page, not merely counting from it
      And something I had only just started is not remembered at all

    Scenario: How far into it I am, while it plays
      Given a break is showing me a video
      Then the picture fills the screen, and nothing at all is drawn on it
      And the wall beside it names what is playing
      And a thin line there says how much of it is behind me
      And the position and the length are over its right-hand end, quiet
      And both are as live as the countdown they stand next to
      And a document says its page there the same way
      And a break with only one screen keeps them in a row under the picture

    Scenario: It plays the way the player that works here plays
      Given a break is showing me a video
      Then it is mpv playing it, inside a surface of Traker's own window
      And the decoding, the timing and the sound server are all mpv's business
      And nothing of mpv's is started as a window, and no key of mine reaches it
      And nothing of the break is drawn over the picture, because nothing can be

    Scenario: A machine without libmpv still holds a break
      Given libmpv is not installed
      Then the break still takes the screens, and still lists what is due
      And the screen that would show a film says it could not play it

    Scenario: How far into each one I am, before I choose
      Given offers I have opened on an earlier break
      Then the wall says how far into each of them I am, beside its key
      And a video reads as a position out of a length, a document as its page
      And closing one leaves the wall saying where I had just got to

    Scenario: Something Traker cannot place
      Given an offer whose length was never recorded
      Then no progress is drawn for it rather than a wrong one
      And a break with nothing opened yet lists the names alone

    Scenario: The break goes on being a break
      Given a break is showing me something
      Then the time still accrues to rest
      And the break still ends on its own, and the one exit still costs the same hold

    Scenario: When the break ends
      When the break reaches zero
      Then what was playing stops, remembered where it stopped
      And the wall underneath stays until I start focus, saying which key does

    Scenario: An entry I wrote wrong is skipped, not guessed at
      Given an activity entry with no name, or no file
      Then it is not offered, and the entries around it still are

    Scenario: An entry written for the launcher says so
      Given an entry that still names a command and an app id
      Then it is not offered, and the log says to write the file instead

    Scenario: A file that cannot be shown says so where I am looking
      Given an offer whose file is missing, or is not something that can be decoded
      When I press its key
      Then that screen says so instead of showing me a black rectangle
      And the break goes on, and the other screens are unchanged

  Rule: What to open on a break is queued, not configured

    Scenario: Queuing something
      When I queue a path from the command bar
      Then it is added to the end of the queue
      And it is offered on the next break, ahead of my standing entries
      And nothing has to be declared to open it
      And nothing about it reaches the household service

    Scenario: Anything may write the queue
      Given the queue is a plain file, one path per line, comments ignored
      When something other than Traker appends to it
      Then the next break offers what it added

    Scenario: Reading the queue back
      When I ask for the queue with no path
      Then it is reported with the key for each entry
      And an empty queue says so

    Scenario: Pruning it
      When I drop an entry by its number, or empty the queue
      Then the file is rewritten without it, keeping what it says about itself
      And a number that is not in the queue is refused, leaving my line to correct

    Scenario: Queuing the same thing twice
      Then the queue is left as it was, rather than offering it on two keys

    Scenario: An item stays until I remove it
      Given I opened a queued video and the break ended part-way through it
      Then it is still queued for the next break
      And opening it again carries on from exactly where I stopped

    Scenario: The numbers do not move under my fingers
      Given a break is holding the screens
      When something is queued while it holds
      Then the offers on screen and the keys that open them are unchanged
      And the new entry is offered on the next break

    Scenario: A queue of mixed things
      Given the queue holds a video and a PDF
      Then both are offered, and neither needed anything declared

  Rule: A held break shows what is coming

    Scenario: Today's session on the break surface
      Given my cycle has a session today
      When a break begins
      Then every screen the break covers names that session and the movements prescribed for it
      And the prescription is the one the Plans tab shows for the same day

    Scenario: Read once, not once a frame
      When a break begins
      Then what is coming is read once, off the interface thread
      And no further read happens while the break counts down
      And a cycle I edited between two breaks shows at the second

    Scenario: A day with nothing on it
      Given my cycle has no session today
      Then the surface names the day and says nothing is planned

    Scenario: No cycle at all
      Given I have no training cycle
      Then the surface says nothing about plans

    Scenario: A read that did not arrive
      When the read does not reach the household service
      Then the surface shows nothing, rather than a plan from another day

    Scenario: With something showing on the screen it took
      Given a break is showing me a video or a document
      Then the screens it still covers go on showing what is coming
      And the wall behind what is showing has it too, for when I ask for it back

  Rule: A strict break is announced before it lands

    Scenario: The warning
      Given breaks take the screens
      When the focus interval has the configured warning time left on it
      Then the session's notification service is asked to say that a break is coming, audibly
      And the message says how long the coming break is, and how to leave one
      And exactly one warning goes out for that focus interval

    Scenario: Nothing to announce
      Given breaks do not take the screens, or the warning time is zero
      Then no warning goes out

  Rule: Skipping is recorded as a debt, not hidden

    Scenario: Skipping an interval
      Given no strict break is holding the screens
      When I skip the current interval
      Then an event is recorded naming the phase skipped and how much time remained
      And the timer moves to the next phase as though the interval had elapsed

  Rule: What the day has left is visible

    Scenario: The long breaks
      Then a row of dots shows the day's long breaks, filled as they are spent
      And they are back tomorrow

    Scenario: The tray icon reflects the timer without the window being visible
      Then the tray icon shows how far the current phase has progressed
      And its centre carries the colour of my current schedule regime

  Rule: Shutdown is orderly

    Scenario: Closing the window while the timer runs
      When I close the application
      Then the timer and its animations stop
      And any strict-mode overlays are removed
      And the compositor is told to stop holding the break
      And in-flight writes are given a moment to finish
