# vector-graph

The radar for vibe coding. Real-time code knowledge graph that watches your codebase, visualizes changes in 3D, and warns AI agents about risky edits.

```
pip install vector-graph
vector-graph ~/project --watch --serve
```

Open `http://localhost:5555` — nodes grouped into nebulae by package, colored by group, with stardust particles and orbital rings.

## Quick Start

### 1. Install

```bash
git clone https://github.com/yusenthebot/vector-graph.git
cd vector-graph
pip install -e ".[dev]"
```

### 2. Visualize any Python project

```bash
vector-graph ~/your/project --serve
```

### 3. Live Radar (vibe coding mode)

```bash
# Terminal 1 — start the radar
vector-graph ~/your/project --watch --serve

# Terminal 2 — vibe code with any AI tool
claude   # or aider, cursor, etc.
```

Every file change triggers: camera fly-to, impact chain highlight, affected nebula glow, Changes timeline update.

### 4. Claude Code Integration (one command)

```bash
vector-graph --install-hook
```

This installs a `PreToolUse` hook that checks risk before every `Edit`/`Write`:
- **LOW/MEDIUM**: silent, zero token cost
- **HIGH/CRITICAL**: one-line warning (~30 tokens)
- Server not running: silent, no error

### 5. MCP Server (AI agent tools)

```bash
# Add to project .mcp.json
{
  "mcpServers": {
    "vector-graph": {
      "command": "vector-graph-mcp",
      "args": ["/path/to/project"]
    }
  }
}
```

15 MCP tools available — AI agents can self-assess risk during coding:

| Tool | What it does |
|------|-------------|
| `impact_preview` | Blast radius before changing a function |
| `safe_to_modify` | Risk assessment for a file |
| `suggest_tests` | Which tests to run after a change |
| `what_changed` | Session change summary |
| `dependency_check` | Would this import create a cycle? |
| `graph_query` | 8 structured query types |
| `health` | Full codebase health report |
| `complexity` | Per-function complexity score |
| `cycles` | Dependency cycle detection |
| `orphans` | Unreachable code detection |
| `export` | JSON/DOT graph export |
| `impact` | Blast radius analysis |
| `context` | 360-degree symbol view |
| `query` | Keyword search |
| `detect_changes` | Changed files report |

## Usage

```bash
# Static 3D visualization
vector-graph ~/project --serve

# Live radar (watch + web)
vector-graph ~/project --watch --serve

# Terminal radar (no browser)
vector-graph ~/project --watch --tui

# Watch only (stdout)
vector-graph ~/project --watch

# CLI analysis
vector-graph ~/project --impact FunctionName
vector-graph ~/project --orphans
vector-graph ~/project --export json
vector-graph ~/project --export dot

# Install Claude Code hook
vector-graph --install-hook

# MCP server (stdio)
vector-graph-mcp ~/project
```

## 3D Nebula Visualization

Nodes grouped by package directory into nebulae — transparent sphere shells with stardust particles and orbital rings.

- **Nebulae**: each package directory = one nebula cluster (Three.js spheres + particles)
- **Node colors**: match their nebula (golden-ratio hue spacing)
- **Click node**: everything else dims, connections highlighted, inspector opens
- **Groups tab**: click a package to fly camera to that nebula
- **Health mode**: toggle in Filters to color nodes by complexity risk (green/yellow/orange/red)

### Live Change Visualization

When `--watch --serve` is active:
- Camera auto-flies to changed area
- Changed nodes glow bright yellow (persistent)
- Impact chain highlighted in orange (BFS depth 2)
- Everything else dims to near-invisible
- Affected nebula brightens
- Changes tab shows timeline with risk badges
- ESC or background click to clear highlight
- Cumulative heatmap: frequently changed nodes glow progressively warmer

## Analysis Engine

- **Type inference**: intra-procedural (constructor, annotation, `self.attr`, parameter types)
- **Call resolution**: 93% of calls resolved via type inference (0.95 confidence), only 7% global fallback
- **Code health**: cyclomatic complexity, fan-in/fan-out, module coupling/cohesion, god class detection
- **Impact analysis**: BFS blast radius with depth-based risk scoring
- **Cycle detection**: Tarjan's SCC for dependency cycles
- **Communities**: label propagation or union-find clustering
- **Execution flows**: entry point scoring + BFS trace
- **ROS2**: node/topic/service/action extraction from AST + launch file parsing

## Architecture

```
vector_graph/
  graph/        KnowledgeGraph, SymbolTable, ResolutionContext, GraphProtocol
  parse/        Python AST parser, import resolver, type inference
  analysis/     type_inference, call_graph, complexity, query, export,
                cycles, impact, execution_flow, community, orphan, suggest_tests
  watch/        file_watcher (watchdog), change_tracker (diff + impact)
  api/          web_server (Three.js nebula), mcp_server (15 tools),
                sse_server (real-time push), tui (rich dashboard), python_api (CLI)
  hooks/        Claude Code hook installer
  ros2/         node_extractor, launch_parser, msg_parser, ros2_graph
  pipeline.py   9-phase orchestrator
```

Pipeline phases:
```
1.Walk → 2.Parse → 3.Symbols → 3b.Heritage → 3c.Types →
4.Imports → 5.Calls → 6.Communities → 7.Flows → 8.ROS2
```

## Example Project

```bash
# Try with the included taskflow demo (6 nebulae, 491 nodes, cycles, orphans)
vector-graph examples/taskflow --serve --max-nodes 500
```

## Testing

```bash
python3 -m pytest -q              # 670 tests, ~19s
python3 -m pytest --cov=vector_graph  # 88% coverage
```

## Dependencies

- **Core**: zero (stdlib `ast` only)
- **Visualization**: Three.js r137 + 3d-force-graph 1.79.1 (CDN)
- **Watch**: watchdog (optional)
- **MCP**: mcp (optional)
- **TUI**: rich (optional)
- **Analysis**: networkx (optional, for community detection)

## License

MIT
