"""Upcoming calendar events. Prefers icalBuddy; falls back to Calendar.app via AppleScript."""
import datetime as dt
import re
import shutil
import subprocess

DATE_RE = re.compile(
    r"^(?P<d1>\d{4}-\d{2}-\d{2}) at (?P<t1>\d{2}:\d{2})"
    r"(?: - (?:(?P<d2>\d{4}-\d{2}-\d{2}) at )?(?P<t2>\d{2}:\d{2}))?$"
)
PROP_RE = re.compile(r"^(?P<key>location|notes|attendees|url):\s?(?P<val>.*)$")
BULLET = "@@LIOCO@@"


def _run(cmd, timeout=15):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def parse_icalbuddy(text, now=None):
    """Parse icalBuddy output produced with the flags used in _icalbuddy()."""
    now = now or dt.datetime.now()
    events = []
    current = None
    last_key = None
    for raw in text.splitlines():
        if raw.startswith(BULLET):
            current = {"title": raw[len(BULLET):].strip(), "attendees": [], "notes": "", "location": "", "url": ""}
            events.append(current)
            last_key = None
            continue
        if current is None:
            continue
        line = raw.strip()
        if not line:
            continue
        m = DATE_RE.match(line)
        if m:
            d1 = m.group("d1")
            start = dt.datetime.strptime(f"{d1} {m.group('t1')}", "%Y-%m-%d %H:%M")
            end = None
            if m.group("t2"):
                d2 = m.group("d2") or d1
                end = dt.datetime.strptime(f"{d2} {m.group('t2')}", "%Y-%m-%d %H:%M")
            current["start"] = start
            current["end"] = end
            last_key = None
            continue
        pm = PROP_RE.match(line)
        if pm:
            key, val = pm.group("key"), pm.group("val")
            if key == "attendees":
                current["attendees"] = [a.strip() for a in val.split(",") if a.strip()]
            else:
                current[key] = val
            last_key = key
            continue
        if last_key == "notes":
            current["notes"] += "\n" + line
    return [e for e in events if e.get("start")]


def _icalbuddy(hours):
    cmd = [
        "icalBuddy", "-nc", "-nrd", "-ea", "-b", BULLET,
        "-iep", "title,datetime,attendees,location,url,notes",
        "-po", "title,datetime,attendees,location,url,notes",
        "-df", "%Y-%m-%d", "-tf", "%H:%M",
        f"eventsFrom:now to:+{hours}h",
    ]
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "icalBuddy failed")
    return parse_icalbuddy(r.stdout)


APPLESCRIPT = """
set nowDate to current date
set endDate to nowDate + ({hours} * hours)
set out to ""
tell application "Calendar"
  repeat with c in calendars
    set evs to (every event of c whose start date >= nowDate - (4 * hours) and start date <= endDate and allday event is false)
    repeat with e in evs
      set s to start date of e
      set en to end date of e
      set out to out & (summary of e) & "\t" & (s as «class isot» as string) & "\t" & (en as «class isot» as string) & "\t" & (location of e) & "\t" & (url of e) & linefeed
    end repeat
  end repeat
end tell
return out
"""


def _applescript(hours):
    r = _run(["osascript", "-e", APPLESCRIPT.format(hours=hours)], timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "Calendar.app query failed")
    events = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            start = dt.datetime.fromisoformat(parts[1].replace("Z", ""))
            end = dt.datetime.fromisoformat(parts[2].replace("Z", ""))
        except ValueError:
            continue
        events.append({
            "title": parts[0], "start": start, "end": end,
            "location": parts[3] if len(parts) > 3 else "",
            "url": parts[4] if len(parts) > 4 and parts[4] != "missing value" else "",
            "attendees": [], "notes": "",
        })
    return events


def upcoming(hours=10):
    if shutil.which("icalBuddy") or shutil.which("icalbuddy"):
        return _icalbuddy(hours)
    return _applescript(hours)


def summarize(events, now=None):
    """Return (in_meeting, next_meeting, meetings_left) with JSON-safe values."""
    now = now or dt.datetime.now()
    in_meeting = False
    nxt = None
    left = 0
    for e in sorted(events, key=lambda x: x["start"]):
        end = e.get("end") or (e["start"] + dt.timedelta(minutes=30))
        if e["start"] <= now < end:
            in_meeting = True
            continue
        if e["start"] > now:
            left += 1
            if nxt is None:
                nxt = e
    out = None
    if nxt:
        end = nxt.get("end")
        out = {
            "title": nxt["title"],
            "start": nxt["start"].isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes") if end else None,
            "start_clock": nxt["start"].strftime("%-I:%M %p"),
            "minutes_until": int((nxt["start"] - now).total_seconds() // 60),
            "attendees": nxt.get("attendees", []),
            "location": nxt.get("location", ""),
            "url": nxt.get("url", ""),
            "notes": (nxt.get("notes") or "").strip(),
        }
    return in_meeting, out, left
