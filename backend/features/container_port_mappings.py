import sqlite3
from typing import Any

from fastapi import HTTPException, status


MAX_CONTAINER_PORT_MAPPING_SLOTS = 3


def normalize_container_port_mappings(port_mappings: list[Any]) -> list[dict]:
    normalized_items: list[dict] = []
    seen_slots: set[int] = set()
    seen_container_ports: set[int] = set()

    for raw_item in port_mappings or []:
        if isinstance(raw_item, dict):
            item = raw_item
        else:
            item = {
                "slot_index": getattr(raw_item, "slot_index", None),
                "public_port": getattr(raw_item, "public_port", None),
                "container_port": getattr(raw_item, "container_port", None),
            }

        try:
            slot_index = int(item.get("slot_index"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="端口映射槽位无效")

        if slot_index < 1 or slot_index > MAX_CONTAINER_PORT_MAPPING_SLOTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="端口映射槽位必须在 1 到 3 之间")
        if slot_index in seen_slots:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="端口映射槽位不能重复")
        seen_slots.add(slot_index)

        public_port = item.get("public_port")
        container_port = item.get("container_port")
        has_public_port = public_port is not None
        has_container_port = container_port is not None

        if has_public_port != has_container_port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"端口{slot_index} 必须同时填写公网端口和容器端口",
            )
        if not has_public_port:
            continue

        try:
            normalized_public_port = int(public_port)
            normalized_container_port = int(container_port)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"端口{slot_index} 的公网端口和容器端口必须是整数",
            )

        if not 1 <= normalized_public_port <= 65535 or not 1 <= normalized_container_port <= 65535:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"端口{slot_index} 的端口范围必须在 1 到 65535 之间",
            )
        if normalized_container_port in seen_container_ports:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="同一服务器的容器端口不能重复")
        seen_container_ports.add(normalized_container_port)

        normalized_items.append(
            {
                "slot_index": slot_index,
                "public_port": normalized_public_port,
                "container_port": normalized_container_port,
            }
        )

    return sorted(normalized_items, key=lambda item: item["slot_index"])


def ensure_public_ports_available(
    connection: sqlite3.Connection,
    port_mappings: list[dict],
    container_id: int | None = None,
) -> None:
    if not port_mappings:
        return

    public_ports = [int(item["public_port"]) for item in port_mappings]
    placeholders = ",".join("?" for _ in public_ports)
    params: list[object] = [*public_ports]
    sql = f"""
        SELECT public_port, container_id
        FROM container_port_mappings
        WHERE public_port IN ({placeholders})
    """
    if container_id is not None:
        sql += " AND container_id != ?"
        params.append(container_id)

    rows = connection.execute(sql, params).fetchall()
    if rows:
        conflicted_port = int(rows[0]["public_port"])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"公网端口 {conflicted_port} 已被其他服务器占用",
        )


def replace_container_port_mappings(
    connection: sqlite3.Connection,
    container_id: int,
    port_mappings: list[dict],
) -> None:
    connection.execute("DELETE FROM container_port_mappings WHERE container_id = ?", (container_id,))
    if not port_mappings:
        return

    connection.executemany(
        """
        INSERT INTO container_port_mappings (
            container_id,
            slot_index,
            public_port,
            container_port
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                container_id,
                int(item["slot_index"]),
                int(item["public_port"]),
                int(item["container_port"]),
            )
            for item in port_mappings
        ],
    )


def fetch_container_port_mapping_map(
    connection: sqlite3.Connection,
    container_ids: list[int] | None = None,
) -> dict[int, list[dict]]:
    sql = """
        SELECT container_id, slot_index, public_port, container_port
        FROM container_port_mappings
    """
    params: list[object] = []
    if container_ids:
        placeholders = ",".join("?" for _ in container_ids)
        sql += f" WHERE container_id IN ({placeholders})"
        params.extend(container_ids)
    sql += " ORDER BY container_id ASC, slot_index ASC"

    rows = connection.execute(sql, params).fetchall()
    mapping_map: dict[int, list[dict]] = {}
    for row in rows:
        mapping_map.setdefault(int(row["container_id"]), []).append(
            {
                "slot_index": int(row["slot_index"]),
                "public_port": int(row["public_port"]),
                "container_port": int(row["container_port"]),
            }
        )
    return mapping_map
