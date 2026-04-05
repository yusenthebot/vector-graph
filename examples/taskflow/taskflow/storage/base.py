"""Abstract storage backend — strategy pattern for pluggable persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """Abstract storage backend.

    Concrete implementations: InMemoryStore, FileStore.
    """

    @abstractmethod
    def save(self, collection: str, id: str, data: dict) -> None:
        """Persist a record."""
        ...

    @abstractmethod
    def load(self, collection: str, id: str) -> Optional[dict]:
        """Return record or None if not found."""
        ...

    @abstractmethod
    def delete(self, collection: str, id: str) -> bool:
        """Delete record. Returns True if it existed."""
        ...

    @abstractmethod
    def list_all(self, collection: str) -> list[dict]:
        """Return all records in a collection."""
        ...

    @abstractmethod
    def count(self, collection: str) -> int:
        """Return number of records in a collection."""
        ...

    def exists(self, collection: str, id: str) -> bool:
        """Check if a record exists (default: load + check)."""
        return self.load(collection, id) is not None
