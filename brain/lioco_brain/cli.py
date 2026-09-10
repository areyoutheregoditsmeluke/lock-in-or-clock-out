"""Subcommands: context, tasks, prep, winddown, stats, doctor. Output is always one JSON object."""
import argparse
import collections
import datetime as dt
import json
import os
import re
import shutil
import sys

from . import cal, config, linear, notes, rank, winddown


def emit(obj, code=0):
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()
    return code


def _calendar(cfg):
    try:
        return cal.upcoming(cfg.get("calendar_hours_ahead", 10)), None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _notes(cfg):
    try:
        return notes.load(cfg), None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _todo_tags(cfg):
    return (cfg.get("notes") or {}).get("todo_tags") or ["todo"]


def _linear(cfg):
    try:
        return linear.issues(cfg), None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _meeting_terms(meeting):
    terms = set(re.findall(r"[A-Za-z][A-Za-z0-9'\-]{2,}", meeting.get("title") or ""))
    for a in meeting.get("attendees") or []:
        first = a.split("@")[0].split()[0] if a.strip() else ""
        if first:
            terms.add(first)
    return sorted(terms)


def cmd_context(cfg, args):
    events, cal_err = _calendar(cfg)
    in_meeting, nxt, left = cal.summarize(events)
    all_notes, notes_err = _notes(cfg)
    todos = notes.todos(all_notes, _todo_tags(cfg))
    out = {
        "now": dt.datetime.now().isoformat(timespec="minutes"),
        "in_meeting": in_meeting,
        "next_meeting": nxt,
        "meetings_left_today": left,
        "notes_backend": notes.backend_name(cfg),
        "todo_count": len(todos),
        "errors": {k: v for k, v in {"calendar": cal_err, "notes": notes_err}.items() if v},
    }
    return emit(out)


def cmd_tasks(cfg, args):
    all_notes, notes_err = _notes(cfg)
    todos = notes.todos(all_notes, _todo_tags(cfg))
    issues, lin_err = _linear(cfg)
    focus = None
    if args.focus_next_meeting:
        events, _ = _calendar(cfg)
        _, nxt, _ = cal.summarize(events)
        if nxt:
            focus = _meeting_terms(nxt)
    ranked = rank.rank(todos, issues, focus_terms=focus)
    if args.small:
        small = [t for t in ranked if t["small"]]
        ranked = small + [t for t in ranked if not t["small"]]
    out = {
        "tasks": ranked[: args.limit],
        "total": len(ranked),
        "errors": {k: v for k, v in {"notes": notes_err, "linear": lin_err}.items() if v},
    }
    return emit(out)


def cmd_prep(cfg, args):
    events, cal_err = _calendar(cfg)
    _, nxt, _ = cal.summarize(events)
    if not nxt:
        return emit({"meeting": None, "error": cal_err or "no upcoming meeting"}, 1)
    terms = _meeting_terms(nxt)
    all_notes, notes_err = _notes(cfg)
    related = notes.search(all_notes, terms, limit=5, exclude_title_prefix="Prep: ")
    todos = notes.todos(all_notes, _todo_tags(cfg))
    issues, _ = _linear(cfg)
    focused = [t for t in rank.rank(todos, issues, focus_terms=terms) if any(f.lower() in t["text"].lower() for f in terms)][:5]

    attendees = ", ".join(nxt.get("attendees") or []) or "—"
    date = dt.date.today().strftime("%Y-%m-%d")
    title = f"Prep: {nxt['title']} — {date}"
    lines = [
        f"**When** {nxt['start_clock']} (in {nxt['minutes_until']} min)",
        f"**Who** {attendees}",
    ]
    if nxt.get("location"):
        lines.append(f"**Where** {nxt['location']}")
    if nxt.get("url"):
        lines.append(f"**Link** {nxt['url']}")
    lines += ["", "## My goal for this meeting", "- [ ] ", ""]
    if nxt.get("notes"):
        lines += ["## Agenda / invite notes", nxt["notes"].strip(), ""]
    if related:
        lines.append("## Related notes")
        for n in related:
            lines.append(f"- [{n['title']}]({n['url']})" + (f" — {n['snippet']}" if n["snippet"] else ""))
        lines.append("")
    if focused:
        lines.append("## Open items that mention this")
        for t in focused:
            lines.append(f"- [ ] {t['text']}" + (f" ({t['sub']})" if t.get("sub") else ""))
        lines.append("")
    lines += ["## Notes", ""]
    text = "\n".join(lines)

    prep_url = None
    backend = notes.backend(cfg)
    if not args.no_write and backend is not None:
        try:
            existing = notes.find_by_title(all_notes, title)
            if existing:
                prep_url = existing.get("url")
            else:
                prep_url = backend.create(cfg, title, text, tags=["meeting-prep"])
        except Exception as e:  # noqa: BLE001
            notes_err = str(e)

    summary_bits = [f"{len(related)} related notes", f"{len(focused)} open items"]
    if nxt.get("attendees"):
        summary_bits.insert(0, f"with {attendees}")
    return emit({
        "meeting": nxt,
        "summary": " · ".join(summary_bits),
        "related_notes": related,
        "related_tasks": focused,
        "prep_note_title": title,
        "prep_note_url": prep_url,
        "prep_text": text,
        "errors": {k: v for k, v in {"calendar": cal_err, "notes": notes_err}.items() if v},
    })


def cmd_winddown(cfg, args):
    try:
        out = winddown.run(cfg, note=args.note, tomorrow=args.tomorrow, park_tabs=args.park_tabs,
                           do_quit=args.quit_apps, do_slack=args.slack_away)
        return emit(out)
    except Exception as e:  # noqa: BLE001
        return emit({"ok": False, "error": str(e), "steps": []}, 1)


def cmd_stats(cfg, args):
    path = cfg["log_path"]
    if not os.path.exists(path):
        return emit({"error": f"no log at {path}"}, 1)
    by_hour = collections.defaultdict(list)
    nudges = collections.Counter()
    responses = collections.Counter()
    cutoff = dt.datetime.now() - dt.timedelta(days=args.days)
    with open(path) as f:
        for line in f:
            try:
                ev = json.loads(line)
                t = dt.datetime.fromisoformat(ev["t"])
            except Exception:  # noqa: BLE001
                continue
            if t < cutoff:
                continue
            if ev.get("kind") == "eval" and "score" in ev:
                by_hour[t.hour].append(ev["score"])
            elif ev.get("kind") == "nudge":
                nudges[ev.get("mode")] += 1
            elif ev.get("kind") == "response":
                responses[ev.get("action")] += 1
    hours = {h: {"avg": round(sum(v) / len(v), 3), "drift_share": round(sum(1 for s in v if s >= 0.6) / len(v), 2), "n": len(v)}
             for h, v in sorted(by_hour.items())}
    return emit({"days": args.days, "score_by_hour": hours, "nudges_by_mode": nudges, "responses": responses})


def cmd_doctor(cfg, args):
    checks = {}
    checks["config_path"] = config.CONFIG_PATH
    checks["config_exists"] = os.path.exists(config.CONFIG_PATH)
    checks["icalBuddy"] = shutil.which("icalBuddy") or shutil.which("icalbuddy") or "missing (brew install ical-buddy)"
    events, cal_err = _calendar(cfg)
    checks["calendar"] = cal_err or f"{len(events)} events in next {cfg.get('calendar_hours_ahead', 10)}h"
    from . import bear, markdown
    backend = notes.backend_name(cfg)
    checks["notes_backend"] = backend
    dbp = bear.db_path(cfg)
    checks["bear_db"] = dbp if os.path.exists(dbp) else f"not found at {dbp}"
    checks["markdown_dir"] = markdown.notes_dir(cfg) + ("" if markdown.available(cfg) else " (will be created on first write)")
    all_notes, notes_err = _notes(cfg)
    if notes_err:
        checks["notes"] = notes_err
    elif backend == "none":
        checks["notes"] = "disabled: tasks come from Linear only, clock-out notes are not saved"
    else:
        todos = notes.todos(all_notes, _todo_tags(cfg))
        checks["notes"] = f"{len(all_notes)} notes, {len(todos)} open todos tagged {_todo_tags(cfg)}"
    key_env = (cfg.get("linear") or {}).get("api_key_env") or "LINEAR_API_KEY"
    if os.environ.get(key_env):
        issues, lin_err = _linear(cfg)
        checks["linear"] = lin_err or f"{len(issues)} open issues assigned to you"
    else:
        checks["linear"] = f"skipped ({key_env} not set)"
    checks["slack"] = "token present" if os.environ.get("SLACK_USER_TOKEN") else "skipped (SLACK_USER_TOKEN not set)"
    checks["work_dirs"] = {d: os.path.isdir(d) for d in cfg.get("work_dirs", [])}
    return emit({"ok": True, "checks": checks})


def main(argv):
    p = argparse.ArgumentParser(prog="lioco")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("context")
    t = sub.add_parser("tasks")
    t.add_argument("--limit", type=int, default=6)
    t.add_argument("--small", action="store_true", help="float small tasks to the top")
    t.add_argument("--focus-next-meeting", action="store_true")
    pr = sub.add_parser("prep")
    pr.add_argument("--no-write", action="store_true", help="do not create the Bear note")
    w = sub.add_parser("winddown")
    w.add_argument("--note", default="")
    w.add_argument("--tomorrow", default="")
    w.add_argument("--park-tabs", action="store_true")
    w.add_argument("--quit-apps", action="store_true")
    w.add_argument("--slack-away", action="store_true")
    s = sub.add_parser("stats")
    s.add_argument("--days", type=int, default=7)
    sub.add_parser("doctor")

    args = p.parse_args(argv)
    cfg = config.load(args.config)
    fn = {
        "context": cmd_context, "tasks": cmd_tasks, "prep": cmd_prep,
        "winddown": cmd_winddown, "stats": cmd_stats, "doctor": cmd_doctor,
    }[args.cmd]
    try:
        return fn(cfg, args)
    except Exception as e:  # noqa: BLE001
        return emit({"error": f"{type(e).__name__}: {e}"}, 1)
