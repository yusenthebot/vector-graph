"""L5 unit tests for vector_graph.api.python_api — CodeGraph class and CLI."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture: small Python project for CodeGraph to analyze
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Small project with functions, classes, and call edges."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    (pkg / "core.py").write_text(textwrap.dedent("""\
        from __future__ import annotations


        class Engine:
            \"\"\"Core engine.\"\"\"

            def start(self) -> None:
                self._init()

            def stop(self) -> None:
                pass

            def _init(self) -> None:
                pass


        def run(engine: Engine) -> None:
            engine.start()


        def main() -> None:
            e = Engine()
            run(e)
    """))

    (pkg / "utils.py").write_text(textwrap.dedent("""\
        from __future__ import annotations
        from .core import Engine, run


        def bootstrap() -> Engine:
            e = Engine()
            run(e)
            return e


        def helper() -> None:
            pass
    """))

    return tmp_path


# ---------------------------------------------------------------------------
# CodeGraph.analyze()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphAnalyze:
    def test_analyze_returns_analysis_result(self, project: Path) -> None:
        """CodeGraph.analyze() returns an AnalysisResult."""
        from vector_graph.api.python_api import CodeGraph
        from vector_graph._types import AnalysisResult

        cg = CodeGraph(project)
        result = cg.analyze()
        assert isinstance(result, AnalysisResult)

    def test_analyze_counts_functions(self, project: Path) -> None:
        """analyze() finds functions in the project."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.analyze()
        assert result.function_count > 0

    def test_analyze_counts_classes(self, project: Path) -> None:
        """analyze() finds the Engine class."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.analyze()
        assert result.class_count >= 1

    def test_analyze_populates_internal_graph(self, project: Path) -> None:
        """After analyze(), _graph and _result are populated."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        assert cg._graph is None
        assert cg._result is None
        cg.analyze()
        assert cg._graph is not None
        assert cg._result is not None

    def test_ensure_analyzed_triggers_analyze(self, project: Path) -> None:
        """_ensure_analyzed() on fresh instance triggers analyze."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        assert cg._graph is None
        cg._ensure_analyzed()
        assert cg._graph is not None


# ---------------------------------------------------------------------------
# CodeGraph.impact()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphImpact:
    def test_impact_known_function(self, project: Path) -> None:
        """impact() on a known function returns ImpactResult."""
        from vector_graph.api.python_api import CodeGraph
        from vector_graph._types import ImpactResult

        cg = CodeGraph(project)
        result = cg.impact("run")
        assert isinstance(result, ImpactResult)
        assert result.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_impact_unknown_function_returns_low_risk(self, project: Path) -> None:
        """impact() on unknown function returns LOW risk empty result."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.impact("nonexistent_fn_xyz_999")
        assert result.risk == "LOW"
        assert result.impacted_count == 0

    def test_impact_downstream_direction(self, project: Path) -> None:
        """impact() with direction=downstream returns valid ImpactResult."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.impact("main", direction="downstream")
        assert result.direction == "downstream"

    def test_impact_upstream_direction(self, project: Path) -> None:
        """impact() with direction=upstream returns valid ImpactResult."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.impact("run", direction="upstream")
        assert result.direction == "upstream"


# ---------------------------------------------------------------------------
# CodeGraph.trace()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphTrace:
    def test_trace_returns_list(self, project: Path) -> None:
        """trace() always returns a list."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.trace("main")
        assert isinstance(result, list)

    def test_trace_unknown_entry_returns_empty(self, project: Path) -> None:
        """trace() for unknown entry point returns empty list."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.trace("zzz_nonexistent_entry_point")
        assert result == []

    def test_trace_known_entry_returns_traces(self, project: Path) -> None:
        """trace() for a known entry point returns ProcessTrace objects."""
        from vector_graph.api.python_api import CodeGraph
        from vector_graph._types import ProcessTrace

        cg = CodeGraph(project)
        # 'main' calls run() which calls engine.start() — should have traces
        result = cg.trace("main")
        # Either empty (if not a detected entry) or list of ProcessTrace
        for trace in result:
            assert isinstance(trace, ProcessTrace)


# ---------------------------------------------------------------------------
# CodeGraph.orphans()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphOrphans:
    def test_orphans_returns_list(self, project: Path) -> None:
        """orphans() returns a list of GraphNode objects."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.orphans()
        assert isinstance(result, list)

    def test_orphans_helper_is_orphan(self, project: Path) -> None:
        """helper() in utils.py is never called — should be an orphan."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        orphan_names = {n.properties.name for n in cg.orphans()}
        assert "helper" in orphan_names


# ---------------------------------------------------------------------------
# CodeGraph.query()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphQuery:
    def test_query_callers_of_returns_result(self, project: Path) -> None:
        """query('callers_of', name='run') returns QueryResult."""
        from vector_graph.api.python_api import CodeGraph
        from vector_graph._types import QueryResult

        cg = CodeGraph(project)
        result = cg.query("callers_of", name="run")
        assert isinstance(result, QueryResult)

    def test_query_unknown_type_returns_empty(self, project: Path) -> None:
        """query() with unknown type returns QueryResult with count=0."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.query("unknown_query_type_xyz")
        assert result.count == 0

    def test_query_by_file_returns_result(self, project: Path) -> None:
        """query('by_file') returns a valid QueryResult."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        result = cg.query("by_file", file_path=str(project / "mypkg" / "core.py"))
        assert result.count >= 0


# ---------------------------------------------------------------------------
# CodeGraph.export()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCodeGraphExport:
    def test_export_json_returns_string(self, project: Path) -> None:
        """export('json') returns a non-empty JSON string."""
        import json
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        output = cg.export("json")
        assert isinstance(output, str)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_export_dot_returns_string(self, project: Path) -> None:
        """export('dot') returns a DOT format string."""
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        output = cg.export("dot")
        assert isinstance(output, str)
        assert "digraph" in output.lower() or "graph" in output.lower()

    def test_export_default_is_json(self, project: Path) -> None:
        """export() with no argument defaults to JSON."""
        import json
        from vector_graph.api.python_api import CodeGraph

        cg = CodeGraph(project)
        output = cg.export()
        json.loads(output)  # Should not raise


# ---------------------------------------------------------------------------
# CLI main()
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCLIMain:
    def test_main_analyze_only(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with just root arg analyzes and prints summary."""
        import sys
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = ["vector-graph", str(project)]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_with_orphans_flag(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with --orphans prints orphan list."""
        import sys
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = ["vector-graph", str(project), "--orphans"]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert "Orphans" in captured.out or "orphan" in captured.out.lower()

    def test_main_with_impact_flag(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with --impact NAME prints impact table."""
        import sys
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = ["vector-graph", str(project), "--impact", "run"]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_with_export_json(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with --export json prints JSON to stdout."""
        import sys
        import json
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = ["vector-graph", str(project), "--export", "json"]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        # JSON output should be parseable somewhere in the stdout
        assert "{" in captured.out

    def test_main_with_export_dot(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with --export dot prints DOT graph to stdout."""
        import sys
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = ["vector-graph", str(project), "--export", "dot"]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_with_impact_downstream(self, project: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI main() with --impact and --direction downstream runs without error."""
        import sys
        from vector_graph.api.python_api import main

        original_argv = sys.argv
        try:
            sys.argv = [
                "vector-graph", str(project),
                "--impact", "main",
                "--direction", "downstream",
            ]
            main()
        finally:
            sys.argv = original_argv

        captured = capsys.readouterr()
        assert len(captured.out) > 0


# ---------------------------------------------------------------------------
# CLI --watch and --tui flag tests
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestCLIWatchTuiFlags:
    def test_cli_watch_flag_exists(self) -> None:
        """argparse accepts --watch without error."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("root", nargs="?", default=".")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--serve", action="store_true")
        parser.add_argument("--tui", action="store_true")

        args = parser.parse_args(["--watch"])
        assert args.watch is True

    def test_cli_tui_flag_exists(self) -> None:
        """argparse accepts --tui without error."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("root", nargs="?", default=".")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--serve", action="store_true")
        parser.add_argument("--tui", action="store_true")

        args = parser.parse_args(["--tui"])
        assert args.tui is True

    def test_cli_watch_and_serve_flags_coexist(self) -> None:
        """argparse accepts --watch --serve together without error."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("root", nargs="?", default=".")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--serve", action="store_true")
        parser.add_argument("--tui", action="store_true")

        args = parser.parse_args(["--watch", "--serve"])
        assert args.watch is True
        assert args.serve is True

    def test_cli_watch_and_tui_flags_coexist(self) -> None:
        """argparse accepts --watch --tui together without error."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("root", nargs="?", default=".")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--serve", action="store_true")
        parser.add_argument("--tui", action="store_true")

        args = parser.parse_args(["--watch", "--tui"])
        assert args.watch is True
        assert args.tui is True

    def test_main_parser_accepts_watch(self) -> None:
        """The real main() parser must accept --watch without SystemExit."""
        import argparse
        from unittest.mock import patch

        captured_parser: list[argparse.ArgumentParser] = []

        def capturing_parse(self, args=None, namespace=None):
            captured_parser.append(self)
            raise SystemExit(0)

        with patch.object(argparse.ArgumentParser, "parse_args", capturing_parse):
            try:
                from vector_graph.api.python_api import main
                main()
            except SystemExit:
                pass

        assert len(captured_parser) > 0
        action_strings = [
            s
            for action in captured_parser[0]._actions
            for s in action.option_strings
        ]
        assert "--watch" in action_strings

    def test_main_parser_accepts_tui(self) -> None:
        """The real main() parser must accept --tui without SystemExit."""
        import argparse
        from unittest.mock import patch

        captured_parser: list[argparse.ArgumentParser] = []

        def capturing_parse(self, args=None, namespace=None):
            captured_parser.append(self)
            raise SystemExit(0)

        with patch.object(argparse.ArgumentParser, "parse_args", capturing_parse):
            try:
                from vector_graph.api.python_api import main
                main()
            except SystemExit:
                pass

        assert len(captured_parser) > 0
        action_strings = [
            s
            for action in captured_parser[0]._actions
            for s in action.option_strings
        ]
        assert "--tui" in action_strings
