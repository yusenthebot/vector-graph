"""In-memory storage backend — fast, ephemeral, test-friendly."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from taskflow.storage.base import StorageBackend


class InMemoryStore(StorageBackend):
    """Stores all data in a nested dict — no persistence across restarts."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = defaultdict(dict)

    def save(self, collection: str, id: str, data: dict) -> None:
        self._data[collection][id] = dict(data)

    def load(self, collection: str, id: str) -> Optional[dict]:
        return self._data.get(collection, {}).get(id)

    def delete(self, collection: str, id: str) -> bool:
        if id in self._data.get(collection, {}):
            del self._data[collection][id]
            return True
        return False

    def list_all(self, collection: str) -> list[dict]:
        return list(self._data.get(collection, {}).values())

    def count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))

    def clear(self) -> None:
        """Wipe all data — useful in tests."""
        self._data.clear()

    def collections(self) -> list[str]:
        """Return names of all non-empty collections."""
        return [k for k, v in self._data.items() if v]
