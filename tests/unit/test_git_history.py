"""Unit tests for git history analysis."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vector_graph.analysis.git_history import (
    FileHotspot,
    CoChangeEdge,
    analyze_hotspots,
    analyze_co_changes,
    get_git_summary,
    _is_git_repo,
    _run_git,
)


# ---------------------------------------------------------------------------
# Mock git log outputs
# ---------------------------------------------------------------------------

# 90-day log with 4 commits
MOCK_LOG_90 = """\
COMMIT abc123 alice@example.com 2026-04-01T10:00:00+00:00
src/engine.py
src/models.py

COMMIT def456 bob@example.com 2026-04-02T10:00:00+00:00
src/engine.py
src/utils.py

COMMIT ghi789 alice@example.com 2026-04-03T10:00:00+00:00
src/engine.py
src/models.py
src/api.py

COMMIT jkl012 alice@example.com 2026-03-15T10:00:00+00:00
src/engine.py
"""

# 30-day log (COMMIT format without metadata)
MOCK_LOG_30 = """\
COMMIT
src/engine.py
src/models.py

COMMIT
src/engine.py
src/utils.py

COMMIT
src/engine.py
src/models.py
src/api.py
"""

# Co-change log (plain COMMIT marker, name-only)
MOCK_CO_LOG = """\
COMMIT
src/engine.py
src/models.py

COMMIT
src/engine.py
src/utils.py

COMMIT
src/engine.py
src/models.py
src/api.py

COMMIT
src/engine.py
src/models.py
"""


def _make_run_git_side_effect(
    main_log: str,
    recent_log: str,
) -> "function":
    """Return a side_effect callable that yields different outputs per call."""
    call_count = [0]

    def _side_effect(root: str, args: list[str], timeout: int = 10) -> str:
        # _is_git_repo check comes first — returns "true"
        if "rev-parse" in args:
            return "true\n"
        # First git log call = main (90-day with metadata)
        # Second git log call = recent (30-day)
        call_count[0] += 1
        if call_count[0] == 1:
            return main_log
        return recent_log

    return _side_effect


# ---------------------------------------------------------------------------
# Tests: _run_git
# ---------------------------------------------------------------------------


class TestRunGit:
    def test_returns_empty_on_nonexistent_repo(self) -> None:
        """_run_git returns empty string for invalid repo path."""
        result = _run_git("/nonexistent/path/xyz", ["status"])
        assert result == ""

    def test_returns_empty_on_timeout(self) -> None:
        """_run_git catches TimeoutExpired and returns empty string."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 1)):
            result = _run_git("/some/path", ["log"], timeout=1)
        assert result == ""

    def test_returns_empty_on_nonzero_exit(self) -> None:
        """_run_git returns empty string when git exits non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = "fatal: not a git repository"
        with patch("subprocess.run", return_value=mock_result):
            result = _run_git("/some/path", ["log"])
        assert result == ""

    def test_returns_stdout_on_success(self) -> None:
        """_run_git returns stdout when git exits zero."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "true\n"
        with patch("subprocess.run", return_value=mock_result):
            result = _run_git("/repo", ["rev-parse", "--is-inside-work-tree"])
        assert result == "true\n"


# ---------------------------------------------------------------------------
# Tests: _is_git_repo
# ---------------------------------------------------------------------------


class TestIsGitRepo:
    def test_returns_true_for_valid_repo(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._run_git", return_value="true\n"
        ):
            assert _is_git_repo("/some/repo") is True

    def test_returns_false_for_non_repo(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._run_git", return_value=""
        ):
            assert _is_git_repo("/not/a/repo") is False


# ---------------------------------------------------------------------------
# Tests: analyze_hotspots
# ---------------------------------------------------------------------------


class TestAnalyzeHotspots:
    def _patch(self) -> "patch":
        return patch("vector_graph.analysis.git_history._run_git")

    def test_returns_empty_for_non_git_repo(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=False
        ):
            result = analyze_hotspots("/not/a/repo")
        assert result == {}

    def test_returns_empty_for_empty_log(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=""
        ):
            result = analyze_hotspots("/repo")
        assert result == {}

    def test_change_count_correct(self) -> None:
        """engine.py appears in 4 commits, models.py in 2."""
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        assert "src/engine.py" in result
        assert result["src/engine.py"].change_count == 4
        assert "src/models.py" in result
        assert result["src/models.py"].change_count == 2

    def test_recent_changes_populated(self) -> None:
        """recent_changes reflects 30-day window (3 engine.py hits in MOCK_LOG_30)."""
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        assert result["src/engine.py"].recent_changes == 3

    def test_top_contributors_sorted_by_count(self) -> None:
        """alice has 3 commits on engine.py, bob has 1 — alice listed first."""
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        contributors = result["src/engine.py"].top_contributors
        assert len(contributors) <= 3
        assert contributors[0] == "alice@example.com"

    def test_hotspot_score_without_complexity_map(self) -> None:
        """Without complexity_map, score = change_count / max_changes."""
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        # engine.py has max changes (4/4 = 1.0)
        assert result["src/engine.py"].hotspot_score == pytest.approx(1.0)

    def test_hotspot_score_with_complexity_map(self) -> None:
        """hotspot_score = freq_normalized * complexity, capped at 1.0."""
        complexity_map = {"src/engine.py": 2.0, "src/models.py": 0.5}
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", complexity_map=complexity_map, days=90)

        # engine.py: (4/4) * 2.0 = 2.0 -> capped to 1.0
        assert result["src/engine.py"].hotspot_score == pytest.approx(1.0)
        # models.py: (2/4) * 0.5 = 0.25
        assert result["src/models.py"].hotspot_score == pytest.approx(0.25)

    def test_last_modified_is_latest_date(self) -> None:
        """last_modified should be the most recent commit date for the file."""
        side_effect = _make_run_git_side_effect(MOCK_LOG_90, MOCK_LOG_30)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        # engine.py's latest commit is 2026-04-03
        assert result["src/engine.py"].last_modified == "2026-04-03T10:00:00+00:00"

    def test_non_python_files_excluded(self) -> None:
        """Only .py files are tracked; .txt, .md, etc. are ignored."""
        log_with_other = """\
COMMIT abc123 dev@example.com 2026-04-01T10:00:00+00:00
src/engine.py
README.md
setup.cfg
"""
        recent_empty = ""
        side_effect = _make_run_git_side_effect(log_with_other, recent_empty)
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", side_effect=side_effect
        ):
            result = analyze_hotspots("/repo", days=90)

        assert "src/engine.py" in result
        assert "README.md" not in result
        assert "setup.cfg" not in result

    def test_filehotspot_is_frozen_dataclass(self) -> None:
        """FileHotspot must be immutable (frozen=True)."""
        h = FileHotspot(
            file_path="a.py",
            change_count=1,
            recent_changes=0,
            top_contributors=("dev@x.com",),
            last_modified="2026-01-01T00:00:00+00:00",
            churn_lines=0,
            hotspot_score=0.5,
        )
        with pytest.raises((AttributeError, TypeError)):
            h.change_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: analyze_co_changes
# ---------------------------------------------------------------------------


class TestAnalyzeCoChanges:
    def test_returns_empty_for_non_git_repo(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=False
        ):
            result = analyze_co_changes("/not/a/repo")
        assert result == []

    def test_returns_empty_for_empty_log(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=""
        ):
            result = analyze_co_changes("/repo")
        assert result == []

    def test_co_change_pair_detected(self) -> None:
        """engine.py + models.py appear together in 3 commits in MOCK_CO_LOG."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            result = analyze_co_changes("/repo", min_count=2, min_confidence=0.0)

        pairs = {(e.file_a, e.file_b) for e in result}
        assert ("src/engine.py", "src/models.py") in pairs

    def test_min_count_filter_applied(self) -> None:
        """Pairs below min_count threshold are excluded."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            # engine.py + api.py co-change only once -> excluded at min_count=2
            result = analyze_co_changes("/repo", min_count=2, min_confidence=0.0)

        pairs = {(e.file_a, e.file_b) for e in result}
        assert ("src/api.py", "src/engine.py") not in pairs
        assert ("src/engine.py", "src/api.py") not in pairs

    def test_confidence_calculation(self) -> None:
        """confidence = co_change_count / min(changes_a, changes_b)."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            result = analyze_co_changes("/repo", min_count=1, min_confidence=0.0)

        # Find the engine+models edge
        engine_models = next(
            (
                e
                for e in result
                if set([e.file_a, e.file_b])
                == {"src/engine.py", "src/models.py"}
            ),
            None,
        )
        assert engine_models is not None
        # engine: 4 commits (appears in all 4), models: 3 commits (appears in 3)
        # co-change: 3 times -> confidence = 3/3 = 1.0
        assert engine_models.confidence == pytest.approx(1.0, abs=0.01)

    def test_min_confidence_filter_applied(self) -> None:
        """Pairs below min_confidence are excluded."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            # engine+utils: 1 co-change / min(4,1) = 1.0 confidence but only 1 count
            result = analyze_co_changes(
                "/repo", min_count=1, min_confidence=0.99
            )

        # only high-confidence pairs survive
        for edge in result:
            assert edge.confidence >= 0.99

    def test_results_sorted_by_co_change_count_desc(self) -> None:
        """Results are sorted descending by co_change_count."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            result = analyze_co_changes("/repo", min_count=1, min_confidence=0.0)

        counts = [e.co_change_count for e in result]
        assert counts == sorted(counts, reverse=True)

    def test_max_pairs_limit_respected(self) -> None:
        """No more than max_pairs edges are returned."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history._run_git", return_value=MOCK_CO_LOG
        ):
            result = analyze_co_changes(
                "/repo", min_count=1, min_confidence=0.0, max_pairs=1
            )

        assert len(result) <= 1

    def test_cochange_edge_is_frozen_dataclass(self) -> None:
        """CoChangeEdge must be immutable (frozen=True)."""
        edge = CoChangeEdge(
            file_a="a.py",
            file_b="b.py",
            co_change_count=5,
            confidence=0.8,
        )
        with pytest.raises((AttributeError, TypeError)):
            edge.co_change_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: get_git_summary
# ---------------------------------------------------------------------------


class TestGetGitSummary:
    def test_returns_not_git_repo_for_non_repo(self) -> None:
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=False
        ):
            result = get_git_summary("/not/a/repo")
        assert result == {"is_git_repo": False}

    def test_summary_structure_for_valid_repo(self) -> None:
        """get_git_summary returns expected keys for a valid repo."""
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history.analyze_hotspots",
            return_value={},
        ), patch(
            "vector_graph.analysis.git_history.analyze_co_changes",
            return_value=[],
        ):
            result = get_git_summary("/repo", days=60)

        assert result["is_git_repo"] is True
        assert result["days_analyzed"] == 60
        assert result["files_with_history"] == 0
        assert result["active_contributors"] == 0
        assert result["most_volatile_file"] == ""
        assert result["total_co_change_pairs"] == 0

    def test_summary_most_volatile_file(self) -> None:
        """most_volatile_file is the file with the highest change_count."""
        hotspots = {
            "src/a.py": FileHotspot(
                file_path="src/a.py",
                change_count=10,
                recent_changes=5,
                top_contributors=("dev@x.com",),
                last_modified="2026-04-01T00:00:00+00:00",
                churn_lines=0,
                hotspot_score=1.0,
            ),
            "src/b.py": FileHotspot(
                file_path="src/b.py",
                change_count=3,
                recent_changes=1,
                top_contributors=("other@x.com",),
                last_modified="2026-04-02T00:00:00+00:00",
                churn_lines=0,
                hotspot_score=0.3,
            ),
        }
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history.analyze_hotspots",
            return_value=hotspots,
        ), patch(
            "vector_graph.analysis.git_history.analyze_co_changes",
            return_value=[],
        ):
            result = get_git_summary("/repo")

        assert result["most_volatile_file"] == "src/a.py"
        assert result["files_with_history"] == 2
        assert result["active_contributors"] == 2

    def test_summary_active_contributors_deduped(self) -> None:
        """Same contributor across multiple files counted once."""
        shared = ("alice@example.com",)
        hotspots = {
            "src/a.py": FileHotspot(
                file_path="src/a.py",
                change_count=2,
                recent_changes=0,
                top_contributors=shared,
                last_modified="2026-04-01T00:00:00+00:00",
                churn_lines=0,
                hotspot_score=0.5,
            ),
            "src/b.py": FileHotspot(
                file_path="src/b.py",
                change_count=1,
                recent_changes=0,
                top_contributors=shared,
                last_modified="2026-04-01T00:00:00+00:00",
                churn_lines=0,
                hotspot_score=0.25,
            ),
        }
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history.analyze_hotspots",
            return_value=hotspots,
        ), patch(
            "vector_graph.analysis.git_history.analyze_co_changes",
            return_value=[],
        ):
            result = get_git_summary("/repo")

        assert result["active_contributors"] == 1

    def test_summary_co_change_pairs_count(self) -> None:
        """total_co_change_pairs reflects the length of co_changes list."""
        edges = [
            CoChangeEdge("a.py", "b.py", 5, 0.8),
            CoChangeEdge("a.py", "c.py", 3, 0.6),
        ]
        with patch(
            "vector_graph.analysis.git_history._is_git_repo", return_value=True
        ), patch(
            "vector_graph.analysis.git_history.analyze_hotspots",
            return_value={},
        ), patch(
            "vector_graph.analysis.git_history.analyze_co_changes",
            return_value=edges,
        ):
            result = get_git_summary("/repo")

        assert result["total_co_change_pairs"] == 2
