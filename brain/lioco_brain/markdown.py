"""Markdown-folder backend: a directory of .md files (Obsidian vault, plain folder, anything)."""
import datetime as dt
import os
import re
import urllib.request

NAME = "markdown"
DEFAULT_DIR = "~/Documents/lioco-notes"
HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules"}


def notes_dir(cfg):
    return os.path.expanduser((cfg.get("notes") or {}).get("markdown_dir") or DEFAULT_DIR)


def available(cfg):
    return os.path.isdir(notes_dir(cfg))


def _url(path):
    return "file://" + urllib.request.pathname2url(os.path.abspath(path))


def _title_of(path, text):
    for line in text.splitlines()[:5]:
        m = HEADING_RE.match(line)
        if m:
            return m.group(1)
    return os.path.splitext(os.path.basename(path))[0]


def load(cfg):
    root = notes_dir(cfg)
    if not os.path.isdir(root):
        return []
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith((".md", ".markdown", ".txt")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                mtime = dt.datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                continue
            out.append({"id": os.path.relpath(path, root), "title": _title_of(path, text),
                        "text": text, "modified": mtime, "url": _url(path)})
    return out


def _safe_filename(title):
    s = re.sub(r"[\\/:*?\"<>|]", "-", title).strip().rstrip(".")
    return (s or "untitled")[:120] + ".md"


def _path_for(cfg, title):
    root = notes_dir(cfg)
    os.makedirs(root, exist_ok=True)
    # Prefer an existing file whose heading or name matches the title.
    for n in load(cfg):
        if n["title"].strip().lower() == title.strip().lower():
            return os.path.join(root, n["id"])
    return os.path.join(root, _safe_filename(title))


def create(cfg, title, text, tags=None):
    path = _path_for(cfg, title)
    body = f"# {title}\n\n{text.lstrip()}"
    if tags:
        body = body.rstrip() + "\n\n" + " ".join(f"#{t}" for t in tags) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return _url(path)


def append(cfg, title, text):
    path = _path_for(cfg, title)
    if not os.path.exists(path):
        return create(cfg, title, text)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + text.rstrip() + "\n")
    return _url(path)
