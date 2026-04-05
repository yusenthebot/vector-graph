"""Unit tests for SSEBroadcaster and format_sse_event (TDD — written before implementation)."""

from __future__ import annotations

import json
import queue
import threading
import time

import pytest

from vector_graph.api.sse_server import SSEBroadcaster, format_sse_event


# ---------------------------------------------------------------------------
# T1: test_sse_format_event
# ---------------------------------------------------------------------------

class TestSseFormatEvent:
    def test_format_basic_structure(self) -> None:
        """format_sse_event returns 'event: change\\ndata: {...}\\n\\n'."""
        data = {"file": "/project/a.py", "type": "modified"}
        result = format_sse_event(data)
        assert result.startswith("event: change\n")
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_format_default_event_type_is_change(self) -> None:
        data = {"x": 1}
        result = format_sse_event(data)
        assert result.startswith("event: change\n")

    def test_format_custom_event_type(self) -> None:
        data = {"x": 1}
        result = format_sse_event(data, event_type="session")
        assert result.startswith("event: session\n")

    def test_format_two_trailing_newlines(self) -> None:
        """SSE requires exactly two newlines at the end."""
        data = {"k": "v"}
        result = format_sse_event(data)
        assert result[-2:] == "\n\n"
        # Exactly one blank line (the double newline terminates the event)
        assert result.count("\n\n") == 1


# ---------------------------------------------------------------------------
# T2: test_sse_format_valid_json
# ---------------------------------------------------------------------------

class TestSseFormatValidJson:
    def test_data_field_is_valid_json(self) -> None:
        """The data: line must contain parseable JSON."""
        data = {"file": "/x.py", "nodes_added": ["fn_a", "fn_b"], "risk": "LOW"}
        result = format_sse_event(data)
        # Extract the data: line
        for line in result.split("\n"):
            if line.startswith("data: "):
                payload = line[len("data: "):]
                parsed = json.loads(payload)
                assert parsed["file"] == "/x.py"
                assert parsed["nodes_added"] == ["fn_a", "fn_b"]
                return
        pytest.fail("No data: line found in SSE output")

    def test_non_serializable_values_coerced(self) -> None:
        """Non-serializable values (e.g. custom objects) should not raise — default=str."""
        class Weird:
            def __str__(self) -> str:
                return "weird_obj"

        data = {"obj": Weird()}
        # Should not raise
        result = format_sse_event(data)
        assert "weird_obj" in result

    def test_empty_dict_is_valid(self) -> None:
        result = format_sse_event({})
        for line in result.split("\n"):
            if line.startswith("data: "):
                parsed = json.loads(line[len("data: "):])
                assert parsed == {}
                return
        pytest.fail("No data: line found")


# ---------------------------------------------------------------------------
# T3: test_sse_broadcaster_add_remove_client
# ---------------------------------------------------------------------------

class TestSseBroadcasterAddRemoveClient:
    def test_add_client_returns_queue(self) -> None:
        broadcaster = SSEBroadcaster()
        q = broadcaster.add_client()
        assert isinstance(q, queue.Queue)

    def test_client_count_increments(self) -> None:
        broadcaster = SSEBroadcaster()
        assert broadcaster.client_count == 0
        q1 = broadcaster.add_client()
        assert broadcaster.client_count == 1
        q2 = broadcaster.add_client()
        assert broadcaster.client_count == 2

    def test_remove_client_decrements_count(self) -> None:
        broadcaster = SSEBroadcaster()
        q = broadcaster.add_client()
        assert broadcaster.client_count == 1
        broadcaster.remove_client(q)
        assert broadcaster.client_count == 0

    def test_remove_nonexistent_client_is_safe(self) -> None:
        """Removing a queue that was never added should not raise."""
        broadcaster = SSEBroadcaster()
        orphan: queue.Queue = queue.Queue()
        broadcaster.remove_client(orphan)  # Must not raise
        assert broadcaster.client_count == 0

    def test_add_multiple_then_remove_one(self) -> None:
        broadcaster = SSEBroadcaster()
        q1 = broadcaster.add_client()
        q2 = broadcaster.add_client()
        q3 = broadcaster.add_client()
        broadcaster.remove_client(q2)
        assert broadcaster.client_count == 2


# ---------------------------------------------------------------------------
# T4: test_sse_broadcaster_push_event
# ---------------------------------------------------------------------------

class TestSseBroadcasterPushEvent:
    def test_push_delivers_to_client(self) -> None:
        """push() places a formatted SSE message in the client queue."""
        broadcaster = SSEBroadcaster()
        q = broadcaster.add_client()
        data = {"file": "/a.py", "type": "modified"}
        broadcaster.push(data)
        msg = q.get_nowait()
        assert "event: change" in msg
        assert "/a.py" in msg

    def test_push_with_custom_event_type(self) -> None:
        broadcaster = SSEBroadcaster()
        q = broadcaster.add_client()
        broadcaster.push({"x": 1}, event_type="session")
        msg = q.get_nowait()
        assert "event: session" in msg

    def test_push_empty_broadcaster_does_not_raise(self) -> None:
        """Pushing with no clients should silently do nothing."""
        broadcaster = SSEBroadcaster()
        broadcaster.push({"file": "/x.py"})  # No clients — must not raise

    def test_push_removes_full_client_queue(self) -> None:
        """If a client queue is full, it should be silently removed."""
        broadcaster = SSEBroadcaster()
        # maxsize=1 so it fills immediately
        small_q: queue.Queue = queue.Queue(maxsize=1)
        broadcaster._clients.append(small_q)
        broadcaster._clients.append(small_q)  # two refs to same queue

        # Fill the queue
        small_q.put_nowait("already full")
        # Now push — should not raise even though queue is full
        broadcaster.push({"file": "/overflow.py"})
        # The full client was removed
        assert broadcaster.client_count == 0


# ---------------------------------------------------------------------------
# T5: test_sse_broadcaster_multiple_clients
# ---------------------------------------------------------------------------

class TestSseBroadcasterMultipleClients:
    def test_three_clients_all_receive_event(self) -> None:
        """All connected clients receive the same event."""
        broadcaster = SSEBroadcaster()
        q1 = broadcaster.add_client()
        q2 = broadcaster.add_client()
        q3 = broadcaster.add_client()
        data = {"file": "/broadcast.py", "count": 3}
        broadcaster.push(data)
        for q in (q1, q2, q3):
            msg = q.get_nowait()
            assert "/broadcast.py" in msg

    def test_each_client_gets_independent_copy(self) -> None:
        """Each client queue holds its own message string (not a shared reference)."""
        broadcaster = SSEBroadcaster()
        q1 = broadcaster.add_client()
        q2 = broadcaster.add_client()
        broadcaster.push({"x": 42})
        m1 = q1.get_nowait()
        m2 = q2.get_nowait()
        # Content is equal but they are independent strings
        assert m1 == m2

    def test_push_only_active_clients(self) -> None:
        """After removing a client, it should not receive further events."""
        broadcaster = SSEBroadcaster()
        q1 = broadcaster.add_client()
        q2 = broadcaster.add_client()
        broadcaster.remove_client(q2)
        broadcaster.push({"event": "ping"})
        # q1 gets the message
        assert not q1.empty()
        # q2 should be empty
        assert q2.empty()


# ---------------------------------------------------------------------------
# T6: Thread-safety
# ---------------------------------------------------------------------------

class TestSseBroadcasterThreadSafety:
    def test_concurrent_push_and_add(self) -> None:
        """Concurrent push + add should not deadlock or raise."""
        broadcaster = SSEBroadcaster()
        errors: list[Exception] = []

        def pusher() -> None:
            for _ in range(50):
                try:
                    broadcaster.push({"tick": 1})
                except Exception as exc:
                    errors.append(exc)

        def adder() -> None:
            queues = []
            for _ in range(20):
                try:
                    q = broadcaster.add_client()
                    queues.append(q)
                except Exception as exc:
                    errors.append(exc)
            # Clean up
            for q in queues:
                broadcaster.remove_client(q)

        t1 = threading.Thread(target=pusher)
        t2 = threading.Thread(target=adder)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert not errors
