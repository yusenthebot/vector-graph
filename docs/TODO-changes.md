# TODO: Changes Visualization (next session)

## Current State (v0.4.0)

Working:
- SSE real-time push from file watcher to browser
- Change highlight: changed nodes glow yellow, impact chain orange
- Impact tree panel (right side): What Changed / Calls / Depended On By / Impact
- Directional particle flow along impact chain edges
- Cumulative heat map across session
- 15 MCP tools including impact_preview, safe_to_modify, suggest_tests
- Claude Code PreToolUse hook (--install-hook)
- Changes timeline sidebar tab with session summary
- 670 tests, 88% coverage

## Next: Changes Visualization Improvements

### P0 — Must Do

1. **Impact panel polish**
   - The impact tree panel opens but node matching is by name (fragile)
   - Should match by node ID — ChangeTracker needs to send node IDs in SSE events, not just names
   - Backend: modify ChangeEvent to include `node_ids_added`, `node_ids_modified`, `node_ids_removed`

2. **Better change detection accuracy**
   - Current: watcher detects file save → removes all nodes → re-parses → diffing by name
   - Problem: "modified" nodes are really "all surviving names" — no actual diff
   - Fix: compare AST signatures (function params, line count) before/after to detect real modifications

3. **Click items in impact tree → navigate AND highlight in 3D**
   - Currently `selectNode()` clears the change highlight (conflict)
   - Need: clicking a dep in the tree should fly to it WITHOUT clearing the change context
   - Maybe: `previewNode(id)` that just flies camera + shows tooltip, without full select

### P1 — Should Do

4. **2D mini impact diagram**
   - Instead of (or in addition to) the tree list, show a small 2D force graph
   - Only contains: changed nodes + their direct connections
   - Rendered with a separate small ForceGraph2D instance in the panel
   - Much more readable than a text tree for understanding topology

5. **Change diff view**
   - Show actual code diff (before/after) in the impact panel
   - ChangeTracker saves the old source when snapshotting → can compute diff
   - Display as unified diff with syntax highlighting

6. **Animated ripple on 3D graph**
   - When change arrives, a visible "wave" propagates outward from changed nodes
   - Not just particle flow on edges — an actual expanding ring/sphere that fades
   - Gives immediate spatial awareness of "something happened HERE"

7. **Session summary view**
   - "What did AI change this session?" button
   - Shows aggregated: files touched, functions added/modified/removed, highest risk change
   - Heatmap overlay: most-changed areas glow warmest

### P2 — Nice to Have

8. **Before/after graph comparison**
   - Split view: graph structure before session vs now
   - New nodes/edges highlighted in green, removed in red

9. **Change grouping by commit/action**
   - Group related file changes together (e.g., "Claude added feature X" touched 3 files)
   - Show as a single "changeset" rather than 3 separate events

10. **Sound/notification on HIGH risk change**
    - Browser notification API when a CRITICAL change is detected
    - Subtle sound cue so user can glance at screen

## Architecture Notes

Key files:
- `watch/change_tracker.py` — ChangeEvent, ChangeTracker, session history
- `api/sse_server.py` — SSEBroadcaster, format_sse_event
- `api/web_server.py` — _HTML template (JS: handleChangeEvent, showImpactPanel, buildChangeStory, updateChangesPanel)
- `watch/file_watcher.py` — GraphWatcher._process_event calls tracker.snapshot_file + tracker.record_change

The SSE flow:
```
file save → watchdog → GraphWatcher._process_event
  → tracker.snapshot_file (before)
  → graph.remove_nodes_by_file + re-parse + re-register
  → tracker.record_change (after, computes diff + impact)
  → tracker listener → broadcaster.push
  → SSE /api/events → browser EventSource
  → handleChangeEvent → showImpactPanel + 3D highlight
```
