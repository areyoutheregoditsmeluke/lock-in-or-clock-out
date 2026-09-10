"""The clock-out ritual: write the daily note, park tabs, quiet Slack, quit apps."""
import datetime as dt
import json
import os
import subprocess
import urllib.request

from . import bear, browser


def daily_title(cfg, now=None):
    now = now or dt.datetime.now()
    fmt = (cfg.get("bear") or {}).get("daily_note_title") or "Daily {date}"
    return fmt.replace("{date}", now.strftime("%Y-%m-%d"))


def build_entry(note, tomorrow, tabs, now=None):
    now = now or dt.datetime.now()
    lines = [f"## Clocked out {now.strftime('%-I:%M %p')}"]
    if note.strip():
        lines += ["**Where I left off**", note.strip(), ""]
    if tomorrow.strip():
        lines += ["**First thing tomorrow**", f"- [ ] {tomorrow.strip()}", ""]
    if tabs:
        lines.append(f"**Parked tabs ({len(tabs)})**")
        for t in tabs[:60]:
            lines.append(f"- [{t['title'][:90]}]({t['url']})")
        if len(tabs) > 60:
            lines.append(f"- … and {len(tabs) - 60} more")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def slack_away(status_text="Done for the day", timeout=8):
    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        return "Slack: skipped (no SLACK_USER_TOKEN)"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    tomorrow_9 = dt.datetime.combine(dt.date.today() + dt.timedelta(days=1), dt.time(9, 0))
    profile = {"status_text": status_text, "status_emoji": ":wave:", "status_expiration": int(tomorrow_9.timestamp())}
    for url, body in (
        ("https://slack.com/api/users.profile.set", {"profile": profile}),
        ("https://slack.com/api/users.setPresence", {"presence": "away"}),
    ):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        if not data.get("ok"):
            return f"Slack: error {data.get('error')}"
    return "Slack: status set, presence away"


def quit_apps(apps):
    done = []
    for app in apps:
        if not browser.is_running(app):
            continue
        subprocess.run(["osascript", "-e", f'tell application "{app}" to quit'], capture_output=True, timeout=15)
        done.append(app)
    return done


def run(cfg, note="", tomorrow="", park_tabs=False, do_quit=False, do_slack=False, now=None):
    now = now or dt.datetime.now()
    steps = []
    tabs = []
    if park_tabs:
        try:
            tabs = browser.tabs(cfg.get("browsers") or [])
            steps.append(f"Parked {len(tabs)} browser tabs")
        except Exception as e:  # noqa: BLE001
            steps.append(f"Tabs: {e}")

    title = daily_title(cfg, now)
    entry = build_entry(note, tomorrow, tabs, now)
    tag = (cfg.get("bear") or {}).get("daily_note_tag")
    exists = False
    try:
        conn = bear.connect(bear.db_path(cfg))
        exists = bear.find_by_title(bear.notes(conn), title) is not None
    except Exception:  # noqa: BLE001
        exists = False
    if exists:
        url = bear.append_to_note(title, entry)
        steps.append(f"Appended to Bear note “{title}”")
    else:
        url = bear.create_note(title, entry, tags=[tag] if tag else None)
        steps.append(f"Created Bear note “{title}”")

    if do_slack:
        try:
            steps.append(slack_away())
        except Exception as e:  # noqa: BLE001
            steps.append(f"Slack: {e}")

    if do_quit:
        apps = (cfg.get("winddown") or {}).get("quit_apps") or []
        quit_done = quit_apps(apps)
        if quit_done:
            steps.append("Quit " + ", ".join(quit_done))

    return {"ok": True, "steps": steps, "note_url": url, "tabs": len(tabs)}
