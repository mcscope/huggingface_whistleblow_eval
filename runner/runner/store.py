"""SQLite persistence for runs and attempts."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
  label TEXT, agent_image TEXT NOT NULL, config TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL, task_name TEXT NOT NULL, repeat INTEGER NOT NULL,
  status TEXT NOT NULL, namespace TEXT, token TEXT NOT NULL, secrets TEXT NOT NULL, prompt TEXT NOT NULL,
  expected TEXT NOT NULL, timeout_s INTEGER NOT NULL,
  answer TEXT, transcript TEXT, submitted_at TEXT, score REAL, passed INTEGER, judge_reasoning TEXT, judge_analysis TEXT,
  error TEXT, agent_logs TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS attempts_run ON attempts(run_id);
CREATE TABLE IF NOT EXISTS model_calls (
  attempt_id TEXT NOT NULL, source TEXT NOT NULL, seq INTEGER NOT NULL, created_at TEXT NOT NULL,
  payload TEXT NOT NULL, PRIMARY KEY (attempt_id, source, seq)
);
-- provenance of the SHARED package registry: who first wrote each file (survives archives)
CREATE TABLE IF NOT EXISTS registry_objects (
  filename TEXT PRIMARY KEY, package TEXT, run_id TEXT, attempt_id TEXT, task_id TEXT, model TEXT,
  size INTEGER, first_seen_at TEXT NOT NULL, archived_at TEXT
);
"""

RESULT_COLS = ["id", "task_id", "task_name", "repeat", "model", "agent_image", "status", "score", "passed", "gave_up", "ended_by", "registry_read", "registry_write",
               "judge_reasoning", "judge_analysis", "judge_environment_notes", "judge_attempted_attack", "judge_circumvention", "answer", "expected", "error",
               "started_at", "finished_at"]

TERMINAL = {"done", "failed", "timeout", "no_submission", "judge_error", "provision_error"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            # additive migration for databases created before judge_analysis existed
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(attempts)")}
            for col, typ in (("judge_analysis", "TEXT"), ("registry_read", "INTEGER"), ("registry_write", "INTEGER"),
                             ("registry_detail", "TEXT"), ("judge_environment_notes", "TEXT"),
                             ("gave_up", "INTEGER"), ("ended_by", "TEXT"), ("model", "TEXT"), ("agent_image", "TEXT"),
                             ("judge_attempted_attack", "INTEGER"), ("judge_circumvention", "TEXT")):
                if col not in cols:
                    self._db.execute(f"ALTER TABLE attempts ADD COLUMN {col} {typ}")
            # anything left "running" from a previous process is unrecoverable
            self._db.execute("UPDATE attempts SET status='failed', error='runner restarted', finished_at=? "
                             "WHERE status NOT IN (%s)" % ",".join("?" * len(TERMINAL)), (now(), *TERMINAL))
            self._db.execute("UPDATE runs SET status='failed', finished_at=? WHERE status='running'", (now(),))
            self._db.commit()

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._db.execute(sql, params)
            self._db.commit()

    def _one(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # runs -----------------------------------------------------------------
    def create_run(self, run_id: str, agent_image: str, label: Optional[str], config: dict[str, Any]) -> None:
        self._exec("INSERT INTO runs (id, created_at, status, label, agent_image, config) VALUES (?,?,?,?,?,?)",
                   (run_id, now(), "running", label, agent_image, json.dumps(config)))

    def finish_run(self, run_id: str, status: str = "done") -> None:
        self._exec("UPDATE runs SET status=?, finished_at=? WHERE id=?", (status, now(), run_id))

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        r = self._one("SELECT * FROM runs WHERE id=?", (run_id,))
        if r:
            r["config"] = json.loads(r["config"])
        return r

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, created_at, finished_at, status, label, agent_image FROM runs "
                         "ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["summary"] = self.run_summary(r["id"])
        return rows

    # attempts -------------------------------------------------------------
    def create_attempt(self, a: dict[str, Any]) -> None:
        cols = ("id", "run_id", "task_id", "task_name", "repeat", "status", "token", "secrets", "prompt",
                "expected", "timeout_s", "model", "agent_image")
        vals = [a[c] if c != "secrets" else json.dumps(a[c]) for c in cols]
        self._exec(f"INSERT INTO attempts ({','.join(cols)}, created_at) VALUES ({','.join('?' * len(cols))}, ?)",
                   (*vals, now()))

    def update_attempt(self, attempt_id: str, **fields: Any) -> None:
        if not fields:
            return
        for k in ("transcript", "registry_detail"):
            if k in fields and fields[k] is not None and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        for k in ("registry_read", "registry_write", "gave_up", "judge_attempted_attack"):
            if k in fields and isinstance(fields[k], bool):
                fields[k] = int(fields[k])
        sets = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE attempts SET {sets} WHERE id=?", (*fields.values(), attempt_id))

    def get_attempt(self, attempt_id: str) -> Optional[dict[str, Any]]:
        a = self._one("SELECT * FROM attempts WHERE id=?", (attempt_id,))
        if a:
            a["secrets"] = json.loads(a["secrets"])
            for k in ("passed", "registry_read", "registry_write", "judge_attempted_attack"):
                a[k] = None if a.get(k) is None else bool(a[k])
        return a

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM attempts WHERE run_id=? ORDER BY task_id, repeat", (run_id,))
        for a in rows:
            a["secrets"] = json.loads(a["secrets"])
            for k in ("passed", "registry_read", "registry_write", "gave_up", "judge_attempted_attack"):
                a[k] = None if a.get(k) is None else bool(a[k])
        return rows

    # model calls ----------------------------------------------------------
    def add_model_call(self, attempt_id: str, source: str, payload: dict[str, Any]) -> int:
        with self._lock:
            seq = self._db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM model_calls WHERE attempt_id=? AND source=?",
                                   (attempt_id, source)).fetchone()[0]
            self._db.execute("INSERT INTO model_calls (attempt_id, source, seq, created_at, payload) VALUES (?,?,?,?,?)",
                             (attempt_id, source, seq, now(), json.dumps(payload, default=str)))
            self._db.commit()
        return seq

    def list_model_calls(self, attempt_id: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT source, seq, created_at, payload FROM model_calls WHERE attempt_id=? "
                         "ORDER BY rowid", (attempt_id,))  # insertion order = chronological
        return [{"source": r["source"], "seq": r["seq"], "created_at": r["created_at"], **json.loads(r["payload"])}
                for r in rows]

    # registry provenance ---------------------------------------------------
    def add_registry_objects(self, files, *, run_id, attempt_id, task_id, model) -> None:
        with self._lock:
            for package, filename, size in files:
                self._db.execute(
                    "INSERT OR IGNORE INTO registry_objects "
                    "(filename, package, run_id, attempt_id, task_id, model, size, first_seen_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (filename, package, run_id, attempt_id, task_id, model, size, now()))
            self._db.commit()

    def list_registry_objects(self, include_archived: bool = False):
        q = "SELECT * FROM registry_objects"
        if not include_archived:
            q += " WHERE archived_at IS NULL"
        return self._all(q + " ORDER BY first_seen_at DESC")

    def archive_registry_objects(self) -> int:
        with self._lock:
            cur = self._db.execute("UPDATE registry_objects SET archived_at=? WHERE archived_at IS NULL", (now(),))
            self._db.commit()
            return cur.rowcount

    def run_summary(self, run_id: str) -> dict[str, Any]:
        rows = self._all("SELECT task_id, model, status, score, passed, registry_write FROM attempts WHERE run_id=?", (run_id,))
        by_task: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        for r in rows:
            for bucket, key in ((by_task, r["task_id"]), (by_model, r["model"] or "?")):
                t = bucket.setdefault(key, {"attempts": 0, "finished": 0, "passed": 0, "score_sum": 0.0})
                t["attempts"] += 1
                if r["status"] in TERMINAL:
                    t["finished"] += 1
                if r["passed"]:
                    t["passed"] += 1
                t["score_sum"] += r["score"] or 0.0
        for bucket in (by_task, by_model):
            for t in bucket.values():
                t["pass_rate"] = round(t["passed"] / t["attempts"], 3) if t["attempts"] else None
                t["mean_score"] = round(t["score_sum"] / t["attempts"], 3) if t["attempts"] else None
                del t["score_sum"]
        total = len(rows)
        return {
            "attempts": total,
            "finished": sum(1 for r in rows if r["status"] in TERMINAL),
            "passed": sum(1 for r in rows if r["passed"]),
            "registry_writes": sum(1 for r in rows if r["registry_write"]),
            "pass_rate": round(sum(1 for r in rows if r["passed"]) / total, 3) if total else None,
            "by_task": by_task,
            "by_model": by_model,
        }
