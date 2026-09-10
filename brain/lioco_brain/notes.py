"""Backend-neutral note logic. A note is {id, title, text, modified, url}.

Backends (bear, markdown) provide: available(cfg), load(cfg), create(cfg, title, text, tags),
append(cfg, title, text). Everything else here is pure and shared.
"""
import datetime as dt
import re

UNCHECKED_RE = re.compile(r"^\s*[-*+]\s\[\s\]\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
STOP = {"the", "and", "with", "for", "sync", "meeting", "call", "chat", "weekly", "daily", "standup", "1:1", "one", "review"}


def backend(cfg):
    from . import bear, markdown
    name = ((cfg.get("notes") or {}).get("backend") or "auto").lower()
    if name == "auto":
        name = "bear" if bear.available(cfg) else "markdown"
    if name == "bear":
        return bear
    if name == "markdown":
        return markdown
    if name in ("none", "off"):
        return None
    raise ValueError(f"unknown notes backend {name!r} (use bear, markdown, auto, or none)")


def backend_name(cfg):
    b = backend(cfg)
    return b.NAME if b else "none"


def load(cfg):
    b = backend(cfg)
    return b.load(cfg) if b else []


def has_tag(text, tag):
    return re.search(rf"(?<![\w/])#{re.escape(tag)}(?![\w/])", text or "") is not None


def todos(all_notes, tags):
    """Unchecked checkbox lines from notes carrying any of the tags."""
    out = []
    for n in all_notes:
        if not any(has_tag(n["text"], t) or has_tag(n["title"], t) for t in tags):
            continue
        heading = None
        for line in n["text"].splitlines():
            hm = HEADING_RE.match(line)
            if hm:
                heading = hm.group(2)
                continue
            m = UNCHECKED_RE.match(line)
            if m:
                out.append({
                    "text": m.group(1),
                    "note_title": n["title"],
                    "note_id": n["id"],
                    "heading": heading,
                    "url": n.get("url"),
                    "source": "notes",
                    "modified": n.get("modified"),
                })
    return out


def find_by_title(all_notes, title):
    for n in all_notes:
        if n["title"].strip().lower() == title.strip().lower():
            return n
    return None


def _tokens(s):
    return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9'\-]{2,}", s or "")}


def search(all_notes, terms, limit=5, exclude_title_prefix=None, now=None):
    """Score notes by term matches in title (x3) and text, with a recency boost."""
    now = now or dt.datetime.now()
    terms = {t.lower() for t in terms if t and t.lower() not in STOP and len(t) >= 3}
    if not terms:
        return []
    scored = []
    for n in all_notes:
        if exclude_title_prefix and n["title"].startswith(exclude_title_prefix):
            continue
        title_hits = len(terms & _tokens(n["title"]))
        text_hits = len(terms & _tokens(n["text"]))
        if title_hits == 0 and text_hits == 0:
            continue
        score = title_hits * 3 + text_hits
        if n.get("modified"):
            age_days = max(0, (now - n["modified"]).days)
            score += max(0, 2 - age_days / 14)
        scored.append((score, n))
    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    return [{"title": n["title"], "id": n["id"], "url": n.get("url"), "snippet": snippet(n["text"], terms), "score": s}
            for s, n in scored[:limit]]


def snippet(text, terms, width=110):
    lines = text.splitlines()[1:]
    for line in lines:
        if any(t in line.lower() for t in terms):
            s = line.strip()
            return s[:width] + ("…" if len(s) > width else "")
    for line in lines:
        if line.strip():
            s = line.strip()
            return s[:width] + ("…" if len(s) > width else "")
    return ""
