# vector-graph Roadmap

## Product Vision

**vector-graph is the radar for vibe coding.**

When developers use CLI AI tools (Claude Code, aider, Cursor CLI) to write code, they lose track of what the AI changed and how it affects the codebase. vector-graph provides real-time situational awareness — a live 3D map of the code that pulses when things change.

Two interfaces, one brain:
- **Web 3D Radar** (for humans): browser tab showing live nebula visualization
- **MCP Server** (for AI agents): Claude Code queries impact/risk before making changes

```
Terminal 1:  claude                                    # vibe coding
Terminal 2:  vector-graph ~/project --watch --serve    # radar
Browser:     localhost:5555                             # 3D view
```

---

## Current: v0.3.1

| Capability | Status |
|---|---|
| Python AST parsing (stdlib, zero deps) | Done |
| Knowledge graph (12K+ nodes on real projects) | Done |
| Type inference + typed call resolution (93% accuracy) | Done |
| Code health engine (complexity, coupling, risk) | Done |
| 3D nebula visualization (group clustering, stardust, labels) | Done |
| 10 MCP tools (query, impact, health, cycles, export...) | Done |
| Incremental file watcher + edge rebuild | Done |
| 577 tests, 90%+ coverage | Done |

---

## v0.4.0 — Live Radar (Vibe Coding Core)

**The killer feature: real-time change visualization + AI risk assessment.**

### A. Watch + SSE Push (for humans)

Real-time browser updates when files change.

```
File saved → GraphWatcher → ChangeTracker → SSE → Browser animation
```

**ChangeTracker** (`watch/change_tracker.py`):
- Records before/after node state on each file change
- Computes diff: nodes added, modified, removed
- Runs impact analysis on changed nodes
- Maintains session history (in-memory ring buffer)

**SSE Server** (`api/sse_server.py`):
- `/api/events` endpoint using Server-Sent Events (standard lib, no deps)
- Event types: `change`, `impact`, `session_summary`
- Browser connects via `EventSource` (native, zero deps)

**Browser Animations**:

| Animation | Trigger | Visual |
|---|---|---|
| Node pulse | Node modified | 3x brightness flash, decay over 2s |
| New node flash | Node added | Scale 0→1 with glow ring |
| Delete fade | Node removed | Shrink + fade to transparent |
| Ripple wave | Any change | Glow propagates along CALLS edges outward |
| Nebula breath | Group has changes | Shell opacity pulse 0.07→0.2→0.07 |

**Changes Timeline** (sidebar tab):
- Chronological feed of file changes
- Each entry: timestamp, file, nodes affected, risk level
- Click entry → highlight affected nodes + blast radius
- Session summary at top: files changed, nodes modified, risk assessment

**Cumulative Heatmap**:
- Nodes modified multiple times in a session glow progressively hotter
- Color gradient: cool blue → warm orange → hot red
- Reset on session restart

### B. Smart MCP Tools (for AI agents)

AI queries vector-graph BEFORE making changes.

| Tool | Input | Output | AI Use Case |
|---|---|---|---|
| `impact_preview` | function name | blast radius + risk | "Should I refactor this?" |
| `safe_to_modify` | file path | risk level + dependents | "Is this file safe to change?" |
| `what_changed` | (none) | session change summary | "What did I modify so far?" |
| `suggest_tests` | file or function name | test files to run | "What tests cover this?" |
| `dependency_check` | import statement | cycle detection result | "Will this import create a cycle?" |

These enable Claude Code to self-assess risk during vibe coding sessions without human intervention.

### C. TUI Dashboard (terminal alternative)

For users who prefer staying in the terminal.

```bash
vector-graph ~/project --watch --tui
```

Using `rich` or `textual`:
- Real-time file change stream with risk indicators
- Module health summary table
- Affected node list per change
- No 3D, pure information density

### Architecture

```
vector_graph/
├── watch/
│   ├── file_watcher.py      # existing — file system monitoring
│   └── change_tracker.py    # NEW — diff computation, session history
├── analysis/
│   ├── suggest_tests.py     # NEW — test suggestion from call graph
│   └── (existing modules)
├── api/
│   ├── sse_server.py        # NEW — Server-Sent Events push
│   ├── web_server.py        # modified — animation JS, timeline tab
│   ├── mcp_server.py        # modified — 5 new smart tools
│   ├── tui.py               # NEW — textual/rich TUI dashboard
│   └── (existing modules)
└── (existing packages)
```

New external dependencies:
- `textual` or `rich` (optional, for TUI only)
- All other features: zero new deps (SSE via stdlib HTTP)

### Acceptance Criteria

- [ ] File change in watched directory triggers browser animation within 500ms
- [ ] SSE connection stays alive across multiple changes
- [ ] ChangeTracker correctly identifies added/modified/removed nodes
- [ ] Impact preview via MCP returns risk level within 200ms
- [ ] `what_changed` summarizes all session modifications
- [ ] `suggest_tests` returns relevant test files for a given function
- [ ] TUI shows live change feed with risk coloring
- [ ] All existing 577 tests pass, coverage >= 88%

---

## v0.5.0 — Scale + Smart Defaults

Handle large codebases (10K+ nodes) without performance degradation.

- **Level of Detail**: zoom out → groups collapse to single mega-nodes; zoom in → expand
- **WebGL InstancedMesh**: same-type nodes rendered via instancing (10K nodes, 60fps)
- **Edge bundling**: 100 cross-group CALLS edges merge into one thick conduit
- **Lazy loading**: browser requests group contents on demand, not all at once
- **Auto-tuning**: `max_nodes` adjusts based on browser performance metrics
- **PyPI release**: `pip install vector-graph`

---

## v0.6.0 — Git Time Dimension

Add temporal analysis by correlating graph with git history.

- **Hotspot detection**: `git log` change frequency × complexity = tech debt heat map
- **Co-change analysis**: functions that always change together → implicit coupling
- **PR impact preview**: `vector-graph diff HEAD~5` shows blast radius of recent changes
- **Blame ownership**: each nebula shows primary contributor
- **Time playback**: slider to scrub through codebase structural evolution

---

## v0.7.0 — Multi-Language

Extend beyond Python to cover full ROS2 stack.

- **C++ support**: tree-sitter-cpp parser, header/source linking
- **Cross-language bridge**: Python launch files → C++ node resolution
- **Mixed graph**: Python and C++ nodes in the same 3D space with distinct visual styles

---

## Distribution Strategy

| Form | Priority | Description |
|---|---|---|
| CLI + Web UI | Now | `vector-graph . --serve --watch` |
| MCP Server | Now | AI agents query via Claude Code config |
| pip package | v0.4 | `pip install vector-graph` |
| TUI dashboard | v0.4 | `vector-graph . --watch --tui` |
| Static HTML export | v0.5 | Share graph snapshots |

**Not planned**: VS Code extension, IDE plugins. vector-graph is a CLI companion tool, not an IDE feature.

---

## MCP Integration (Claude Code)

```jsonc
// ~/.claude/settings.json
{
  "mcpServers": {
    "vector-graph": {
      "command": "vector-graph-mcp",
      "args": ["/path/to/project"]
    }
  }
}
```

This gives Claude Code access to all vector-graph analysis tools during coding sessions.
