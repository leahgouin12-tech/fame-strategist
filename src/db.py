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
CREATE TABLE IF NOT EXISTS engage (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edit_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL, op TEXT NOT NULL,
    params TEXT NOT NULL, before_sha TEXT, after_sha TEXT, made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scores (
    ref TEXT PRIMARY KEY, kind TEXT NOT NULL, score REAL NOT NULL,
    band TEXT NOT NULL, parts TEXT NOT NULL, judged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rubric (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
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

    def save_engage(self, data: dict) -> None:
        self.conn.execute("DELETE FROM engage")
        self.conn.execute("INSERT INTO engage VALUES (1, ?)", (json.dumps(data),))
        self.conn.commit()

    def get_engage(self) -> dict:
        row = self.conn.execute("SELECT payload FROM engage WHERE id = 1").fetchone()
        base = {"comments": "", "targets": "", "bio": "", "replied": []}
        return {**base, **json.loads(row[0])} if row else base

    def save_graph(self, snapshots: list[dict]) -> None:
        """Other people's handles, so the whole table is one row that one button can empty."""
        self.conn.execute("DELETE FROM graph")
        if snapshots:
            self.conn.execute("INSERT INTO graph VALUES (1, ?)", (json.dumps(snapshots),))
        self.conn.commit()

    def get_graph(self) -> list[dict]:
        row = self.conn.execute("SELECT payload FROM graph WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else []

    def save_score(self, ref: str, kind: str, score: float, band: str,
                   parts: dict, judged_at: str) -> None:
        """One row per post reference, newest reading wins. The correlation in spec 5.9 only
        exists if the judgement made before posting survives the day it was posted."""
        self.conn.execute(
            "INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?)",
            (ref, kind, float(score), band, json.dumps(parts), judged_at),
        )
        self.conn.commit()

    def get_scores(self) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT ref, kind, score, band, parts, judged_at FROM scores ORDER BY ref"
        ).fetchall()
        return {
            ref: {"kind": kind, "score": score, "band": band,
                  "parts": json.loads(parts), "judged_at": judged_at}
            for ref, kind, score, band, parts, judged_at in rows
        }

    def get_rubric(self) -> dict | None:
        """Her accepted weights, or None for the app's own opinion."""
        row = self.conn.execute("SELECT payload FROM rubric WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def save_rubric(self, weights: dict) -> None:
        """Empty means back to the shipped weights: the row is deleted rather than parked."""
        self.conn.execute("DELETE FROM rubric")
        if weights:
            self.conn.execute("INSERT INTO rubric VALUES (1, ?)", (json.dumps(weights),))
        self.conn.commit()

    def log_edit(self, file: str, op: str, params, before_sha: str, after_sha: str,
                 made_at: str) -> None:
        self.conn.execute(
            "INSERT INTO edit_chain (file, op, params, before_sha, after_sha, made_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file, op, json.dumps(params), before_sha, after_sha, made_at),
        )
        self.conn.commit()

    def edit_ops(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT file, op, params, before_sha, after_sha, made_at FROM edit_chain ORDER BY id"
        ).fetchall()
        return [{"file": f, "op": o, "params": p, "before_sha": b, "after_sha": a, "made_at": m}
                for f, o, p, b, a, m in rows]

    SPEND_DEFAULT = {"model_calls": 0, "credits": None, "credits_note": ""}

    def get_spend(self) -> dict:
        row = self.conn.execute("SELECT payload FROM spend WHERE id = 1").fetchone()
        return {**self.SPEND_DEFAULT, **json.loads(row[0])} if row else dict(self.SPEND_DEFAULT)

    def save_spend(self, data: dict) -> None:
        self.conn.execute("DELETE FROM spend")
        self.conn.execute("INSERT INTO spend VALUES (1, ?)",
                          (json.dumps({**self.SPEND_DEFAULT, **data}),))
        self.conn.commit()

    def add_model_call(self) -> None:
        """Counted only where a call actually produced text, so the quota column is a receipt."""
        spent = self.get_spend()
        spent["model_calls"] = int(spent.get("model_calls") or 0) + 1
        self.save_spend(spent)
