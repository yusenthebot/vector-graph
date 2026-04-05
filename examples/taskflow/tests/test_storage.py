"""Unit tests for taskflow.storage backends."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from taskflow.storage.file_store import FileStore
from taskflow.storage.memory import InMemoryStore


class TestInMemoryStore:
    def test_save_and_load(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1", "title": "Test"})
        result = store.load("tasks", "t1")
        assert result is not None
        assert result["title"] == "Test"

    def test_load_missing_returns_none(self) -> None:
        store = InMemoryStore()
        assert store.load("tasks", "missing") is None

    def test_delete_existing_returns_true(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1"})
        assert store.delete("tasks", "t1")
        assert store.load("tasks", "t1") is None

    def test_delete_missing_returns_false(self) -> None:
        store = InMemoryStore()
        assert not store.delete("tasks", "missing")

    def test_list_all(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1"})
        store.save("tasks", "t2", {"id": "t2"})
        items = store.list_all("tasks")
        assert len(items) == 2

    def test_count(self) -> None:
        store = InMemoryStore()
        assert store.count("tasks") == 0
        store.save("tasks", "t1", {"id": "t1"})
        assert store.count("tasks") == 1

    def test_clear(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1"})
        store.clear()
        assert store.count("tasks") == 0

    def test_exists(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1"})
        assert store.exists("tasks", "t1")
        assert not store.exists("tasks", "t2")

    def test_save_overwrites_existing(self) -> None:
        store = InMemoryStore()
        store.save("tasks", "t1", {"id": "t1", "v": 1})
        store.save("tasks", "t1", {"id": "t1", "v": 2})
        result = store.load("tasks", "t1")
        assert result is not None
        assert result["v"] == 2


class TestFileStore:
    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            store.save("tasks", "t1", {"id": "t1", "title": "Persisted"})
            result = store.load("tasks", "t1")
            assert result is not None
            assert result["title"] == "Persisted"

    def test_load_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            assert store.load("tasks", "missing") is None

    def test_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            store.save("tasks", "t1", {"id": "t1"})
            assert store.delete("tasks", "t1")
            assert store.load("tasks", "t1") is None

    def test_delete_missing_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            assert not store.delete("tasks", "missing")

    def test_list_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            store.save("tasks", "t1", {"id": "t1"})
            store.save("tasks", "t2", {"id": "t2"})
            assert len(store.list_all("tasks")) == 2

    def test_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            assert store.count("tasks") == 0
            store.save("tasks", "t1", {"id": "t1"})
            assert store.count("tasks") == 1

    def test_persistence_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store1 = FileStore(tmpdir)
            store1.save("tasks", "t1", {"id": "t1", "v": 42})

            store2 = FileStore(tmpdir)
            result = store2.load("tasks", "t1")
            assert result is not None
            assert result["v"] == 42

    def test_clear_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(tmpdir)
            store.save("tasks", "t1", {"id": "t1"})
            store.clear_all()
            assert store.count("tasks") == 0
