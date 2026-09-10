from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).with_name("mosaic_learn.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS topic_progress (
                user_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                reflection TEXT DEFAULT '',
                confidence INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, module_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                user_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                selected_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, module_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS shares (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS community_posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                module_id TEXT,
                topic_id TEXT,
                post_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def upsert_user(user_id: str, email: str, name: str, role: str):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, email, name, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email=excluded.email,
                name=excluded.name,
                role=excluded.role
            """,
            (user_id, email, name, role, now),
        )


def get_user(user_id: str):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def save_topic_progress(
    user_id: str,
    module_id: str,
    topic_id: str,
    *,
    completed: bool | None = None,
    reflection: str | None = None,
    confidence: int | None = None,
):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM topic_progress WHERE user_id=? AND module_id=? AND topic_id=?",
            (user_id, module_id, topic_id),
        ).fetchone()
        current = dict(existing) if existing else {
            "completed": 0,
            "reflection": "",
            "confidence": None,
        }
        new_completed = current["completed"] if completed is None else int(completed)
        new_reflection = current["reflection"] if reflection is None else reflection
        new_confidence = current["confidence"] if confidence is None else confidence
        conn.execute(
            """
            INSERT INTO topic_progress(user_id, module_id, topic_id, completed, reflection, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, module_id, topic_id) DO UPDATE SET
                completed=excluded.completed,
                reflection=excluded.reflection,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (user_id, module_id, topic_id, new_completed, new_reflection, new_confidence, now),
        )


def get_progress(user_id: str, module_id: str) -> dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM topic_progress WHERE user_id=? AND module_id=?",
            (user_id, module_id),
        ).fetchall()
    return {row["topic_id"]: dict(row) for row in rows}


def save_quiz_result(user_id: str, module_id: str, topic_id: str, selected_index: int, is_correct: bool):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO quiz_results(user_id, module_id, topic_id, is_correct, selected_index, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, module_id, topic_id) DO UPDATE SET
                is_correct=excluded.is_correct,
                selected_index=excluded.selected_index,
                updated_at=excluded.updated_at
            """,
            (user_id, module_id, topic_id, int(is_correct), int(selected_index), now),
        )


def get_quiz_results(user_id: str, module_id: str) -> dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM quiz_results WHERE user_id=? AND module_id=?",
            (user_id, module_id),
        ).fetchall()
    return {row["topic_id"]: dict(row) for row in rows}


def create_share(user_id: str, module_id: str, snapshot: dict) -> str:
    token = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO shares(token, user_id, module_id, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (token, user_id, module_id, json.dumps(snapshot), now),
        )
    return token


def get_share(token: str):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["snapshot"] = json.loads(data.pop("snapshot_json"))
    return data


def create_community_post(user_id: str, author_name: str, post_text: str, module_id: str | None = None, topic_id: str | None = None):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO community_posts(user_id, author_name, module_id, topic_id, post_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, author_name, module_id, topic_id, post_text.strip(), now),
        )


def list_community_posts(limit: int = 30):
    limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM community_posts ORDER BY post_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
