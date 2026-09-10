local M = {}

local COLORS = {
  ["locked in"] = { hex = "#3fb950" },
  ["wobbly"] = { hex = "#d29922" },
  ["drifting"] = { hex = "#f85149" },
  ["away"] = { hex = "#8b949e" },
  ["paused"] = { hex = "#8b949e" },
  ["focus"] = { hex = "#58a6ff" },
  ["break"] = { hex = "#a371f7" },
  ["warming up"] = { hex = "#8b949e" },
}

function M.init(handlers)
  M.bar = hs.menubar.new()
  M.handlers = handlers
  M.status = { label = "warming up", detail = "", extra = "" }
  M.render()
end

function M.set(label, detail, extra)
  M.status = { label = label, detail = detail or "", extra = extra or "" }
  M.render()
end

function M.render()
  if not M.bar then return end
  local s = M.status
  local color = (COLORS[s.label] or COLORS["warming up"]).hex
  local dot = hs.styledtext.new("●", { color = { hex = color }, font = { size = 12 } })
  local text = s.extra ~= "" and hs.styledtext.new(" " .. s.extra, { font = { size = 12 } }) or hs.styledtext.new("")
  M.bar:setTitle(dot .. text)

  local h = M.handlers
  M.bar:setMenu(function()
    return {
      { title = "lioco: " .. s.label .. (s.detail ~= "" and (" · " .. s.detail) or ""), disabled = true },
      { title = "-" },
      { title = "Lock in (show tasks)", fn = h.tasks },
      { title = "Prep next meeting", fn = h.prep },
      { title = "Take a break", fn = h.breakNow },
      { title = "Clock out", fn = h.winddown },
      { title = "-" },
      { title = "Nudge me now (test)", fn = h.nudgeNow },
      { title = "Pause for 1 hour", fn = h.pauseHour },
      { title = "Resume", fn = h.resume },
      { title = "-" },
      { title = "Open event log", fn = h.openLog },
      { title = "Reload config", fn = h.reload },
    }
  end)
end

return M
