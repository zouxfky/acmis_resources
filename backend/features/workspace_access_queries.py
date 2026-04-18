import sqlite3


def fetch_user_quota_row(connection: sqlite3.Connection, user_id: int):
    return connection.execute(
        """
        SELECT max_join_keys_per_request, max_containers_per_user
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def fetch_container_join_policy_row(connection: sqlite3.Connection, container_id: int):
    return connection.execute(
        """
        SELECT id, status, max_users
        FROM containers
        WHERE id = ?
        """,
        (container_id,),
    ).fetchone()


def fetch_owned_key_ids(
    connection: sqlite3.Connection,
    user_id: int,
    ssh_key_ids: list[int],
) -> set[int]:
    rows = connection.execute(
        f"""
        SELECT ssh_key_id
        FROM user_ssh_key_bindings
        WHERE user_id = ? AND ssh_key_id IN ({",".join("?" for _ in ssh_key_ids)})
        """,
        (user_id, *ssh_key_ids),
    ).fetchall()
    return {int(row["ssh_key_id"]) for row in rows}


def fetch_existing_selected_key_ids(
    connection: sqlite3.Connection,
    user_id: int,
    container_id: int,
    ssh_key_ids: list[int],
) -> set[int]:
    rows = connection.execute(
        f"""
        SELECT scb.ssh_key_id
        FROM ssh_key_container_bindings scb
        JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
        WHERE ub.user_id = ? AND scb.container_id = ? AND scb.ssh_key_id IN ({",".join("?" for _ in ssh_key_ids)})
        """,
        (user_id, container_id, *ssh_key_ids),
    ).fetchall()
    return {int(row["ssh_key_id"]) for row in rows}


def fetch_existing_membership(connection: sqlite3.Connection, user_id: int, container_id: int):
    return connection.execute(
        """
        SELECT 1
        FROM ssh_key_container_bindings scb
        JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
        WHERE ub.user_id = ? AND scb.container_id = ?
        LIMIT 1
        """,
        (user_id, container_id),
    ).fetchone()


def fetch_joined_container_count(connection: sqlite3.Connection, user_id: int) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(DISTINCT scb.container_id)
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE ub.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
    )


def fetch_active_user_count(connection: sqlite3.Connection, container_id: int) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(DISTINCT ub.user_id)
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE scb.container_id = ?
            """,
            (container_id,),
        ).fetchone()[0]
    )


def insert_container_key_bindings(
    connection: sqlite3.Connection,
    container_id: int,
    ssh_key_ids: list[int],
) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO ssh_key_container_bindings (ssh_key_id, container_id)
        VALUES (?, ?)
        """,
        [(ssh_key_id, container_id) for ssh_key_id in ssh_key_ids],
    )


def fetch_current_container_key_ids(connection: sqlite3.Connection, user_id: int, container_id: int) -> set[int]:
    rows = connection.execute(
        """
        SELECT scb.ssh_key_id
        FROM ssh_key_container_bindings scb
        JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
        WHERE ub.user_id = ? AND scb.container_id = ?
        """,
        (user_id, container_id),
    ).fetchall()
    return {int(row["ssh_key_id"]) for row in rows}


def delete_container_key_bindings(
    connection: sqlite3.Connection,
    container_id: int,
    ssh_key_ids: list[int],
) -> None:
    connection.executemany(
        """
        DELETE FROM ssh_key_container_bindings
        WHERE ssh_key_id = ? AND container_id = ?
        """,
        [(ssh_key_id, container_id) for ssh_key_id in ssh_key_ids],
    )


def fetch_user_ssh_key_binding(connection: sqlite3.Connection, user_id: int, ssh_key_id: int):
    return connection.execute(
        """
        SELECT ssh_key_id
        FROM user_ssh_key_bindings
        WHERE user_id = ? AND ssh_key_id = ?
        """,
        (user_id, ssh_key_id),
    ).fetchone()


def fetch_affected_container_rows_for_key(connection: sqlite3.Connection, user_id: int, ssh_key_id: int):
    return connection.execute(
        """
        SELECT DISTINCT scb.container_id, c.status
        FROM ssh_key_container_bindings scb
        JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
        JOIN containers c ON c.id = scb.container_id
        WHERE ub.user_id = ? AND scb.ssh_key_id = ?
        ORDER BY scb.container_id ASC
        """,
        (user_id, ssh_key_id),
    ).fetchall()


def delete_ssh_key_everywhere(connection: sqlite3.Connection, user_id: int, ssh_key_id: int) -> None:
    connection.execute("DELETE FROM ssh_key_container_bindings WHERE ssh_key_id = ?", (ssh_key_id,))
    connection.execute(
        "DELETE FROM user_ssh_key_bindings WHERE user_id = ? AND ssh_key_id = ?",
        (user_id, ssh_key_id),
    )
    connection.execute("DELETE FROM ssh_public_keys WHERE id = ?", (ssh_key_id,))
