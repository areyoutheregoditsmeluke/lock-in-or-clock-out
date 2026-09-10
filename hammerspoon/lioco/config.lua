-- Loads defaults and merges ~/.config/lioco/config.json on top.
local M = {}

local HOME = os.getenv("HOME") or ""

local function expand(p)
  if type(p) ~= "string" then return p end
  return (p:gsub("^~", HOME))
end

M.defaults = {
  brain_path = expand("~/code/lock-in-or-clock-out/brain/lioco.py"),
  python = "/usr/bin/python3",

  poll_seconds = 60,
  window_minutes = 15,
  churn_threshold = 0.6,
  sustain_evaluations = 3,
  cooldown_minutes = 25,
  snooze_minutes = 10,
  idle_reset_seconds = 300,
  focus_block_minutes = 25,
  weekdays_only = true,

  hours = {
    day_start = "08:00",
    lunch = "12:00",
    afternoon = "13:30",
    wind_down = "16:30",
    hard_stop = "18:30",
  },

  meeting_prep_window_minutes = { 10, 60 },
  walk_min_gap_minutes = 25,
  break_minutes = 15,
  lunch_minutes = 30,

  work_dirs = { expand("~/code") },
  browsers = { "Google Chrome", "Arc", "Safari", "Brave Browser", "Firefox" },
  meeting_apps = { "zoom.us" },

  bear = {
    todo_tags = { "todo" },
    daily_note_title = "Daily {date}",
    daily_note_tag = "daily",
  },
  linear = { api_key_env = "LINEAR_API_KEY" },
  winddown = {
    park_tabs = true,
    quit_apps = { "Slack" },
    slack_away = true,
    lock_screen = false,
  },

  log_path = expand("~/.local/share/lioco/events.jsonl"),
}

local function isArray(t)
  return type(t) == "table" and #t > 0
end

local function deepcopy(v)
  if type(v) ~= "table" then return v end
  local out = {}
  for k, x in pairs(v) do out[k] = deepcopy(x) end
  return out
end

-- Maps merge recursively. Arrays replace wholesale.
local function merge(dst, src)
  for k, v in pairs(src) do
    if type(v) == "table" and type(dst[k]) == "table" and not isArray(v) and not isArray(dst[k]) then
      merge(dst[k], v)
    else
      dst[k] = deepcopy(v)
    end
  end
  return dst
end

M.path = expand("~/.config/lioco/config.json")

function M.load()
  local cfg = deepcopy(M.defaults)
  local ok, user = pcall(hs.json.read, M.path)
  if ok and type(user) == "table" then
    merge(cfg, user)
  end
  cfg.brain_path = expand(cfg.brain_path)
  cfg.log_path = expand(cfg.log_path)
  for i, d in ipairs(cfg.work_dirs or {}) do cfg.work_dirs[i] = expand(d) end
  return cfg
end

-- "16:30" -> 990 (minutes since midnight)
function M.hm(s)
  local h, m = tostring(s):match("^(%d+):(%d+)$")
  if not h then return 0 end
  return tonumber(h) * 60 + tonumber(m)
end

return M
