"""Bear backend: read the SQLite database (via a short-lived copy), write via x-callback URLs."""
import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.parse

NAME = "bear"
DEFAULT_DB = os.path.expanduser(
    "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
)
CORE_DATA_EPOCH = 978307200  # 2001-01-01


def db_path(cfg):
    return os.path.expanduser((cfg.get("bear") or {}).get("db_path") or DEFAULT_DB)


def available(cfg):
    return os.path.exists(db_path(cfg))


def note_url(note_id):
    return f"bear://x-callback-url/open-note?id={urllib.parse.quote(note_id)}"


def _to_dt(core_ts):
    if core_ts is None:
        return None
    return dt.datetime.fromtimestamp(core_ts + CORE_DATA_EPOCH)


def load(cfg, include_archived=False):
    """Copy the db (and WAL) to a temp dir, read it, delete the copy. Avoids lock fights with Bear
    and leaves no second copy of your notes lying around."""
    path = db_path(cfg)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Bear database not found at {path}")
    tmp = tempfile.mkdtemp(prefix="lioco-bear-")
    try:
        dst = os.path.join(tmp, "db.sqlite")
        shutil.copy2(path, dst)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(path + suffix):
                shutil.copy2(path + suffix, dst + suffix)
        conn = sqlite3.connect(dst)
        conn.row_factory = sqlite3.Row
        try:
            return _read(conn, include_archived)
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read(conn, include_archived):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ZSFNOTE)")}
    where = ["ZTRASHED = 0"]
    if "ZARCHIVED" in cols and not include_archived:
        where.append("(ZARCHIVED = 0 OR ZARCHIVED IS NULL)")
    if "ZENCRYPTED" in cols:
        where.append("(ZENCRYPTED = 0 OR ZENCRYPTED IS NULL)")
    sql = ("SELECT ZUNIQUEIDENTIFIER AS id, ZTITLE AS title, ZTEXT AS text, ZMODIFICATIONDATE AS mod "
           f"FROM ZSFNOTE WHERE {' AND '.join(where)}")
    out = []
    for r in conn.execute(sql):
        out.append({"id": r["id"], "title": r["title"] or "", "text": r["text"] or "",
                    "modified": _to_dt(r["mod"]), "url": note_url(r["id"])})
    return out


def _open(url):
    subprocess.run(["open", "-g", url], check=False, timeout=10)


def _title_url(title):
    return f"bear://x-callback-url/open-note?title={urllib.parse.quote(title)}"


def create(cfg, title, text, tags=None):
    body = text
    if tags:
        body = body.rstrip() + "\n\n" + " ".join(f"#{t}" for t in tags) + "\n"
    q = urllib.parse.urlencode({"title": title, "text": body, "open_note": "no", "show_window": "no"},
                               quote_via=urllib.parse.quote)
    _open(f"bear://x-callback-url/create?{q}")
    return _title_url(title)


def append(cfg, title, text):
    q = urllib.parse.urlencode({"title": title, "text": text, "mode": "append", "new_line": "yes",
                                "open_note": "no", "show_window": "no"}, quote_via=urllib.parse.quote)
    _open(f"bear://x-callback-url/add-text?{q}")
    return _title_url(title)
