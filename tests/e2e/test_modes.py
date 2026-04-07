"""Test: mode switching (Arch / Logic / Deep)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_mode_buttons_present(e2e_page) -> None:
    """All three mode buttons should be visible."""
    for mode in ["arch", "logic", "deep"]:
        btn = e2e_page.locator(f"[data-testid='mode-btn-{mode}']")
        assert btn.is_visible(), f"Mode button '{mode}' not visible"


def test_logic_mode_active_by_default(e2e_page) -> None:
    """Logic mode should be the default active mode."""
    btn = e2e_page.locator("[data-testid='mode-btn-logic']")
    assert "active" in btn.get_attribute("class")


def test_switch_to_arch_mode(e2e_page) -> None:
    """Switching to Arch mode should update stats (fewer nodes)."""
    logic_stats = e2e_page.evaluate("document.getElementById('sb-stats').textContent")

    e2e_page.locator("[data-testid='mode-btn-arch']").click()
    e2e_page.wait_for_timeout(1000)

    arch_stats = e2e_page.evaluate("document.getElementById('sb-stats').textContent")
    assert "nodes" in arch_stats

    # Arch mode shows only File nodes — should have fewer nodes than Logic
    import re
    logic_count = int(re.search(r"(\d+)\s*nodes", logic_stats).group(1))
    arch_count = int(re.search(r"(\d+)\s*nodes", arch_stats).group(1))
    assert arch_count < logic_count, f"Arch ({arch_count}) should have fewer nodes than Logic ({logic_count})"


def test_switch_to_deep_mode(e2e_page) -> None:
    """Switching to Deep mode should show more nodes than Logic."""
    logic_stats = e2e_page.evaluate("document.getElementById('sb-stats').textContent")

    e2e_page.locator("[data-testid='mode-btn-deep']").click()
    e2e_page.wait_for_timeout(1000)

    deep_stats = e2e_page.evaluate("document.getElementById('sb-stats').textContent")

    import re
    logic_count = int(re.search(r"(\d+)\s*nodes", logic_stats).group(1))
    deep_count = int(re.search(r"(\d+)\s*nodes", deep_stats).group(1))
    assert deep_count >= logic_count, f"Deep ({deep_count}) should have >= nodes than Logic ({logic_count})"
