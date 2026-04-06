# vector-graph Roadmap

## Product Vision

**vector-graph is the radar for vibe coding.**

When developers use CLI AI tools (Claude Code, aider, Cursor CLI) to write code, they lose track of what the AI changed and how it affects the codebase. vector-graph provides real-time situational awareness -- a live 3D map of the code that pulses when things change.

Two interfaces, one brain:
- **Web 3D Radar** (for humans): browser tab showing live nebula visualization
- **MCP Server** (for AI agents): Claude Code queries impact/risk before making changes

---

## Done

### v0.4.x -- Core Engine
- Python AST parsing (stdlib, zero deps)
- Knowledge graph (12K+ nodes on real projects)
- Type inference + typed call resolution (93% accuracy)
- Code health engine (complexity, coupling, risk)
- 3D nebula visualization (Three.js + 3d-force-graph)
- 15 MCP tools + Claude Code PreToolUse hook
- Incremental file watcher + edge rebuild
- SSE real-time push + change timeline
- TUI terminal dashboard

### v0.5.0 -- UX Enhancement
- Three visualization modes (Arch / Logic / Deep) with instant switching
- Distinct 3D node shapes per type (cube, diamond, sphere, etc.)
- Resizable sidebar and inspector panels
- Enriched change panel (Summary / Detail modes)
- Inline code diffs with Python syntax highlighting
- Expandable source preview for dependencies
- Test suggestions from call graph
- web_server.py extracted to static files (2183 -> 562 lines)
- AST signature comparison for real modification detection
- Node ID tracking in change events

### v0.6.x -- Git Time + Polish
- Git hotspot detection (change frequency x complexity)
- Co-change analysis (implicit coupling from commit history)
- 17 MCP tools (added hotspot_report, co_change)
- Hotspot heatmap toggle + git info in node tooltips
- Spotlight change mode (pulsing glow, no blackout)
- Change narrative synthesis ("Added X and integrated into Y")
- Semantic change grouping (union-find on call graph)
- Animated ripple wave on change arrival
- Change grouping (5s window batching)
- Browser notifications on HIGH/CRITICAL risk

### v0.7.0 -- 2D Impact Graph
- Interactive 2D force-directed graph in inspector panel (force-graph 1.51.2)
- Progressive disclosure: click to expand node connections
- Node detail panel with callers/callees/source preview
- 766 tests, 86% coverage

---

### v0.8.0 -- Intuitive Visualization
- Hover-to-show edges: edges hidden by default, appear on node hover/selection
- Connectivity-based node sizing (fan-in + fan-out logarithmic scale)
- Fan-in/fan-out data in graph API
- 2D impact graph: conditional labels (hover-only when >15 nodes)
- 778 tests, 86% coverage

### v0.9.0 -- Terminal Cockpit
- Full-width status bar (replaces helpbar/topbar/sidebar-stats) with mode badge, stats, context-sensitive shortcuts, FPS counter
- Panel collapse: Ctrl+B toggle sidebar, Ctrl+I toggle inspector
- Command palette overlay: Ctrl+K or / for fuzzy search across nodes, files, commands
- Sidebar tabs replaced with stacked accordion sections (all visible at once, multiple expandable)
- 810 tests, 86% coverage

---

## Next: v1.0.0 -- Scale + Polish

Priority items:
- Containment visualization (class -> methods boundary)
- Edge bundling for cross-group connections
- Minimap for spatial context
- Level of Detail / InstancedMesh for 10K nodes
- Zen mode (full-screen graph with floating panels)
- Theme switching (Catppuccin Mocha/Macchiato, Dracula, Tokyo Night)
- PyPI release: `pip install vector-graph`

---

## Future

### v1.1.0 -- Multi-Language
- C++ support via tree-sitter
- Cross-language bridge (Python launch -> C++ node resolution)
- Mixed graph visualization

---

## Distribution

| Form | Status |
|------|--------|
| CLI + Web UI | Done |
| MCP Server (17 tools) | Done |
| TUI dashboard | Done |
| Claude Code hook | Done |
| pip package | Planned (v0.9) |
| Static HTML export | Planned (v0.9) |
