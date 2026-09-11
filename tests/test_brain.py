import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.join(HERE, "..", "brain")
sys.path.insert(0, BRAIN)

from lioco_brain import bear, cal, config, markdown, notes, rank, winddown  # noqa: E402

ICAL = """@@LIOCO@@Standup
    attendees: Alice Smith, Bob Jones
    location: Zoom
    url: https://zoom.us/j/123
    notes: Agenda
        - blockers
        - demo
    2026-09-10 at 14:45 - 15:15
@@LIOCO@@Roadmap review with Carol
    2026-09-10 at 16:00 - 2026-09-10 at 17:00
"""


def make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ZSFNOTE (Z_PK INTEGER PRIMARY KEY, ZTRASHED INTEGER, ZARCHIVED INTEGER, ZENCRYPTED INTEGER, "
                 "ZUNIQUEIDENTIFIER TEXT, ZTITLE TEXT, ZTEXT TEXT, ZMODIFICATIONDATE REAL)")
    now = dt.datetime.now().timestamp() - bear.CORE_DATA_EPOCH
    rows = [
        (1, 0, 0, 0, "A1", "Todo", "# Todo #todo\n## Today\n- [ ] Reply to Alice about roadmap !\n- [x] done thing\n## Later\n- [ ] Write the long design doc for the ingestion pipeline rewrite\n- [ ] Ping Bob", now),
        (2, 0, 0, 0, "B2", "Roadmap notes", "# Roadmap notes\nCarol wants Q4 roadmap by Friday.\n", now - 86400),
        (3, 1, 0, 0, "C3", "Trashed", "# Trashed #todo\n- [ ] should not appear", now),
        (4, 0, 0, 0, "D4", "Random", "# Random\nnothing here", now - 86400 * 40),
    ]
    conn.executemany("INSERT INTO ZSFNOTE VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


class CalTests(unittest.TestCase):
    def test_parse_and_summarize(self):
        events = cal.parse_icalbuddy(ICAL)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["attendees"], ["Alice Smith", "Bob Jones"])
        self.assertIn("- demo", events[0]["notes"])
        self.assertEqual(events[1]["end"], dt.datetime(2026, 9, 10, 17, 0))
        now = dt.datetime(2026, 9, 10, 14, 10)
        in_mtg, nxt, left = cal.summarize(events, now)
        self.assertFalse(in_mtg)
        self.assertEqual(nxt["title"], "Standup")
        self.assertEqual(nxt["minutes_until"], 35)
        self.assertEqual(left, 2)
        in_mtg, nxt, _ = cal.summarize(events, dt.datetime(2026, 9, 10, 15, 0))
        self.assertTrue(in_mtg)
        self.assertEqual(nxt["title"], "Roadmap review with Carol")
        mj = cal.meetings_json(events)
        self.assertEqual([m["title"] for m in mj], ["Standup", "Roadmap review with Carol"])
        self.assertEqual(mj[0]["start"], "2026-09-10T14:45")
        self.assertEqual(mj[0]["end"], "2026-09-10T15:15")
        no_end = cal.meetings_json([{"title": "X", "start": dt.datetime(2026, 9, 10, 9, 0), "end": None}])
        self.assertEqual(no_end[0]["end"], "2026-09-10T09:30")


class BearTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "database.sqlite")
        make_db(self.db)
        self.cfg = config.load(os.path.join(self.tmp, "nonexistent.json"))
        self.cfg["bear"]["db_path"] = self.db
        self.cfg["notes"]["markdown_dir"] = os.path.join(self.tmp, "md")
        self.notes = bear.load(self.cfg)

    def test_notes_excludes_trashed(self):
        self.assertEqual({n["title"] for n in self.notes}, {"Todo", "Roadmap notes", "Random"})

    def test_load_cleans_temp_copy(self):
        before = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("lioco-bear-")}
        bear.load(self.cfg)
        after = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("lioco-bear-")}
        self.assertEqual(before, after)

    def test_backend_autodetect(self):
        self.assertIs(notes.backend(self.cfg), bear)
        self.cfg["bear"]["db_path"] = os.path.join(self.tmp, "missing.sqlite")
        self.assertIs(notes.backend(self.cfg), markdown)
        self.cfg["notes"]["backend"] = "none"
        self.assertIsNone(notes.backend(self.cfg))
        self.assertEqual(notes.load(self.cfg), [])

    def test_markdown_backend_roundtrip(self):
        self.cfg["notes"]["backend"] = "markdown"
        md = self.cfg["notes"]["markdown_dir"]
        os.makedirs(md)
        with open(os.path.join(md, "inbox.md"), "w") as f:
            f.write("# Inbox #todo\n- [ ] Email Dana re: budget\n- [ ] Refactor everything\n")
        loaded = markdown.load(self.cfg)
        self.assertEqual(loaded[0]["title"], "Inbox #todo")
        self.assertTrue(loaded[0]["url"].startswith("file://"))
        todos = notes.todos(loaded, ["todo"])
        self.assertEqual([t["text"] for t in todos], ["Email Dana re: budget", "Refactor everything"])
        # clock-out writes a daily note, then appends to it on the second run
        out = winddown.run(self.cfg, note="left off here", tomorrow="do the thing", now=dt.datetime(2026, 9, 10, 17, 0))
        self.assertIn("Created markdown note", out["steps"][0])
        out = winddown.run(self.cfg, note="second pass", now=dt.datetime(2026, 9, 10, 17, 30))
        self.assertIn("Appended to markdown note", out["steps"][0])
        with open(os.path.join(md, "Daily 2026-09-10.md")) as f:
            text = f.read()
        self.assertTrue(text.startswith("# Daily 2026-09-10"))
        self.assertIn("left off here", text)
        self.assertIn("second pass", text)
        self.assertIn("- [ ] do the thing", text)
        self.assertIn("#daily", text)

    def test_winddown_with_notes_disabled_warns(self):
        self.cfg["notes"]["backend"] = "none"
        out = winddown.run(self.cfg, note="important thought")
        self.assertTrue(any("NOT saved" in s for s in out["steps"]))
        self.assertIsNone(out["note_url"])

    def test_todos(self):
        todos = notes.todos(self.notes, ["todo"])
        texts = [t["text"] for t in todos]
        self.assertEqual(texts, ["Reply to Alice about roadmap !", "Write the long design doc for the ingestion pipeline rewrite", "Ping Bob"])
        self.assertEqual(todos[0]["heading"], "Today")
        self.assertTrue(todos[0]["url"].startswith("bear://x-callback-url/open-note?id=A1"))

    def test_search(self):
        hits = notes.search(self.notes, ["Roadmap", "Carol"], limit=3)
        self.assertEqual(hits[0]["title"], "Roadmap notes")
        self.assertIn("Carol", hits[0]["snippet"])

    def test_rank(self):
        todos = notes.todos(self.notes, ["todo"])
        issues = [
            {"text": "ENG-1 Fix login", "title": "Fix login", "priority": 1, "due": None, "estimate": 1, "state": "Todo", "state_type": "unstarted", "project": "Auth", "url": "https://linear.app/x", "source": "linear"},
            {"text": "ENG-2 Big refactor", "title": "Big refactor", "priority": 3, "due": None, "estimate": 8, "state": "Todo", "state_type": "unstarted", "project": None, "url": None, "source": "linear"},
        ]
        ranked = rank.rank(todos, issues)
        self.assertEqual(ranked[0]["text"], "Reply to Alice about roadmap !")  # hot + today heading
        self.assertTrue(ranked[0]["hot"] and ranked[0]["small"])
        self.assertEqual(ranked[1]["text"], "ENG-1 Fix login")
        big = next(t for t in ranked if t["text"].startswith("Write the long"))
        self.assertFalse(big["small"])
        focused = rank.rank(todos, [], focus_terms=["Bob"])
        self.assertIn("Bob", focused[0]["text"] + focused[1]["text"])

    def test_build_entry(self):
        entry = winddown.build_entry("scorer done", "wire buttons", [{"title": "Doc", "url": "https://x"}], dt.datetime(2026, 9, 10, 17, 5))
        self.assertIn("Clocked out 5:05 PM", entry)
        self.assertIn("- [ ] wire buttons", entry)
        self.assertIn("[Doc](https://x)", entry)

    def test_cli_tasks_and_context(self):
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, "w") as f:
            json.dump({"bear": {"db_path": self.db}, "notes": {"todo_tags": ["todo"]}, "work_dirs": []}, f)
        env = dict(os.environ, LINEAR_API_KEY="", PATH="/nonexistent")
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "lioco.py"), "--config", cfg_path, "tasks", "--limit", "2", "--small"],
                           capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["tasks"]), 2)
        self.assertTrue(all(t["small"] for t in out["tasks"]))
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "lioco.py"), "--config", cfg_path, "context"],
                           capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        self.assertEqual(out["todo_count"], 3)
        self.assertEqual(out["notes_backend"], "bear")
        self.assertIn("calendar", out["errors"])  # no icalBuddy/osascript here, fails gracefully


if __name__ == "__main__":
    unittest.main()
