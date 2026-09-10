"""Read-only access to the Bear notes database, plus x-callback writes."""
import datetime as dt
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.parse

DEFAULT_DB = os.path.expanduser(
    "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
)
CORE_DATA_EPOCH = 978307200  # 2001-01-01
UNCHECKED_RE = re.compile(r"^\s*[-*+]\s\[\s\]\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")


def db_path(cfg):
    return os.path.expanduser((cfg.get("bear") or {}).get("db_path") or DEFAULT_DB)


def connect(path):
    """Copy the db (and WAL) to a temp dir, then open read-only. Avoids lock fights with Bear."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Bear database not found at {path}")
    tmp = tempfile.mkdtemp(prefix="lioco-bear-")
    dst = os.path.join(tmp, "db.sqlite")
    shutil.copy2(path, dst)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.copy2(path + suffix, dst + suffix)
    conn = sqlite3.connect(dst)
    conn.row_factory = sqlite3.Row
    return conn


def _to_dt(core_ts):
    if core_ts is None:
        return None
    return dt.datetime.fromtimestamp(core_ts + CORE_DATA_EPOCH)


def notes(conn, include_archived=False):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ZSFNOTE)")}
    where = ["ZTRASHED = 0"]
    if "ZARCHIVED" in cols and not include_archived:
        where.append("(ZARCHIVED = 0 OR ZARCHIVED IS NULL)")
    if "ZENCRYPTED" in cols:
        where.append("(ZENCRYPTED = 0 OR ZENCRYPTED IS NULL)")
    sql = f"SELECT ZUNIQUEIDENTIFIER AS id, ZTITLE AS title, ZTEXT AS text, ZMODIFICATIONDATE AS mod FROM ZSFNOTE WHERE {' AND '.join(where)}"
    out = []
    for r in conn.execute(sql):
        out.append({"id": r["id"], "title": r["title"] or "", "text": r["text"] or "", "modified": _to_dt(r["mod"])})
    return out


def note_url(note_id):
    return f"bear://x-callback-url/open-note?id={urllib.parse.quote(note_id)}"


def has_tag(text, tag):
    return re.search(rf"(?<![\w/])#{re.escape(tag)}(?![\w/])", text) is not None


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
                    "url": note_url(n["id"]),
                    "source": "bear",
                    "modified": n["modified"],
                })
    return out


def find_by_title(all_notes, title):
    for n in all_notes:
        if n["title"].strip().lower() == title.strip().lower():
            return n
    return None


def _tokens(s):
    return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9'\-]{2,}", s or "")}


STOP = {"the", "and", "with", "for", "sync", "meeting", "call", "chat", "weekly", "daily", "standup", "1:1", "one", "review"}


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
        tt = _tokens(n["title"])
        xt = _tokens(n["text"])
        title_hits = len(terms & tt)
        text_hits = len(terms & xt)
        if title_hits == 0 and text_hits == 0:
            continue
        score = title_hits * 3 + text_hits
        if n["modified"]:
            age_days = max(0, (now - n["modified"]).days)
            score += max(0, 2 - age_days / 14)
        scored.append((score, n))
    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    out = []
    for score, n in scored[:limit]:
        out.append({"title": n["title"], "id": n["id"], "url": note_url(n["id"]), "snippet": snippet(n["text"], terms), "score": score})
    return out


def snippet(text, terms, width=110):
    for line in text.splitlines()[1:]:
        low = line.lower()
        if any(t in low for t in terms):
            s = line.strip()
            return s[:width] + ("…" if len(s) > width else "")
    for line in text.splitlines()[1:]:
        if line.strip():
            s = line.strip()
            return s[:width] + ("…" if len(s) > width else "")
    return ""


def _open(url):
    subprocess.run(["open", "-g", url], check=False, timeout=10)


def create_note(title, text, tags=None, open_note=False):
    body = text
    if tags:
        body = body.rstrip() + "\n\n" + " ".join(f"#{t}" for t in tags) + "\n"
    q = urllib.parse.urlencode({
        "title": title,
        "text": body,
        "open_note": "yes" if open_note else "no",
        "show_window": "yes" if open_note else "no",
    }, quote_via=urllib.parse.quote)
    _open(f"bear://x-callback-url/create?{q}")
    return f"bear://x-callback-url/open-note?title={urllib.parse.quote(title)}"


def append_to_note(title, text):
    q = urllib.parse.urlencode({
        "title": title,
        "text": text,
        "mode": "append",
        "new_line": "yes",
        "open_note": "no",
        "show_window": "no",
    }, quote_via=urllib.parse.quote)
    _open(f"bear://x-callback-url/add-text?{q}")
    return f"bear://x-callback-url/open-note?title={urllib.parse.quote(title)}"
