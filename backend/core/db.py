import sqlite3

from backend.core.config import (
    DB_PATH,
    DEFAULT_LINUX_GID_BASE,
    DEFAULT_LINUX_UID_BASE,
    SQLITE_BUSY_TIMEOUT_MS,
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def allocate_next_linux_identity(connection: sqlite3.Connection) -> tuple[int, int]:
    uid_row = connection.execute(
        "SELECT COALESCE(MAX(linux_uid), ?) AS max_uid FROM users",
        (DEFAULT_LINUX_UID_BASE - 1,),
    ).fetchone()
    gid_row = connection.execute(
        "SELECT COALESCE(MAX(linux_gid), ?) AS max_gid FROM users",
        (DEFAULT_LINUX_GID_BASE - 1,),
    ).fetchone()
    next_uid = max(DEFAULT_LINUX_UID_BASE, int(uid_row["max_uid"] or DEFAULT_LINUX_UID_BASE - 1) + 1)
    next_gid = max(DEFAULT_LINUX_GID_BASE, int(gid_row["max_gid"] or DEFAULT_LINUX_GID_BASE - 1) + 1)
    return next_uid, next_gid


def init_db() -> None:
    from backend.features.runtime import create_runtime_schema_tables, upsert_container_runtime_system
    from backend.core.security import hash_password

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                real_name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                linux_uid INTEGER NOT NULL UNIQUE,
                linux_gid INTEGER NOT NULL UNIQUE,
                max_ssh_keys_per_user INTEGER NOT NULL DEFAULT 5,
                max_join_keys_per_request INTEGER NOT NULL DEFAULT 3,
                max_containers_per_user INTEGER NOT NULL DEFAULT 3
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                host TEXT NOT NULL,
                ssh_port INTEGER NOT NULL DEFAULT 22,
                root_password TEXT NOT NULL DEFAULT '',
                max_users INTEGER NOT NULL DEFAULT 3,
                gpu_model TEXT NOT NULL DEFAULT '',
                gpu_memory TEXT NOT NULL DEFAULT '',
                gpu_count INTEGER NOT NULL DEFAULT 1,
                cpu_cores INTEGER NOT NULL DEFAULT 1,
                memory_size TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'offline', 'disabled'))
            )
            """
        )
        create_runtime_schema_tables(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ssh_public_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                public_key TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_ssh_key_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ssh_key_id INTEGER NOT NULL,
                UNIQUE(user_id, ssh_key_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ssh_key_container_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ssh_key_id INTEGER NOT NULL,
                container_id INTEGER NOT NULL,
                UNIQUE(ssh_key_id, container_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token_hash TEXT NOT NULL UNIQUE,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS login_rate_limits (
                scope_key TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                first_failed_at INTEGER NOT NULL DEFAULT 0,
                locked_until INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        container_rows = connection.execute(
            """
            SELECT id, gpu_count, gpu_memory
            FROM containers
            ORDER BY id ASC
            """
        ).fetchall()
        for row in container_rows:
            upsert_container_runtime_system(connection, int(row["id"]))

        user_count_row = connection.execute("SELECT COUNT(1) AS count FROM users").fetchone()
        user_count = int(user_count_row["count"]) if user_count_row else 0
        if user_count == 0:
            admin_linux_uid, admin_linux_gid = allocate_next_linux_identity(connection)
            connection.execute(
                """
                INSERT INTO users (
                    username,
                    real_name,
                    password_hash,
                    role,
                    linux_uid,
                    linux_gid,
                    max_ssh_keys_per_user,
                    max_join_keys_per_request,
                    max_containers_per_user
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "admin",
                    "Admin",
                    hash_password("acmis@admin"),
                    "admin",
                    admin_linux_uid,
                    admin_linux_gid,
                    5,
                    3,
                    3,
                ),
            )
        connection.commit()
