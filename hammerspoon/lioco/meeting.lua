-- Am I in a meeting? Any of these count:
--   * a calendar event is happening right now (from the brain's meetings list)
--   * the microphone or a camera is in use (Zoom, Meet, Teams, Slack huddle, FaceTime)
--   * a meeting app or browser has a window whose title looks like a live call
local M = {}

-- "2026-09-11T14:45" or "2026-09-11T14:45:00" -> epoch seconds (local time)
function M.parseISO(s)
  if type(s) ~= "string" then return nil end
  local y, mo, d, h, mi, se = s:match("^(%d+)%-(%d+)%-(%d+)T(%d+):(%d+):?(%d*)")
  if not y then return nil end
  return os.time({ year = tonumber(y), month = tonumber(mo), day = tonumber(d),
    hour = tonumber(h), min = tonumber(mi), sec = tonumber(se) or 0 })
end

-- Returns the meeting table if one is happening at `now`, else nil.
function M.inCalendarMeeting(ctx, now)
  for _, m in ipairs(ctx and ctx.meetings or {}) do
    local s = M.parseISO(m.start)
    local e = m["end"] and M.parseISO(m["end"]) or (s and s + 30 * 60)
    if s and e and now >= s and now < e then return m end
  end
  return nil
end

local function micInUse()
  local ok, dev = pcall(hs.audiodevice.defaultInputDevice)
  if not ok or not dev then return false end
  local ok2, inUse = pcall(function() return dev:inUse() end)
  return ok2 and inUse == true
end

local function cameraInUse()
  local ok, cams = pcall(hs.camera.allCameras)
  if not ok then return false end
  for _, c in ipairs(cams or {}) do
    local ok2, inUse = pcall(function() return c:isInUse() end)
    if ok2 and inUse == true then return true end
  end
  return false
end

-- Pure: does any title match any pattern? (patterns are Lua patterns)
function M.titleMatches(titles, patterns)
  for _, t in ipairs(titles) do
    for _, pat in ipairs(patterns or {}) do
      if t:find(pat) then return t end
    end
  end
  return nil
end

local function callWindow(cfg)
  local names = {}
  for _, n in ipairs(cfg.meeting_apps or {}) do names[#names + 1] = n end
  for _, n in ipairs(cfg.browsers or {}) do names[#names + 1] = n end
  local titles = {}
  for _, name in ipairs(names) do
    local app = hs.application.get(name)
    if app then
      for _, w in ipairs(app:allWindows()) do
        local t = w:title()
        if t and t ~= "" then titles[#titles + 1] = t end
      end
    end
  end
  return M.titleMatches(titles, cfg.meeting_window_patterns)
end

-- Returns a short reason string when in a meeting, else nil.
function M.detect(cfg, ctx, now)
  local m = M.inCalendarMeeting(ctx, now or os.time())
  if m then return "calendar: " .. (m.title or "meeting") end
  if micInUse() then return "microphone in use" end
  if cameraInUse() then return "camera in use" end
  local t = callWindow(cfg)
  if t then return "call window: " .. t end
  return nil
end

return M
