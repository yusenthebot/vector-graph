# vector-graph v0.3.0 Task List

## Execution Status
- Total tasks: 9
- Completed: 0
- In progress: 0
- Pending: 9

## Tasks

### Task 1: Protocol types + _types.py additions
- **Status**: [ ] pending
- **Agent**: alpha
- **Depends**: none
- **Input**: `_types.py`, all analysis/*.py files
- **Output**: `graph/protocols.py`, updated `_types.py`, updated analysis/ signatures
- **TDD Deliverables**:
  - RED: `tests/unit/test_protocols.py` — Protocol satisfaction, new type constructors
  - GREEN: `graph/protocols.py` with GraphProtocol; `_types.py` with TypeBinding, QueryResult; replace `graph: object` across analysis/
  - REFACTOR: ensure all existing tests pass
- **Acceptance Criteria**:
  - [ ] AC7: All `graph: object` params replaced with Protocol types
  - [ ] GraphProtocol defines: get_node, get_edges_from, get_edges_to, iter_nodes, iter_edges, node_count, edge_count
  - [ ] KnowledgeGraph structurally satisfies GraphProtocol (no explicit inheritance needed)
  - [ ] TypeBinding and QueryResult are frozen dataclasses
  - [ ] All 330 existing tests still pass
- **Verify**: `python3 -m pytest -q`

### Task 2: Caller index optimization
- **Status**: [ ] pending
- **Agent**: beta
- **Depends**: none
- **Input**: `analysis/call_graph.py`
- **Output**: Modified `call_graph.py` with index-based caller lookup
- **TDD Deliverables**:
  - RED: `tests/unit/test_call_graph.py` — add tests for `_build_caller_index`, index lookup, same-name-different-file
  - GREEN: `_build_caller_index()` function, replace `_find_caller_node_id` usage in `build_call_edges`
  - REFACTOR: remove `_find_caller_node_id` if fully replaced
- **Acceptance Criteria**:
  - [ ] AC3: Self-analysis call graph build time does not regress
  - [ ] `_find_caller_node_id` linear scan replaced with dict lookup
  - [ ] Same-name functions in different files resolve correctly
  - [ ] All existing call_graph tests pass
- **Verify**: `python3 -m pytest tests/unit/test_call_graph.py -q`

### Task 3: Type inference engine
- **Status**: [ ] pending
- **Agent**: gamma
- **Depends**: none
- **Input**: `_types.py` (TypeBinding from T1, but can use local definition initially), `parse/python_parser.py` output
- **Output**: `analysis/type_inference.py`
- **TDD Deliverables**:
  - RED: `tests/unit/test_type_inference.py` — all test contracts from spec (constructor, annotation, self.attr, parameter, multi-assign, scoped lookup)
  - GREEN: `TypeMap` class, `build_type_map()` function
  - REFACTOR: optimize lookup paths
- **Acceptance Criteria**:
  - [ ] AC1: `x = Foo()` correctly infers x -> Foo
  - [ ] AC2: `self.graph = KnowledgeGraph()` in __init__ infers self.graph -> KnowledgeGraph
  - [ ] Parameter annotations inferred
  - [ ] Last-assignment-wins semantics
  - [ ] TypeMap.lookup() and TypeMap.lookup_attribute() work correctly
- **Verify**: `python3 -m pytest tests/unit/test_type_inference.py -q`

### Task 4: Type-aware call resolution
- **Status**: [ ] pending
- **Agent**: alpha
- **Depends**: T1 (protocols), T2 (caller index), T3 (type inference)
- **Input**: Modified `call_graph.py` from T2, `TypeMap` from T3
- **Output**: Modified `call_graph.py` with typed attribute call resolution, modified `pipeline.py` with phase 3c
- **TDD Deliverables**:
  - RED: `tests/unit/test_call_graph.py` — add typed resolution tests (attribute call with typed receiver, self.method, self.attr.method, untyped fallback, confidence boost)
  - GREEN: `_resolve_typed_attribute_call()`, integrate TypeMap into `build_call_edges`, add phase 3c to pipeline
  - REFACTOR: clean up, verify self-analysis accuracy improvement
- **Acceptance Criteria**:
  - [ ] AC1: obj.method() with typed receiver resolves to correct class method
  - [ ] AC2: self.attr.method() where attr assigned in __init__ resolves correctly
  - [ ] AC10: GLOBAL-tier call edges decrease by >= 20% on self-analysis
  - [ ] Untyped calls fall back to existing behavior
  - [ ] Confidence boost to 0.95 for typed resolutions
- **Verify**: `python3 -m pytest tests/unit/test_call_graph.py tests/unit/test_pipeline.py -q`

### Task 5: Graph query API
- **Status**: [ ] pending
- **Agent**: beta
- **Depends**: T1 (protocols)
- **Input**: `graph/protocols.py`, `graph/knowledge_graph.py`
- **Output**: `analysis/query.py`, updated `api/python_api.py`
- **TDD Deliverables**:
  - RED: `tests/unit/test_query.py` — all 8 query types + unknown type error + empty results
  - GREEN: `execute_query()` with dispatch to per-type implementations, `CodeGraph.query()` method
  - REFACTOR: ensure consistent return format
- **Acceptance Criteria**:
  - [ ] AC4: All 8 query types work (callers_of, callees_of, subclasses_of, implementations_of, path_between, by_file, by_pattern, by_decorator)
  - [ ] Returns QueryResult with nodes and edges
  - [ ] path_between returns shortest path via BFS
  - [ ] by_pattern supports fnmatch glob
- **Verify**: `python3 -m pytest tests/unit/test_query.py -q`

### Task 6: Export (JSON + DOT)
- **Status**: [ ] pending
- **Agent**: gamma
- **Depends**: T1 (protocols)
- **Input**: `graph/protocols.py`
- **Output**: `analysis/export.py`, updated `api/python_api.py`
- **TDD Deliverables**:
  - RED: `tests/unit/test_export.py` — valid JSON, roundtrip, valid DOT, edge correctness
  - GREEN: `export_json()`, `export_dot()`, `CodeGraph.export()` method, `--export` CLI flag
  - REFACTOR: clean up
- **Acceptance Criteria**:
  - [ ] AC5: export("json") produces valid, re-importable JSON
  - [ ] DOT output has correct nodes and edges
  - [ ] CLI --export json and --export dot work
- **Verify**: `python3 -m pytest tests/unit/test_export.py -q`

### Task 7: Incremental pipeline (file watcher)
- **Status**: [ ] pending
- **Agent**: alpha
- **Depends**: T3 (type inference), T4 (type-aware calls)
- **Input**: `watch/file_watcher.py`, `pipeline.py`
- **Output**: Modified `file_watcher.py` with edge rebuild capability
- **TDD Deliverables**:
  - RED: `tests/unit/test_file_watcher.py` — add incremental edge rebuild tests (single file update, preserve other files, cross-file edges, delete, new file)
  - GREEN: `GraphWatcher._rebuild_edges()`, store ResolutionContext + TypeMap on watcher
  - REFACTOR: ensure thread safety
- **Acceptance Criteria**:
  - [ ] AC6: GraphWatcher triggers incremental edge rebuild on file change
  - [ ] Modified file nodes refreshed, other file nodes untouched
  - [ ] Cross-file edges rebuilt correctly
  - [ ] Incremental update < 500ms for single file
- **Verify**: `python3 -m pytest tests/unit/test_file_watcher.py -q`

### Task 8: Coverage hardening
- **Status**: [ ] pending
- **Agent**: beta
- **Depends**: T5 (query, for python_api coverage)
- **Input**: All api/ and ros2/ modules
- **Output**: New/expanded test files
- **TDD Deliverables**:
  - RED+GREEN: `tests/unit/test_visualize.py` (new), expand `test_web_api.py`, expand `test_mcp_server.py`, expand `test_ros2_graph.py`
  - Coverage: visualize 0%->60%, python_api 55%->75%, web_server 51%->65%, mcp 68%->75%, ros2_graph 72%->80%
- **Acceptance Criteria**:
  - [ ] AC8: Overall coverage >= 85%, no module below 60%
  - [ ] AC9: All existing tests pass
- **Verify**: `python3 -m pytest --cov=vector_graph --cov-report=term-missing -q`

### Task 9: Integration tests + final verification
- **Status**: [ ] pending
- **Agent**: gamma
- **Depends**: T4, T5, T6, T7, T8
- **Input**: Full codebase after all modifications
- **Output**: New integration tests, verified self-analysis metrics
- **TDD Deliverables**:
  - RED+GREEN: `tests/integration/test_self_analysis.py` — add tests for typed call accuracy, query API, export, coverage threshold
  - Verify AC10 (GLOBAL-tier edge reduction >= 20%)
  - Full test suite green
- **Acceptance Criteria**:
  - [ ] AC10: Self-analysis GLOBAL-tier call edges decrease >= 20%
  - [ ] All 10 acceptance criteria verified
  - [ ] Full suite passes: `python3 -m pytest -q`
- **Verify**: `python3 -m pytest -q && python3 -m pytest --cov=vector_graph -q`

## Dependency Graph

```
T1 (protocols) ──────> T4 (typed calls) ──> T7 (incremental) ──> T9 (integration)
T2 (caller idx) ─────> T4                                        T9
T3 (type infer) ─────> T4 ──────────────────────────────────────> T9
T1 ──────────────────> T5 (query) ─────> T8 (coverage) ────────> T9
T1 ──────────────────> T6 (export) ─────────────────────────────> T9
```

## Execution Waves

| Wave | Tasks | Agents | Gate |
|------|-------|--------|------|
| 1 | T1, T2, T3 | Alpha, Beta, Gamma | unit tests pass |
| 2 | T4, T5, T6 | Alpha, Beta, Gamma | unit tests pass |
| 3 | T7, T8 | Alpha, Beta | unit tests pass |
| 4 | T9 | Gamma | full suite + coverage |
| -- | review | code-reviewer | approve |
