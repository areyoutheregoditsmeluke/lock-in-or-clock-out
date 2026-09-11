-- Run with: lua5.4 tests/test_lua.lua  (from repo root)
package.path = "hammerspoon/?.lua;hammerspoon/?/init.lua;" .. package.path

-- Minimal hs stub so pure modules load outside Hammerspoon.
hs = { json = { read = function() return nil end } }

local churn = require("lioco.churn")
local modes = require("lioco.modes")
local config = require("lioco.config")

local function assertf(cond, msg) if not cond then error("FAIL: " .. msg, 2) end print("ok  " .. msg) end
local function near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end

local now = 1000000
local W = 15 * 60

-- Locked in: one app for 15 min, heavy typing, a file changed.
local res = churn.score({}, "Code", { keys = 900, clicks = 20, scrolls = 5 }, now, W, true)
assertf(res.score < 0.2, string.format("locked-in scores low (%.2f)", res.score))
assertf(res.top_app == "Code" and near(res.top_share, 1), "single app has full share")

-- Drifting: Slack <-> Chrome <-> Mail every 20 s, tab hopping, scroll/click only, nothing produced.
local evs = {}
local apps = { "Slack", "Google Chrome", "Slack", "Mail", "Google Chrome" }
for i = 0, 44 do
  local t = now - W + i * 20
  local app = apps[(i % #apps) + 1]
  evs[#evs + 1] = { t = t, kind = "app", app = app }
  evs[#evs + 1] = { t = t, kind = "window", app = app }
  if app == "Google Chrome" then evs[#evs + 1] = { t = t + 5, kind = "title", app = app } end
end
res = churn.score(evs, "Code", { keys = 30, clicks = 80, scrolls = 120 }, now, W, false)
assertf(res.score >= 0.6, string.format("drifting scores high (%.2f)", res.score))
assertf(res.counts.return_trips > 5, "return trips detected: " .. res.counts.return_trips)
assertf(res.counts.tab_switches > 0, "tab switches counted")

-- Same churn but with real output lowers the score.
local res2 = churn.score(evs, "Code", { keys = 30, clicks = 80, scrolls = 120 }, now, W, true)
assertf(res2.score < res.score, "recent output lowers score")

-- Research pattern: many tab switches but heavy typing should not fire.
local evs3 = {}
for i = 0, 30 do evs3[#evs3 + 1] = { t = now - W + i * 30, kind = "title", app = "Google Chrome" } end
res = churn.score(evs3, "Google Chrome", { keys = 700, clicks = 40, scrolls = 40 }, now, W, nil)
assertf(res.score < 0.6, string.format("research with typing stays under threshold (%.2f)", res.score))

-- No activity at all: score is zero (idle handled by caller).
res = churn.score({}, "Slack", { keys = 0, clicks = 0, scrolls = 0 }, now, W, nil)
assertf(res.score == 0, "no input -> 0")

assertf(churn.label({ score = 0.7 }, 0.6) == "drifting", "label drifting")
assertf(churn.label({ score = 0.4 }, 0.6) == "wobbly", "label wobbly")
assertf(churn.label({ score = 0.1 }, 0.6) == "locked in", "label locked in")

-- Modes by time of day (use a fixed Wednesday).
local cfg = config.load()
local function at(h, m) return os.time({ year = 2026, month = 9, day = 9, hour = h, min = m, sec = 0 }) end
assertf(modes.period(cfg, at(7, 0)) == nil, "before day start is off")
assertf(modes.period(cfg, at(9, 0)) == "morning", "9am morning")
assertf(modes.period(cfg, at(12, 30)) == "lunch", "12:30 lunch")
assertf(modes.period(cfg, at(15, 0)) == "afternoon", "3pm afternoon")
assertf(modes.period(cfg, at(17, 0)) == "wind_down", "5pm wind down")
assertf(modes.period(cfg, at(19, 0)) == "hard_stop", "7pm hard stop")
assertf(modes.isWorkday(cfg, at(9, 0)), "wednesday is a workday")
assertf(not modes.isWorkday(cfg, os.time({ year = 2026, month = 9, day = 12, hour = 9 })), "saturday is not")

local st = { driftMinutes = 12, level = 1 }
local m = modes.pick(cfg, nil, st, at(17, 0))
assertf(m.id == "wind_down" and m.secondary.action == "winddown" and m.primary.small, "5pm -> lock in small / clock out")
m = modes.pick(cfg, nil, st, at(9, 30))
assertf(m.id == "morning" and m.primary.action == "tasks", "morning -> lock in")
m = modes.pick(cfg, nil, st, at(15, 0))
assertf(m.id == "afternoon_walk" and m.primary.action == "break", "afternoon, no break yet -> walk")
m = modes.pick(cfg, nil, { driftMinutes = 12, level = 1, lastBreak = at(14, 30) }, at(15, 0))
assertf(m.id == "afternoon_focus" and m.primary.action == "tasks", "afternoon after break -> lock in")
m = modes.pick(cfg, { next_meeting = { title = "Standup", minutes_until = 40 } }, st, at(15, 0))
assertf(m.id == "pre_meeting" and m.primary.action == "prep" and m.secondary.action == "break" and m.secondary.minutes == 30, "meeting in 40 -> prep / walk 30")
m = modes.pick(cfg, { next_meeting = { title = "Standup", minutes_until = 15 } }, st, at(15, 0))
assertf(m.id == "pre_meeting" and m.secondary.action == "tasks", "meeting in 15 -> prep / lock in")
m = modes.pick(cfg, { next_meeting = { title = "Standup", minutes_until = 5 } }, st, at(15, 0))
assertf(m.id == "afternoon_walk", "meeting in 5 is below prep window")
m = modes.pick(cfg, { next_meeting = { title = "X", minutes_until = 30 } }, { level = 2 }, at(19, 0))
assertf(m.id == "hard_stop" and m.size == "large" and m.primary.action == "winddown", "hard stop wins, escalates to large")

print("all lua tests passed")

-- Meeting detection (pure parts).
local meeting = require("lioco.meeting")
local ts = meeting.parseISO("2026-09-11T14:45")
assertf(ts == os.time({ year = 2026, month = 9, day = 11, hour = 14, min = 45, sec = 0 }), "parseISO minutes")
assertf(meeting.parseISO("2026-09-11T14:45:30") == ts + 30, "parseISO with seconds")
assertf(meeting.parseISO("garbage") == nil and meeting.parseISO(nil) == nil, "parseISO rejects junk")
local ctx = { meetings = {
  { title = "Standup", start = "2026-09-11T14:45", ["end"] = "2026-09-11T15:15" },
  { title = "No end", start = "2026-09-11T16:00" },
} }
assertf(meeting.inCalendarMeeting(ctx, ts + 600).title == "Standup", "inside standup")
assertf(meeting.inCalendarMeeting(ctx, ts - 60) == nil, "one minute before standup is not in meeting")
assertf(meeting.inCalendarMeeting(ctx, ts + 30 * 60) == nil, "end is exclusive")
local t16 = meeting.parseISO("2026-09-11T16:00")
assertf(meeting.inCalendarMeeting(ctx, t16 + 29 * 60).title == "No end", "missing end defaults to 30 min")
assertf(meeting.inCalendarMeeting(ctx, t16 + 31 * 60) == nil, "default 30 min expires")
assertf(meeting.inCalendarMeeting(nil, ts) == nil and meeting.inCalendarMeeting({}, ts) == nil, "no ctx is fine")
local pats = cfg.meeting_window_patterns
assertf(meeting.titleMatches({ "Zoom Meeting" }, pats) ~= nil, "zoom meeting window")
assertf(meeting.titleMatches({ "Meet - abc-defg-hij - Google Chrome" }, pats) ~= nil, "google meet tab")
assertf(meeting.titleMatches({ "Zoom", "Home", "GitHub - Google Chrome" }, pats) == nil, "zoom home window is not a call")
assertf(meeting.titleMatches({ "Huddle: #eng" }, pats) ~= nil, "slack huddle")
print("meeting tests passed")
