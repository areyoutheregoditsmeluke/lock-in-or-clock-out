-- Runs the Python brain and hands back parsed JSON.
local M = {}

function M.run(cfg, args, cb)
  local fullArgs = { cfg.brain_path }
  for _, a in ipairs(args) do fullArgs[#fullArgs + 1] = tostring(a) end

  local task = hs.task.new(cfg.python, function(exitCode, stdout, stderr)
    local ok, data = pcall(hs.json.decode, stdout or "")
    if ok and type(data) == "table" then
      if data.error and exitCode ~= 0 then
        cb(false, data, stderr)
      else
        cb(true, data, stderr)
      end
    else
      cb(false, { error = "brain returned no JSON", exit = exitCode, stdout = stdout, stderr = stderr }, stderr)
    end
  end, fullArgs)

  -- Inherit env so LINEAR_API_KEY / SLACK_USER_TOKEN from the shell are visible
  -- when Hammerspoon was launched from a login session that has them.
  local env = task:environment()
  env.PATH = (env.PATH or "") .. ":/opt/homebrew/bin:/usr/local/bin"
  task:setEnvironment(env)

  task:start()
  hs.timer.doAfter(25, function()
    if task:isRunning() then
      task:terminate()
      cb(false, { error = "brain timed out" }, "")
    end
  end)
  return task
end

return M
