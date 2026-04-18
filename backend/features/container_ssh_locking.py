import threading
from contextlib import contextmanager
from typing import Iterator


_SYNC_LOCKS: dict[tuple[int, int], threading.Lock] = {}
_SYNC_LOCKS_GUARD = threading.Lock()


def get_sync_lock(key: tuple[int, int]) -> threading.Lock:
    with _SYNC_LOCKS_GUARD:
        lock = _SYNC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SYNC_LOCKS[key] = lock
        return lock


@contextmanager
def acquire_container_user_sync_lock(container_id: int, user_id: int) -> Iterator[None]:
    lock = get_sync_lock((int(container_id), int(user_id)))
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@contextmanager
def acquire_container_user_sync_locks(lock_items: list[tuple[int, int]]) -> Iterator[None]:
    normalized_items = sorted({(int(container_id), int(user_id)) for container_id, user_id in lock_items})
    locks = [get_sync_lock(item) for item in normalized_items]
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()
