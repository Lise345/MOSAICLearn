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

# The Streamlit backend is the only supported database client. These tables live
# in Supabase's public schema for PostgreSQL compatibility, but they must not be
# directly readable or writable through PostgREST's anon/authenticated roles.
# RLS is enabled without FORCE ROW LEVEL SECURITY so the table owner used by the
# server-side DATABASE_URL can continue to run the existing backend queries.
SERVER_ONLY_PUBLIC_TABLES = (
    "users",
    "privacy_consents",
    "topic_progress",
    "quiz_results",
    "shares",
    "community_posts",
    "community_reactions",
    "community_comments",
    "community_notifications",
    "mycelium_memberships",
    "mycelium_connections",
    "carousel_content",
    "carousel_revisions",
    "cms_modules",
    "cms_lessons",
    "cms_tools",
    "cms_resource_files",
    "learning_content_revisions",
)
POSTGREST_CLIENT_ROLES = ("anon", "authenticated")


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


def _existing_postgres_roles(cur, role_names: tuple[str, ...]) -> set[str]:
    """Return the requested PostgreSQL roles that exist on this server."""
    cur.execute(
        "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
        (list(role_names),),
    )
    return {str(row["rolname"]) for row in cur.fetchall()}


def _harden_postgres_public_tables(cur) -> None:
    """Keep app-managed public tables server-only when PostgREST is enabled.

    Supabase exposes the public schema through PostgREST. MOSAIC Learn does not
    use browser-side Supabase table access; all reads and writes go through the
    server-side PostgreSQL DATABASE_URL. Enabling RLS with no client policies is
    therefore intentional: PostgREST clients get no rows, while the table owner
    used by the backend keeps its normal PostgreSQL access.
    """
    existing_roles = _existing_postgres_roles(cur, POSTGREST_CLIENT_ROLES)

    for table in SERVER_ONLY_PUBLIC_TABLES:
        # Table names are fixed application constants, not user input.
        qualified = f'public."{table}"'
        cur.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        cur.execute(f"REVOKE ALL PRIVILEGES ON TABLE {qualified} FROM PUBLIC")
        for role in existing_roles:
            cur.execute(
                f'REVOKE ALL PRIVILEGES ON TABLE {qualified} FROM "{role}"'
            )

    # Prevent newly created app tables/sequences from inheriting broad API-role
    # privileges from this database owner. This only changes defaults for future
    # objects created by the current role.
    cur.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE ALL ON TABLES FROM PUBLIC"
    )
    cur.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE ALL ON SEQUENCES FROM PUBLIC"
    )
    for role in existing_roles:
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'REVOKE ALL ON TABLES FROM "{role}"'
        )
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'REVOKE ALL ON SEQUENCES FROM "{role}"'
        )


def postgres_security_status() -> dict:
    """Return whether server-only public tables are protected from PostgREST.

    This is intentionally a startup check rather than an authentication policy:
    user identity in MOSAIC Learn comes from Streamlit/OIDC and does not map to
    Supabase auth.uid().
    """
    if database_backend() != "postgres":
        return {"backend": "sqlite", "ok": True, "tables": {}}

    report: dict[str, dict] = {}
    with _connect() as conn:
        with conn.cursor() as cur:
            existing_roles = _existing_postgres_roles(cur, POSTGREST_CLIENT_ROLES)
            for table in SERVER_ONLY_PUBLIC_TABLES:
                cur.execute(
                    """
                    SELECT c.relrowsecurity AS rls_enabled
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname='public' AND c.relname=%s AND c.relkind='r'
                    """,
                    (table,),
                )
                row = cur.fetchone()
                rls_enabled = bool(row and row["rls_enabled"])
                role_access: dict[str, bool] = {}
                for role in sorted(existing_roles):
                    qualified = f"public.{table}"
                    cur.execute(
                        """
                        SELECT
                            has_table_privilege(%s, %s, 'SELECT') OR
                            has_table_privilege(%s, %s, 'INSERT') OR
                            has_table_privilege(%s, %s, 'UPDATE') OR
                            has_table_privilege(%s, %s, 'DELETE') AS has_dml
                        """,
                        (
                            role, qualified, role, qualified,
                            role, qualified, role, qualified,
                        ),
                    )
                    access_row = cur.fetchone()
                    role_access[role] = bool(access_row and access_row["has_dml"])
                report[table] = {
                    "rls_enabled": rls_enabled,
                    "postgrest_role_access": role_access,
                }

    ok = all(
        item["rls_enabled"]
        and not any(item["postgrest_role_access"].values())
        for item in report.values()
    )
    return {"backend": "postgres", "ok": ok, "tables": report}


def assert_postgres_security_hardened() -> None:
    """Fail closed if a production PostgreSQL table remains API-exposed."""
    status = postgres_security_status()
    if status["backend"] != "postgres" or status["ok"]:
        return
    insecure = [
        table
        for table, item in status["tables"].items()
        if (
            not item["rls_enabled"]
            or any(item["postgrest_role_access"].values())
        )
    ]
    raise RuntimeError(
        "PostgreSQL security hardening is incomplete for: "
        + ", ".join(insecure)
    )


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
                    CREATE TABLE IF NOT EXISTS mycelium_memberships (
                        user_id TEXT PRIMARY KEY,
                        joined_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mycelium_connections (
                        connection_id BIGSERIAL PRIMARY KEY,
                        pair_key TEXT NOT NULL UNIQUE,
                        requester_user_id TEXT NOT NULL,
                        recipient_user_id TEXT NOT NULL,
                        requester_name TEXT NOT NULL,
                        requester_email TEXT DEFAULT '',
                        share_requester_email INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        responded_at TEXT DEFAULT ''
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mycelium_connections_recipient ON mycelium_connections(recipient_user_id, status, connection_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mycelium_connections_requester ON mycelium_connections(requester_user_id, status, connection_id)"
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
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cms_modules (
                        module_id TEXT PRIMARY KEY,
                        draft_json TEXT NOT NULL DEFAULT '',
                        published_json TEXT NOT NULL DEFAULT '',
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        archived INTEGER NOT NULL DEFAULT 0,
                        updated_by TEXT DEFAULT '',
                        updated_at TEXT DEFAULT '',
                        published_at TEXT DEFAULT ''
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cms_lessons (
                        module_id TEXT NOT NULL,
                        lesson_id TEXT NOT NULL,
                        draft_json TEXT NOT NULL DEFAULT '',
                        published_json TEXT NOT NULL DEFAULT '',
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        archived INTEGER NOT NULL DEFAULT 0,
                        updated_by TEXT DEFAULT '',
                        updated_at TEXT DEFAULT '',
                        published_at TEXT DEFAULT '',
                        PRIMARY KEY (module_id, lesson_id)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cms_lessons_module ON cms_lessons(module_id, sort_order, lesson_id)"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS learning_content_revisions (
                        revision_id BIGSERIAL PRIMARY KEY,
                        content_type TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        lesson_id TEXT DEFAULT '',
                        content_json TEXT NOT NULL,
                        published_by TEXT DEFAULT '',
                        published_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cms_tools (
                        tool_id TEXT PRIMARY KEY,
                        draft_json TEXT NOT NULL DEFAULT '',
                        published_json TEXT NOT NULL DEFAULT '',
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        archived INTEGER NOT NULL DEFAULT 0,
                        updated_by TEXT DEFAULT '',
                        updated_at TEXT DEFAULT '',
                        published_at TEXT DEFAULT ''
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cms_resource_files (
                        resource_id TEXT PRIMARY KEY,
                        scope_type TEXT NOT NULL,
                        scope_id TEXT NOT NULL,
                        module_id TEXT DEFAULT '',
                        resource_kind TEXT DEFAULT 'File',
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        file_name TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        file_data BYTEA NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        archived INTEGER NOT NULL DEFAULT 0,
                        updated_by TEXT DEFAULT '',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cms_resource_scope ON cms_resource_files(scope_type, scope_id, archived, sort_order, resource_id)"
                )
                _harden_postgres_public_tables(cur)
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

            CREATE TABLE IF NOT EXISTS mycelium_memberships (
                user_id TEXT PRIMARY KEY,
                joined_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mycelium_connections (
                connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_key TEXT NOT NULL UNIQUE,
                requester_user_id TEXT NOT NULL,
                recipient_user_id TEXT NOT NULL,
                requester_name TEXT NOT NULL,
                requester_email TEXT DEFAULT '',
                share_requester_email INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                responded_at TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_mycelium_connections_recipient
                ON mycelium_connections(recipient_user_id, status, connection_id);
            CREATE INDEX IF NOT EXISTS idx_mycelium_connections_requester
                ON mycelium_connections(requester_user_id, status, connection_id);

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

            CREATE TABLE IF NOT EXISTS cms_modules (
                module_id TEXT PRIMARY KEY,
                draft_json TEXT NOT NULL DEFAULT '',
                published_json TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                published_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cms_lessons (
                module_id TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                draft_json TEXT NOT NULL DEFAULT '',
                published_json TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                PRIMARY KEY (module_id, lesson_id)
            );

            CREATE INDEX IF NOT EXISTS idx_cms_lessons_module
                ON cms_lessons(module_id, sort_order, lesson_id);

            CREATE TABLE IF NOT EXISTS learning_content_revisions (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                module_id TEXT NOT NULL,
                lesson_id TEXT DEFAULT '',
                content_json TEXT NOT NULL,
                published_by TEXT DEFAULT '',
                published_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cms_tools (
                tool_id TEXT PRIMARY KEY,
                draft_json TEXT NOT NULL DEFAULT '',
                published_json TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                published_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cms_resource_files (
                resource_id TEXT PRIMARY KEY,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                module_id TEXT DEFAULT '',
                resource_kind TEXT DEFAULT 'File',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                file_data BLOB NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cms_resource_scope
                ON cms_resource_files(scope_type, scope_id, archived, sort_order, resource_id);
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
        # Mycelium is optional account-linked data. Remove it before deleting the user.
        conn.execute(
            _query(
                "DELETE FROM mycelium_connections WHERE requester_user_id=? OR recipient_user_id=?"
            ),
            (user_id, user_id),
        )
        conn.execute(
            _query("DELETE FROM mycelium_memberships WHERE user_id=?"),
            (user_id,),
        )

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
        conn.execute(
            _query("UPDATE cms_modules SET updated_by='' WHERE updated_by=?"),
            (user_id,),
        )
        conn.execute(
            _query("UPDATE cms_lessons SET updated_by='' WHERE updated_by=?"),
            (user_id,),
        )
        conn.execute(
            _query("UPDATE cms_tools SET updated_by='' WHERE updated_by=?"),
            (user_id,),
        )
        conn.execute(
            _query("UPDATE cms_resource_files SET updated_by='' WHERE updated_by=?"),
            (user_id,),
        )
        conn.execute(
            _query("UPDATE learning_content_revisions SET published_by='' WHERE published_by=?"),
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
    if account_role not in {"learner", "editor", "administrator"}:
        raise ValueError("account_role must be 'learner', 'editor' or 'administrator'")
    with _connect() as conn:
        conn.execute(
            _query("UPDATE users SET account_role=?, updated_at=? WHERE user_id=?"),
            (account_role, _now(), user_id),
        )



def _decode_content_record(row: Any) -> dict | None:
    data = _dict(row)
    if not data:
        return None
    for source, target in (("draft_json", "draft"), ("published_json", "published")):
        try:
            data[target] = json.loads(data.get(source) or "") if data.get(source) else None
        except (TypeError, json.JSONDecodeError):
            data[target] = None
    data["archived"] = bool(data.get("archived"))
    data["sort_order"] = int(data.get("sort_order") or 0)
    return data


def list_cms_modules() -> list[dict]:
    """Return module CMS rows, including drafts and archived records."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT module_id, draft_json, published_json, sort_order, archived,
                   updated_by, updated_at, published_at
            FROM cms_modules
            ORDER BY sort_order, module_id
            """
        ).fetchall()
    return [record for row in rows if (record := _decode_content_record(row))]


def get_cms_module(module_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            _query("SELECT * FROM cms_modules WHERE module_id=?"),
            (module_id,),
        ).fetchone()
    return _decode_content_record(row)


def save_cms_module_draft(
    module_id: str,
    content: dict,
    sort_order: int,
    updated_by: str,
) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_modules(
                    module_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, ?, '', ?, 0, ?, ?, '')
                ON CONFLICT(module_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    sort_order=excluded.sort_order,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (module_id, payload, int(sort_order), updated_by, now),
        )


def publish_cms_module(
    module_id: str,
    content: dict,
    sort_order: int,
    published_by: str,
) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        existing = _dict(
            conn.execute(
                _query("SELECT published_json FROM cms_modules WHERE module_id=?"),
                (module_id,),
            ).fetchone()
        )
        if existing and existing.get("published_json"):
            conn.execute(
                _query(
                    """
                    INSERT INTO learning_content_revisions(
                        content_type, module_id, lesson_id, content_json,
                        published_by, published_at
                    ) VALUES ('module', ?, '', ?, ?, ?)
                    """
                ),
                (module_id, existing["published_json"], published_by, now),
            )
        conn.execute(
            _query(
                """
                INSERT INTO cms_modules(
                    module_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    published_json=excluded.published_json,
                    sort_order=excluded.sort_order,
                    archived=0,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at,
                    published_at=excluded.published_at
                """
            ),
            (module_id, payload, payload, int(sort_order), published_by, now, now),
        )


def set_cms_module_archived(
    module_id: str,
    archived: bool,
    updated_by: str,
    *,
    sort_order: int = 0,
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_modules(
                    module_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, '', '', ?, ?, ?, ?, '')
                ON CONFLICT(module_id) DO UPDATE SET
                    archived=excluded.archived,
                    sort_order=CASE
                        WHEN cms_modules.sort_order=0 THEN excluded.sort_order
                        ELSE cms_modules.sort_order
                    END,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (module_id, int(sort_order), int(bool(archived)), updated_by, now),
        )


def list_cms_lessons(module_id: str | None = None) -> list[dict]:
    """Return lesson CMS rows, including drafts and archived records."""
    with _connect() as conn:
        if module_id is None:
            rows = conn.execute(
                """
                SELECT module_id, lesson_id, draft_json, published_json, sort_order,
                       archived, updated_by, updated_at, published_at
                FROM cms_lessons
                ORDER BY module_id, sort_order, lesson_id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                _query(
                    """
                    SELECT module_id, lesson_id, draft_json, published_json, sort_order,
                           archived, updated_by, updated_at, published_at
                    FROM cms_lessons
                    WHERE module_id=?
                    ORDER BY sort_order, lesson_id
                    """
                ),
                (module_id,),
            ).fetchall()
    return [record for row in rows if (record := _decode_content_record(row))]


def get_cms_lesson(module_id: str, lesson_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            _query("SELECT * FROM cms_lessons WHERE module_id=? AND lesson_id=?"),
            (module_id, lesson_id),
        ).fetchone()
    return _decode_content_record(row)


def save_cms_lesson_draft(
    module_id: str,
    lesson_id: str,
    content: dict,
    sort_order: int,
    updated_by: str,
) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_lessons(
                    module_id, lesson_id, draft_json, published_json, sort_order,
                    archived, updated_by, updated_at, published_at
                ) VALUES (?, ?, ?, '', ?, 0, ?, ?, '')
                ON CONFLICT(module_id, lesson_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    sort_order=excluded.sort_order,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (module_id, lesson_id, payload, int(sort_order), updated_by, now),
        )


def publish_cms_lesson(
    module_id: str,
    lesson_id: str,
    content: dict,
    sort_order: int,
    published_by: str,
) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        existing = _dict(
            conn.execute(
                _query(
                    "SELECT published_json FROM cms_lessons WHERE module_id=? AND lesson_id=?"
                ),
                (module_id, lesson_id),
            ).fetchone()
        )
        if existing and existing.get("published_json"):
            conn.execute(
                _query(
                    """
                    INSERT INTO learning_content_revisions(
                        content_type, module_id, lesson_id, content_json,
                        published_by, published_at
                    ) VALUES ('lesson', ?, ?, ?, ?, ?)
                    """
                ),
                (module_id, lesson_id, existing["published_json"], published_by, now),
            )
        conn.execute(
            _query(
                """
                INSERT INTO cms_lessons(
                    module_id, lesson_id, draft_json, published_json, sort_order,
                    archived, updated_by, updated_at, published_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(module_id, lesson_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    published_json=excluded.published_json,
                    sort_order=excluded.sort_order,
                    archived=0,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at,
                    published_at=excluded.published_at
                """
            ),
            (module_id, lesson_id, payload, payload, int(sort_order), published_by, now, now),
        )


def set_cms_lesson_archived(
    module_id: str,
    lesson_id: str,
    archived: bool,
    updated_by: str,
    *,
    sort_order: int = 0,
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_lessons(
                    module_id, lesson_id, draft_json, published_json, sort_order,
                    archived, updated_by, updated_at, published_at
                ) VALUES (?, ?, '', '', ?, ?, ?, ?, '')
                ON CONFLICT(module_id, lesson_id) DO UPDATE SET
                    archived=excluded.archived,
                    sort_order=CASE
                        WHEN cms_lessons.sort_order=0 THEN excluded.sort_order
                        ELSE cms_lessons.sort_order
                    END,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (module_id, lesson_id, int(sort_order), int(bool(archived)), updated_by, now),
        )


def list_cms_tools() -> list[dict]:
    """Return tool CMS rows, including drafts and archived records."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT tool_id, draft_json, published_json, sort_order, archived,
                   updated_by, updated_at, published_at
            FROM cms_tools
            ORDER BY sort_order, tool_id
            """
        ).fetchall()
    return [record for row in rows if (record := _decode_content_record(row))]


def get_cms_tool(tool_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            _query("SELECT * FROM cms_tools WHERE tool_id=?"),
            (tool_id,),
        ).fetchone()
    return _decode_content_record(row)


def save_cms_tool_draft(tool_id: str, content: dict, sort_order: int, updated_by: str) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_tools(
                    tool_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, ?, '', ?, 0, ?, ?, '')
                ON CONFLICT(tool_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    sort_order=excluded.sort_order,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (tool_id, payload, int(sort_order), updated_by, now),
        )


def publish_cms_tool(tool_id: str, content: dict, sort_order: int, published_by: str) -> None:
    now = _now()
    payload = json.dumps(content, ensure_ascii=False)
    with _connect() as conn:
        existing = _dict(
            conn.execute(
                _query("SELECT published_json FROM cms_tools WHERE tool_id=?"),
                (tool_id,),
            ).fetchone()
        )
        if existing and existing.get("published_json"):
            conn.execute(
                _query(
                    """
                    INSERT INTO learning_content_revisions(
                        content_type, module_id, lesson_id, content_json,
                        published_by, published_at
                    ) VALUES ('tool', '', ?, ?, ?, ?)
                    """
                ),
                (tool_id, existing["published_json"], published_by, now),
            )
        conn.execute(
            _query(
                """
                INSERT INTO cms_tools(
                    tool_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(tool_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    published_json=excluded.published_json,
                    sort_order=excluded.sort_order,
                    archived=0,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at,
                    published_at=excluded.published_at
                """
            ),
            (tool_id, payload, payload, int(sort_order), published_by, now, now),
        )


def set_cms_tool_archived(tool_id: str, archived: bool, updated_by: str, *, sort_order: int = 0) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO cms_tools(
                    tool_id, draft_json, published_json, sort_order, archived,
                    updated_by, updated_at, published_at
                ) VALUES (?, '', '', ?, ?, ?, ?, '')
                ON CONFLICT(tool_id) DO UPDATE SET
                    archived=excluded.archived,
                    sort_order=CASE
                        WHEN cms_tools.sort_order=0 THEN excluded.sort_order
                        ELSE cms_tools.sort_order
                    END,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (tool_id, int(sort_order), int(bool(archived)), updated_by, now),
        )


def _validate_resource_scope(scope_type: str) -> str:
    scope = str(scope_type or "").strip().lower()
    if scope not in {"convince", "tool"}:
        raise ValueError("scope_type must be 'convince' or 'tool'")
    return scope


def list_cms_resource_files(
    scope_type: str | None = None,
    scope_id: str | None = None,
    *,
    include_archived: bool = False,
) -> list[dict]:
    """Return resource metadata without loading file bytes."""
    clauses = []
    params: list[Any] = []
    if scope_type is not None:
        clauses.append("scope_type=?")
        params.append(_validate_resource_scope(scope_type))
    if scope_id is not None:
        clauses.append("scope_id=?")
        params.append(str(scope_id))
    if not include_archived:
        clauses.append("archived=0")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            _query(
                """
                SELECT resource_id, scope_type, scope_id, module_id, resource_kind,
                       title, description, file_name, mime_type,
                       LENGTH(file_data) AS size_bytes, sort_order, archived,
                       updated_by, updated_at
                FROM cms_resource_files
                """ + where + " ORDER BY scope_type, scope_id, sort_order, resource_id"
            ),
            tuple(params),
        ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        data["archived"] = bool(data.get("archived"))
        data["sort_order"] = int(data.get("sort_order") or 0)
        data["size_bytes"] = int(data.get("size_bytes") or 0)
        result.append(data)
    return result


def get_cms_resource_file(resource_id: str) -> dict | None:
    """Return one resource including its binary payload for download."""
    with _connect() as conn:
        row = conn.execute(
            _query("SELECT * FROM cms_resource_files WHERE resource_id=?"),
            (resource_id,),
        ).fetchone()
    data = _dict(row)
    if not data:
        return None
    data["archived"] = bool(data.get("archived"))
    data["sort_order"] = int(data.get("sort_order") or 0)
    payload = data.get("file_data")
    if payload is not None and not isinstance(payload, bytes):
        try:
            data["file_data"] = bytes(payload)
        except Exception:
            pass
    return data


def save_cms_resource_file(
    resource_id: str,
    *,
    scope_type: str,
    scope_id: str,
    module_id: str = "",
    resource_kind: str = "File",
    title: str,
    description: str = "",
    file_name: str | None = None,
    mime_type: str | None = None,
    file_data: bytes | None = None,
    sort_order: int = 0,
    updated_by: str = "",
) -> None:
    """Create a resource or update its metadata; file_data replaces bytes when supplied."""
    scope = _validate_resource_scope(scope_type)
    now = _now()
    resource_id = str(resource_id or "").strip()
    if not resource_id:
        raise ValueError("resource_id is required")
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    with _connect() as conn:
        existing = _dict(
            conn.execute(
                _query("SELECT file_name, mime_type, file_data FROM cms_resource_files WHERE resource_id=?"),
                (resource_id,),
            ).fetchone()
        )
        if file_data is None:
            if not existing:
                raise ValueError("A file is required for a new resource")
            file_name = str(file_name or existing.get("file_name") or "")
            mime_type = str(mime_type or existing.get("mime_type") or "application/octet-stream")
            file_data = existing.get("file_data")
        else:
            file_name = str(file_name or "").strip()
            mime_type = str(mime_type or "application/octet-stream").strip()
            if not file_name:
                raise ValueError("file_name is required when replacing file data")
        conn.execute(
            _query(
                """
                INSERT INTO cms_resource_files(
                    resource_id, scope_type, scope_id, module_id, resource_kind,
                    title, description, file_name, mime_type, file_data,
                    sort_order, archived, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    scope_type=excluded.scope_type,
                    scope_id=excluded.scope_id,
                    module_id=excluded.module_id,
                    resource_kind=excluded.resource_kind,
                    title=excluded.title,
                    description=excluded.description,
                    file_name=excluded.file_name,
                    mime_type=excluded.mime_type,
                    file_data=excluded.file_data,
                    sort_order=excluded.sort_order,
                    archived=0,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """
            ),
            (
                resource_id, scope, str(scope_id or ""), str(module_id or ""),
                str(resource_kind or "File").strip() or "File", clean_title,
                str(description or "").strip(), file_name, mime_type, file_data,
                int(sort_order), str(updated_by or ""), now,
            ),
        )


def set_cms_resource_archived(resource_id: str, archived: bool, updated_by: str) -> None:
    with _connect() as conn:
        conn.execute(
            _query(
                "UPDATE cms_resource_files SET archived=?, updated_by=?, updated_at=? WHERE resource_id=?"
            ),
            (int(bool(archived)), str(updated_by or ""), _now(), resource_id),
        )


def list_content_revisions(limit: int = 100) -> list[dict]:
    """Return recent module/lesson/idea/tool publication history for the admin studio."""
    limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        learning_rows = conn.execute(
            _query(
                """
                SELECT revision_id, content_type, module_id, lesson_id,
                       published_by, published_at
                FROM learning_content_revisions
                ORDER BY revision_id DESC
                LIMIT ?
                """
            ),
            (limit,),
        ).fetchall()
        carousel_rows = conn.execute(
            _query(
                """
                SELECT revision_id, module_id, topic_id AS lesson_id,
                       published_by, published_at
                FROM carousel_revisions
                ORDER BY revision_id DESC
                LIMIT ?
                """
            ),
            (limit,),
        ).fetchall()
    result = []
    for row in learning_rows:
        result.append(dict(row))
    for row in carousel_rows:
        data = dict(row)
        data["content_type"] = "ideas"
        result.append(data)
    result.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    return result[:limit]


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


def _mycelium_pair_key(user_a: str, user_b: str) -> str:
    a = str(user_a or "").strip()
    b = str(user_b or "").strip()
    if not a or not b:
        raise ValueError("Both Mycelium user IDs are required")
    if a == b:
        raise ValueError("You cannot connect to yourself")
    return "|".join(sorted((a, b)))


def join_mycelium(user_id: str) -> None:
    """Opt one learner into the visible Mycelium directory."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            _query(
                """
                INSERT INTO mycelium_memberships(user_id, joined_at)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """
            ),
            (user_id, now),
        )


def leave_mycelium(user_id: str) -> None:
    """Opt out and remove Mycelium-specific links and invitations for this learner."""
    with _connect() as conn:
        conn.execute(
            _query(
                """
                DELETE FROM community_notifications
                WHERE event_type IN ('mycelium_request', 'mycelium_accepted')
                  AND (recipient_user_id=? OR actor_user_id=?)
                """
            ),
            (user_id, user_id),
        )
        conn.execute(
            _query(
                "DELETE FROM mycelium_connections WHERE requester_user_id=? OR recipient_user_id=?"
            ),
            (user_id, user_id),
        )
        conn.execute(
            _query("DELETE FROM mycelium_memberships WHERE user_id=?"),
            (user_id,),
        )


def request_mycelium_connection(
    requester_user_id: str,
    requester_name: str,
    requester_email: str,
    recipient_user_id: str,
    *,
    share_email: bool = False,
) -> int:
    """Create one private pending invitation and notify only the recipient."""
    pair_key = _mycelium_pair_key(requester_user_id, recipient_user_id)
    now = _now()
    shared_email = str(requester_email or "").strip() if share_email else ""

    with _connect() as conn:
        membership_rows = conn.execute(
            _query(
                """
                SELECT user_id
                FROM mycelium_memberships
                WHERE user_id IN (?, ?)
                """
            ),
            (requester_user_id, recipient_user_id),
        ).fetchall()
        members = {str(row["user_id"]) for row in membership_rows}
        if requester_user_id not in members:
            raise ValueError("Join Our mycelium before sending connection requests.")
        if recipient_user_id not in members:
            raise ValueError("That learner is no longer part of Our mycelium.")

        existing = _dict(
            conn.execute(
                _query(
                    """
                    SELECT connection_id, requester_user_id, recipient_user_id, status
                    FROM mycelium_connections
                    WHERE pair_key=?
                    """
                ),
                (pair_key,),
            ).fetchone()
        )
        if existing:
            if existing.get("status") == "accepted":
                raise ValueError("You are already connected with this learner.")
            if (
                existing.get("status") == "pending"
                and existing.get("recipient_user_id") == requester_user_id
            ):
                raise ValueError(
                    "This learner already invited you. Open Our mycelium to accept or decline their request."
                )
            raise ValueError("A connection request is already pending with this learner.")

        conn.execute(
            _query(
                """
                INSERT INTO mycelium_connections(
                    pair_key,
                    requester_user_id,
                    recipient_user_id,
                    requester_name,
                    requester_email,
                    share_requester_email,
                    status,
                    created_at,
                    responded_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, '')
                """
            ),
            (
                pair_key,
                requester_user_id,
                recipient_user_id,
                str(requester_name or "Learner").strip() or "Learner",
                shared_email,
                int(bool(share_email)),
                now,
            ),
        )
        connection = _dict(
            conn.execute(
                _query(
                    "SELECT connection_id FROM mycelium_connections WHERE pair_key=?"
                ),
                (pair_key,),
            ).fetchone()
        )
        if not connection:
            raise RuntimeError("Could not create Mycelium connection request")
        connection_id = int(connection["connection_id"])

        conn.execute(
            _query(
                """
                INSERT INTO community_notifications(
                    recipient_user_id,
                    actor_user_id,
                    actor_name,
                    event_type,
                    event_detail,
                    post_id,
                    created_at,
                    read_at
                ) VALUES (?, ?, ?, 'mycelium_request', ?, NULL, ?, '')
                """
            ),
            (
                recipient_user_id,
                requester_user_id,
                str(requester_name or "Learner").strip() or "Learner",
                str(connection_id),
                now,
            ),
        )
    return connection_id


def respond_mycelium_connection(
    connection_id: int,
    recipient_user_id: str,
    recipient_name: str,
    *,
    accept: bool,
) -> bool:
    """Accept or decline a pending invitation; only its intended recipient may do so."""
    now = _now()
    with _connect() as conn:
        request = _dict(
            conn.execute(
                _query(
                    """
                    SELECT connection_id, requester_user_id, recipient_user_id, status
                    FROM mycelium_connections
                    WHERE connection_id=?
                    """
                ),
                (int(connection_id),),
            ).fetchone()
        )
        if not request or request.get("status") != "pending":
            raise ValueError("This connection request is no longer pending.")
        if request.get("recipient_user_id") != recipient_user_id:
            raise PermissionError("Only the intended recipient can respond to this request.")

        if accept:
            conn.execute(
                _query(
                    """
                    UPDATE mycelium_connections
                    SET status='accepted', responded_at=?
                    WHERE connection_id=? AND recipient_user_id=? AND status='pending'
                    """
                ),
                (now, int(connection_id), recipient_user_id),
            )
            conn.execute(
                _query(
                    """
                    INSERT INTO community_notifications(
                        recipient_user_id,
                        actor_user_id,
                        actor_name,
                        event_type,
                        event_detail,
                        post_id,
                        created_at,
                        read_at
                    ) VALUES (?, ?, ?, 'mycelium_accepted', ?, NULL, ?, '')
                    """
                ),
                (
                    request["requester_user_id"],
                    recipient_user_id,
                    str(recipient_name or "Learner").strip() or "Learner",
                    str(int(connection_id)),
                    now,
                ),
            )
        else:
            # Delete declined requests so either learner can send a fresh request later.
            conn.execute(
                _query(
                    "DELETE FROM mycelium_connections WHERE connection_id=? AND recipient_user_id=? AND status='pending'"
                ),
                (int(connection_id), recipient_user_id),
            )

        # Responding is itself an acknowledgement of the original invitation.
        conn.execute(
            _query(
                """
                UPDATE community_notifications
                SET read_at=?
                WHERE recipient_user_id=?
                  AND event_type='mycelium_request'
                  AND event_detail=?
                  AND COALESCE(read_at, '')=''
                """
            ),
            (now, recipient_user_id, str(int(connection_id))),
        )
    return bool(accept)


def get_mycelium_state(user_id: str) -> dict:
    """Return public network topology plus only this user's private pending requests."""
    with _connect() as conn:
        membership = conn.execute(
            _query("SELECT 1 FROM mycelium_memberships WHERE user_id=?"),
            (user_id,),
        ).fetchone()
        if not membership:
            return {
                "is_member": False,
                "members": [],
                "connections": [],
                "incoming": [],
                "outgoing": [],
                "connected": [],
                "blocked_user_ids": [],
            }

        member_rows = conn.execute(
            """
            SELECT u.user_id, u.name, u.organisation, u.country
            FROM mycelium_memberships m
            JOIN users u ON u.user_id=m.user_id
            ORDER BY LOWER(COALESCE(u.name, '')), u.user_id
            """
        ).fetchall()
        members = [dict(row) for row in member_rows]
        member_ids = {str(row["user_id"]) for row in members}

        accepted_rows = conn.execute(
            """
            SELECT connection_id, requester_user_id, recipient_user_id,
                   requester_email, share_requester_email, created_at, responded_at
            FROM mycelium_connections
            WHERE status='accepted'
            ORDER BY connection_id
            """
        ).fetchall()
        accepted = [dict(row) for row in accepted_rows]
        connections = [
            {
                "connection_id": int(row["connection_id"]),
                "source": row["requester_user_id"],
                "target": row["recipient_user_id"],
            }
            for row in accepted
            if row["requester_user_id"] in member_ids
            and row["recipient_user_id"] in member_ids
        ]

        incoming_rows = conn.execute(
            _query(
                """
                SELECT c.connection_id, c.requester_user_id, c.requester_name,
                       c.requester_email, c.share_requester_email, c.created_at,
                       u.organisation, u.country
                FROM mycelium_connections c
                LEFT JOIN users u ON u.user_id=c.requester_user_id
                WHERE c.recipient_user_id=? AND c.status='pending'
                ORDER BY c.connection_id DESC
                """
            ),
            (user_id,),
        ).fetchall()
        incoming = [dict(row) for row in incoming_rows]
        for row in incoming:
            if not int(row.get("share_requester_email") or 0):
                row["requester_email"] = ""

        outgoing_rows = conn.execute(
            _query(
                """
                SELECT c.connection_id, c.recipient_user_id, c.created_at,
                       u.name AS recipient_name, u.organisation, u.country
                FROM mycelium_connections c
                LEFT JOIN users u ON u.user_id=c.recipient_user_id
                WHERE c.requester_user_id=? AND c.status='pending'
                ORDER BY c.connection_id DESC
                """
            ),
            (user_id,),
        ).fetchall()
        outgoing = [dict(row) for row in outgoing_rows]

        connected = []
        for row in accepted:
            if row["requester_user_id"] == user_id:
                peer_id = row["recipient_user_id"]
                shared_email = ""
            elif row["recipient_user_id"] == user_id:
                peer_id = row["requester_user_id"]
                shared_email = (
                    str(row.get("requester_email") or "").strip()
                    if int(row.get("share_requester_email") or 0)
                    else ""
                )
            else:
                continue
            peer = next((member for member in members if member["user_id"] == peer_id), None)
            if peer:
                connected.append(
                    {
                        "connection_id": int(row["connection_id"]),
                        "user_id": peer_id,
                        "name": peer.get("name") or "Learner",
                        "organisation": peer.get("organisation") or "",
                        "country": peer.get("country") or "",
                        "shared_email": shared_email,
                    }
                )

    blocked = {user_id}
    for row in incoming:
        blocked.add(str(row["requester_user_id"]))
    for row in outgoing:
        blocked.add(str(row["recipient_user_id"]))
    for row in connected:
        blocked.add(str(row["user_id"]))

    return {
        "is_member": True,
        "members": members,
        "connections": connections,
        "incoming": incoming,
        "outgoing": outgoing,
        "connected": connected,
        "blocked_user_ids": sorted(blocked),
    }
