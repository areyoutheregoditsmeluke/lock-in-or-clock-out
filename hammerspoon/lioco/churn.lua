-- Pure scoring. Turns a window of switch events and input counts into a
-- 0..1 "drift" score. High switching + no typing + no output = drifting.
local M = {}

local function clamp(x, lo, hi)
  if x < lo then return lo elseif x > hi then return hi end
  return x
end

-- events: list of {t, kind, app}; before: app active at window start
-- input: {keys, clicks, scrolls}; now, windowSec; recentOutput: bool|nil
function M.score(events, before, input, now, windowSec, recentOutput)
  local minutes = windowSec / 60
  local cutoff = now - windowSec

  local appSwitches, intraSwitches, tabSwitches, returnTrips = 0, 0, 0, 0
  local seq = {}
  local timeIn = {}
  local distinct = {}

  local curApp = before
  local curStart = cutoff
  local lastApp = before

  for _, ev in ipairs(events) do
    if ev.kind == "app" then
      if ev.app ~= curApp then
        if curApp then timeIn[curApp] = (timeIn[curApp] or 0) + (ev.t - curStart) end
        curApp, curStart = ev.app, ev.t
        appSwitches = appSwitches + 1
        seq[#seq + 1] = ev.app
        distinct[ev.app] = true
        if #seq >= 3 and seq[#seq] == seq[#seq - 2] and seq[#seq] ~= seq[#seq - 1] then
          returnTrips = returnTrips + 1
        end
      end
      lastApp = ev.app
    elseif ev.kind == "window" then
      -- window focus that is not part of an app switch = intra-app switch
      if ev.app == lastApp then intraSwitches = intraSwitches + 1 end
    elseif ev.kind == "title" then
      tabSwitches = tabSwitches + 1
    end
  end
  if curApp then timeIn[curApp] = (timeIn[curApp] or 0) + (now - curStart) end

  local total, maxShare, topApp = 0, 0, nil
  for app, secs in pairs(timeIn) do total = total + secs end
  if total > 0 then
    for app, secs in pairs(timeIn) do
      if secs / total > maxShare then maxShare, topApp = secs / total, app end
    end
  else
    maxShare = 1
  end

  local nDistinct = 0
  for _ in pairs(distinct) do nDistinct = nDistinct + 1 end

  -- Components (each 0..1, higher = more drift)
  local weightedSwitches = appSwitches + 0.7 * intraSwitches + 0.5 * tabSwitches
  local switching = clamp((weightedSwitches / minutes) / 4, 0, 1)       -- 4/min saturates
  local bouncing = clamp((returnTrips / minutes) / 1.5, 0, 1)            -- 1.5 A-B-A/min saturates
  local fragmentation = clamp(1 - maxShare, 0, 1)
  local keysPerMin = input.keys / minutes
  local typing = clamp(keysPerMin / 60, 0, 1)                            -- 60 keys/min = solid typing
  local acts = input.keys + input.clicks + input.scrolls
  local passive = acts > 0 and (input.clicks + input.scrolls) / acts or 0
  local consuming = passive * (1 - typing)

  local raw = 0.35 * switching + 0.2 * bouncing + 0.2 * fragmentation + 0.25 * consuming

  local adjusted = raw
  if recentOutput == true then adjusted = adjusted - 0.2 end
  if acts == 0 then adjusted = 0 end -- nothing happening at all; idle handled elsewhere
  adjusted = clamp(adjusted, 0, 1)

  return {
    score = adjusted,
    raw = raw,
    components = {
      switching = switching,
      bouncing = bouncing,
      fragmentation = fragmentation,
      consuming = consuming,
      typing = typing,
    },
    counts = {
      app_switches = appSwitches,
      intra_switches = intraSwitches,
      tab_switches = tabSwitches,
      return_trips = returnTrips,
      distinct_apps = nDistinct,
      keys = input.keys,
      clicks = input.clicks,
      scrolls = input.scrolls,
    },
    top_app = topApp,
    top_share = maxShare,
    recent_output = recentOutput,
  }
end

function M.label(result, threshold)
  if not result then return "warming up" end
  if result.score >= threshold then return "drifting" end
  if result.score >= threshold * 0.6 then return "wobbly" end
  return "locked in"
end

return M
