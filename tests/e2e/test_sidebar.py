"""Test: sidebar tabs and filter interactions."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_tab_switching(e2e_page) -> None:
    """Clicking a sidebar tab should switch the visible panel."""
    # Explorer is active by default
    explorer = e2e_page.locator("#panel-explorer")
    assert explorer.is_visible()

    # Switch to Filters
    e2e_page.locator("[data-testid='sidebar-tab-filters']").click()
    e2e_page.wait_for_timeout(500)

    filters = e2e_page.locator("#panel-filters")
    assert filters.is_visible()

    # Explorer should no longer be active
    assert not explorer.evaluate("el => el.classList.contains('active')")


def test_explorer_has_files(e2e_page) -> None:
    """Explorer tab should show file tree with actual files."""
    explorer = e2e_page.locator("#panel-explorer")
    text = explorer.inner_text()
    # The taskflow example should have some .py files
    assert ".py" in text or "task" in text.lower(), f"Explorer should show files: {text[:200]}"


def test_filters_show_node_types(e2e_page) -> None:
    """Filters tab should list node types with counts."""
    e2e_page.locator("[data-testid='sidebar-tab-filters']").click()
    e2e_page.wait_for_timeout(500)

    filters = e2e_page.locator("#panel-filters")
    text = filters.inner_text()
    assert "Function" in text, "Filters should show 'Function' type"
    assert "Class" in text, "Filters should show 'Class' type"
    assert "File" in text, "Filters should show 'File' type"
