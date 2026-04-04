# vector-graph v0.3.0 Specification — Full-Spectrum Upgrade

## 1. Overview

Upgrade vector-graph from v0.2.0-dev to v0.3.0 with six pillars: type inference for method resolution, caller index optimization, incremental pipeline, graph query API, export formats, and coverage hardening.

## 2. Background & Motivation

vector-graph v0.2.0-dev has a working 8-phase pipeline, 330 tests at 82% coverage, and a 3D web UI. But the **call graph is noisy**: `obj.method()` calls resolve by name only, producing false positives. The `_find_caller_node_id` function scans all nodes per call (O(N*M)). The file watcher exists but only does node-level incremental updates — no cross-file edge rebuilding. The query API is limited to 3 operations. Coverage has holes in api/ and ros2/. These issues compound: inaccurate call graph degrades impact analysis, communities, and execution flows.

## 3. Goals

### MUST (release blockers)

- M1: Intra-procedural type inference that propagates types through assignments (`x = Foo()` => x is `Foo`)
- M2: Attribute call resolution using inferred receiver types (`x.bar()` => `Foo.bar`)
- M3: Caller lookup index — O(1) per call instead of O(N) full-graph scan
- M4: Graph query API with at least: `find_by_pattern`, `path_between`, `find_callers`, `find_callees`, `find_subclasses`, `find_by_file`
- M5: Test coverage >= 85% overall, no module below 60%
- M6: All existing 330 tests continue to pass

### SHOULD (expected)

- S1: Incremental pipeline — file watcher triggers per-file re-parse + cross-file edge rebuild for changed files only
- S2: Export to JSON and DOT format
- S3: Pipeline performance: self-analysis < 5s (currently ~13s including test overhead, pipeline itself ~2s)
- S4: Protocol types for duck-typed `graph: object` parameters

### MAY (optional)

- Y1: Confidence boost — when type inference confirms a call target, boost confidence from 0.5/0.9 to 0.95
- Y2: `--export` CLI flag
- Y3: Scope-aware variable tracking (per-function variable map)

## 4. Non-Goals

- C++ / tree-sitter support (deferred to v0.4)
- Web UI improvements (deferred to v0.4)
- Inter-procedural type inference (call chain propagation) — too complex, intra-procedural is sufficient
- Full Python type checker (mypy-level) — we do best-effort, not sound analysis

## 5. User Scenarios

### Scenario 1: Accurate method call resolution
- **Actor**: Developer running `vector-graph ~/project --serve`
- **Trigger**: Graph displayed in web UI
- **Expected**: `self.graph.add_node(n)` in pipeline.py resolves to `KnowledgeGraph.add_node`, not to every function named `add_node` across the codebase
- **Success Criteria**: Method calls with typed receivers produce at most 2 candidates (down from N)

### Scenario 2: Query API via Python
- **Actor**: Developer using `CodeGraph` programmatically
- **Trigger**: `cg.query("callers_of", "add_node")`
- **Expected**: Returns list of all functions/methods that call `add_node` with file locations
- **Success Criteria**: Query returns correct, complete results matching manual inspection

### Scenario 3: Incremental update
- **Actor**: Developer editing a file while `GraphWatcher` is running
- **Trigger**: Save `pipeline.py`
- **Expected**: Only `pipeline.py` nodes are re-parsed; edges from/to pipeline.py nodes are rebuilt; other file nodes untouched
- **Success Criteria**: Incremental update completes in <500ms for a single file change

### Scenario 4: Export
- **Actor**: Developer running `vector-graph ~/project --export json`
- **Trigger**: CLI command
- **Expected**: JSON file with all nodes and edges written to stdout or file
- **Success Criteria**: Output is valid JSON, re-importable

## 6. Technical Constraints

- Runtime: Python 3.10+, stdlib ast only for parsing (no tree-sitter)
- Zero required dependencies (networkx, watchdog remain optional)
- Frozen dataclasses for all data types (existing pattern)
- No breaking changes to existing public API (`CodeGraph`, `run_pipeline`)
- Pipeline phases must remain composable and independently testable

## 7. Interface Definitions

### Python API (additions to `CodeGraph`)

```python
class CodeGraph:
    # Existing
    def analyze(self) -> AnalysisResult: ...
    def impact(self, target, direction, max_depth) -> ImpactResult: ...
    def trace(self, entry) -> list[ProcessTrace]: ...
    def orphans(self) -> list[GraphNode]: ...

    # New in v0.3.0
    def query(self, query_type: str, **kwargs) -> QueryResult: ...
    def export(self, format: str = "json") -> str: ...
```

### Query Types

| Query | Parameters | Returns |
|-------|-----------|---------|
| `callers_of` | `name: str` | All nodes that call `name` |
| `callees_of` | `name: str` | All nodes that `name` calls |
| `subclasses_of` | `name: str` | All classes extending `name` |
| `implementations_of` | `name: str` | Classes + methods that implement/override `name` |
| `path_between` | `source: str, target: str` | Shortest edge path between two named nodes |
| `by_file` | `file_path: str` | All nodes in a file |
| `by_pattern` | `pattern: str` | Nodes whose name matches glob/regex |
| `by_decorator` | `decorator: str` | All nodes decorated by `decorator` |

### New Data Types

```python
@dataclass(frozen=True)
class TypeBinding:
    """Inferred type for a variable in a scope."""
    variable_name: str
    inferred_type: str        # class name or module.class
    source_file: str
    scope: str                # function/method name, or "<module>"
    line: int
    confidence: float         # 0.0-1.0

@dataclass(frozen=True)
class QueryResult:
    """Result of a graph query."""
    query_type: str
    params: dict[str, str]
    nodes: tuple[GraphNode, ...]
    edges: tuple[Edge, ...]   # for path queries
    count: int
```

### Pipeline Phase Addition

```
Existing:  1-walk  2-parse  3-symbols  3b-heritage  4-imports  5-calls  6-communities  7-flows  8-ros2
New:       1-walk  2-parse  3-symbols  3b-heritage  3c-types   4-imports  5-calls*  6-communities  7-flows  8-ros2
                                                     ^^^^^^^^              ^^^^^^^
                                                     NEW phase             MODIFIED (uses type info)
```

Phase 3c: Type Inference
- Walk assignments in each function scope
- For `x = ClassName(...)` => bind x -> ClassName
- For `x = module.ClassName(...)` => bind x -> ClassName
- For `x: TypeAnnotation = ...` => bind x -> TypeAnnotation
- For `self.attr = ClassName(...)` => bind self.attr -> ClassName
- Store bindings in a new `TypeMap` structure, keyed by (file, scope, variable)

Phase 5 modification:
- When resolving `x.method()` calls, look up x's type in TypeMap
- If x has a known type T, restrict resolution to methods of T and its bases
- Boost confidence to 0.95 for type-confirmed resolutions

## 8. Test Contracts

### Unit Test Contracts — Type Inference

- [ ] `test_type_binding_from_constructor`: `x = Foo()` => TypeBinding(variable_name="x", inferred_type="Foo")
- [ ] `test_type_binding_from_annotation`: `x: Foo = ...` => TypeBinding with inferred_type="Foo"
- [ ] `test_type_binding_from_module_constructor`: `x = mod.Foo()` => inferred_type="Foo"
- [ ] `test_type_binding_self_attr`: `self.graph = KnowledgeGraph()` => binds self.graph -> KnowledgeGraph
- [ ] `test_type_binding_return_type`: function with `-> Foo` return type, `x = func()` => x is Foo
- [ ] `test_type_binding_parameter_annotation`: `def f(x: Foo)` => x is Foo within f's scope
- [ ] `test_type_binding_ignores_primitives`: `x = 42` => no type binding (or "int", not useful for method resolution)
- [ ] `test_type_binding_multi_assignment`: `x = Foo(); x = Bar()` => last assignment wins
- [ ] `test_type_map_lookup_scoped`: lookup in function scope, then module scope

### Unit Test Contracts — Call Resolution with Types

- [ ] `test_attribute_call_with_typed_receiver`: `x = Foo(); x.bar()` resolves to `Foo.bar` only
- [ ] `test_attribute_call_self_method`: `self.process()` in method of class C resolves to `C.process`
- [ ] `test_attribute_call_self_attr_method`: `self.graph.add_node()` where self.graph is KnowledgeGraph resolves to `KnowledgeGraph.add_node`
- [ ] `test_attribute_call_untyped_fallback`: `x.bar()` with no type info falls back to global name resolution (existing behavior)
- [ ] `test_confidence_boost_for_typed_resolution`: type-confirmed call has confidence >= 0.95

### Unit Test Contracts — Caller Index

- [ ] `test_caller_index_build`: index built from graph, lookup by (name, file) returns node_id in O(1)
- [ ] `test_caller_index_multiple_same_name`: two functions named "process" in different files resolve correctly
- [ ] `test_caller_index_empty_graph`: returns None for missing entries

### Unit Test Contracts — Query API

- [ ] `test_query_callers_of`: returns all direct callers of a named function
- [ ] `test_query_callees_of`: returns all direct callees
- [ ] `test_query_subclasses_of`: returns all classes with EXTENDS edge to target
- [ ] `test_query_path_between`: returns shortest path between two nodes (BFS)
- [ ] `test_query_path_between_no_path`: returns empty when no path exists
- [ ] `test_query_by_file`: returns all nodes in a specific file
- [ ] `test_query_by_pattern`: glob match on node names
- [ ] `test_query_by_decorator`: finds all nodes with a specific decorator
- [ ] `test_query_unknown_type`: returns error/empty for unknown query_type

### Unit Test Contracts — Export

- [ ] `test_export_json_valid`: export produces valid JSON with nodes and edges arrays
- [ ] `test_export_json_roundtrip`: exported JSON can be loaded and node/edge counts match
- [ ] `test_export_dot_valid`: export produces valid DOT graph syntax
- [ ] `test_export_dot_edges`: DOT output contains correct edge relationships

### Unit Test Contracts — Incremental Pipeline

- [ ] `test_incremental_single_file_update`: modify one file, only that file's nodes are refreshed
- [ ] `test_incremental_preserves_other_files`: nodes from untouched files remain unchanged
- [ ] `test_incremental_rebuilds_cross_file_edges`: edges from modified file to other files are rebuilt
- [ ] `test_incremental_handles_delete`: deleted file's nodes and edges are removed
- [ ] `test_incremental_handles_new_file`: new file is parsed and integrated

### Unit Test Contracts — Protocol Types

- [ ] `test_graph_protocol_type_check`: KnowledgeGraph satisfies GraphProtocol at type-check time
- [ ] `test_resolution_protocol`: ResolutionContext satisfies ResolutionProtocol

### Integration Test Contracts

- [ ] `test_self_analysis_typed_calls_reduce_candidates`: self-analysis produces fewer GLOBAL-tier call edges than v0.2
- [ ] `test_self_analysis_query_callers_of_add_node`: query("callers_of", name="add_node") returns pipeline functions
- [ ] `test_self_analysis_export_json`: self-analysis exports valid JSON
- [ ] `test_self_analysis_coverage_above_85`: overall coverage >= 85%

## 9. Acceptance Criteria

- [ ] AC1: `obj.method()` calls with constructor-inferred receiver types resolve to correct class methods
- [ ] AC2: `self.attr.method()` calls where attr is assigned in `__init__` resolve correctly
- [ ] AC3: Call graph build time for self-analysis does not regress (stays under 3s)
- [ ] AC4: `CodeGraph.query()` supports all 8 query types from the table
- [ ] AC5: `CodeGraph.export("json")` produces valid, re-importable JSON
- [ ] AC6: `GraphWatcher` triggers incremental edge rebuild on file change
- [ ] AC7: All duck-typed `graph: object` parameters replaced with Protocol types
- [ ] AC8: Test coverage >= 85% overall, no module below 60%
- [ ] AC9: All 330 existing tests pass without modification
- [ ] AC10: Self-analysis call edge count with GLOBAL tier decreases by >= 20% (accuracy improvement)

## 10. Open Questions

None — all design decisions can be made by the Architect during planning.
