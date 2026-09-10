import json
import os

CONFIG_PATH = os.path.expanduser("~/.config/lioco/config.json")

DEFAULTS = {
    "work_dirs": ["~/code"],
    "browsers": ["Google Chrome", "Arc", "Safari", "Brave Browser", "Firefox"],
    "meeting_prep_window_minutes": [10, 60],
    "bear": {
        "todo_tags": ["todo"],
        "daily_note_title": "Daily {date}",
        "daily_note_tag": "daily",
        "db_path": None,
    },
    "linear": {"api_key_env": "LINEAR_API_KEY"},
    "winddown": {"park_tabs": True, "quit_apps": ["Slack"], "slack_away": True, "lock_screen": False},
    "log_path": "~/.local/share/lioco/events.jsonl",
    "calendar_hours_ahead": 10,
}


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load(path=None):
    cfg = json.loads(json.dumps(DEFAULTS))
    path = path or os.environ.get("LIOCO_CONFIG") or CONFIG_PATH
    try:
        with open(path) as f:
            _merge(cfg, json.load(f))
    except FileNotFoundError:
        pass
    cfg["work_dirs"] = [os.path.expanduser(d) for d in cfg.get("work_dirs", [])]
    cfg["log_path"] = os.path.expanduser(cfg["log_path"])
    return cfg
