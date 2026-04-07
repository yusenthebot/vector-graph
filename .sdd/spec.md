# v0.9.2 Specification — Impact Tree Diagram + Bug Fix

## 1. Overview

Fix the broken 2D impact graph and replace it with a full-panel 2D tree diagram that shows change impact as a readable hierarchy — like a real-time compiled dependency tree.

## 2. Problems

**Bug**: The 2D impact force-graph in the inspector panel renders empty. Root cause: `buildImpactSubgraph()` finds no matching nodes because `activeChangeIds` may be empty due to node ID/name matching failures between backend ChangeTracker and frontend graph data.

**UX**: The 3D nebula is not good for understanding change impact topology. When changes arrive, the user needs a clear, structured 2D view — not a 3D spatial representation.

## 3. Solution

### Part A: Fix Impact Graph Bug

Debug and fix the `activeChangeIds` population in `handleChangeEvent()`. Ensure:
1. Backend `node_ids_added`/`node_ids_modified` are correctly sent in SSE events
2. Frontend fallback name+file matching works when IDs are missing
3. `buildImpactSubgraph()` correctly finds nodes from `activeChangeIds`

### Part B: 2D Impact Tree Diagram (replaces force-graph)

When a change arrives, the inspector panel shows a **tree diagram** instead of the current force-directed 2D graph. The tree is structured as:

```
task_engine.py (MODIFIED)
├── Changed Functions
│   ├── create_task() ──→ calls:
│   │   ├── validate_task_id()      validators.py
│   │   ├── notify_created()        notifier.py
│   │   └── count()                 file_store.py
│   └── delete_task() ──→ calls:
│       └── notify_deleted()        notifier.py
├── Affected By (callers)
│   ├── make_engine()               test_engine.py
│   ├── test_create_task()          test_engine.py
│   └── handle_create()            cli.py
└── Impact Summary
    19 outgoing · 47 dependents · LOW risk
```

**Key properties:**
- Rendered as styled HTML (not canvas/SVG — simpler, scrollable, selectable text)
- Indented tree with connecting lines (CSS border-left + padding)
- Color-coded: green=added, yellow=modified, red=removed
- Each node clickable → flies to it in 3D graph
- Expandable/collapsible branches (default: expanded 2 levels)
- Shows file + line for each function
- Real-time: tree updates when new changes arrive via SSE

**Why HTML tree, not canvas force-graph:**
- More readable than force-directed layout for hierarchical data
- Text is selectable/searchable
- No canvas rendering overhead
- Naturally scrollable for large trees
- Easier to style with CSS
- Better for understanding parent-child relationships

### Part C: Tree Data Construction

The tree is built from existing graph data (no new backend APIs):

```javascript
function buildImpactTree(change) {
  // Root: changed file
  // Level 1: changed/added/removed functions (from change event)
  // Level 2: for each changed function:
  //   - calls (outgoing CALLS edges from linkIndex)
  //   - callers (incoming CALLS edges from linkIndex)
  // Level 3: callers of callers (2-hop impact)
  // Cap: max 100 nodes in tree
}
```

## 4. Non-Goals

- No new backend APIs
- No new CDN dependencies
- Don't change the 3D graph behavior (it stays as-is for exploration)
- Don't remove the existing inspector node-detail view (tree only shows during change events)

## 5. Technical Constraints

- Pure HTML/CSS tree (no canvas, no SVG, no new libraries)
- graph.js is ~3000 lines — keep additions focused
- All 821 existing tests must pass
- Tree must handle 50+ nodes without lag

## 6. Test Contracts

- [ ] `test_js_build_impact_tree`: "buildImpactTree" function present
- [ ] `test_js_impact_tree_html`: "impact-tree" class present
- [ ] `test_css_impact_tree_styles`: ".impact-tree" styles present
- [ ] `test_js_active_change_ids_fallback`: fallback matching logic present
- [ ] `test_js_change_event_node_matching`: node matching in handleChangeEvent

## 7. Acceptance Criteria

- [ ] AC1: 2D impact graph no longer empty — activeChangeIds correctly populated
- [ ] AC2: Inspector shows HTML tree diagram when changes arrive
- [ ] AC3: Tree shows changed functions with their calls and callers
- [ ] AC4: Tree nodes are clickable (fly to 3D node)
- [ ] AC5: Tree is expandable/collapsible
- [ ] AC6: Color-coded: green=added, yellow=modified, red=removed
- [ ] AC7: All 821+ tests pass
