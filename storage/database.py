from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from config import DB_PATH, STORAGE_DIR


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS missions (
            mission_id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
            summary TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY, title TEXT, description TEXT, status TEXT,
            task_type TEXT, skill_name TEXT, dependencies TEXT, artifact_path TEXT,
            created_at TEXT
        )""")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        migrations = {
            "mission_id": "TEXT DEFAULT ''", "input_data": "TEXT DEFAULT '{}'",
            "result": "TEXT DEFAULT ''", "error": "TEXT DEFAULT ''",
        }
        for name, declaration in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {declaration}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)")
        conn.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            mission_id TEXT DEFAULT '', task_id TEXT DEFAULT '', level TEXT DEFAULT 'INFO',
            message TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        conn.execute("""CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, timestamp TEXT,
            agent TEXT, tool_name TEXT, arguments TEXT, status TEXT, output TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, step_name TEXT,
            completed_at TEXT, artifact_path TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS processes (
            pid INTEGER PRIMARY KEY, task_id TEXT, command TEXT, status TEXT, started_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, action TEXT,
            reason TEXT, timestamp TEXT
        )""")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_mission(mission_id: str, request: str, status: str, summary: str = "") -> None:
    now = _now()
    with _db() as conn:
        conn.execute("""INSERT INTO missions(mission_id,request,status,summary,created_at,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(mission_id) DO UPDATE SET
            status=excluded.status, summary=excluded.summary, updated_at=excluded.updated_at""",
            (mission_id, request, status, summary, now, now))


def save_task(task: Any) -> None:
    with _db() as conn:
        conn.execute("""INSERT INTO tasks
            (task_id,title,description,status,task_type,skill_name,dependencies,artifact_path,created_at,mission_id,input_data,result,error)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET title=excluded.title, description=excluded.description,
            status=excluded.status, task_type=excluded.task_type, skill_name=excluded.skill_name,
            dependencies=excluded.dependencies, artifact_path=excluded.artifact_path,
            mission_id=excluded.mission_id, input_data=excluded.input_data,
            result=excluded.result, error=excluded.error""",
            (task.task_id, task.title, task.description, task.status.value, task.task_type,
             task.skill_name, json.dumps(task.dependencies, ensure_ascii=False), task.artifact_path,
             task.created_at.isoformat(), task.mission_id,
             json.dumps(task.input_data, ensure_ascii=False), task.result, task.error))


def emit_event(message: str, level: str = "INFO", mission_id: str = "", task_id: str = "") -> int:
    with _db() as conn:
        cur = conn.execute("INSERT INTO events(timestamp,mission_id,task_id,level,message) VALUES(?,?,?,?,?)",
                           (_now(), mission_id, task_id, level, message))
        return int(cur.lastrowid)


def get_events_since(event_id: int = 0, limit: int = 300):
    with _db() as conn:
        return conn.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (event_id, limit)).fetchall()


def get_latest_event_id() -> int:
    with _db() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id),0) AS n FROM events").fetchone()
        return int(row["n"])


def get_all_tasks(limit: int = 200):
    with _db() as conn:
        return conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def get_task(task_id: str):
    with _db() as conn:
        return conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()


def get_task_history(task_id: str):
    with _db() as conn:
        executions = conn.execute("SELECT * FROM executions WHERE task_id=? ORDER BY timestamp DESC", (task_id,)).fetchall()
        checkpoints = conn.execute("SELECT * FROM checkpoints WHERE task_id=? ORDER BY completed_at DESC", (task_id,)).fetchall()
        return executions, checkpoints


def log_execution(task_id: str, agent: str, tool_name: str, arguments: str, status: str, output: str) -> None:
    with _db() as conn:
        conn.execute("INSERT INTO executions(task_id,timestamp,agent,tool_name,arguments,status,output) VALUES(?,?,?,?,?,?,?)",
                     (task_id, _now(), agent, tool_name, arguments, status, output[:4000]))


def save_checkpoint(task_id: str, step_name: str, artifact_path: str | None = None) -> None:
    with _db() as conn:
        conn.execute("INSERT INTO checkpoints(task_id,step_name,completed_at,artifact_path) VALUES(?,?,?,?)",
                     (task_id, step_name, _now(), artifact_path))


def recover_interrupted_tasks() -> int:
    """Mark tasks left RUNNING by a previous process; never blindly rerun side effects."""
    with _db() as conn:
        rows = conn.execute("SELECT task_id,mission_id FROM tasks WHERE status='RUNNING'").fetchall()
        for row in rows:
            conn.execute("UPDATE tasks SET status='FAILED', error=? WHERE task_id=?",
                         ("FORGE đã dừng trước khi tác vụ kết thúc. Hãy gửi lại nhiệm vụ để chạy lại an toàn.", row["task_id"]))
            conn.execute("INSERT INTO events(timestamp,mission_id,task_id,level,message) VALUES(?,?,?,?,?)",
                         (_now(), row["mission_id"] or "", row["task_id"], "WARN", "Tác vụ bị gián đoạn ở phiên FORGE trước; không tự chạy lại để tránh lặp side-effect."))
        return len(rows)
