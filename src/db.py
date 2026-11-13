import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS interview (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT, week INTEGER, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS days (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL, done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, posted_at TEXT, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voice (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edit_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL, op TEXT NOT NULL,
    params TEXT NOT NULL, before_sha TEXT, after_sha TEXT, made_at TEXT NOT NULL
);
"""


class DB:
    """One file, no server. The edit_chain table exists so 'this is not an AI image'
    is answerable with a log rather than an assertion."""

    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def save_interview(self, answers) -> int:
        self.conn.execute("DELETE FROM interview")
        self.conn.execute(
            "INSERT INTO interview VALUES (1, ?)", (json.dumps(vars(answers), default=str),)
        )
        self.conn.commit()
        return 1

    def get_interview(self):
        row = self.conn.execute("SELECT payload FROM interview WHERE id = 1").fetchone()
        if not row:
            return None
        from src.strategist.interview import InterviewAnswers

        return InterviewAnswers(**json.loads(row[0]))

    def save_plan(self, week: int, payload: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO plans (week, payload) VALUES (?, ?)", (week, json.dumps(payload))
        )
        self.conn.commit()
        return cur.lastrowid

    def save_current_plan(self, payload: dict) -> None:
        self.conn.execute("DELETE FROM plans")
        self.conn.execute("INSERT INTO plans (week, payload) VALUES (0, ?)", (json.dumps(payload),))
        self.conn.commit()

    def get_current_plan(self):
        row = self.conn.execute("SELECT payload FROM plans ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def save_day(self, date: str, payload: dict) -> int:
        self.conn.execute(
            "INSERT INTO days (date, payload) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET payload = excluded.payload",
            (date, json.dumps(payload)),
        )
        self.conn.commit()
        return self.conn.execute("SELECT id FROM days WHERE date = ?", (date,)).fetchone()[0]

    def get_days(self, since: str, until: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT date, payload, done FROM days WHERE date >= ? AND date <= ? ORDER BY date",
            (since, until),
        ).fetchall()
        return [{"date": d, "done": bool(done), **json.loads(payload)} for d, payload, done in rows]

    def mark_done(self, date: str) -> None:
        self.conn.execute("UPDATE days SET done = 1 WHERE date = ?", (date,))
        self.conn.commit()

    def save_voice(self, samples: list[str]) -> None:
        self.conn.execute("DELETE FROM voice")
        if samples:
            self.conn.execute("INSERT INTO voice VALUES (1, ?)", (json.dumps(samples),))
        self.conn.commit()

    def get_voice(self) -> list[str]:
        row = self.conn.execute("SELECT payload FROM voice WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else []
