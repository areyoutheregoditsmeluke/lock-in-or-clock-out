-- lioco: lock in or clock out.
-- Watches for "high switching, no output" and, depending on time of day,
-- offers two buttons: lock in on a task / prep the next meeting / take a
-- walk / clock out with a wind-down ritual.
local config = require("lioco.config")
local log = require("lioco.log")
local observer = require("lioco.observer")
local churn = require("lioco.churn")
local modes = require("lioco.modes")
local brain = require("lioco.brain")
local card = require("lioco.card")
local bar = require("lioco.menubar")
local meeting = require("lioco.meeting")

local M = {}
local cfg = config.load()

local state = {
  sustain = 0,
  driftStart = nil,
  lastNudge = 0,
  lastNudgeAnswered = true,
  level = 1,
  lastBreak = nil,
  breakUntil = nil,
  breakTimer = nil,
  focusUntil = nil,
  focusTask = nil,
  snoozeUntil = 0,
  pausedUntil = 0,
  recentOutput = nil,
  ctx = nil,
  ctxAt = 0,
  last = nil,
}

local function now() return os.time() end
local function minutes(n) return n * 60 end

------------------------------------------------------------------------
-- Output check: did any file under work_dirs change in the last 20 min?
------------------------------------------------------------------------
local function refreshOutput()
  if not cfg.work_dirs or #cfg.work_dirs == 0 then state.recentOutput = nil; return end
  local args = {}
  for _, d in ipairs(cfg.work_dirs) do args[#args + 1] = d end
  for _, a in ipairs({ "-type", "f", "-mmin", "-20",
    "-not", "-path", "*/.git/*", "-not", "-path", "*/node_modules/*",
    "-not", "-path", "*/.venv/*", "-not", "-name", ".DS_Store", "-print", "-quit" }) do
    args[#args + 1] = a
  end
  hs.task.new("/usr/bin/find", function(_, out)
    state.recentOutput = (out or ""):match("%S") ~= nil
  end, args):start()
end

------------------------------------------------------------------------
-- Context from the brain (calendar, tasks). Cached for 5 minutes.
------------------------------------------------------------------------
local function refreshContext(cb)
  if state.ctx and now() - state.ctxAt < minutes(5) then
    if cb then cb(state.ctx) end
    return
  end
  brain.run(cfg, { "context" }, function(ok, data)
    if ok then
      state.ctx = data
      state.ctxAt = now()
    else
      log.write("brain_error", { where = "context", err = data })
    end
    if cb then cb(state.ctx) end
  end)
end

------------------------------------------------------------------------
-- Actions
------------------------------------------------------------------------
local actions = {}

local function markAnswered(action)
  state.lastNudgeAnswered = true
  state.level = 1
  log.write("response", { action = action })
end

function actions.snooze()
  state.snoozeUntil = now() + minutes(cfg.snooze_minutes)
  state.sustain = 0
  card.hide()
end

function actions.close()
  -- Dismissed without choosing. Counts as ignored, so the next nudge escalates.
  state.lastNudgeAnswered = false
  state.sustain = 0
  card.hide()
  log.write("response", { action = "dismissed" })
end

function actions.breakStart(mins, why)
  mins = mins or cfg.break_minutes
  card.hide()
  state.lastBreak = now()
  state.breakUntil = now() + minutes(mins)
  state.sustain = 0
  if state.breakTimer then state.breakTimer:stop() end
  local back = modes.clock(state.breakUntil)
  local msg = string.format("Walk. Be back by %s.", back)
  local mtg = state.ctx and state.ctx.next_meeting
  if mtg and mtg.minutes_until and mtg.minutes_until > mins then
    msg = string.format("Walk. Be back by %s for %s at %s.", back, mtg.title or "your meeting", mtg.start_clock or "")
  end
  hs.notify.new({ title = "Break", informativeText = msg, withdrawAfter = 15 }):send()
  bar.set("break", "until " .. back, "🚶 " .. back)
  state.breakTimer = hs.timer.doAfter(minutes(mins), function()
    state.breakUntil = nil
    local text = "Break is over. Back to one thing."
    if mtg and mtg.minutes_until then
      text = string.format("Break is over. %s is coming up.", mtg.title or "Your meeting")
    end
    hs.notify.new({ title = "Back", informativeText = text, withdrawAfter = 20 }):send()
    bar.set("locked in", "", "")
  end)
  log.write("break", { minutes = mins, why = why })
end

function actions.showTasks(opts)
  opts = opts or {}
  card.show({ kicker = "lioco", title = "Pulling your tasks…", size = "small" })
  local args = { "tasks", "--limit", "6" }
  if opts.small then args[#args + 1] = "--small" end
  brain.run(cfg, args, function(ok, data)
    if not ok then
      card.show({ kicker = "lioco", title = "Could not load tasks", pre = data.error or "unknown error",
        primary = { label = "OK", action = "close" } }, function() card.hide() end)
      return
    end
    local items = {}
    for _, t in ipairs(data.tasks or {}) do
      local badges = {}
      if t.hot then badges[#badges + 1] = { text = "important", kind = "hot" } end
      if t.small then badges[#badges + 1] = { text = "small", kind = "small" } end
      if t.source then badges[#badges + 1] = { text = t.source } end
      items[#items + 1] = { text = t.text, sub = t.sub, url = t.url, badges = badges, task = t }
    end
    local title = opts.small and "One small thing, then stop." or "Pick one. Just one."
    if #items == 0 then title = "No open tasks found." end
    card.show({
      kicker = "lioco · lock in",
      title = title,
      body = #items == 0 and "Add unchecked boxes to a Bear note tagged #todo, or set LINEAR_API_KEY." or nil,
      items = items,
      note = string.format("Pick one to start a %d-minute focus block. Nudges pause while you work.", cfg.focus_block_minutes),
      primary = nil,
      secondary = { label = "Not now", action = "close" },
      size = opts.size or "small",
    }, function(action, payload)
      if action == "item" and payload.item then
        actions.focus(payload.item.task, payload.item.url)
      elseif action == "secondary" or action == "close" then
        actions.close()
      end
    end)
  end)
end

function actions.focus(task, url)
  card.hide()
  state.focusUntil = now() + minutes(cfg.focus_block_minutes)
  state.focusTask = task and task.text or "task"
  state.sustain = 0
  if url and url ~= "" then hs.urlevent.openURL(url) end
  bar.set("focus", state.focusTask, "🔒")
  hs.notify.new({ title = "Locked in", informativeText = state.focusTask, withdrawAfter = 8 }):send()
  log.write("focus", { task = state.focusTask, minutes = cfg.focus_block_minutes })
  hs.timer.doAfter(minutes(cfg.focus_block_minutes), function()
    if state.focusUntil and now() >= state.focusUntil then
      state.focusUntil = nil
      state.focusTask = nil
      bar.set("locked in", "", "")
    end
  end)
end

function actions.prep()
  card.show({ kicker = "lioco", title = "Building your prep…", size = "small" })
  brain.run(cfg, { "prep" }, function(ok, data)
    if not ok or not data.meeting then
      card.show({ kicker = "lioco", title = "No upcoming meeting found",
        pre = data and data.error or nil,
        primary = { label = "OK", action = "close" } }, function() card.hide() end)
      return
    end
    local m = data.meeting
    local items = {}
    for _, n in ipairs(data.related_notes or {}) do
      items[#items + 1] = { text = n.title, sub = n.snippet, url = n.url, badges = { { text = "note" } } }
    end
    for _, t in ipairs(data.related_tasks or {}) do
      items[#items + 1] = { text = t.text, sub = t.sub, url = t.url, badges = { { text = "todo" } } }
    end
    card.show({
      kicker = string.format("lioco · %s in %d min", m.title or "meeting", m.minutes_until or 0),
      title = m.title or "Meeting prep",
      body = data.summary,
      items = items,
      note = data.prep_note_url and "A prep note was created in Bear. Click below to open it." or nil,
      primary = data.prep_note_url and { label = "Open prep note", action = "primary" } or nil,
      secondary = { label = "Done", action = "close" },
      size = "large",
    }, function(action, payload)
      if action == "primary" and data.prep_note_url then
        hs.urlevent.openURL(data.prep_note_url)
      elseif action == "item" and payload.url then
        hs.urlevent.openURL(payload.url)
      elseif action == "secondary" or action == "close" then
        card.hide()
      end
    end)
    log.write("prep", { meeting = m.title })
  end)
end

function actions.winddown()
  local wd = cfg.winddown or {}
  card.show({
    kicker = "lioco · clock out",
    title = "Set it down.",
    body = "Two lines now saves you twenty minutes of re-finding the thread tomorrow.",
    form = {
      fields = {
        { name = "left_off", label = "Where did you leave off?", placeholder = "e.g. churn scorer works, card buttons not wired yet" },
        { name = "tomorrow", label = "First thing tomorrow", placeholder = "one concrete task" },
      },
      checks = {
        { name = "park_tabs", label = "Park browser tabs into the note", checked = wd.park_tabs ~= false },
        { name = "quit_apps", label = "Quit " .. table.concat(wd.quit_apps or {}, ", "), checked = (wd.quit_apps and #wd.quit_apps > 0) or false },
        { name = "slack_away", label = "Set Slack away", checked = wd.slack_away == true },
        { name = "lock_screen", label = "Lock screen", checked = wd.lock_screen == true },
      },
    },
    primary = { label = "Clock out", action = "winddown_go" },
    secondary = { label = "Not yet", action = "close" },
    size = "large",
  }, function(action, payload)
    if action == "primary" then
      local f = payload.form or {}
      local args = { "winddown", "--note", f.left_off or "", "--tomorrow", f.tomorrow or "" }
      if f.park_tabs then args[#args + 1] = "--park-tabs" end
      if f.quit_apps then args[#args + 1] = "--quit-apps" end
      if f.slack_away then args[#args + 1] = "--slack-away" end
      card.show({ kicker = "lioco", title = "Closing the day…", size = "small" })
      brain.run(cfg, args, function(ok, data)
        local lines = {}
        for _, s in ipairs(data and data.steps or {}) do lines[#lines + 1] = "• " .. s end
        if not ok then lines[#lines + 1] = "! " .. (data and data.error or "error") end
        card.show({
          kicker = "lioco · clocked out",
          title = "Done. Walk away.",
          pre = table.concat(lines, "\n"),
          primary = { label = "Bye", action = "primary" },
          size = "small",
        }, function()
          card.hide()
          if f.lock_screen then hs.caffeinate.lockScreen() end
        end)
        state.pausedUntil = now() + minutes(120)
        bar.set("paused", "clocked out", "")
        log.write("clock_out", { ok = ok, steps = data and data.steps })
      end)
    else
      actions.close()
    end
  end)
end

local function dispatch(mode, action, payload)
  local btn = payload and payload.button or {}
  local a = action
  if action == "primary" or action == "secondary" then a = btn.action end
  if a ~= "close" and a ~= "snooze" then markAnswered(a) end

  if a == "tasks" then actions.showTasks({ small = btn.small })
  elseif a == "prep" then actions.prep()
  elseif a == "break" then actions.breakStart(btn.minutes, mode.id)
  elseif a == "winddown" then actions.winddown()
  elseif a == "snooze" then actions.snooze()
  else actions.close() end
end

------------------------------------------------------------------------
-- Nudge
------------------------------------------------------------------------
local function nudge(force)
  if card.visible() and not force then return end
  if not state.lastNudgeAnswered and now() - state.lastNudge < minutes(60) then
    state.level = math.min(3, state.level + 1)
  end
  state.lastNudge = now()
  state.lastNudgeAnswered = false
  local drift = state.driftStart and math.floor((now() - state.driftStart) / 60) or 0

  refreshContext(function(ctx)
    local mode = modes.pick(cfg, ctx, { lastBreak = state.lastBreak, driftMinutes = drift, level = state.level })
    log.write("nudge", { mode = mode.id, level = state.level, drift = drift, score = state.last and state.last.score })
    card.show(mode, function(action, payload) dispatch(mode, action, payload) end)
    if state.level >= 2 then local snd = hs.sound.getByName("Glass"); if snd then snd:play() end end
  end)
end

------------------------------------------------------------------------
-- Evaluate loop
------------------------------------------------------------------------
local function evaluate()
  local t = now()
  if t < state.pausedUntil then bar.set("paused", "until " .. modes.clock(state.pausedUntil), ""); return end
  if not modes.isWorkday(cfg, t) or not modes.period(cfg, t) then bar.set("away", "off hours", ""); return end

  local idle = hs.host.idleTime()
  if idle > cfg.idle_reset_seconds then
    state.sustain = 0
    state.driftStart = nil
    bar.set("away", string.format("idle %dm", math.floor(idle / 60)), "")
    return
  end

  refreshOutput()
  refreshContext()

  -- In a meeting: switching windows is normal. Do not count it as drift.
  local meetingReason = meeting.detect(cfg, state.ctx, t)
  if meetingReason then
    state.sustain = 0
    state.driftStart = nil
    state.lastMeetingEnd = t
    bar.set("meeting", meetingReason, "")
    log.write("eval", { meeting = meetingReason, period = modes.period(cfg, t) })
    return
  end
  -- Short grace period after a call ends, so the post-meeting shuffle does not fire.
  if state.lastMeetingEnd and t - state.lastMeetingEnd < minutes(cfg.meeting_grace_minutes or 5) then
    state.sustain = 0
    state.driftStart = nil
    bar.set("locked in", "just left a meeting", "")
    return
  end

  local windowSec = minutes(cfg.window_minutes)
  local evs, before = observer.events(t - windowSec)
  local res = churn.score(evs, before, observer.input(t - windowSec), t, windowSec, state.recentOutput)
  state.last = res
  local label = churn.label(res, cfg.churn_threshold)

  log.write("eval", { score = res.score, raw = res.raw, c = res.components, n = res.counts, top = res.top_app,
    share = res.top_share, out = res.recent_output, period = modes.period(cfg, t) })

  if state.breakUntil and t < state.breakUntil then return end
  if state.focusUntil and t < state.focusUntil then
    bar.set("focus", state.focusTask or "", "🔒")
    return
  end

  local drifting = res.score >= cfg.churn_threshold
  if drifting then
    state.sustain = state.sustain + 1
    state.driftStart = state.driftStart or t
  else
    state.sustain = math.max(0, state.sustain - 1)
    if state.sustain == 0 then state.driftStart = nil end
  end

  local detail = string.format("%.2f · %s %d%%", res.score, res.top_app or "?", math.floor((res.top_share or 0) * 100))
  bar.set(label, detail, "")

  if t < state.snoozeUntil then return end

  local cooled = t - state.lastNudge > minutes(cfg.cooldown_minutes)
  local period = modes.period(cfg, t)
  if period == "hard_stop" and cooled then
    nudge()
  elseif state.sustain >= cfg.sustain_evaluations and cooled then
    nudge()
  end
end

------------------------------------------------------------------------
-- Wiring
------------------------------------------------------------------------
function M.start()
  cfg = config.load()
  log.init(cfg.log_path)
  observer.start(cfg)
  bar.init({
    tasks = function() actions.showTasks({}) end,
    prep = actions.prep,
    breakNow = function() actions.breakStart(cfg.break_minutes, "manual") end,
    winddown = actions.winddown,
    nudgeNow = function() state.driftStart = state.driftStart or now(); nudge(true) end,
    pauseHour = function() state.pausedUntil = now() + minutes(60); card.hide(); evaluate() end,
    resume = function() state.pausedUntil = 0; state.snoozeUntil = 0; evaluate() end,
    openLog = function() hs.execute(string.format("open -a Console '%s'", cfg.log_path)) end,
    reload = function() hs.reload() end,
  })
  M.timer = hs.timer.doEvery(cfg.poll_seconds, function()
    local ok, err = pcall(evaluate)
    if not ok then log.write("error", { err = tostring(err) }) end
  end)
  log.write("start", { cfg = { threshold = cfg.churn_threshold, window = cfg.window_minutes } })
  hs.notify.new({ title = "lioco", informativeText = "Watching. Menubar dot shows your focus state.", withdrawAfter = 5 }):send()
end

function M.stop()
  if M.timer then M.timer:stop() end
  observer.stop()
  card.hide()
end

M.state = state
M.evaluate = evaluate
M.nudge = nudge
M.actions = actions

M.start()
return M
