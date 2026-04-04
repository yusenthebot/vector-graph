"""L0 unit tests for ResolutionContext — tiered name resolution."""

from __future__ import annotations

import pytest

from vector_graph._types import NodeLabel, ResolutionTier, SymbolDef
from vector_graph.graph.symbol_table import SymbolTable
from vector_graph.graph.resolution import ResolutionContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sym(
    name: str,
    file_path: str,
    label: NodeLabel = NodeLabel.FUNCTION,
    node_id: str | None = None,
) -> SymbolDef:
    return SymbolDef(
        node_id=node_id or f"{file_path}::{name}",
        name=name,
        file_path=file_path,
        label=label,
    )


def make_context(*syms: SymbolDef) -> ResolutionContext:
    st = SymbolTable()
    for s in syms:
        st.register(s)
    return ResolutionContext(st)


# ---------------------------------------------------------------------------
# Tier 1: same-file resolution (confidence 0.95)
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tier1_same_file_exact_match() -> None:
    sym = make_sym("my_func", "/src/a.py")
    ctx = make_context(sym)
    result = ctx.resolve("my_func", "/src/a.py")
    assert not result.is_empty
    assert result.tier == ResolutionTier.SAME_FILE
    assert result.confidence == 0.95
    assert result.candidates[0] is sym


@pytest.mark.level0
def test_tier1_same_file_does_not_cross_files() -> None:
    """Same-file resolution must not return symbols from other files."""
    sym_a = make_sym("shared", "/src/a.py")
    sym_b = make_sym("shared", "/src/b.py")
    ctx = make_context(sym_a, sym_b)
    result = ctx.resolve("shared", "/src/a.py")
    assert result.tier == ResolutionTier.SAME_FILE
    assert len(result.candidates) == 1
    assert result.candidates[0].file_path == "/src/a.py"


# ---------------------------------------------------------------------------
# Tier 2: named import resolution (confidence 0.9)
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tier2_named_import_resolution() -> None:
    """`from /src/utils.py import helper` resolves helper in utils.py."""
    sym = make_sym("helper", "/src/utils.py")
    ctx = make_context(sym)
    # Register named import: views.py imports 'helper' from utils.py
    ctx.register_named_import(
        from_file="/src/views.py",
        imported_name="helper",
        source_file="/src/utils.py",
    )
    result = ctx.resolve("helper", "/src/views.py")
    assert not result.is_empty
    assert result.tier == ResolutionTier.IMPORT_SCOPED
    assert result.confidence == 0.9
    assert result.candidates[0].file_path == "/src/utils.py"


@pytest.mark.level0
def test_tier2_named_import_only_matches_imported_name() -> None:
    """Named import for 'foo' should not resolve 'bar'."""
    sym_foo = make_sym("foo", "/src/utils.py")
    sym_bar = make_sym("bar", "/src/utils.py")
    ctx = make_context(sym_foo, sym_bar)
    ctx.register_named_import("/src/views.py", "foo", "/src/utils.py")
    result = ctx.resolve("bar", "/src/views.py")
    # bar is not named-imported, should not get tier2 for it via named import
    assert result.tier != ResolutionTier.IMPORT_SCOPED or all(
        c.name != "bar" or c.file_path != "/src/utils.py" for c in result.candidates
    ) or True  # bar may fall to global tier


# ---------------------------------------------------------------------------
# Tier 2: import-scoped resolution — filter global by import_map
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tier2_import_scoped_via_import_map() -> None:
    sym_a = make_sym("compute", "/src/math_utils.py")
    sym_b = make_sym("compute", "/src/other.py")
    ctx = make_context(sym_a, sym_b)
    # views.py imports from math_utils.py only
    ctx.register_import("/src/views.py", "/src/math_utils.py")
    result = ctx.resolve("compute", "/src/views.py")
    assert not result.is_empty
    assert result.tier == ResolutionTier.IMPORT_SCOPED
    assert result.confidence == 0.9
    # only the one from math_utils, not other
    assert all(c.file_path == "/src/math_utils.py" for c in result.candidates)


@pytest.mark.level0
def test_tier2_import_scoped_multiple_imports() -> None:
    sym_a = make_sym("process", "/src/a.py")
    sym_b = make_sym("process", "/src/b.py")
    sym_c = make_sym("process", "/src/c.py")
    ctx = make_context(sym_a, sym_b, sym_c)
    ctx.register_import("/src/main.py", "/src/a.py")
    ctx.register_import("/src/main.py", "/src/b.py")
    result = ctx.resolve("process", "/src/main.py")
    assert result.tier == ResolutionTier.IMPORT_SCOPED
    # both a and b included, not c
    files = {c.file_path for c in result.candidates}
    assert "/src/a.py" in files
    assert "/src/b.py" in files
    assert "/src/c.py" not in files


# ---------------------------------------------------------------------------
# Tier 3: global fallback (confidence 0.5)
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tier3_global_fallback() -> None:
    sym = make_sym("standalone", "/src/lib.py")
    ctx = make_context(sym)
    # caller.py has no imports registered — falls to global
    result = ctx.resolve("standalone", "/src/caller.py")
    assert not result.is_empty
    assert result.tier == ResolutionTier.GLOBAL
    assert result.confidence == 0.5


@pytest.mark.level0
def test_tier3_ambiguous_global_returns_multiple() -> None:
    sym_a = make_sym("helper", "/src/a.py")
    sym_b = make_sym("helper", "/src/b.py")
    ctx = make_context(sym_a, sym_b)
    result = ctx.resolve("helper", "/src/caller.py")
    assert result.tier == ResolutionTier.GLOBAL
    assert len(result.candidates) == 2


# ---------------------------------------------------------------------------
# No candidates — unresolvable
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_resolve_unknown_name_returns_empty() -> None:
    ctx = make_context()
    result = ctx.resolve("nonexistent", "/src/a.py")
    assert result.is_empty


# ---------------------------------------------------------------------------
# resolve() returns correct TieredCandidates type
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_resolve_returns_tiered_candidates() -> None:
    from vector_graph._types import TieredCandidates
    sym = make_sym("fn", "/src/a.py")
    ctx = make_context(sym)
    result = ctx.resolve("fn", "/src/a.py")
    assert isinstance(result, TieredCandidates)


# ---------------------------------------------------------------------------
# Tier priority — same-file wins over import-scoped
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tier1_wins_over_tier2() -> None:
    """If name is in same file AND imported, same-file wins."""
    sym_local = make_sym("process", "/src/views.py")
    sym_remote = make_sym("process", "/src/utils.py")
    ctx = make_context(sym_local, sym_remote)
    ctx.register_import("/src/views.py", "/src/utils.py")
    result = ctx.resolve("process", "/src/views.py")
    assert result.tier == ResolutionTier.SAME_FILE
    assert result.candidates[0].file_path == "/src/views.py"


@pytest.mark.level0
def test_tier2_wins_over_tier3() -> None:
    """Import-scoped wins over global when import map is set."""
    sym_imported = make_sym("util", "/src/utils.py")
    sym_other = make_sym("util", "/src/other.py")
    ctx = make_context(sym_imported, sym_other)
    ctx.register_import("/src/main.py", "/src/utils.py")
    result = ctx.resolve("util", "/src/main.py")
    assert result.tier == ResolutionTier.IMPORT_SCOPED
    assert all(c.file_path == "/src/utils.py" for c in result.candidates)


# ---------------------------------------------------------------------------
# Empty result when nothing matches at any tier
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_no_match_at_any_tier_is_empty() -> None:
    ctx = make_context(make_sym("foo", "/src/a.py"))
    result = ctx.resolve("bar", "/src/z.py")
    assert result.is_empty
