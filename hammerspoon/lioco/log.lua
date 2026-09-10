-- Append-only JSONL log so thresholds can be tuned against real behavior.
local M = { path = nil }

function M.init(path)
  M.path = path
  local dir = path:match("^(.*)/[^/]*$")
  if dir then os.execute(string.format("mkdir -p '%s'", dir)) end
end

function M.write(kind, data)
  if not M.path then return end
  data = data or {}
  data.kind = kind
  data.t = os.date("%Y-%m-%dT%H:%M:%S")
  local ok, line = pcall(hs.json.encode, data)
  if not ok then return end
  local f = io.open(M.path, "a")
  if f then
    f:write(line, "\n")
    f:close()
  end
end

return M
