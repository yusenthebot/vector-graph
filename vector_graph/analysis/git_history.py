"""Git history analysis for hotspot detection and co-change coupling.

Uses subprocess to call git — zero external dependencies.
Results cached after first computation (git history doesn't change during a session).
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileHotspot:
    """Per-file hotspot metrics from git history."""

    file_path: str
    change_count: int  # total commits touching this file
    recent_changes: int  # commits in last 30 days (subset of change_count)
    top_contributors: tuple[str, ...]  # sorted by commit count, top 3
    last_modified: str  # ISO date string
    churn_lines: int  # total lines added+removed (approximate)
    hotspot_score: float  # normalized 0-1 (change_frequency * complexity)


@dataclass(frozen=True)
class CoChangeEdge:
    """Two files that frequently change together (implicit coupling)."""

    file_a: str
    file_b: str
    co_change_count: int  # commits where both files changed
    confidence: float  # co_change_count / min(changes_a, changes_b)


def _run_git(root: str, args: list[str], timeout: int = 10) -> str:
    """Run a git command and return stdout. Returns empty string on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _is_git_repo(root: str) -> bool:
    """Check if root is inside a git repository."""
    return bool(_run_git(root, ["rev-parse", "--is-inside-work-tree"]).strip())


def analyze_hotspots(
    root: str,
    complexity_map: dict[str, float] | None = None,
    days: int = 90,
) -> dict[str, FileHotspot]:
    """Analyze git log to compute per-file change frequency and hotspot scores.

    Parameters
    ----------
    root:
        Project root directory (must be inside a git repo).
    complexity_map:
        Optional mapping of relative file path -> average complexity score.
        Used to weight hotspot_score. If None, score is based on change_count only.
    days:
        Number of days of history to analyze.

    Returns dict of relative_file_path -> FileHotspot.
    """
    if not _is_git_repo(root):
        return {}

    # Get commit log: hash, author email, date, and changed files
    log_output = _run_git(
        root,
        [
            "log",
            f"--since={days} days ago",
            "--format=COMMIT %H %ae %aI",
            "--name-only",
        ],
    )

    if not log_output.strip():
        return {}

    # Parse log output
    # file -> [{hash, author, date}]
    file_commits: dict[str, list[dict[str, str]]] = defaultdict(list)
    current_commit: dict[str, str] | None = None

    for line in log_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("COMMIT "):
            parts = line.split(" ", 3)
            if len(parts) >= 4:
                current_commit = {
                    "hash": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                }
            continue
        if current_commit and line and not line.startswith("COMMIT"):
            # This is a file path — only track Python files
            if line.endswith(".py"):
                file_commits[line].append(current_commit)

    # Also get recent (30 day) counts
    recent_output = _run_git(
        root,
        [
            "log",
            "--since=30 days ago",
            "--format=COMMIT",
            "--name-only",
        ],
    )
    recent_files: dict[str, int] = defaultdict(int)
    in_commit = False
    for line in recent_output.splitlines():
        line = line.strip()
        if line == "COMMIT":
            in_commit = True
            continue
        if in_commit and line and line.endswith(".py"):
            recent_files[line] += 1

    # Build hotspots
    max_changes = max(
        (len(commits) for commits in file_commits.values()), default=1
    )

    hotspots: dict[str, FileHotspot] = {}
    for file_path, commits in file_commits.items():
        # Count unique authors
        author_counts: dict[str, int] = defaultdict(int)
        for c in commits:
            author_counts[c["author"]] += 1
        top_authors = sorted(
            author_counts.keys(),
            key=lambda a: author_counts[a],
            reverse=True,
        )[:3]

        # Latest date
        last_date = max(c["date"] for c in commits) if commits else ""

        # Hotspot score: normalized change frequency * complexity
        freq_normalized = len(commits) / max_changes if max_changes > 0 else 0
        complexity = (
            complexity_map.get(file_path, 1.0) if complexity_map else 1.0
        )
        score = min(1.0, freq_normalized * complexity)

        hotspots[file_path] = FileHotspot(
            file_path=file_path,
            change_count=len(commits),
            recent_changes=recent_files.get(file_path, 0),
            top_contributors=tuple(top_authors),
            last_modified=last_date,
            churn_lines=0,  # approximate — could use --stat but adds complexity
            hotspot_score=score,
        )

    return hotspots


def analyze_co_changes(
    root: str,
    days: int = 90,
    min_count: int = 3,
    min_confidence: float = 0.3,
    max_pairs: int = 100,
) -> list[CoChangeEdge]:
    """Find files that frequently change together in the same commit.

    Returns list of CoChangeEdge sorted by co_change_count descending.
    """
    if not _is_git_repo(root):
        return []

    log_output = _run_git(
        root,
        [
            "log",
            f"--since={days} days ago",
            "--format=COMMIT",
            "--name-only",
        ],
    )

    if not log_output.strip():
        return []

    # Parse commits -> list of file sets
    commits_files: list[set[str]] = []
    current_files: set[str] = set()

    for line in log_output.splitlines():
        line = line.strip()
        if line == "COMMIT":
            if current_files:
                commits_files.append(current_files)
            current_files = set()
            continue
        if line and line.endswith(".py"):
            current_files.add(line)
    if current_files:
        commits_files.append(current_files)

    # Count per-file changes and co-changes
    file_change_count: dict[str, int] = defaultdict(int)
    pair_count: dict[tuple[str, str], int] = defaultdict(int)

    for files in commits_files:
        py_files = sorted(files)
        for f in py_files:
            file_change_count[f] += 1
        # Count pairs (O(n^2) per commit, but n is typically small)
        for i in range(len(py_files)):
            for j in range(i + 1, len(py_files)):
                pair_count[(py_files[i], py_files[j])] += 1

    # Filter and build edges
    edges: list[CoChangeEdge] = []
    for (fa, fb), count in pair_count.items():
        if count < min_count:
            continue
        min_changes = min(file_change_count[fa], file_change_count[fb])
        confidence = count / min_changes if min_changes > 0 else 0
        if confidence < min_confidence:
            continue
        edges.append(
            CoChangeEdge(
                file_a=fa,
                file_b=fb,
                co_change_count=count,
                confidence=round(confidence, 2),
            )
        )

    edges.sort(key=lambda e: e.co_change_count, reverse=True)
    return edges[:max_pairs]


def get_git_summary(root: str, days: int = 90) -> dict[str, Any]:
    """High-level git repository summary."""
    if not _is_git_repo(root):
        return {"is_git_repo": False}

    hotspots = analyze_hotspots(root, days=days)
    co_changes = analyze_co_changes(root, days=days)

    # Count unique authors
    all_authors: set[str] = set()
    for h in hotspots.values():
        all_authors.update(h.top_contributors)

    most_volatile = (
        max(hotspots.values(), key=lambda h: h.change_count).file_path
        if hotspots
        else ""
    )

    return {
        "is_git_repo": True,
        "days_analyzed": days,
        "files_with_history": len(hotspots),
        "active_contributors": len(all_authors),
        "most_volatile_file": most_volatile,
        "total_co_change_pairs": len(co_changes),
    }
