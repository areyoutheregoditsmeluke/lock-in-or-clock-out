-- Picks what to say and which two buttons to show, based on time of day,
-- the next meeting, and what has already happened today.
local config = require("lioco.config")
local M = {}

-- "4:42 PM". Lua 5.4 rejects "%-I", so build it by hand.
local function fmtClock(t)
  local d = os.date("*t", t)
  local h12 = d.hour % 12
  if h12 == 0 then h12 = 12 end
  return string.format("%d:%02d %s", h12, d.min, d.hour < 12 and "AM" or "PM")
end
M.clock = fmtClock

local function minutesNow(now)
  local d = os.date("*t", now)
  return d.hour * 60 + d.min
end

-- Returns nil when we are outside working hours.
function M.period(cfg, now)
  local m = minutesNow(now)
  local h = cfg.hours
  if m < config.hm(h.day_start) then return nil end
  if m >= config.hm(h.hard_stop) then return "hard_stop" end
  if m >= config.hm(h.wind_down) then return "wind_down" end
  if m >= config.hm(h.afternoon) then return "afternoon" end
  if m >= config.hm(h.lunch) then return "lunch" end
  return "morning"
end

function M.isWorkday(cfg, now)
  if not cfg.weekdays_only then return true end
  local wd = os.date("*t", now).wday -- 1 = Sunday
  return wd >= 2 and wd <= 6
end

-- ctx: brain context (may be nil). state: { lastBreak, driftMinutes, level }
function M.pick(cfg, ctx, state, now)
  now = now or os.time()
  local period = M.period(cfg, now)
  local drift = state.driftMinutes or 0
  local kicker = string.format("%s · drifting for %d min", fmtClock(now), drift)
  local level = state.level or 1

  local mtg = ctx and ctx.next_meeting or nil
  local until_ = mtg and mtg.minutes_until or nil
  local lo, hi = cfg.meeting_prep_window_minutes[1], cfg.meeting_prep_window_minutes[2]

  -- Hard stop wins over everything.
  if period == "hard_stop" then
    return {
      id = "hard_stop", kicker = fmtClock(now) .. " · past your stop time",
      title = "You are done for today.",
      body = "Nothing good happens at the desk after this. Write down where you left off and walk away.",
      primary = { label = "Clock out", action = "winddown" },
      secondary = { label = "10 more minutes", action = "snooze" },
      size = level >= 2 and "large" or "small",
    }
  end

  -- A meeting is coming up: prep, or walk first if there is room.
  if until_ and until_ >= lo and until_ <= hi then
    local sec
    if until_ >= cfg.walk_min_gap_minutes then
      sec = { label = "Walk first", action = "break", minutes = math.max(10, until_ - 10) }
    else
      sec = { label = "Lock in", action = "tasks" }
    end
    return {
      id = "pre_meeting", kicker = kicker,
      title = string.format("%s starts in %d min.", mtg.title or "Your next meeting", until_),
      body = "You are not getting deep work done before it. Use the time to walk in prepared.",
      primary = { label = "Prep for it", action = "prep" },
      secondary = sec,
      size = "small",
    }
  end

  if period == "wind_down" then
    return {
      id = "wind_down", kicker = kicker,
      title = "Lock in or clock out?",
      body = "It is late in the day and you are tabbing around. Pick one small thing to finish, or close the day on purpose.",
      primary = { label = "One small task", action = "tasks", small = true },
      secondary = { label = "Clock out", action = "winddown" },
      size = level >= 2 and "large" or "small",
    }
  end

  if period == "afternoon" then
    local sinceBreak = state.lastBreak and (now - state.lastBreak) / 60 or 999
    if sinceBreak > 90 then
      return {
        id = "afternoon_walk", kicker = kicker,
        title = "Afternoon slump.",
        body = "Your attention has been bouncing for a while. A short walk will buy back the rest of the afternoon.",
        primary = { label = "Take a walk", action = "break", minutes = cfg.break_minutes },
        secondary = { label = "Lock in", action = "tasks" },
        size = "small",
      }
    end
    return {
      id = "afternoon_focus", kicker = kicker,
      title = "You already took a break. Lock in.",
      body = "Pick the next concrete task and give it one focused block.",
      primary = { label = "Lock in", action = "tasks" },
      secondary = { label = "Another break", action = "break", minutes = cfg.break_minutes },
      size = "small",
    }
  end

  if period == "lunch" then
    return {
      id = "lunch", kicker = kicker,
      title = "Step away for lunch?",
      body = "You are drifting around midday. Eat, move, then come back to one task.",
      primary = { label = "Take lunch", action = "break", minutes = cfg.lunch_minutes },
      secondary = { label = "Lock in", action = "tasks" },
      size = "small",
    }
  end

  -- morning (or unknown)
  return {
    id = "morning", kicker = kicker,
    title = "You have drifted. What is the one thing?",
    body = "Morning attention is the good stuff. Point it at something.",
    primary = { label = "Lock in", action = "tasks" },
    secondary = { label = "Short break", action = "break", minutes = 10 },
    size = "small",
  }
end

return M
