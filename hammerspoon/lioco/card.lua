-- A floating card with a title, body, optional list, optional form, and two
-- buttons. Built on hs.webview so both buttons are real buttons.
local M = {}

local function esc(s)
  s = tostring(s == nil and "" or s)
  return (s:gsub("[&<>\"']", { ["&"] = "&amp;", ["<"] = "&lt;", [">"] = "&gt;", ['"'] = "&quot;", ["'"] = "&#39;" }))
end

local CSS = [[
  * { box-sizing: border-box; }
  html, body { margin: 0; background: transparent; }
  body { font: 14px/1.45 -apple-system, "SF Pro Text", Helvetica, sans-serif; color: #e6edf3; -webkit-user-select: none; }
  .card { background: rgba(22, 27, 34, 0.94); border: 1px solid rgba(240,246,252,0.12); border-radius: 14px;
          padding: 16px 18px 14px; min-height: 100%; display: flex; flex-direction: column; gap: 10px; }
  .kicker { font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #8b949e; display:flex; justify-content: space-between; }
  .kicker .x { cursor: pointer; color:#8b949e; font-size: 14px; line-height: 1; padding: 0 2px; }
  .kicker .x:hover { color: #e6edf3; }
  h1 { font-size: 17px; margin: 0; font-weight: 650; letter-spacing: -0.01em; }
  p { margin: 0; color: #c9d1d9; }
  ul { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
  li { padding: 8px 10px; border-radius: 8px; background: rgba(240,246,252,0.05); cursor: pointer; display:flex; flex-direction:column; gap:2px; }
  li:hover { background: rgba(88,166,255,0.18); }
  li .t { color: #e6edf3; }
  li .s { color: #8b949e; font-size: 12px; }
  .badge { display:inline-block; font-size: 10px; padding: 1px 6px; border-radius: 999px; background: rgba(240,246,252,0.1); color:#c9d1d9; margin-right: 6px; vertical-align: middle; }
  .badge.hot { background: rgba(248,81,73,0.25); color: #ffb4ae; }
  .badge.small { background: rgba(63,185,80,0.22); color: #9be9a8; }
  textarea { width: 100%; min-height: 72px; resize: vertical; border-radius: 8px; border: 1px solid rgba(240,246,252,0.15);
             background: rgba(1,4,9,0.5); color: #e6edf3; padding: 8px 10px; font: inherit; -webkit-user-select: text; }
  textarea:focus { outline: none; border-color: #58a6ff; }
  .checks { display:flex; flex-wrap: wrap; gap: 6px 14px; color:#c9d1d9; font-size: 13px; }
  .checks label { display:flex; align-items:center; gap:6px; cursor:pointer; }
  .buttons { display: flex; gap: 8px; margin-top: 4px; }
  button { flex: 1; padding: 9px 12px; border-radius: 9px; border: 1px solid transparent; font: inherit; font-weight: 600; cursor: pointer; }
  .primary { background: #238636; color: #fff; }
  .primary:hover { background: #2ea043; }
  .secondary { background: rgba(240,246,252,0.06); color: #e6edf3; border-color: rgba(240,246,252,0.15); }
  .secondary:hover { background: rgba(240,246,252,0.12); }
  .muted { color:#8b949e; font-size: 12px; }
  pre { white-space: pre-wrap; font: 12px/1.4 ui-monospace, Menlo, monospace; color:#c9d1d9; background: rgba(1,4,9,0.4); padding: 8px 10px; border-radius: 8px; margin:0; max-height: 240px; overflow:auto; -webkit-user-select: text; }
]]

local JS = [[
  function send(msg) { try { webkit.messageHandlers.lioco.postMessage(msg); } catch (e) {} }
  function form() {
    var out = {};
    document.querySelectorAll('textarea, input[type=text]').forEach(function (el) { out[el.name] = el.value; });
    document.querySelectorAll('input[type=checkbox]').forEach(function (el) { out[el.name] = el.checked; });
    return out;
  }
  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-action]');
    if (!el) return;
    var msg = { action: el.getAttribute('data-action'), form: form() };
    if (el.hasAttribute('data-url')) msg.url = el.getAttribute('data-url');
    if (el.hasAttribute('data-index')) msg.index = parseInt(el.getAttribute('data-index'), 10);
    send(msg);
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') send({ action: 'close', form: form() });
    if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) send({ action: 'primary', form: form() });
  });
]]

local function render(spec)
  local parts = {}
  local function add(s) parts[#parts + 1] = s end
  add("<!doctype html><html><head><meta charset='utf-8'><style>" .. CSS .. "</style></head><body><div class='card'>")
  add(string.format("<div class='kicker'><span>%s</span><span class='x' data-action='close' title='Not now'>✕</span></div>", esc(spec.kicker or "lioco")))
  if spec.title then add("<h1>" .. esc(spec.title) .. "</h1>") end
  if spec.body then add("<p>" .. esc(spec.body) .. "</p>") end
  if spec.pre then add("<pre>" .. esc(spec.pre) .. "</pre>") end
  if spec.items and #spec.items > 0 then
    add("<ul>")
    for i, it in ipairs(spec.items) do
      local badges = ""
      for _, b in ipairs(it.badges or {}) do
        badges = badges .. string.format("<span class='badge %s'>%s</span>", esc(b.kind or ""), esc(b.text))
      end
      add(string.format("<li data-action='item' data-index='%d'%s><span class='t'>%s%s</span>%s</li>",
        i,
        it.url and (" data-url='" .. esc(it.url) .. "'") or "",
        badges, esc(it.text),
        it.sub and ("<span class='s'>" .. esc(it.sub) .. "</span>") or ""))
    end
    add("</ul>")
  end
  if spec.form then
    if spec.form.fields then
      for _, f in ipairs(spec.form.fields) do
        add(string.format("<div class='muted'>%s</div><textarea name='%s' placeholder='%s'>%s</textarea>",
          esc(f.label or ""), esc(f.name), esc(f.placeholder or ""), esc(f.value or "")))
      end
    end
    if spec.form.checks then
      add("<div class='checks'>")
      for _, c in ipairs(spec.form.checks) do
        add(string.format("<label><input type='checkbox' name='%s'%s> %s</label>",
          esc(c.name), c.checked and " checked" or "", esc(c.label)))
      end
      add("</div>")
    end
  end
  if spec.note then add("<div class='muted'>" .. esc(spec.note) .. "</div>") end
  if spec.primary or spec.secondary then
    add("<div class='buttons'>")
    if spec.secondary then
      add(string.format("<button class='secondary' data-action='secondary'>%s</button>", esc(spec.secondary.label)))
    end
    if spec.primary then
      add(string.format("<button class='primary' data-action='primary'>%s</button>", esc(spec.primary.label)))
    end
    add("</div>")
  end
  add("</div><script>" .. JS .. "</script></body></html>")
  return table.concat(parts)
end

local function frameFor(spec)
  local screen = hs.screen.mainScreen():frame()
  local w, h
  if spec.size == "large" then
    w, h = 520, 360
    if spec.items then h = h + math.min(#spec.items, 5) * 44 end
    if spec.form then h = h + 150 end
    if spec.pre then h = h + 200 end
    return { x = screen.x + (screen.w - w) / 2, y = screen.y + (screen.h - h) / 2, w = w, h = h }
  end
  w, h = 400, 190
  if spec.items then h = h + math.min(#spec.items, 5) * 46 end
  if spec.form then h = h + 150 end
  if spec.pre then h = h + 200 end
  return { x = screen.x + screen.w - w - 18, y = screen.y + screen.h - h - 18, w = w, h = h }
end

function M.hide()
  if M.view then
    pcall(function() M.view:delete() end)
    M.view = nil
  end
  M.spec = nil
  M.onAction = nil
end

-- onAction(action, payload): action is "primary"|"secondary"|"close"|"item"|"open"
function M.show(spec, onAction)
  M.hide()
  M.spec = spec
  M.onAction = onAction

  M.ucc = hs.webview.usercontent.new("lioco")
  M.ucc:setCallback(function(msg)
    local body = msg and msg.body or {}
    if type(body) ~= "table" then return end
    local action = body.action
    local payload = { form = body.form or {}, url = body.url, index = body.index }
    if action == "item" and body.index and spec.items and spec.items[body.index] then
      payload.item = spec.items[body.index]
    end
    if action == "primary" then payload.button = spec.primary end
    if action == "secondary" then payload.button = spec.secondary end
    if M.onAction then M.onAction(action, payload) end
  end)

  local frame = frameFor(spec)
  local style = { "borderless" }
  if not spec.form then style[#style + 1] = "nonactivating" end

  M.view = hs.webview.new(frame, { developerExtrasEnabled = false }, M.ucc)
  M.view:windowStyle(style)
  M.view:level(hs.drawing.windowLevels.floating)
  M.view:allowTextEntry(true)
  M.view:transparent(true)
  M.view:shadow(true)
  M.view:deleteOnClose(true)
  M.view:closeOnEscape(true)
  M.view:html(render(spec))
  M.view:show()
  if spec.form then M.view:bringToFront(true) end
  return M.view
end

function M.visible()
  return M.view ~= nil
end

return M
