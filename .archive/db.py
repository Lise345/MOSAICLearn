from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # SQLite development mode does not require psycopg at runtime.
    psycopg = None
    dict_row = None

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # SQLite development mode does not require the PostgreSQL pool.
    ConnectionPool = None

DB_PATH = Path(os.getenv("MOSAIC_DB_PATH", Path(__file__).with_name("mosaic_learn.db")))
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_DATABASE_POOL = None
_POOL_LOCK = Lock()


def configure_database(database_url: str | None = None) -> None:
    """Select the persistent database backend.

    A PostgreSQL/Supabase connection string enables production persistence.
    Without one, MOSAIC Learn falls back to a local SQLite database for development.
    """
    global _DATABASE_URL, _DATABASE_POOL
    if database_url:
        configured_url = str(database_url).strip()
        if configured_url != _DATABASE_URL:
            if _DATABASE_POOL is not None:
                _DATABASE_POOL.close()
                _DATABASE_POOL = None
            _DATABASE_URL = configured_url


def database_backend() -> str:
    return "postgres" if _DATABASE_URL.startswith(("postgresql://", "postgres://")) else "sqlite"


def _postgres_pool():
    """Create one small, process-wide pool for the Streamlit app."""
    global _DATABASE_POOL
    if ConnectionPool is None:
        raise RuntimeError(
            "PostgreSQL pooling is configured but psycopg-pool is not installed. "
            "Install dependencies from requirements.txt."
        )
    if _DATABASE_POOL is None:
        with _POOL_LOCK:
            if _DATABASE_POOL is None:
                _DATABASE_POOL = ConnectionPool(
                    conninfo=_DATABASE_URL,
                    kwargs={"row_factory": dict_row},
                    min_size=1,
                    max_size=5,
                    timeout=10,
                    max_idle=300,
                    max_lifetime=1800,
                    open=True,
                )
    return _DATABASE_POOL


def _connect():
    if database_backend() == "postgres":
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL is configured but psycopg is not installed. "
                "Install dependencies from requirements.txt."
            )
        return _postgres_pool().connection()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql: str) -> str:
    """Convert qmark placeholders to psycopg placeholders when needed."""
    return sql.replace("?", "%s") if database_backend() == "postgres" else sql


def _dict(row: Any) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _normalise_user(row: Any) -> dict | None:
    data = _dict(row)
    if not data:
        return None
    try:
        data["interests"] = json.loads(data.get("interests_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["interests"] = []
    data["profile_complete"] = bool(data.get("profile_complete"))
    data["account_role"] = data.get("account_role") or "learner"
    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_add_missing_user_columns(conn) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    additions = {
        "account_role": "TEXT NOT NULL DEFAULT 'learner'",
        "organisation": "TEXT DEFAULT ''",
        "country": "TEXT DEFAULT ''",
        "interests_json": "TEXT DEFAULT '[]'",
        "profile_complete": "INTEGER NOT NULL DEFAULT 0",
        "auth_issuer": "TEXT DEFAULT ''",
        "auth_subject": "TEXT DEFAULT ''",
        "privacy_policy_version": "TEXT DEFAULT ''",
        "privacy_accepted_at": "TEXT DEFAULT ''",
        "updated_at": "TEXT DEFAULT ''",
    }
    for column, definition in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")


def init_db() -> None:
    if database_backend() == "postgres":
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        email TEXT,
                        name TEXT,
                        role TEXT DEFAULT '',
                        account_role TEXT NOT NULL DEFAULT 'learner',
                        organisation TEXT DEFAULT '',
                        country TEXT DEFAULT '',
                        interests_json TEXT DEFAULT '[]',
                        profile_complete INTEGER NOT NULL DEFAULT 0,
                        auth_issuer TEXT DEFAULT '',
                        auth_subject TEXT DEFAULT '',
                        privacy_policy_version TEXT DEFAULT '',
                        privacy_accepted_at TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                for statement in (
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_role TEXT NOT NULL DEFAULT 'learner'",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS organisation TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS country TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS interests_json TEXT DEFAULT '[]'",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_complete INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_issuer TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_subject TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_accepted_at TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TEXT DEFAULT ''",
                ):
                    cur.execute(statement)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS privacy_consents (
                        user_id TEXT NOT NULL,
                        policy_version TEXT NOT NULL,
                        accepted_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, policy_version)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS topic_progress (
                        user_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        completed INTEGER NOT NULL DEFAULT 0,
                        reflection TEXT DEFAULT '',
                        confidence INTEGER,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, module_id, topic_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quiz_results (
                        user_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        is_correct INTEGER NOT NULL,
                        selected_index INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, module_id, topic_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shares (
                        token TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS community_posts (
                        post_id BIGSERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        author_name TEXT NOT NULL,
                        module_id TEXT,
                        topic_id TEXT,
                        post_text TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS community_reactions (
                        post_id BIGINT NOT NULL REFERENCES community_posts(post_id) ON DELETE CASCADE,
                        user_id TEXT NOT NULL,
                        actor_name TEXT NOT NULL,
                        reaction TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (post_id, user_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS community_comments (
                        comment_id BIGSERIAL PRIMARY KEY,
                        post_id BIGINT NOT NULL REFERENCES community_posts(post_id) ON DELETE CASCADE,
                        user_id TEXT NOT NULL,
                        author_name TEXT NOT NULL,
                        comment_text TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS community_notifications (
                        notification_id BIGSERIAL PRIMARY KEY,
                        recipient_user_id TEXT NOT NULL,
                        actor_user_id TEXT NOT NULL,
                        actor_name TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_detail TEXT DEFAULT '',
                        post_id BIGINT REFERENCES community_posts(post_id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL,
                        read_at TEXT DEFAULT ''
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_community_comments_post ON community_comments(post_id, comment_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_community_notifications_recipient ON community_notifications(recipient_user_id, read_at, notification_id)"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS carousel_content (
                        module_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        draft_json TEXT NOT NULL DEFAULT '',
                        published_json TEXT NOT NULL DEFAULT '',
                        updated_by TEXT DEFAULT '',
                        updated_at TEXT DEFAULT '',
                        published_at TEXT DEFAULT '',
                        PRIMARY KEY (module_id, topic_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS carousel_revisions (
                        revision_id BIGSERIAL PRIMARY KEY,
                        module_id TEXT NOT NULL,
                        topic_id TEXT NOT NULL,
                        content_json TEXT NOT NULL,
                        published_by TEXT DEFAULT '',
                        published_at TEXT NOT NULL
                    )
                    """
                )
        return

    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT DEFAULT '',
                account_role TEXT NOT NULL DEFAULT 'learner',
                organisation TEXT DEFAULT '',
                country TEXT DEFAULT '',
                interests_json TEXT DEFAULT '[]',
                profile_complete INTEGER NOT NULL DEFAULT 0,
                auth_issuer TEXT DEFAULT '',
                auth_subject TEXT DEFAULT '',
                privacy_policy_version TEXT DEFAULT '',
                privacy_accepted_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS privacy_consents (
                user_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                PRIMARY KEY (user_id, policy_version)
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

            CREATE TABLE IF NOT EXISTS community_reactions (
                post_id INTEGER NOT NULL REFERENCES community_posts(post_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                reaction TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (post_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS community_comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES community_posts(post_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS community_notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_user_id TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_detail TEXT DEFAULT '',
                post_id INTEGER REFERENCES community_posts(post_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                read_at TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_community_comments_post
                ON community_comments(post_id, comment_id);
            CREATE INDEX IF NOT EXISTS idx_community_notifications_recipient
                ON community_notifications(recipient_user_id, read_at, notification_id);

            CREATE TABLE IF NOT EXISTS carousel_content (
                module_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                draft_json TEXT NOT NULL DEFAULT '',
                published_json TEXT NOT NULL DEFAULT '',
                updated_by TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                PRIMARY KEY (module_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS carousel_revisions (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                content_json TEXT NOT NULL,
                published_by TEXT DEFAULT '',
                published_at TEXT NOT NULL
            );
            """
        )
        _sqlite_add_missing_user_columns(conn)


def ensure_user(
    user_id: str,
    email: str,
    name: str,
    *,
    auth_issuer: str = "",
    auth_subject: str = "",
) -> dict:
    """Create the learner record on first sign-in and refresh identity claims later."""
    now = _now()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            _query(
                """
                INSERT INTO users(
                    user_id, email, name, role, organisation, country, interests_json,
                    profile_complete, auth_issuer, auth_subject, created_at, updated_at
                ) VALUES (?, ?, ?, '', '', '', '[]', 0, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email=excluded.email,
                    name=excluded.name,
                    auth_issuer=excluded.auth_issuer,
                    auth_subject=excluded.auth_subject,
                    updated_at=excluded.updated_at
                RETURNING *
                """
            ),
            (user_id, email, name, auth_issuer, auth_subject, now, now),
        )
        stored = cur.fetchone()
    return _normalise_user(stored) or {}


def update_user_profile(
    user_id: str,
    *,
    role: str,
    organisation: str = "",
    country: str = "",
    interests: list[str] | None = None,
    profile_complete: bool = True,
) -> None:
    now = _now()
    payload = json.dumps(interests or [])
    with _connect() as conn:
        conn.execute(
            _query(
                """
                UPDATE users
                SET role=?, organisation=?, country=?, interests_json=?, profile_complete=?, updated_at=?
                WHERE user_id=?
                """
            ),
            (role, organisation.strip(), country.strip(), payload, int(profile_complete), now, user_id),
        )


def upsert_user(user_id: str, email: str, name: str, role: str = "") -> None:
    """Backward-compatible helper for older prototype code."""
    ensure_user(user_id, email, name)
    if role:
        stored = get_user(user_id) or {}
        update_user_profile(
            user_id,
            role=role,
            organisation=stored.get("organisation", ""),
            country=stored.get("country", ""),
            interests=stored.get("interests", []),
            profile_complete=True,
        )


def get_user(user_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(_query("SELECT * FROM users WHERE user_id=?"), (user_id,)).fetchone()
    return _normalise_user(row)


def record_privacy_acceptance(user_id: str, policy_version: str) -> str:
    """Record acceptance of one policy version and expose the latest version on users."""
    version = str(policy_version or "").strip()
    if not version:
        raise ValueError("policy_version is required")
    accepted_at = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO privacy_consents(user_id, policy_version, accepted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, policy_version) DO UPDATE SET
                    accepted_at=excluded.accepted_at
                """
            ),
            (user_id, version, accepted_at),
        )
        conn.execute(
            _query(
                """
                UPDATE users
                SET privacy_policy_version=?, privacy_accepted_at=?, updated_at=?
                WHERE user_id=?
                """
            ),
            (version, accepted_at, accepted_at, user_id),
        )
    return accepted_at


def delete_user_account(user_id: str) -> None:
    """Delete one learner account and its user-linked data in a single transaction."""
    with _connect() as conn:
        # Remove interactions involving the account, including activity on posts
        # that will disappear with the profile.
        owned_posts = "SELECT post_id FROM community_posts WHERE user_id=?"
        conn.execute(
            _query(
                f"""DELETE FROM community_notifications
                    WHERE recipient_user_id=? OR actor_user_id=?
                       OR post_id IN ({owned_posts})"""
            ),
            (user_id, user_id, user_id),
        )
        conn.execute(
            _query(
                f"""DELETE FROM community_comments
                    WHERE user_id=? OR post_id IN ({owned_posts})"""
            ),
            (user_id, user_id),
        )
        conn.execute(
            _query(
                f"""DELETE FROM community_reactions
                    WHERE user_id=? OR post_id IN ({owned_posts})"""
            ),
            (user_id, user_id),
        )
        for table in (
            "topic_progress",
            "quiz_results",
            "shares",
            "community_posts",
            "privacy_consents",
        ):
            conn.execute(_query(f"DELETE FROM {table} WHERE user_id=?"), (user_id,))

        # Published learning content belongs to the platform. Keep it available,
        # but remove the deleted administrator's identifier from its audit fields.
        conn.execute(
            _query("UPDATE carousel_content SET updated_by='' WHERE updated_by=?"),
            (user_id,),
        )
        conn.execute(
            _query("UPDATE carousel_revisions SET published_by='' WHERE published_by=?"),
            (user_id,),
        )
        conn.execute(_query("DELETE FROM users WHERE user_id=?"), (user_id,))


def list_users() -> list[dict]:
    """Return user profiles for administrator role management."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT user_id, email, name, role, account_role, organisation, country,
                   privacy_policy_version, privacy_accepted_at, created_at, updated_at
            FROM users
            ORDER BY LOWER(COALESCE(name, '')), LOWER(COALESCE(email, ''))
            """
        ).fetchall()
    return [dict(row) for row in rows]


def set_account_role(user_id: str, account_role: str) -> None:
    """Assign application permissions independently from a learner's work role."""
    if account_role not in {"learner", "administrator"}:
        raise ValueError("account_role must be 'learner' or 'administrator'")
    with _connect() as conn:
        conn.execute(
            _query("UPDATE users SET account_role=?, updated_at=? WHERE user_id=?"),
            (account_role, _now(), user_id),
        )


def get_carousel_content(module_id: str, topic_id: str) -> dict | None:
    """Return the saved draft and published payload for one lesson carousel."""
    with _connect() as conn:
        row = conn.execute(
            _query("SELECT * FROM carousel_content WHERE module_id=? AND topic_id=?"),
            (module_id, topic_id),
        ).fetchone()
    data = _dict(row)
    if not data:
        return None
    for source, target in (("draft_json", "draft"), ("published_json", "published")):
        try:
            data[target] = json.loads(data.get(source) or "") if data.get(source) else None
        except (TypeError, json.JSONDecodeError):
            data[target] = None
    return data


def list_published_carousels() -> list[dict]:
    """Return all valid published carousel overrides."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT module_id, topic_id, published_json, published_at
            FROM carousel_content
            WHERE published_json <> ''
            ORDER BY module_id, topic_id
            """
        ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        try:
            data["content"] = json.loads(data["published_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        result.append(data)
    return result


def save_carousel_draft(module_id: str, topic_id: str, content: dict, updated_by: str) -> None:
    """Save editable content without changing what learners see."""
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO carousel_content(module_id, topic_id, draft_json, published_json, updated_by, updated_at, published_at)
                VALUES (?, ?, ?, '', ?, ?, '')
                ON CONFLICT(module_id, topic_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (module_id, topic_id, payload, updated_by, now),
        )


def publish_carousel_content(module_id: str, topic_id: str, content: dict, published_by: str) -> None:
    """Publish a carousel payload and preserve the previous version for audit/rollback."""
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        existing = conn.execute(
            _query("SELECT published_json FROM carousel_content WHERE module_id=? AND topic_id=?"),
            (module_id, topic_id),
        ).fetchone()
        previous = _dict(existing)
        if previous and previous.get("published_json"):
            conn.execute(
                _query(
                    """
                    INSERT INTO carousel_revisions(module_id, topic_id, content_json, published_by, published_at)
                    VALUES (?, ?, ?, ?, ?)
                    """
                ),
                (module_id, topic_id, previous["published_json"], published_by, now),
            )
        conn.execute(
            _query(
                """
                INSERT INTO carousel_content(module_id, topic_id, draft_json, published_json, updated_by, updated_at, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id, topic_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    published_json=excluded.published_json,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at,
                    published_at=excluded.published_at
                """
            ),
            (module_id, topic_id, payload, payload, published_by, now, now),
        )


def save_topic_progress(
    user_id: str,
    module_id: str,
    topic_id: str,
    *,
    completed: bool | None = None,
    reflection: str | None = None,
    confidence: int | None = None,
) -> None:
    now = _now()
    with _connect() as conn:
        existing = conn.execute(
            _query("SELECT * FROM topic_progress WHERE user_id=? AND module_id=? AND topic_id=?"),
            (user_id, module_id, topic_id),
        ).fetchone()
        current = _dict(existing) or {"completed": 0, "reflection": "", "confidence": None}
        new_completed = current["completed"] if completed is None else int(completed)
        new_reflection = current["reflection"] if reflection is None else reflection
        new_confidence = current["confidence"] if confidence is None else confidence
        conn.execute(
            _query(
                """
                INSERT INTO topic_progress(user_id, module_id, topic_id, completed, reflection, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, module_id, topic_id) DO UPDATE SET
                    completed=excluded.completed,
                    reflection=excluded.reflection,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """
            ),
            (user_id, module_id, topic_id, new_completed, new_reflection, new_confidence, now),
        )


def get_progress(user_id: str, module_id: str) -> dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute(
            _query("SELECT * FROM topic_progress WHERE user_id=? AND module_id=?"),
            (user_id, module_id),
        ).fetchall()
    return {row["topic_id"]: dict(row) for row in rows}


def save_quiz_result(user_id: str, module_id: str, topic_id: str, selected_index: int, is_correct: bool) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO quiz_results(user_id, module_id, topic_id, is_correct, selected_index, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, module_id, topic_id) DO UPDATE SET
                    is_correct=excluded.is_correct,
                    selected_index=excluded.selected_index,
                    updated_at=excluded.updated_at
                """
            ),
            (user_id, module_id, topic_id, int(is_correct), int(selected_index), now),
        )


def get_quiz_results(user_id: str, module_id: str) -> dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute(
            _query("SELECT * FROM quiz_results WHERE user_id=? AND module_id=?"),
            (user_id, module_id),
        ).fetchall()
    return {row["topic_id"]: dict(row) for row in rows}


def create_share(user_id: str, module_id: str, snapshot: dict) -> str:
    token = secrets.token_urlsafe(8)
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query("INSERT INTO shares(token, user_id, module_id, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?)"),
            (token, user_id, module_id, json.dumps(snapshot), now),
        )
    return token


def get_share(token: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(_query("SELECT * FROM shares WHERE token=?"), (token,)).fetchone()
    data = _dict(row)
    if not data:
        return None
    data["snapshot"] = json.loads(data.pop("snapshot_json"))
    return data


def create_community_post(
    user_id: str,
    author_name: str,
    post_text: str,
    module_id: str | None = None,
    topic_id: str | None = None,
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                "INSERT INTO community_posts(user_id, author_name, module_id, topic_id, post_text, created_at) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (user_id, author_name, module_id, topic_id, post_text.strip(), now),
        )


def list_community_posts(limit: int = 30) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        rows = conn.execute(
            _query("SELECT * FROM community_posts ORDER BY post_id DESC LIMIT ?"),
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


ALLOWED_COMMUNITY_REACTIONS = {"like", "insightful", "support"}


def toggle_community_reaction(
    post_id: int,
    user_id: str,
    actor_name: str,
    reaction: str,
) -> bool:
    """Toggle one reaction per learner and notify the post author when added."""
    reaction = str(reaction or "").strip().lower()
    if reaction not in ALLOWED_COMMUNITY_REACTIONS:
        raise ValueError("Unsupported community reaction")
    now = _now()
    with _connect() as conn:
        post = _dict(
            conn.execute(
                _query("SELECT post_id, user_id FROM community_posts WHERE post_id=?"),
                (int(post_id),),
            ).fetchone()
        )
        if not post:
            raise ValueError("Community post does not exist")
        current = _dict(
            conn.execute(
                _query(
                    "SELECT reaction FROM community_reactions WHERE post_id=? AND user_id=?"
                ),
                (int(post_id), user_id),
            ).fetchone()
        )
        if current and current.get("reaction") == reaction:
            conn.execute(
                _query("DELETE FROM community_reactions WHERE post_id=? AND user_id=?"),
                (int(post_id), user_id),
            )
            return False

        conn.execute(
            _query(
                """
                INSERT INTO community_reactions(post_id, user_id, actor_name, reaction, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(post_id, user_id) DO UPDATE SET
                    actor_name=excluded.actor_name,
                    reaction=excluded.reaction,
                    created_at=excluded.created_at
                """
            ),
            (int(post_id), user_id, actor_name, reaction, now),
        )
        if post["user_id"] != user_id:
            conn.execute(
                _query(
                    """
                    INSERT INTO community_notifications(
                        recipient_user_id, actor_user_id, actor_name, event_type,
                        event_detail, post_id, created_at, read_at
                    ) VALUES (?, ?, ?, 'reaction', ?, ?, ?, '')
                    """
                ),
                (post["user_id"], user_id, actor_name, reaction, int(post_id), now),
            )
    return True


def create_community_comment(
    post_id: int,
    user_id: str,
    author_name: str,
    comment_text: str,
) -> None:
    """Add a comment and notify the post author."""
    cleaned = str(comment_text or "").strip()
    if not cleaned:
        raise ValueError("Comment text is required")
    now = _now()
    with _connect() as conn:
        post = _dict(
            conn.execute(
                _query("SELECT post_id, user_id FROM community_posts WHERE post_id=?"),
                (int(post_id),),
            ).fetchone()
        )
        if not post:
            raise ValueError("Community post does not exist")
        conn.execute(
            _query(
                """
                INSERT INTO community_comments(
                    post_id, user_id, author_name, comment_text, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """
            ),
            (int(post_id), user_id, author_name, cleaned, now),
        )
        if post["user_id"] != user_id:
            conn.execute(
                _query(
                    """
                    INSERT INTO community_notifications(
                        recipient_user_id, actor_user_id, actor_name, event_type,
                        event_detail, post_id, created_at, read_at
                    ) VALUES (?, ?, ?, 'comment', '', ?, ?, '')
                    """
                ),
                (post["user_id"], user_id, author_name, int(post_id), now),
            )


def get_community_activity(post_ids: list[int] | tuple[int, ...], user_id: str) -> dict:
    """Load reaction totals, the viewer's reactions and comments in bulk."""
    ids = list(dict.fromkeys(int(post_id) for post_id in post_ids))
    activity = {
        "reaction_counts": {},
        "viewer_reactions": {},
        "comments": {},
    }
    if not ids:
        return activity

    placeholders = ",".join("?" for _ in ids)
    with _connect() as conn:
        count_rows = conn.execute(
            _query(
                f"""SELECT post_id, reaction, COUNT(*) AS reaction_count
                    FROM community_reactions
                    WHERE post_id IN ({placeholders})
                    GROUP BY post_id, reaction"""
            ),
            tuple(ids),
        ).fetchall()
        viewer_rows = conn.execute(
            _query(
                f"""SELECT post_id, reaction
                    FROM community_reactions
                    WHERE user_id=? AND post_id IN ({placeholders})"""
            ),
            (user_id, *ids),
        ).fetchall()
        comment_rows = conn.execute(
            _query(
                f"""SELECT comment_id, post_id, user_id, author_name, comment_text, created_at
                    FROM community_comments
                    WHERE post_id IN ({placeholders})
                    ORDER BY comment_id ASC"""
            ),
            tuple(ids),
        ).fetchall()

    for row in count_rows:
        data = dict(row)
        post_counts = activity["reaction_counts"].setdefault(int(data["post_id"]), {})
        post_counts[data["reaction"]] = int(data["reaction_count"])
    for row in viewer_rows:
        data = dict(row)
        activity["viewer_reactions"][int(data["post_id"])] = data["reaction"]
    for row in comment_rows:
        data = dict(row)
        activity["comments"].setdefault(int(data["post_id"]), []).append(data)
    return activity


def unread_community_notification_count(user_id: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            _query(
                """SELECT COUNT(*) AS notification_count
                   FROM community_notifications
                   WHERE recipient_user_id=? AND COALESCE(read_at, '')=''"""
            ),
            (user_id,),
        ).fetchone()
    data = _dict(row) or {}
    return int(data.get("notification_count") or 0)


def list_community_notifications(user_id: str, limit: int = 30) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    with _connect() as conn:
        rows = conn.execute(
            _query(
                """
                SELECT n.*, p.post_text
                FROM community_notifications n
                LEFT JOIN community_posts p ON p.post_id=n.post_id
                WHERE n.recipient_user_id=?
                ORDER BY n.notification_id DESC
                LIMIT ?
                """
            ),
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_community_notifications_read(user_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            _query(
                """UPDATE community_notifications
                   SET read_at=?
                   WHERE recipient_user_id=? AND COALESCE(read_at, '')=''"""
            ),
            (_now(), user_id),
        )
