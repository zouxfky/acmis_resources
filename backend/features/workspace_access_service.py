from backend.core.db import begin_immediate, get_connection
from backend.features.container_ssh_access import (
    acquire_container_user_sync_lock,
    acquire_container_user_sync_locks,
    build_container_user_sync_payload,
    ensure_container_ssh_available,
    sync_container_user_authorized_keys_payload,
)
from backend.features.workspace_access_queries import (
    delete_container_key_bindings,
    delete_ssh_key_everywhere,
    fetch_active_user_count,
    fetch_affected_container_rows_for_key,
    fetch_container_join_policy_row,
    fetch_current_container_key_ids,
    fetch_existing_membership,
    fetch_existing_selected_key_ids,
    fetch_joined_container_count,
    fetch_owned_key_ids,
    fetch_user_quota_row,
    fetch_user_ssh_key_binding,
    insert_container_key_bindings,
)
from backend.features.workspace_access_validators import (
    build_inserted_key_ids,
    normalize_ssh_key_ids,
    require_non_empty_join_selection,
    resolve_join_quota_limits,
    resolve_leaving_key_ids,
    validate_container_capacity,
    validate_current_container_key_ids,
    validate_join_container_row,
    validate_join_request_size,
    validate_leave_container_row,
    validate_owned_key_ids,
    validate_ssh_key_binding_exists,
    validate_user_container_quota,
)


def join_workspace_container_access(user_id: int, container_id: int, ssh_key_ids: list[int]) -> None:
    normalized_key_ids = normalize_ssh_key_ids(ssh_key_ids)
    require_non_empty_join_selection(normalized_key_ids)

    with acquire_container_user_sync_lock(container_id, user_id):
        ensure_container_ssh_available(container_id)
        with get_connection() as connection:
            begin_immediate(connection)
            try:
                quota_row = fetch_user_quota_row(connection, user_id)
                max_join_keys_per_request, max_containers_per_user = resolve_join_quota_limits(quota_row)
                validate_join_request_size(normalized_key_ids, max_join_keys_per_request)

                container = fetch_container_join_policy_row(connection, container_id)
                validate_join_container_row(container)

                owned_key_ids = fetch_owned_key_ids(connection, user_id, normalized_key_ids)
                validate_owned_key_ids(normalized_key_ids, owned_key_ids)

                existing_selected_ids = fetch_existing_selected_key_ids(
                    connection,
                    user_id,
                    container_id,
                    normalized_key_ids,
                )
                inserted_key_ids = build_inserted_key_ids(normalized_key_ids, existing_selected_ids)
                if not inserted_key_ids:
                    connection.rollback()
                    return

                existing_membership = fetch_existing_membership(connection, user_id, container_id)
                if not existing_membership:
                    joined_container_count = fetch_joined_container_count(connection, user_id)
                    validate_user_container_quota(joined_container_count, max_containers_per_user)

                    active_user_count = fetch_active_user_count(connection, container_id)
                    validate_container_capacity(active_user_count, int(container["max_users"]))

                insert_container_key_bindings(connection, container_id, inserted_key_ids)
                payload = build_container_user_sync_payload(connection, container_id, user_id)
                sync_container_user_authorized_keys_payload(payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def leave_workspace_container_access(user_id: int, container_id: int, ssh_key_ids: list[int]) -> bool:
    with acquire_container_user_sync_lock(container_id, user_id):
        ensure_container_ssh_available(container_id)
        with get_connection() as connection:
            begin_immediate(connection)
            try:
                container = fetch_container_join_policy_row(connection, container_id)
                validate_leave_container_row(container)

                current_key_ids = fetch_current_container_key_ids(connection, user_id, container_id)
                validate_current_container_key_ids(current_key_ids)

                leaving_key_ids = resolve_leaving_key_ids(ssh_key_ids, current_key_ids)
                if not leaving_key_ids:
                    connection.rollback()
                    return False

                delete_container_key_bindings(connection, container_id, leaving_key_ids)
                payload = build_container_user_sync_payload(connection, container_id, user_id)
                sync_container_user_authorized_keys_payload(payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    return True


def delete_workspace_ssh_key_and_sync(user_id: int, ssh_key_id: int) -> dict:
    with get_connection() as connection:
        begin_immediate(connection)
        binding = fetch_user_ssh_key_binding(connection, user_id, ssh_key_id)
        validate_ssh_key_binding_exists(binding)

        affected_container_rows = fetch_affected_container_rows_for_key(connection, user_id, ssh_key_id)
        affected_container_ids = [int(row["container_id"]) for row in affected_container_rows]
        connection.rollback()

    lock_items = [(container_id, user_id) for container_id in affected_container_ids]
    with acquire_container_user_sync_locks(lock_items):
        active_container_ids = [int(row["container_id"]) for row in affected_container_rows if row["status"] == "active"]
        for container_id in active_container_ids:
            ensure_container_ssh_available(container_id)

        with get_connection() as connection:
            begin_immediate(connection)
            try:
                binding = fetch_user_ssh_key_binding(connection, user_id, ssh_key_id)
                validate_ssh_key_binding_exists(binding)

                delete_ssh_key_everywhere(connection, user_id, ssh_key_id)

                for container_id in active_container_ids:
                    payload = build_container_user_sync_payload(connection, container_id, user_id)
                    sync_container_user_authorized_keys_payload(payload)

                connection.commit()
            except Exception:
                connection.rollback()
                raise

    return {"affected_container_ids": affected_container_ids}
