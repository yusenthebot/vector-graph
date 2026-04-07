"""Test: command palette (Ctrl+K)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_cmd_palette_opens_with_ctrl_k(e2e_page) -> None:
    """Ctrl+K should open the command palette."""
    palette = e2e_page.locator("[data-testid='cmd-palette']")

    # Should be hidden initially
    assert not palette.evaluate("el => el.classList.contains('open')")

    # Open with Ctrl+K
    e2e_page.keyboard.press("Control+k")
    e2e_page.wait_for_timeout(500)

    assert palette.evaluate("el => el.classList.contains('open')")


def test_cmd_palette_closes_with_escape(e2e_page) -> None:
    """Escape should close the command palette."""
    e2e_page.keyboard.press("Control+k")
    e2e_page.wait_for_timeout(500)

    e2e_page.keyboard.press("Escape")
    e2e_page.wait_for_timeout(500)

    palette = e2e_page.locator("[data-testid='cmd-palette']")
    assert not palette.evaluate("el => el.classList.contains('open')")


def test_cmd_palette_shows_commands(e2e_page) -> None:
    """Command palette should list available commands."""
    e2e_page.keyboard.press("Control+k")
    e2e_page.wait_for_timeout(500)

    results = e2e_page.locator("#cmd-results")
    text = results.inner_text()
    assert "Architecture" in text or "Logic" in text or "Deep" in text, \
        f"Command palette should show mode commands: {text[:200]}"
