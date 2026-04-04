# vector-graph v0.3.0 Technical Plan

## 1. Architecture Overview

Six workstreams mapped to the existing module structure. No new top-level packages — all additions go into existing directories.

```
vector_graph/
├── _types.py            # + TypeBinding, QueryResult, GraphProtocol, ExportFormat
├── graph/
│   ├── knowledge_graph.py  # + satisfies GraphProtocol
│   ├── symbol_table.py     # + caller_index (name,file -> node_id)
│   ├── resolution.py       # unchanged
│   └── protocols.py        # NEW: Protocol definitions
├── parse/
│   ├── python_parser.py    # unchanged
│   ├── python_imports.py   # unchanged
│   └── python_types.py     # unchanged
├── analysis/
│   ├── type_inference.py   # NEW: intra-procedural type propagation
│   ├── call_graph.py       # MODIFIED: type-aware resolution + caller index
│   ├── query.py            # NEW: 8 query types
│   ├── impact.py           # MODIFIED: use Protocol
│   ├── community.py        # MODIFIED: use Protocol
│   ├── execution_flow.py   # MODIFIED: use Protocol
│   ├── orphan.py           # MODIFIED: use Protocol
│   └── export.py           # NEW: JSON + DOT export
├── watch/
│   └── file_watcher.py     # MODIFIED: incremental edge rebuild
├── api/
│   ├── python_api.py       # MODIFIED: + query(), export()
│   ├── web_server.py       # coverage tests added
│   ├── mcp_server.py       # coverage tests added
│   └── visualize.py        # coverage tests added
├── ros2/                   # coverage tests added
└── pipeline.py             # MODIFIED: + phase 3c, caller index
```

## 2. Technical Decisions

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Type inference | Intra-procedural, assignment-based | Covers constructor calls, annotations, self.attr — 80%+ of real cases. Simple, fast, no fixpoint iteration |
| Caller index | dict[(name, file_path)] -> node_id built during phase 3 | Eliminates O(N) scan per call in phase 5. Key is (name, file) to handle same-name functions |
| Protocol types | `typing.Protocol` in `graph/protocols.py` | Replaces `object` annotations, enables static type checking, IDE autocomplete |
| Query engine | Single `execute_query()` dispatch function | Uniform interface, easy to add new query types, maps directly to MCP tools |
| Export | Pure functions, no state | `export_json(graph)` and `export_dot(graph)` — stateless transforms |
| Incremental edges | file_watcher calls `_rebuild_edges_for_file()` | Removes edges from/to file nodes, re-runs import resolution + call graph for that file only |

## 3. Module Design

### Module A: `graph/protocols.py` (NEW)

**Responsibility**: Protocol definitions for duck-typed graph interfaces.

```python
from typing import Protocol, Iterator

class GraphProtocol(Protocol):
    def get_node(self, node_id: str) -> GraphNode | None: ...
    def get_edges_from(self, source_id: str) -> Iterator[Edge]: ...
    def get_edges_to(self, target_id: str) -> Iterator[Edge]: ...
    def iter_nodes(self) -> Iterator[GraphNode]: ...
    def iter_edges(self) -> Iterator[Edge]: ...
    @property
    def node_count(self) -> int: ...
    @property
    def edge_count(self) -> int: ...
```

All `graph: object` params in analysis/, api/ become `graph: GraphProtocol`.

### Module B: `analysis/type_inference.py` (NEW)

**Responsibility**: Infer variable types within function scopes from assignments and annotations.

**Input**: `dict[str, FileParseResult]` (from phase 2)
**Output**: `TypeMap` — a lookup structure `(file, scope, variable) -> TypeBinding`

```python
class TypeMap:
    """Immutable type binding map built by phase 3c."""

    def lookup(self, file_path: str, scope: str, variable: str) -> TypeBinding | None:
        """Look up inferred type for a variable in a scope."""

    def lookup_attribute(self, file_path: str, scope: str, receiver: str) -> str | None:
        """Resolve receiver.attr chain. E.g., 'self.graph' -> 'KnowledgeGraph'."""

def build_type_map(
    parse_results: dict[str, FileParseResult],
    symbol_table: SymbolTable,
) -> TypeMap:
    """Phase 3c: build intra-procedural type map."""
```

**Algorithm**:
1. For each file, for each function/method body:
   - Walk assignments: `x = Foo()` => bind x -> "Foo" (confidence 0.9)
   - Walk annotations: `x: Foo` => bind x -> "Foo" (confidence 0.95)
   - Walk parameters: `def f(x: Foo)` => bind x -> "Foo" (confidence 0.95)
   - Walk `self.attr = Foo()` in `__init__` => bind (class_name, "self.attr") -> "Foo"
2. For constructor calls, verify `Foo` exists in symbol_table as a CLASS
3. Last assignment wins (simple overwrite, no merge)

### Module C: `analysis/call_graph.py` (MODIFIED)

**Changes**:
1. Accept `TypeMap` as optional parameter
2. Build caller index at start: `dict[(name, file_path)] -> node_id`
3. For attribute calls (`x.method()`):
   - Look up receiver type in TypeMap
   - If found, resolve `method` within that class and its bases
   - Boost confidence to 0.95
   - If not found, fall back to existing global name resolution

```python
def build_call_edges(
    graph: GraphProtocol,
    parse_results: dict[str, FileParseResult],
    resolution: object,
    type_map: TypeMap | None = None,   # NEW
) -> list[Edge]:
```

**Caller index** replaces `_find_caller_node_id`:

```python
def _build_caller_index(graph: GraphProtocol) -> dict[tuple[str, str], str]:
    """(name, file_path) -> node_id for all Function/Method nodes."""
    index = {}
    for node in graph.iter_nodes():
        if node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD):
            key = (node.properties.name, node.properties.file_path)
            index[key] = node.id
    return index
```

### Module D: `analysis/query.py` (NEW)

**Responsibility**: Execute structured queries against the graph.

```python
def execute_query(
    graph: GraphProtocol,
    query_type: str,
    **kwargs,
) -> QueryResult:
```

**Query implementations** — each is a pure function:

| Query | Algorithm |
|-------|-----------|
| `callers_of(name)` | Find node by name -> get_edges_to -> filter CALLS -> return source nodes |
| `callees_of(name)` | Find node by name -> get_edges_from -> filter CALLS -> return target nodes |
| `subclasses_of(name)` | Find class node -> get_edges_to -> filter EXTENDS -> return source nodes |
| `path_between(src, tgt)` | BFS from src to tgt using all edge types, return shortest path |
| `by_file(path)` | get_nodes_by_file (already indexed) |
| `by_pattern(pat)` | Iterate nodes, fnmatch on name |
| `by_decorator(dec)` | Iterate nodes, check decorators tuple |

### Module E: `analysis/export.py` (NEW)

**Responsibility**: Serialize graph to JSON and DOT formats.

```python
def export_json(graph: GraphProtocol) -> str:
    """Full graph as JSON: {"nodes": [...], "edges": [...]}"""

def export_dot(graph: GraphProtocol) -> str:
    """Graph as DOT: digraph G { node_id [label="name"]; src -> tgt; }"""
```

### Module F: `watch/file_watcher.py` (MODIFIED)

**Changes**: After re-parsing a file, rebuild cross-file edges:
1. Remove all edges where source or target belongs to the changed file
2. Re-run import resolution for the changed file
3. Re-run call graph for calls originating from the changed file
4. Re-run call graph for calls targeting symbols in the changed file

New method: `GraphWatcher._rebuild_edges(file_path)` called after `_register_file_in_graph`.

Requires storing `ResolutionContext` and `TypeMap` on the watcher for incremental use.

### Module G: Coverage hardening

No new modules — add test files:
- `tests/unit/test_visualize.py` — test `print_summary`, `print_impact`
- `tests/unit/test_web_api.py` — already exists, expand to cover build_graph_data edge cases, build_source_response
- `tests/unit/test_mcp_server.py` — already exists, expand to cover MCP stdio transport mock
- `tests/unit/test_ros2_graph.py` — already exists, expand to cover overlay builder edge cases

## 4. Data Flow

```
Phase 1: walk filesystem          -> file_paths: list[str]
Phase 2: parse files              -> parse_results: dict[str, FileParseResult]
Phase 3: register symbols         -> graph (nodes), symbol_table
Phase 3b: resolve heritage        -> graph (EXTENDS, DECORATES edges)
Phase 3c: infer types (NEW)       -> type_map: TypeMap
Phase 4: resolve imports          -> graph (IMPORTS edges), resolution_context
Phase 5: build call edges (MOD)   -> graph (CALLS edges) — uses type_map + caller_index
Phase 6: detect communities       -> communities: list[CommunityInfo]
Phase 7: detect execution flows   -> flows: list[ProcessTrace]
Phase 8: ROS2 extraction          -> graph (ROS2 overlay)
```

## 5. Directory Structure

New files only:

```
vector_graph/
├── graph/
│   └── protocols.py          # NEW
├── analysis/
│   ├── type_inference.py     # NEW
│   ├── query.py              # NEW
│   └── export.py             # NEW
tests/
├── unit/
│   ├── test_type_inference.py  # NEW
│   ├── test_query.py           # NEW
│   ├── test_export.py          # NEW
│   ├── test_protocols.py       # NEW
│   └── test_visualize.py       # NEW
```

## 6. Key Implementation Details

### Type Inference Algorithm

```python
def _infer_scope_types(
    file_path: str,
    scope_name: str,  # function name or "<module>"
    assignments: list[ExtractedAssignment],
    calls: list[ExtractedCall],
    functions: list[ExtractedFunction],
    symbol_table: SymbolTable,
) -> list[TypeBinding]:
    bindings = []

    # 1. Annotated assignments: x: Foo = ...
    for assign in assignments:
        if assign.declared_type:
            bindings.append(TypeBinding(
                variable_name=assign.name,
                inferred_type=assign.declared_type,
                source_file=file_path,
                scope=scope_name,
                line=assign.line,
                confidence=0.95,
            ))

    # 2. Constructor calls: x = Foo(...)
    for assign in assignments:
        if assign.value_type and not assign.declared_type:
            # Check if value_type is a known class
            if symbol_table.lookup_global(assign.value_type):
                bindings.append(TypeBinding(
                    variable_name=assign.name,
                    inferred_type=assign.value_type,
                    source_file=file_path,
                    scope=scope_name,
                    line=assign.line,
                    confidence=0.9,
                ))

    # 3. Function parameter annotations
    for fn in functions:
        if fn.name == scope_name:
            for param, ptype in zip(fn.parameters, fn.parameter_types):
                if ptype:
                    bindings.append(TypeBinding(
                        variable_name=param,
                        inferred_type=ptype,
                        source_file=file_path,
                        scope=scope_name,
                        line=fn.start_line,
                        confidence=0.95,
                    ))

    return bindings
```

### Caller Index

Replace in `call_graph.py`:

```python
# BEFORE (O(N) per call):
def _find_caller_node_id(graph, caller_name, file_path):
    for node in graph.iter_nodes():
        if node.label in (...) and node.properties.name == caller_name and ...:
            return node.id

# AFTER (O(1) per call):
caller_index = _build_caller_index(graph)  # built once
caller_id = caller_index.get((call.caller_name, call.file_path))
```

### Type-Aware Call Resolution

```python
def _resolve_typed_attribute_call(
    call: ExtractedCall,
    type_map: TypeMap,
    symbol_table: SymbolTable,
    graph: GraphProtocol,
) -> tuple[list[SymbolDef], float] | None:
    """Resolve obj.method() using receiver type info."""
    if not call.is_attribute or not call.receiver:
        return None

    # Look up receiver type
    scope = call.caller_name or "<module>"
    receiver_type = type_map.lookup_attribute(
        call.file_path, scope, call.receiver
    )
    if receiver_type is None:
        return None

    # Find methods named call.callee_name on receiver_type and its bases
    candidates = _find_methods_on_class(
        receiver_type, call.callee_name, symbol_table, graph
    )
    if candidates:
        return candidates, 0.95  # high confidence
    return None
```

## 7. Test Strategy

### TDD execution basis

| Layer | Scope | Count (est.) |
|-------|-------|-------------|
| Unit — type_inference | TypeBinding, TypeMap, inference logic | ~15 |
| Unit — call_graph | Caller index, typed resolution | ~8 |
| Unit — query | 8 query types + error cases | ~12 |
| Unit — export | JSON + DOT output | ~6 |
| Unit — protocols | Protocol satisfaction checks | ~3 |
| Unit — coverage gaps | visualize, web_server, mcp, ros2 | ~20 |
| Integration | Self-analysis accuracy, query, export | ~6 |
| **Total new tests** | | **~70** |
| **Total after** | 330 + ~70 | **~400** |

### Coverage Targets

| Module | Current | Target |
|--------|---------|--------|
| analysis/type_inference.py | N/A (new) | >= 90% |
| analysis/query.py | N/A (new) | >= 90% |
| analysis/export.py | N/A (new) | >= 90% |
| analysis/call_graph.py | 96% | >= 95% |
| api/visualize.py | 0% | >= 60% |
| api/python_api.py | 55% | >= 75% |
| api/web_server.py | 51% | >= 65% |
| api/mcp_server.py | 68% | >= 75% |
| ros2/ros2_graph.py | 72% | >= 80% |
| **Overall** | 82.38% | **>= 85%** |

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Type inference adds latency | Pipeline slowdown on large codebases | Caller index saves more than type inference costs; benchmark on vector_os_nano |
| Self.attr chain resolution complexity | Recursive attribute chains (`self.a.b.c`) | Limit to depth 2 (self.attr.method), deeper chains fall back to global |
| Incremental edge rebuild correctness | Stale edges after file change | Comprehensive test contracts; delete-all-then-rebuild strategy |
| Protocol refactor touches many files | Risk of subtle breakage | Protocols are structural — existing classes satisfy them without modification |
| 70 new tests increase test runtime | Developer friction | Tests are pure-Python, no I/O — <1s each; total suite stays under 20s |
