# v0.5.0 UX Enhancement Specification

## 1. Overview

Three coordinated UX improvements to the vector-graph 3D visualization: resizable panel layout, multi-granularity visualization modes, and an enriched change panel with inline code diffs and developer-focused context.

## 2. Background & Motivation

The current v0.4.1 visualization is functionally complete but has three UX gaps:

1. **Fixed panel widths** -- The 280px sidebar and 380px inspector cannot be resized, wasting screen space on wide monitors and cramping content on narrow ones.

2. **One-size-fits-all graph** -- Every session shows ~600 nodes mixing files, functions, classes, methods. A new developer just wants to see module dependencies. A debugger wants to see parameter-level data flow. There's no way to zoom the conceptual granularity, only the spatial zoom.

3. **Shallow change notifications** -- The change panel shows function names and risk badges but not the actual code that changed. A developer seeing "~ process_data modified" can't assess the change without switching to their editor. The impact chain shows names but not code context.

## 3. Goals

- MUST: Sidebar and inspector panels resizable via drag handles
- MUST: Three visualization modes -- Architecture, Logic, Deep -- switchable via UI and keyboard
- MUST: Change panel shows inline unified code diffs per changed function
- MUST: Impact chain items expandable to show code preview
- MUST: Test suggestions section in change panel (using existing suggest_tests module)
- SHOULD: Change frequency counter per function in session
- SHOULD: Keyboard shortcuts for mode switching (1/2/3)
- SHOULD: Mode persisted across page reload (localStorage)
- MAY: Animated transition when switching modes

## 4. Non-Goals

- No new analysis algorithms (use existing call_graph, impact, suggest_tests)
- No performance optimization for 2000+ nodes (v0.6.0 scope)
- No new backend MCP tools
- No changes to the pipeline or parser

## 5. Feature Details

### 5.1 Resizable Panels

**Left sidebar** (currently fixed 280px):
- Drag handle on right edge (4px invisible hit zone, visible 1px line on hover)
- Min: 200px, Max: 500px, Default: 280px
- Graph container flex-fills remaining space
- Resize triggers `graph3d.width()` recalculation

**Right inspector** (currently fixed 380px):
- Drag handle on left edge (same behavior)
- Min: 280px, Max: 600px, Default: 380px
- Same flex-fill behavior

**Interaction**: cursor changes to `col-resize` on hover. Drag updates width in real-time via `pointermove`. Width saved to `localStorage`.

### 5.2 Visualization Modes

Three modes that filter at the **backend** (different node/edge sets sent to browser, not just CSS hiding):

| Mode | Keyboard | Nodes Included | Edges Included | max_nodes | Use Case |
|------|----------|----------------|----------------|-----------|----------|
| **Architecture** | `1` | FILE | IMPORTS | 200 | Module dependency overview |
| **Logic** | `2` | FILE, FUNCTION, CLASS, METHOD | CALLS, IMPORTS, EXTENDS, HAS_METHOD, CONTAINS, DECORATES | 600 | Call flow analysis (default) |
| **Deep** | `3` | All (+ VARIABLE, PROPERTY, DECORATOR) | All edge types | 2000 | Full type/data flow |

**Backend**: `build_graph_data()` gets a `mode` parameter (`"architecture"` / `"logic"` / `"deep"`). The `/api/data` endpoint accepts `?mode=X` query parameter.

**Frontend**:
- Mode selector in topbar: three buttons `[Arch] [Logic] [Deep]` with active state
- Switching mode fetches new data via `/api/data?mode=X` and reinitializes graph
- Current mode stored in `localStorage('vg-mode')`
- Topbar shows current mode name and node/link count

**Architecture mode specifics**:
- Only FILE nodes visible, grouped by directory (nebulae)
- IMPORTS edges between files
- Node size proportional to number of symbols in file
- Tooltip shows: file name, function count, class count, import count

**Logic mode specifics** (current default behavior):
- FILE + FUNCTION + CLASS + METHOD nodes
- CALLS + IMPORTS + EXTENDS + HAS_METHOD + CONTAINS + DECORATES edges
- This is what the current v0.4.1 shows

**Deep mode specifics**:
- All node types including VARIABLE, PROPERTY, DECORATOR
- All edge types including HAS_PROPERTY, DEFINES, USES_PARAMETER
- Higher max_nodes (2000) -- may be slow on large codebases (acceptable for v0.5.0)

### 5.3 Enriched Change Panel

When a file change arrives via SSE, the impact panel in the inspector area shows:

#### 5.3.1 Code Diff Section

Each modified function shows an expandable unified diff:

```
~ process_data          [click to expand]
  ---
  - def process_data(x, y):
  -     return x + y
  + def process_data(x, y, z):
  +     return x + y + z
  ---
```

**Backend**: ChangeTracker saves old source code (per-function snippet) in `snapshot_file()`. On `record_change()`, computes unified diff via `difflib.unified_diff`. New ChangeEvent field: `diffs: dict[str, str]` mapping function_name -> unified diff string. Sent via SSE.

For added functions: show full new code (no diff, just green).
For removed functions: show full old code (no diff, just red).

#### 5.3.2 Expandable Impact Items

Each item in "Calls" and "Depended On By" sections becomes expandable:

```
Depended On By (3)
  <- main()  [api/python_api.py]     [v]
     ---
     def main():
         result = process_data(1, 2)  # <-- calls changed function
         print(result)
     ---
```

**Implementation**: The node's `source` field already exists in the graph data (inline snippet from `build_graph_data`). The frontend just needs to show/hide it on click.

#### 5.3.3 Test Suggestions

New section in the impact panel:

```
Tests to Run (2)
  tests/test_foo.py::test_process_data     [depth 1]
  tests/test_foo.py::test_main             [depth 2]
```

**Backend**: New `/api/suggest-tests?name=X` endpoint that calls `suggest_tests()` from the existing analysis module. The change panel fetches suggestions for each modified/added function name.

#### 5.3.4 Session Change Frequency

Each changed function shows how many times it was modified this session:

```
~ process_data  (3rd change)
```

**Implementation**: Frontend maintains a `changeCount` map (function name -> count), incremented on each SSE change event. Displayed inline next to the function name.

## 6. Technical Constraints

- Zero new external dependencies (stdlib difflib for diffs)
- All existing 683 tests must continue to pass
- Coverage must stay >= 86%
- Frontend: no build tools, no npm -- plain JS in static files
- CSS: no preprocessors -- plain CSS
- Changes only in: `change_tracker.py`, `web_server.py`, `graph.js`, `graph.css`, `index.html`, and test files

## 7. Interface Definitions

### Modified Python API

```python
# web_server.py -- build_graph_data gains mode parameter
def build_graph_data(
    graph: KnowledgeGraph,
    max_nodes: int = 600,
    root_path: str = "",
    health_map: dict[str, Any] | None = None,
    mode: str = "logic",  # NEW: "architecture" | "logic" | "deep"
) -> dict[str, Any]: ...

# change_tracker.py -- ChangeEvent gains diffs field
@dataclass(frozen=True)
class ChangeEvent:
    ...
    diffs: dict[str, str] = field(default_factory=dict)  # name -> unified diff
```

### Modified HTTP Endpoints

```
GET /api/data?mode=architecture|logic|deep   # graph data filtered by mode
GET /api/suggest-tests?name=X                 # NEW: test suggestions for symbol
```

### Modified SSE Event Payload

```json
{
  "type": "modified",
  "file": "/project/foo.py",
  "nodes_modified": ["process_data"],
  "node_ids_modified": ["abc123"],
  "diffs": {
    "process_data": "--- before\n+++ after\n@@ -1,2 +1,2 @@\n-def process_data(x, y):\n+def process_data(x, y, z):"
  },
  "impact": { "risk": "MEDIUM", "affected_count": 5 }
}
```

## 8. Test Contracts

### Unit Test Contracts

**Visualization Modes**:
- [ ] `test_build_graph_data_architecture_mode_only_files`: mode="architecture" returns only FILE nodes
- [ ] `test_build_graph_data_architecture_mode_only_imports`: mode="architecture" edges are only IMPORTS
- [ ] `test_build_graph_data_logic_mode_includes_functions`: mode="logic" returns FILE + FUNCTION + CLASS + METHOD
- [ ] `test_build_graph_data_logic_mode_excludes_variables`: mode="logic" excludes VARIABLE, PROPERTY, DECORATOR
- [ ] `test_build_graph_data_deep_mode_includes_all`: mode="deep" returns all node types
- [ ] `test_build_graph_data_deep_mode_max_nodes_2000`: mode="deep" allows up to 2000 nodes
- [ ] `test_build_graph_data_default_mode_is_logic`: no mode param defaults to "logic" behavior
- [ ] `test_build_graph_data_architecture_file_node_has_symbol_count`: Architecture mode FILE nodes include function_count and class_count

**Change Tracker Diffs**:
- [ ] `test_change_tracker_records_diff_on_modify`: Modified function includes unified diff in event
- [ ] `test_change_tracker_diff_shows_added_lines`: New lines appear with "+" prefix
- [ ] `test_change_tracker_diff_shows_removed_lines`: Removed lines appear with "-" prefix
- [ ] `test_change_tracker_no_diff_for_unchanged`: Unchanged functions produce no diff entry
- [ ] `test_change_tracker_diff_for_new_function`: Added function shows full code (no before)
- [ ] `test_change_tracker_diff_for_deleted_function`: Deleted function shows old code (no after)
- [ ] `test_change_event_diffs_json_serializable`: diffs field survives JSON round-trip
- [ ] `test_change_tracker_snapshot_saves_source`: snapshot_file captures source code per function

**Suggest Tests Endpoint**:
- [ ] `test_suggest_tests_endpoint_returns_json`: /api/suggest-tests?name=X returns JSON list
- [ ] `test_suggest_tests_endpoint_unknown_name_returns_empty`: unknown name returns empty list

### Integration Test Contracts

- [ ] `test_html_contains_mode_selector`: HTML output includes mode selector UI
- [ ] `test_html_contains_resize_handles`: HTML output includes resize handle elements

## 9. Acceptance Criteria

- [ ] Left sidebar resizable by dragging right edge (200-500px range)
- [ ] Right inspector resizable by dragging left edge (280-600px range)
- [ ] Panel widths persist across page reload via localStorage
- [ ] Architecture mode shows only FILE nodes + IMPORTS edges
- [ ] Logic mode shows FILE/FUNCTION/CLASS/METHOD + call-related edges (default)
- [ ] Deep mode shows all node and edge types
- [ ] Mode switchable via topbar buttons and keyboard shortcuts 1/2/3
- [ ] Current mode persisted in localStorage
- [ ] Modified functions show expandable inline unified diff in change panel
- [ ] Added functions show full new code in green
- [ ] Removed functions show full old code in red
- [ ] Impact chain items expandable to show code preview
- [ ] Test suggestions section shows relevant test files from suggest_tests module
- [ ] Change frequency displayed per function (nth change this session)
- [ ] All 683+ existing tests pass
- [ ] Coverage >= 86%

## 10. Open Questions

None -- all design decisions resolved in this spec.
