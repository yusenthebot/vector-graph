"""Server-Sent Events broadcaster for real-time change push.

Provides:
  - format_sse_event: format a dict as an SSE text/event-stream message.
  - SSEBroadcaster: thread-safe broadcaster that fans out events to all
    connected HTTP clients via per-client Queue objects.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any


def format_sse_event(data: dict[str, Any], event_type: str = "change") -> str:
    """Format a dict as an SSE event string.

    The returned string has the format::

        event: <event_type>\\n
        data: <json>\\n
        \\n

    The double trailing newline is required by the SSE specification to delimit
    events.  Non-serializable values are coerced to strings via ``default=str``.
    """
    json_str = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {json_str}\n\n"


class SSEBroadcaster:
    """Thread-safe broadcaster that pushes events to all connected SSE clients.

    Each call to ``add_client()`` returns a ``queue.Queue`` from which the
    HTTP handler can read pre-formatted SSE strings.  The broadcaster
    automatically prunes clients whose queues are full (indicating a slow or
    disconnected consumer).
    """

    def __init__(self) -> None:
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def add_client(self) -> queue.Queue:
        """Register a new SSE client.

        Returns a ``queue.Queue[str]`` from which the handler reads SSE frames.
        The queue has maxsize=100; if it fills up the client is dropped on the
        next push.
        """
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.append(q)
        return q

    def remove_client(self, q: queue.Queue) -> None:
        """Unregister a client queue.  Safe to call even if queue was never added."""
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    @property
    def client_count(self) -> int:
        """Current number of connected clients."""
        with self._lock:
            return len(self._clients)

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def push(self, data: dict[str, Any], event_type: str = "change") -> None:
        """Format and push an event to all connected clients.

        Clients whose queues are full are removed silently (they are assumed to
        be disconnected or too slow to consume).
        """
        message = format_sse_event(data, event_type)
        with self._lock:
            dead: list[queue.Queue] = []
            for q in self._clients:
                try:
                    q.put_nowait(message)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass
