"""E2E test fixtures — real web server on random port."""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Enable WebGL in headless Chromium for Three.js rendering."""
    return {
        "args": [
            "--use-gl=angle",
            "--use-angle=swiftshader",
            "--enable-webgl",
            "--ignore-gpu-blocklist",
        ],
    }


@pytest.fixture(scope="session")
def e2e_server() -> str:
    """Start a real vector-graph web server on a random port.

    Analyzes the examples/taskflow project so we have real graph data.
    Returns the base URL string, e.g. 'http://127.0.0.1:54321'.
    """
    from vector_graph.api.python_api import CodeGraph
    from vector_graph.api.web_server import serve

    project_root = Path(__file__).parent.parent.parent
    example_dir = project_root / "examples" / "taskflow"

    cg = CodeGraph(str(example_dir))
    cg.analyze()

    graph = cg._graph
    assert graph is not None, "CodeGraph._graph must be set after analyze()"

    port = _find_free_port()

    server_thread = threading.Thread(
        target=serve,
        args=(graph,),
        kwargs={
            "root_path": str(example_dir),
            "host": "127.0.0.1",
            "port": port,
        },
        daemon=True,
    )
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base_url}/api/data", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    yield base_url


@pytest.fixture
def e2e_page(page, e2e_server: str):
    """Navigate to the vector-graph UI and wait for it to load."""
    # Collect JS errors
    js_errors = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    page.goto(e2e_server, wait_until="networkidle")

    # Wait for loadData() to complete by checking the API was fetched
    # and the status bar has content (even if not "visible" per Playwright)
    page.wait_for_function(
        """() => {
            const el = document.getElementById('sb-stats');
            return el && el.textContent && el.textContent.includes('nodes');
        }""",
        timeout=30000,
    )
    page.wait_for_timeout(1000)

    # Store JS errors for tests to check
    page._js_errors = js_errors
    return page


SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


@pytest.fixture(autouse=True)
def _capture_screenshot(request, page, e2e_server: str) -> None:
    """Capture a screenshot after every E2E test (pass or fail)."""
    yield
    name = request.node.name.replace("[", "_").replace("]", "")
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
    except Exception:
        pass
