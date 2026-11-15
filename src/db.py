"""Every byte this app remembers, in one sqlite file and one CREATE TABLE string.

DB opens a single connection in WAL mode and hands out what the routes call:
save_interview and get_interview, save_plan and get_current_plan, save_day, get_days and
mark_done, save_score beside the rubric weights, log_edit and edit_ops for the chain
that answers "was this generated", start_run and add_step and redid_step for the agent,
remember and recall and forget for the notes, and the feature and upgrade rows, which
are replaced whole on every re-read. Most of it is deliberately one row - interview,
voice, engage, graph, rubric, spend, grants, accounts, terms, caption and staged all carry CHECK (id = 1)
and are deleted before they are inserted, because those are settings she set rather than
a history to page through; bench and collab append instead, since a benchmark and a list of
people to pitch are both things she adds to. The collab row keeps its own id through a stage
change because the stage is the one field she is allowed to move and the name is not.

_rebuild_derived drops and recreates feature and upgrade rather than migrating them:
those two are a reading of the source tree, so guessing at a migration would be worse
than losing rows a button refills. The metrics table is in the schema and nothing here
writes to it - the last import lives beside the database as metrics-last.csv.
"""

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
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, asked TEXT NOT NULL, mode TEXT NOT NULL,
    planner TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run INTEGER NOT NULL, tool TEXT NOT NULL,
    args TEXT NOT NULL, kind TEXT NOT NULL, summary TEXT NOT NULL,
    detail TEXT NOT NULL, made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, body TEXT NOT NULL,
    source TEXT NOT NULL, seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grants (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staged (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bench (
    id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collab (
    id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, made_at TEXT NOT NULL,
    moved_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS caption (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS language (
    id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feature (
    key TEXT PRIMARY KEY, payload TEXT NOT NULL, dept TEXT NOT NULL, kind TEXT NOT NULL,
    status TEXT NOT NULL, name TEXT NOT NULL, prove TEXT NOT NULL, found_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS upgrade (
    key TEXT PRIMARY KEY, payload TEXT NOT NULL, dept TEXT NOT NULL, kind TEXT NOT NULL,
    status TEXT NOT NULL, name TEXT NOT NULL, prove TEXT NOT NULL, found_at TEXT NOT NULL
);
"""


class DB:
    """One file, no server. The edit_chain table exists so 'this is not an AI image'
    is answerable with a log rather than an assertion."""

    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._rebuild_derived()

    def _rebuild_derived(self) -> None:
        """Two of these tables are a read of the source tree rather than a record of her
        life, so when their shape is behind the code the answer is to drop them and let the
        audit fill them again - not to guess at a migration. Nothing she typed, posted or
        photographed is in here, and nothing in here is anything she cannot get back by
        pressing the button on the Registry page."""
        for table in ("feature", "upgrade"):
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if not {"kind"} <= have:
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
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

    # ---- the agent: runs, steps, memory, permissions ------------------------

    def start_run(self, asked: str, mode: str, planner: str, started_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (asked, mode, planner, started_at) VALUES (?,?,?,?)",
            (asked, mode, planner, started_at))
        self.conn.commit()
        return cur.lastrowid

    def end_run(self, run_id: int, summary: str, finished_at: str) -> None:
        self.conn.execute("UPDATE runs SET summary = ?, finished_at = ? WHERE id = ?",
                          (summary, finished_at, run_id))
        self.conn.commit()

    def add_step(self, run_id: int, tool: str, args: dict, kind: str, summary: str,
                 detail: dict, made_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO steps (run, tool, args, kind, summary, detail, made_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, tool, json.dumps(args, default=str), kind, summary,
             json.dumps(detail, default=str), made_at))
        self.conn.commit()
        return cur.lastrowid

    def redid_step(self, step_id: int, kind: str, summary: str, detail: dict,
                   made_at: str) -> None:
        """A step she pressed 'do it' on keeps its identity and changes its verdict, so the
        history shows what actually happened rather than a second entry pretending it was a
        different job."""
        self.conn.execute(
            "UPDATE steps SET kind = ?, summary = ?, detail = ?, made_at = ? WHERE id = ?",
            (kind, summary, json.dumps(detail, default=str), made_at, step_id))
        self.conn.commit()

    def steps_of(self, run_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, run, tool, args, kind, summary, detail, made_at FROM steps "
            "WHERE run = ? ORDER BY id", (run_id,)).fetchall()
        return [self._step(*r) for r in rows]

    def get_step(self, step_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, run, tool, args, kind, summary, detail, made_at FROM steps "
            "WHERE id = ?", (int(step_id),)).fetchone()
        return self._step(*row) if row else None

    @staticmethod
    def _step(i, run, t, a, k, s, d, m) -> dict:
        return {"id": i, "run": run, "tool": t, "args": json.loads(a), "kind": k,
                "summary": s, "detail": json.loads(d), "made_at": m}

    def get_run(self, run_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, asked, mode, planner, started_at, finished_at, summary "
            "FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(zip(("id", "asked", "mode", "planner", "started_at", "finished_at",
                        "summary"), row))
        run["steps"] = self.steps_of(run_id)
        return run

    def recent_runs(self, limit: int = 10) -> list[dict]:
        ids = [r[0] for r in self.conn.execute(
            "SELECT id FROM runs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()]
        return [self.get_run(i) for i in ids]

    def pending_steps(self) -> list[dict]:
        """Advised steps from any run, newest first - the queue the command centre works off."""
        rows = self.conn.execute(
            "SELECT id, run, tool, args, summary FROM steps WHERE kind = 'advised' "
            "ORDER BY id DESC LIMIT 40").fetchall()
        return [{"id": i, "run": r, "tool": t, "args": json.loads(a), "summary": s}
                for i, r, t, a, s in rows]

    def remember(self, kind: str, body: str, source: str = "", seen_at: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO notes (kind, body, source, seen_at) VALUES (?,?,?,?)",
            (kind, str(body)[:2000], str(source)[:120], seen_at))
        self.conn.commit()
        return cur.lastrowid

    def recall(self, kind: str | None = None, limit: int = 20) -> list[dict]:
        if kind:
            rows = self.conn.execute(
                "SELECT id, kind, body, source, seen_at FROM notes WHERE kind = ? "
                "ORDER BY id DESC LIMIT ?", (kind, int(limit))).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, kind, body, source, seen_at FROM notes ORDER BY id DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [{"id": i, "kind": k, "body": b, "source": s, "seen_at": t}
                for i, k, b, s, t in rows]

    def forget(self, note_id: int) -> None:
        """She corrects the memory by deleting it; nothing here quietly rewrites the past."""
        self.conn.execute("DELETE FROM notes WHERE id = ?", (int(note_id),))
        self.conn.commit()

    GRANTS_DEFAULT = {"auto": []}

    def get_grants(self) -> dict:
        row = self.conn.execute("SELECT payload FROM grants WHERE id = 1").fetchone()
        return {**self.GRANTS_DEFAULT, **json.loads(row[0])} if row else dict(self.GRANTS_DEFAULT)

    def save_grants(self, caps: list[str], mode: str = "") -> None:
        """The standing permissions and the last mode she used, in the one row that the
        agent screen reads back."""
        payload = {"auto": sorted(set(caps))}
        if mode:
            payload["mode"] = mode
        self.conn.execute("DELETE FROM grants")
        self.conn.execute("INSERT INTO grants VALUES (1, ?)", (json.dumps(payload),))
        self.conn.commit()

    def get_accounts(self) -> dict:
        """Which platforms she has marked, under which handle, and when an export last came
        in. A note about her own browser - no session, no password, nothing to lose."""
        row = self.conn.execute("SELECT payload FROM accounts WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else {}

    def save_account(self, platform: str, row: dict) -> None:
        data = self.get_accounts()
        data[platform] = {**data.get(platform, {}), **row}
        self.conn.execute("DELETE FROM accounts")
        self.conn.execute("INSERT INTO accounts VALUES (1, ?)", (json.dumps(data),))
        self.conn.commit()

    def get_staged(self) -> dict:
        row = self.conn.execute(
            "SELECT payload, made_at FROM staged WHERE id = 1").fetchone()
        return {**json.loads(row[0]), "made_at": row[1]} if row else {}

    def save_staged(self, package: dict, made_at: str) -> None:
        """The last thing she got ready to post. One row, overwritten on purpose: a queue of
        staged posts is a schedule she did not ask for."""
        self.conn.execute("DELETE FROM staged")
        self.conn.execute("INSERT INTO staged VALUES (1, ?, ?)",
                          (json.dumps(package), made_at))
        self.conn.commit()

    def add_bench(self, row: dict, made_at: str) -> int:
        """One post she wrote numbers for. A benchmark is a list, so this appends instead of
        replacing - the smallest honest comparison still needs five lines in it."""
        cur = self.conn.execute("INSERT INTO bench (payload, made_at) VALUES (?, ?)",
                                (json.dumps(row), made_at))
        self.conn.commit()
        return int(cur.lastrowid)

    def get_bench(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload, made_at FROM bench ORDER BY id").fetchall()
        return [{**json.loads(payload), "id": rid, "made_at": made_at}
                for rid, payload, made_at in rows]

    def forget_bench(self, bench_id: int) -> None:
        self.conn.execute("DELETE FROM bench WHERE id = ?", (int(bench_id),))
        self.conn.commit()

    def clear_bench(self) -> None:
        self.conn.execute("DELETE FROM bench")
        self.conn.commit()

    def add_collab(self, row: dict, made_at: str) -> int:
        """One person she wants to work with. Appends like a benchmark does: the names come from
        her, and nothing in this file is able to find one."""
        cur = self.conn.execute("INSERT INTO collab (payload, made_at) VALUES (?, ?)",
                                (json.dumps(row), made_at))
        self.conn.commit()
        return int(cur.lastrowid)

    def get_collab(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload, made_at, moved_at FROM collab ORDER BY id").fetchall()
        return [{**json.loads(payload), "id": rid, "made_at": made_at, "moved_at": moved}
                for rid, payload, made_at, moved in rows]

    def move_collab(self, collab_id: int, status: str, moved_at: str) -> bool:
        """The stage is the only field rewritten here, and only because she said it moved - this
        app cannot see a reply. False means the row is gone, so a stale link reports instead of
        inserting a candidate she never typed."""
        row = self.conn.execute("SELECT payload FROM collab WHERE id = ?",
                                 (int(collab_id),)).fetchone()
        if row is None:
            return False
        payload = json.loads(row[0])
        payload["status"] = status
        self.conn.execute("UPDATE collab SET payload = ?, moved_at = ? WHERE id = ?",
                          (json.dumps(payload), moved_at, int(collab_id)))
        self.conn.commit()
        return True

    def forget_collab(self, collab_id: int) -> None:
        self.conn.execute("DELETE FROM collab WHERE id = ?", (int(collab_id),))
        self.conn.commit()

    TERMS_DEFAULT = {"hourly": 0, "minutes": 0}

    def get_terms(self) -> dict:
        """The two numbers the money page cannot guess: what an hour of her time is worth to
        her, and how long a finished post actually takes. Blank is 0, and 0 means the app
        refuses to state a floor rather than adopting a wage."""
        row = self.conn.execute("SELECT payload FROM terms WHERE id = 1").fetchone()
        return {**self.TERMS_DEFAULT, **json.loads(row[0])} if row else dict(self.TERMS_DEFAULT)

    def save_terms(self, data: dict) -> None:
        self.conn.execute("DELETE FROM terms")
        self.conn.execute("INSERT INTO terms VALUES (1, ?)",
                          (json.dumps({**self.TERMS_DEFAULT, **data}),))
        self.conn.commit()

    CAPTION_DEFAULT = {"casual": False, "markers": False}

    def get_caption(self) -> dict:
        """Her two switches over the app's own typing, held the same way everything else here is
        held: absent means off, because an abbreviation the app guessed is a spelling she would
        have to own in front of whoever reads it."""
        row = self.conn.execute("SELECT payload FROM caption WHERE id = 1").fetchone()
        return {**self.CAPTION_DEFAULT, **json.loads(row[0])} if row else dict(self.CAPTION_DEFAULT)

    def save_caption(self, data: dict) -> None:
        self.conn.execute("DELETE FROM caption")
        self.conn.execute("INSERT INTO caption VALUES (1, ?)",
                          (json.dumps({**self.CAPTION_DEFAULT, **data}),))
        self.conn.commit()

    LANGUAGE_DEFAULT = {"targets": [], "keep": ""}

    def get_language(self) -> dict:
        """Which languages she posts in, and the words she does not want translated.

        Both start empty on purpose. A default of Spanish would be this app deciding her audience,
        and a keep-list of words she never named would put brand names she does not own in front of
        a model with an instruction not to translate them."""
        row = self.conn.execute("SELECT payload FROM language WHERE id = 1").fetchone()
        if not row:
            return dict(self.LANGUAGE_DEFAULT)
        data = {**self.LANGUAGE_DEFAULT, **json.loads(row[0])}
        data["targets"] = [str(c) for c in (data.get("targets") or [])]
        return data

    def save_language(self, data: dict) -> None:
        self.conn.execute("DELETE FROM language")
        self.conn.execute("INSERT INTO language VALUES (1, ?)",
                          (json.dumps({**self.LANGUAGE_DEFAULT, **data}),))
        self.conn.commit()

    def save_registry(self, features, upgrades, found_at) -> None:
        """The audit replaces the whole registry, because a registry that keeps entries for
        code that no longer exists is worse than no registry. Nothing is edited by hand in
        here, so there is nothing a re-run can lose."""
        with self.conn:
            for table, rows in (("feature", features), ("upgrade", upgrades)):
                self.conn.execute(f"DELETE FROM {table}")
                self.conn.executemany(
                    f"INSERT OR REPLACE INTO {table} (key, payload, dept, kind, status, name,"
                    " prove, found_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(r["key"], json.dumps(r), r["dept"], r["kind"], r["status"], r["name"],
                      " ".join(r["acceptance"]), found_at) for r in rows])

    def search_registry(self, kind, q="", dept="", status="", limit=400) -> list[dict]:
        """Searches the words she types against the name, the description and the tests that
        prove it - which is the only three things worth searching in a registry."""
        if kind not in ("feature", "upgrade"):
            raise ValueError(f"no such registry: {kind}")
        where, args = [], []
        if q:
            where.append("(lower(name) LIKE ? OR lower(prove) LIKE ? OR lower(payload) LIKE ?)")
            like = f"%{q.lower()}%"
            args += [like, like, like]
        if dept:
            where.append("dept = ?")
            args.append(dept)
        if status:
            where.append("status = ?")
            args.append(status)
        sql = f"SELECT payload FROM {kind}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY dept, name"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.conn.execute(sql, args).fetchall()
        return [json.loads(payload) for (payload,) in rows]

    def registry_totals(self) -> dict:
        out = {}
        for kind in ("feature", "upgrade"):
            rows = self.conn.execute(
                f"SELECT dept, status, COUNT(*) FROM {kind} GROUP BY dept, status").fetchall()
            out[kind] = [{"dept": d, "status": s, "n": n} for d, s, n in rows]
            out[kind + "_all"] = sum(n for _, _, n in rows)
        return out

