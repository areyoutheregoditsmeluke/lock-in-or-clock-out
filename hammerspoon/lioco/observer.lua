-- Watches app/window/tab switches and input rhythm. Never records content,
-- only counts, app names, and (for browsers) that the tab title changed.
local M = {}

local events = {}       -- { t, kind = "app"|"window"|"title", app }
local buckets = {}      -- per-minute { t, keys, clicks, scrolls }
local cur = { t = os.time(), keys = 0, clicks = 0, scrolls = 0 }
local MAX_AGE = 60 * 60
local lastTitleKey = {}
local lastScroll = 0
local browsers = {}

M.onEvent = nil

local function prune()
  local cutoff = os.time() - MAX_AGE
  while events[1] and events[1].t < cutoff do table.remove(events, 1) end
  while buckets[1] and buckets[1].t < cutoff do table.remove(buckets, 1) end
end

local function push(kind, app)
  local ev = { t = os.time(), kind = kind, app = app or "?" }
  events[#events + 1] = ev
  prune()
  if M.onEvent then M.onEvent(ev) end
end

local function isBrowser(name)
  return name and browsers[name] == true
end

function M.start(cfg)
  for _, b in ipairs(cfg.browsers or {}) do browsers[b] = true end

  M.appWatcher = hs.application.watcher.new(function(name, event, _)
    if event == hs.application.watcher.activated and name then
      push("app", name)
    end
  end)
  M.appWatcher:start()

  M.wf = hs.window.filter.new(nil)
  M.wf:subscribe(hs.window.filter.windowFocused, function(w, appName)
    push("window", appName)
  end)
  -- Browsers change the window title when the active tab changes.
  M.wf:subscribe(hs.window.filter.windowTitleChanged, function(w, appName)
    if not isBrowser(appName) then return end
    local fw = hs.window.focusedWindow()
    if not fw or not w or fw:id() ~= w:id() then return end
    local key = tostring(w:id()) .. ":" .. (w:title() or "")
    if lastTitleKey[w:id()] ~= key then
      lastTitleKey[w:id()] = key
      push("title", appName)
    end
  end)

  local types = hs.eventtap.event.types
  M.tap = hs.eventtap.new({ types.keyDown, types.leftMouseDown, types.rightMouseDown, types.scrollWheel },
    function(e)
      local ty = e:getType()
      if ty == types.keyDown then
        cur.keys = cur.keys + 1
      elseif ty == types.scrollWheel then
        local now = hs.timer.secondsSinceEpoch()
        if now - lastScroll > 0.5 then cur.scrolls = cur.scrolls + 1 end
        lastScroll = now
      else
        cur.clicks = cur.clicks + 1
      end
      return false
    end)
  M.tap:start()

  M.flush = hs.timer.doEvery(60, function()
    buckets[#buckets + 1] = cur
    cur = { t = os.time(), keys = 0, clicks = 0, scrolls = 0 }
    prune()
  end)

  local front = hs.application.frontmostApplication()
  if front then push("app", front:name()) end
end

function M.stop()
  if M.appWatcher then M.appWatcher:stop() end
  if M.wf then M.wf:unsubscribeAll() end
  if M.tap then M.tap:stop() end
  if M.flush then M.flush:stop() end
end

-- All events with t >= since, plus the last app seen before the window.
function M.events(since)
  local out, before = {}, nil
  for _, ev in ipairs(events) do
    if ev.t >= since then
      out[#out + 1] = ev
    elseif ev.kind == "app" then
      before = ev.app
    end
  end
  return out, before
end

-- Input totals since a timestamp (includes the in-progress minute).
function M.input(since)
  local keys, clicks, scrolls = cur.keys, cur.clicks, cur.scrolls
  for _, b in ipairs(buckets) do
    if b.t >= since then
      keys, clicks, scrolls = keys + b.keys, clicks + b.clicks, scrolls + b.scrolls
    end
  end
  return { keys = keys, clicks = clicks, scrolls = scrolls }
end

function M.currentApp()
  local a = hs.application.frontmostApplication()
  return a and a:name() or nil
end

return M
