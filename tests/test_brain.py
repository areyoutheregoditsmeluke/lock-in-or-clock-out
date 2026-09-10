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

from lioco_brain import bear, cal, rank, winddown  # noqa: E402

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


class BearTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "database.sqlite")
        make_db(self.db)
        self.notes = bear.notes(bear.connect(self.db))

    def test_notes_excludes_trashed(self):
        self.assertEqual({n["title"] for n in self.notes}, {"Todo", "Roadmap notes", "Random"})

    def test_todos(self):
        todos = bear.todos(self.notes, ["todo"])
        texts = [t["text"] for t in todos]
        self.assertEqual(texts, ["Reply to Alice about roadmap !", "Write the long design doc for the ingestion pipeline rewrite", "Ping Bob"])
        self.assertEqual(todos[0]["heading"], "Today")
        self.assertTrue(todos[0]["url"].startswith("bear://x-callback-url/open-note?id=A1"))

    def test_search(self):
        hits = bear.search(self.notes, ["Roadmap", "Carol"], limit=3)
        self.assertEqual(hits[0]["title"], "Roadmap notes")
        self.assertIn("Carol", hits[0]["snippet"])

    def test_rank(self):
        todos = bear.todos(self.notes, ["todo"])
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
            json.dump({"bear": {"db_path": self.db, "todo_tags": ["todo"]}, "work_dirs": []}, f)
        env = dict(os.environ, LINEAR_API_KEY="", PATH="/nonexistent")
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "lioco.py"), "--config", cfg_path, "tasks", "--limit", "2", "--small"],
                           capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["tasks"]), 2)
        self.assertTrue(all(t["small"] for t in out["tasks"]))
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "lioco.py"), "--config", cfg_path, "context"],
                           capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        self.assertEqual(out["bear_todo_count"], 3)
        self.assertIn("calendar", out["errors"])  # no icalBuddy/osascript here, fails gracefully


if __name__ == "__main__":
    unittest.main()
