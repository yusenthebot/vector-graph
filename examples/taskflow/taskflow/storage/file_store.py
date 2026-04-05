"""File-backed JSON storage — persistent across restarts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from taskflow.storage.base import StorageBackend


class FileStore(StorageBackend):
    """Stores each collection as a JSON file under a root directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _collection_path(self, collection: str) -> Path:
        return self._root / f"{collection}.json"

    def _load_collection(self, collection: str) -> dict[str, dict]:
        path = self._collection_path(collection)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_collection(self, collection: str, data: dict[str, dict]) -> None:
        path = self._collection_path(collection)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def save(self, collection: str, id: str, record: dict) -> None:
        col = self._load_collection(collection)
        col[id] = dict(record)
        self._save_collection(collection, col)

    def load(self, collection: str, id: str) -> Optional[dict]:
        return self._load_collection(collection).get(id)

    def delete(self, collection: str, id: str) -> bool:
        col = self._load_collection(collection)
        if id not in col:
            return False
        del col[id]
        self._save_collection(collection, col)
        return True

    def list_all(self, collection: str) -> list[dict]:
        return list(self._load_collection(collection).values())

    def count(self, collection: str) -> int:
        return len(self._load_collection(collection))

    def clear_collection(self, collection: str) -> None:
        path = self._collection_path(collection)
        if path.exists():
            path.unlink()

    def clear_all(self) -> None:
        for path in self._root.glob("*.json"):
            path.unlink()
