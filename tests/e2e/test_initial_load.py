"""Test: page loads, no JS errors, graph data visible."""

from __future__ import annotations

import json
import urllib.request

import pytest

pytestmark = pytest.mark.e2e


def test_page_loads_without_js_errors(e2e_page) -> None:
    """Page should load with no JavaScript errors."""
    # JS errors are captured by the e2e_page fixture during initial load
    errors = getattr(e2e_page, "_js_errors", [])
    assert len(errors) == 0, f"JS errors: {errors}"


def test_statusbar_shows_stats(e2e_page) -> None:
    """Status bar should show node/edge/group counts."""
    text = e2e_page.evaluate("document.getElementById('sb-stats').textContent")
    assert "nodes" in text, f"Expected 'nodes' in stats: {text}"
    assert "edges" in text, f"Expected 'edges' in stats: {text}"
    assert "groups" in text, f"Expected 'groups' in stats: {text}"


def test_sidebar_visible(e2e_page) -> None:
    """Sidebar should be visible with all 4 tabs."""
    sidebar = e2e_page.locator("[data-testid='sidebar']")
    assert sidebar.is_visible()

    for tab in ["explorer", "groups", "filters", "changes"]:
        tab_el = e2e_page.locator(f"[data-testid='sidebar-tab-{tab}']")
        assert tab_el.is_visible(), f"Tab '{tab}' not visible"


def test_graph_container_exists(e2e_page) -> None:
    """Graph container should be present and visible in the DOM."""
    container = e2e_page.locator("[data-testid='graph-container']")
    assert container.is_visible()


def test_api_data_returns_json(e2e_server: str) -> None:
    """The /api/data endpoint should return valid graph data with nodes and links."""
    resp = urllib.request.urlopen(f"{e2e_server}/api/data")
    data: dict = json.loads(resp.read())
    assert "nodes" in data, "Response missing 'nodes' key"
    assert "links" in data, "Response missing 'links' key"
    assert len(data["nodes"]) > 0, "Expected at least one node from the taskflow example"
