# lock in or clock out (lioco)

A macOS menubar agent that notices when you are *at your desk but not working*
and offers exactly two buttons. What the buttons say depends on the time of day
and your calendar.

| When | It sees you drifting and says | Button 1 | Button 2 |
|---|---|---|---|
| Morning | "What is the one thing?" | Lock in (pick a task) | Short break |
| Midday | "Step away for lunch?" | Take lunch | Lock in |
| Meeting in 10–60 min | "Standup starts in 35 min." | Prep for it | Walk first (if ≥25 min) / Lock in |
| Afternoon, no break yet | "Afternoon slump." | Take a walk | Lock in |
| After 4:30 pm | "Lock in or clock out?" | One small task | Clock out |
| After 6:30 pm | "You are done for today." | Clock out | 10 more minutes |

Ignore a nudge and the next one gets bigger and makes a sound. Pick a task and
nudges pause for a 25-minute focus block.

## How it detects drift

Hammerspoon watches, without recording any content:

- **App switches** and **window switches** (Accessibility API).
- **Browser tab switches**, detected as title changes on the focused browser window.
- **Input rhythm**: counts of keystrokes vs. clicks and scrolls.
- **Output**: whether any file under your `work_dirs` changed in the last 20 minutes.

Every minute it scores the last 15 minutes from 0 to 1:

```
score = 0.35·switching + 0.20·bouncing (A→B→A) + 0.20·fragmentation + 0.25·consuming
        − 0.20 if a file changed recently
```

Fast tabbing while typing a lot scores low (research). Fast tabbing while only
clicking and scrolling, with nothing produced, scores high. Three drifting
minutes in a row trigger a nudge. Nothing fires while idle, in a calendar
meeting, on a Zoom call, during a break, or during a focus block.

Every evaluation is logged to `~/.local/share/lioco/events.jsonl` so you can
tune the threshold against your own week: `python3 brain/lioco.py stats`.

## What the buttons do

- **Lock in** pulls open tasks from your notes (unchecked boxes in notes tagged
  `#todo`) and from Linear (issues assigned to you), ranks them, and flags
  `important` and `small`. In wind-down mode the small ones float to the top. Clicking one
  opens it and starts a focus block.
- **Prep for it** finds notes related to the next meeting's title and
  attendees, open todos that mention them, and creates a `Prep: <meeting>` note
  with a goal line, agenda, related links, and space for notes.
- **Take a walk** starts a break timer sized to fit before your next meeting
  and tells you when to be back.
- **Clock out** asks two questions, "where did you leave off" and "first thing
  tomorrow", then appends them to today's `Daily YYYY-MM-DD` note, parks your
  open browser tabs into it, optionally sets Slack away, quits Slack, and locks
  the screen.

## Notes: Bear or a markdown folder

lioco needs somewhere to read todos from and write daily and prep notes to.
Two backends are built in and `notes.backend: "auto"` picks one for you:

| Backend | Chosen when | Reads | Writes |
|---|---|---|---|
| `bear` | Bear's database exists on this Mac | all notes, via a short-lived read-only copy | `bear://x-callback-url` create / append |
| `markdown` | otherwise | every `.md` under `notes.markdown_dir` (an Obsidian vault works) | plain files in that folder |
| `none` | you set it | nothing | nothing; tasks come from Linear only and clock-out text is **not saved** |

Both backends use the same conventions: a note is a todo source when it
contains `#todo` (or any tag in `notes.todo_tags`), a task is a line like
`- [ ] reply to Dana`, and the daily note is titled `Daily YYYY-MM-DD`. Set
`notes.markdown_dir` to your vault to use it directly.

## Install

```bash
git clone <this repo> ~/code/lock-in-or-clock-out
cd ~/code/lock-in-or-clock-out
./install.sh
python3 brain/lioco.py doctor
```

`install.sh` installs Hammerspoon and icalBuddy via Homebrew, symlinks the
module into `~/.hammerspoon/lioco`, adds `require("lioco")` to your init, and
writes `~/.config/lioco/config.json` from `config.example.json`.

Permissions you will be asked for:

- Hammerspoon → Accessibility (window watching, input counts).
- Hammerspoon → Full Disk Access, only if you use Bear and todos do not appear.
- icalBuddy → Calendars, on first run.

Optional environment variables, read from the login shell Hammerspoon inherits:

- `LINEAR_API_KEY` for Linear issues.
- `SLACK_USER_TOKEN` (needs `users.profile:write` and `users:write`) for the
  Slack away step.

## Configure

Edit `~/.config/lioco/config.json`. The useful knobs:

| Key | Default | Meaning |
|---|---|---|
| `hours.wind_down` / `hours.hard_stop` | 16:30 / 18:30 | when the buttons switch to clock-out |
| `churn_threshold` | 0.6 | drift score that counts as "not locked in" |
| `sustain_evaluations` | 3 | consecutive drifting minutes before a nudge |
| `cooldown_minutes` | 25 | minimum gap between nudges |
| `work_dirs` | `~/code` | where "output" is checked |
| `notes.backend` | `auto` | `bear`, `markdown`, `auto`, or `none` |
| `notes.markdown_dir` | `~/Documents/lioco-notes` | folder for the markdown backend |
| `notes.todo_tags` | `["todo"]` | tags whose unchecked boxes are your tasks |
| `notes.daily_note_title` | `Daily {date}` | where clock-out entries go |
| `winddown.*` | | default checkboxes on the clock-out form |

Reload Hammerspoon after editing (menubar dot → Reload config).

## Privacy

Everything runs locally. There is no server and no telemetry.

- The observer records app names, switch counts, and keystroke/click/scroll
  **counts**. It never records window titles, URLs, or what you typed. Browser
  tab switching is detected as "the title changed", and the title itself is
  discarded.
- The event log at `~/.local/share/lioco/events.jsonl` contains scores, counts,
  the top app name per window, and which button you pressed. Delete it any time.
- The Bear backend copies Bear's database to a temp directory to read it without
  fighting Bear for the lock. The copy is deleted as soon as the read finishes.
- **Clock out with "Park browser tabs" checked writes the title and URL of every
  open tab into your daily note.** Uncheck it on the card if that is not what
  you want that day, or set `winddown.park_tabs` to `false`.
- Meeting prep writes the meeting title, attendee names, and invite notes into
  a prep note. Nothing leaves your notes app.
- Linear and Slack are only contacted if you set `LINEAR_API_KEY` or
  `SLACK_USER_TOKEN`. Keys are read from the environment, never stored.

## Layout

```
hammerspoon/lioco/   Hammerspoon module (Lua)
  observer.lua       app/window/tab/input watchers
  churn.lua          pure scoring
  modes.lua          time of day → which two buttons
  card.lua           the floating two-button card (hs.webview)
  brain.lua          runs the Python brain
  menubar.lua        colored dot + menu
  init.lua           evaluate loop, nudges, actions
brain/lioco.py       Python brain entry (prints JSON)
brain/lioco_brain/   cal (icalBuddy), notes (shared todo/search logic), bear + markdown backends,
                     linear, rank, browser, winddown, cli
tests/               python3 -m unittest tests.test_brain ; lua5.4 tests/test_lua.lua
```

## Brain CLI

```bash
python3 brain/lioco.py context            # next meeting, in_meeting, todo count
python3 brain/lioco.py tasks --limit 6    # ranked tasks; add --small for wind-down
python3 brain/lioco.py prep --no-write    # meeting prep without creating the note
python3 brain/lioco.py winddown --note "..." --tomorrow "..." --park-tabs
python3 brain/lioco.py stats --days 7     # drift by hour, nudges, responses
python3 brain/lioco.py doctor
```
