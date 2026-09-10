"""Turn raw todos and issues into a ranked list with 'hot' and 'small' flags."""
import datetime as dt
import re

HOT_WORDS = re.compile(r"\b(urgent|important|asap|today|blocker|blocking|due|deadline|overdue|eod|must)\b", re.I)
HOT_TAGS = re.compile(r"(?<!\w)(#p0|#p1|#urgent|#important|@today|!{1,3})(?!\w)")
SMALL_VERBS = re.compile(
    r"^\s*(reply|respond|send|email|ping|dm|message|review|approve|update|file|book|schedule|read|skim|"
    r"check|confirm|forward|share|rename|merge|close|archive|unsubscribe|pay|order|add|fix typo|comment)\b", re.I)
TODAY_HEADINGS = re.compile(r"\b(today|now|next|this week|urgent|p0|p1)\b", re.I)


def _is_small(text):
    return len(text) <= 60 and (SMALL_VERBS.match(text) is not None or len(text) <= 32)


def _date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def rank(note_todos, linear_issues, focus_terms=None, now=None):
    now = now or dt.datetime.now()
    today = now.date()
    focus = {t.lower() for t in (focus_terms or []) if len(t) >= 3}
    items = []

    for t in note_todos:
        text = t["text"]
        score = 1.0
        hot = False
        if HOT_WORDS.search(text) or HOT_TAGS.search(text):
            score += 3
            hot = True
        if t.get("heading") and TODAY_HEADINGS.search(t["heading"]):
            score += 2
            hot = True
        if t.get("modified"):
            age = max(0, (now - t["modified"]).days)
            score += max(0, 1.5 - age / 7)
        if focus and any(f in text.lower() for f in focus):
            score += 2.5
        small = _is_small(text)
        sub = t["note_title"] + (f" › {t['heading']}" if t.get("heading") else "")
        items.append({"text": text, "sub": sub, "url": t["url"], "source": t.get("source", "notes"), "score": score, "hot": hot, "small": small})

    for i in linear_issues:
        score = 1.0
        hot = False
        pr = i.get("priority") or 0
        if pr == 1:
            score += 4; hot = True
        elif pr == 2:
            score += 2.5; hot = True
        elif pr == 3:
            score += 1
        d = _date(i.get("due"))
        if d:
            days = (d - today).days
            if days <= 0:
                score += 4; hot = True
            elif days <= 2:
                score += 2; hot = True
        if (i.get("state_type") or "") == "started":
            score += 1.5
        if focus and any(f in i["text"].lower() for f in focus):
            score += 2.5
        est = i.get("estimate")
        small = (est is not None and est <= 1) or _is_small(i["title"])
        sub = " · ".join(x for x in [i.get("project"), i.get("state"), f"due {i['due']}" if i.get("due") else None] if x)
        items.append({"text": i["text"], "sub": sub, "url": i.get("url"), "source": "linear", "score": score, "hot": hot, "small": small})

    items.sort(key=lambda x: (-x["score"], x["text"].lower()))
    return items
