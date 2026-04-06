# v0.5.0 UX Enhancement — Technical Plan

## 1. Architecture Overview

Three independent feature tracks that share no backend code paths. Can be developed in parallel by Alpha/Beta/Gamma.

```
Track A: Resizable Panels       (CSS + JS only, no backend)
Track B: Visualization Modes    (backend build_graph_data + frontend mode selector)
Track C: Enriched Change Panel  (backend change_tracker diffs + frontend expandable items)
```

All tracks modify the same 5 files but touch different sections:
- `graph.css` — Track A adds resize styles, Track C adds diff styles
- `graph.js` — Track A adds resize logic, Track B adds mode switching, Track C adds diff/expand UI
- `index.html` — Track A adds resize handles, Track B adds mode buttons
- `web_server.py` — Track B modifies build_graph_data, Track C adds suggest-tests endpoint
- `change_tracker.py` — Track C adds source snapshot + diff computation

## 2. Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mode filtering | Backend (Python) | Reduces payload size, avoids sending 2000 nodes when only 100 needed |
| Diff computation | `difflib.unified_diff` (stdlib) | Zero deps, battle-tested, produces standard unified diff format |
| Panel resize | CSS + pointer events JS | No library needed, 30 lines of JS |
| Diff rendering | highlight.js (already loaded) | Already in page, supports diff language mode via `hljs.highlight(code, {language:'diff'})` — verify compat with v11.9.0 |
| Source snapshot | Per-function source slice | Store `{name: source_lines}` in snapshot, not full file (memory efficient) |
| Expand/collapse | Pure CSS + JS toggle | `display:none` / `display:block` with height transition |

### Version Compatibility Check

| Library | Version | API Used | Status |
|---------|---------|----------|--------|
| Three.js | r137.0 | SphereGeometry, MeshBasicMaterial, BufferGeometry, Points, Group | No new usage — SAFE |
| 3d-force-graph | 1.79.1 | ForceGraph3D, graphData, cameraPosition, nodeColor, linkColor | `.graphData()` for reload on mode switch — SAFE |
| highlight.js | 11.9.0 | `hljs.highlight(code, {language:'diff'})` | diff language built-in since v11.0 — SAFE |

No new CDN scripts. No version changes.

## 3. Module Design

### Track A: Resizable Panels

**Files**: `graph.css`, `graph.js`, `index.html`

CSS:
- `.resize-handle` class: 4px wide, 100% height, cursor col-resize, positioned absolute on panel edge
- `.resize-handle:hover` / `.resize-handle.active`: visible 1px line indicator

JS (`graph.js`):
- `initResize()` called after DOM ready
- `pointerdown` on handle -> track `pointermove` on document -> update panel width
- `pointerup` -> save to localStorage, trigger `graph3d.width()` recalc
- Clamp to min/max (sidebar: 200-500px, inspector: 280-600px)

HTML (`index.html`):
- `<div class="resize-handle" id="sidebar-resize"></div>` after `#sidebar`
- `<div class="resize-handle" id="inspector-resize"></div>` before `#inspector`

### Track B: Visualization Modes

**Files**: `web_server.py`, `graph.js`, `graph.css`, `index.html`

Backend (`web_server.py`):
```python
_MODE_LABELS = {
    "architecture": {NodeLabel.FILE},
    "logic": {NodeLabel.FILE, NodeLabel.FUNCTION, NodeLabel.CLASS, NodeLabel.METHOD},
    "deep": None,  # all labels (no filter)
}
_MODE_EDGES = {
    "architecture": {EdgeType.IMPORTS},
    "logic": {EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.EXTENDS,
              EdgeType.HAS_METHOD, EdgeType.CONTAINS, EdgeType.DECORATES},
    "deep": None,  # all edge types
}
_MODE_MAX_NODES = {
    "architecture": 200,
    "logic": 600,
    "deep": 2000,
}
```

`build_graph_data(mode="logic")`:
- Filter `all_nodes` by `_MODE_LABELS[mode]` if not None
- Filter links by `_MODE_EDGES[mode]` if not None
- Use `_MODE_MAX_NODES[mode]` as limit
- Architecture mode: enrich FILE nodes with `function_count`, `class_count`

HTTP handler: parse `mode` from query string in `/api/data` handler.

Frontend (`graph.js`):
- `currentMode` state variable (default from localStorage or "logic")
- `switchMode(mode)` function: update state, fetch `/api/data?mode=X`, reinit graph
- Keyboard handler: 1/2/3 keys trigger mode switch (when no input focused)
- Mode buttons in topbar

### Track C: Enriched Change Panel

**Files**: `change_tracker.py`, `web_server.py`, `graph.js`, `graph.css`

Backend (`change_tracker.py`):
- `snapshot_file()`: additionally store per-function source snippets
  ```python
  # snapshot now stores: {(name, label): (node_id, sig_hash, source_lines)}
  ```
- `record_change()`: for modified functions, compute unified diff; for added, store new source; for removed, store old source
- `ChangeEvent.diffs`: `dict[str, str]` (frozen via tuple of pairs)
- `ChangeEvent.to_dict()`: include `diffs` field

Backend (`web_server.py`):
- New `/api/suggest-tests?name=X` endpoint: calls `suggest_tests(graph, name)`, returns JSON list
- Handler in `_VectorGraphHandler.do_GET`

Frontend (`graph.js`):
- Modified `showImpactPanel()`:
  - "What Changed" items get expand toggle showing diff
  - "Calls"/"Depended On By" items get expand toggle showing source
  - New "Tests to Run" section: fetch from `/api/suggest-tests` for each changed function
  - Change frequency counter: `sessionChangeCount[name]++` on each event

Frontend (`graph.css`):
- `.diff-block` styles: red/green line coloring, monospace, max-height scroll
- `.expandable` toggle styles

## 4. Test Strategy

| Track | Test File | New Tests | Method |
|-------|-----------|-----------|--------|
| A (Resize) | `test_web_api.py` | 2 | Check HTML contains resize handles |
| B (Modes) | `test_web_api.py` | 8 | Call `build_graph_data(mode=X)`, verify node/edge filtering |
| C (Diffs) | `test_change_tracker.py` | 8 | Snapshot + modify + verify diff content |
| C (Tests endpoint) | `test_web_api.py` | 2 | Verify suggest-tests endpoint behavior |

Total new tests: ~20

## 5. Execution Waves

```
Wave 1 (parallel — no dependencies):
  Alpha:  Track B backend (build_graph_data mode filtering + tests)
  Beta:   Track C backend (change_tracker diffs + tests)
  Gamma:  Track A (resize panels CSS/JS/HTML)

Wave 2 (parallel — after Wave 1):
  Alpha:  Track B frontend (mode selector UI + keyboard shortcuts)
  Beta:   Track C frontend (expandable diffs, test suggestions, change frequency)
  
Wave 3 (sequential):
  Integration: full test suite + manual verification
```
