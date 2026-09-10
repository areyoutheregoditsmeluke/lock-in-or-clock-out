"""Collect open browser tabs (title + URL) so they can be parked in a note."""
import subprocess

CHROMIUM = ("Google Chrome", "Arc", "Brave Browser", "Microsoft Edge", "Vivaldi", "Chromium")
SAFARI = ("Safari", "Safari Technology Preview")

CHROMIUM_SCRIPT = '''
tell application "{app}"
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & (title of t) & tab & (URL of t) & linefeed
    end repeat
  end repeat
  return out
end tell
'''

SAFARI_SCRIPT = '''
tell application "{app}"
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & (name of t) & tab & (URL of t) & linefeed
    end repeat
  end repeat
  return out
end tell
'''


def _osa(script, timeout=20):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def is_running(app):
    try:
        return _osa(f'application "{app}" is running', timeout=10).strip() == "true"
    except Exception:
        return False


def tabs(browsers):
    out = []
    for app in browsers:
        if app in CHROMIUM:
            script = CHROMIUM_SCRIPT
        elif app in SAFARI:
            script = SAFARI_SCRIPT
        else:
            continue  # Firefox has no AppleScript tab access
        if not is_running(app):
            continue
        try:
            text = _osa(script.format(app=app))
        except Exception:
            continue
        for line in text.splitlines():
            if "\t" not in line:
                continue
            title, url = line.split("\t", 1)
            if url.startswith(("http://", "https://")):
                out.append({"app": app, "title": title.strip() or url, "url": url.strip()})
    return out
