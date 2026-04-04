# vector-graph

Python code knowledge graph with 3D visualization for ROS2 development.

Indexes any Python codebase into a knowledge graph — every function call, class hierarchy, import chain, and ROS2 node/topic/service relationship — then visualizes it in an interactive 3D force-directed graph with code inspection.

## Architecture

```
                     +---------------------------+
                     |    vector-graph serve      |
                     |    http://localhost:5555    |
                     +---------------------------+
                               |
              +----------------+----------------+
              |                |                |
    +---------+----+  +--------+-------+  +----+---------+
    | 3D Graph     |  | Left Sidebar   |  | Inspector    |
    | 3d-force-    |  | Explorer tab   |  | Source code  |
    | graph        |  | (file tree +   |  | (syntax      |
    | (Three.js)   |  |  symbols)      |  |  highlight)  |
    |              |  | Filters tab    |  | Connections  |
    | Curved edges |  | (node/edge     |  | Impact       |
    | Particles    |  |  toggles)      |  | analysis     |
    | Highlight    |  | Depth filter   |  |              |
    +--------------+  +----------------+  +--------------+
              |
    +---------+-------------------------------------------+
    |              Python Analysis Engine                  |
    +-----------------------------------------------------+
    | parse/           | graph/           | analysis/      |
    |  python_parser   |  knowledge_graph |  impact        |
    |  python_imports  |  symbol_table    |  execution_flow|
    |  python_types    |  resolution      |  community     |
    |                  |                  |  orphan        |
    +------------------+------------------+----------------+
    | ros2/            | watch/           | api/           |
    |  node_extractor  |  file_watcher    |  web_server    |
    |  launch_parser   |                  |  mcp_server    |
    |  msg_parser      |                  |  python_api    |
    |  ros2_graph      |                  |  visualize     |
    +------------------+------------------+----------------+
    |              Pipeline (8 phases)                     |
    | 1.Walk  2.Parse  3.Symbols  3b.Heritage  4.Imports  |
    | 5.Calls  6.Communities  7.Flows  8.ROS2             |
    +-----------------------------------------------------+
```

## Install

```bash
git clone https://github.com/yusenthebot/vector-graph.git
cd vector-graph
pip install -e ".[dev]"
```

## Usage

```bash
# Analyze + 3D visualization
vector-graph ~/your/project --serve

# CLI analysis only
vector-graph ~/your/project

# Impact analysis
vector-graph ~/your/project --impact ClassName

# Find orphan code
vector-graph ~/your/project --orphans
```

Open http://127.0.0.1:5555 for the 3D visualization.

## 3D Visualization

Interactive force-directed graph powered by 3d-force-graph (Three.js):

- **Nodes**: colored by type (Function=blue, Class=purple, Method=teal, ROS2Node=red, Topic=yellow, Service=green, File=gray)
- **Edges**: curved, colored by type (CALLS=blue, IMPORTS=orange, HAS_METHOD=teal, EXTENDS=purple, ROS2=green/yellow/red)
- **Click node**: highlights connections, dims unrelated, opens inspector with source code
- **Hover node**: tooltip with name, type, file, params, connections count
- **Particles**: animate on connected edges when node selected
- **Sidebar**: Explorer tab (file tree with symbols) + Filters tab (node/edge type toggles, depth filter)
- **Inspector**: syntax-highlighted source code, Called by / Calls lists (clickable), impact analysis

## Graph Coverage

Detected on Vector OS Nano (253 files):

| Node Type | Count | Description |
|-----------|-------|-------------|
| Function | 694 | Top-level functions |
| Class | 654 | Class definitions |
| Method | 2877 | Class methods |
| File | 253 | Python source files |
| Variable | 7909 | Typed assignments |
| ROS2Node | 8 | ROS2 node classes |
| Topic | 21 | ROS2 pub/sub topics |
| Service | 8 | ROS2 services |
| Action | 2 | ROS2 actions |
| Parameter | 10 | ROS2 parameters |

| Edge Type | Count | Description |
|-----------|-------|-------------|
| CALLS | 7458 | Function call relationships |
| HAS_METHOD | 2877 | Class -> method ownership |
| CONTAINS | 1348 | File -> function/class |
| IMPORTS | 601 | File -> file imports |
| DECORATES | 46 | Decorator -> decorated |
| PUBLISHES_TO | 22 | ROS2 node -> topic |
| USES_PARAMETER | 10 | ROS2 node -> parameter |
| SUBSCRIBES_TO | 8 | ROS2 node -> topic |
| PROVIDES_SERVICE | 8 | ROS2 node -> service |
| PROVIDES_ACTION | 2 | ROS2 node -> action |
| EXTENDS | 1 | Class inheritance (project-internal) |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | 3D visualization UI |
| `GET /api/data` | Full graph JSON (nodes + links) |
| `GET /api/tree` | File tree with symbols per file |
| `GET /api/source?file=PATH&start=N&end=M` | Source code content |
| `GET /api/context?node=ID` | Node detail + inbound/outbound edges |
| `GET /api/impact?node=ID` | Blast radius analysis |
| `GET /api/search?q=TERM` | Search nodes by name |

## Analysis Engine

- **Parser**: Python `ast` module — zero external deps for core
- **Resolution**: 3-tier name resolution (same-file 0.95, import 0.9, global 0.5), ported from GitNexus
- **Impact**: BFS blast radius with depth-based risk scoring (CRITICAL/HIGH/MEDIUM/LOW)
- **Execution flows**: Entry point detection + BFS trace
- **Communities**: Label propagation clustering
- **ROS2**: AST-based extraction of create_publisher/subscription/service patterns + launch file parsing + .msg/.srv parsing

## Testing

```bash
# All tests
python -m pytest tests/ -v

# By level
python -m pytest tests/ -m level0   # Types + graph
python -m pytest tests/ -m level1   # Parser + imports
python -m pytest tests/ -m level2   # Analysis + pipeline
python -m pytest tests/ -m level3   # ROS2 extraction
python -m pytest tests/ -m level4   # File watcher
python -m pytest tests/ -m level5   # MCP + web API
```

330 tests, 13s.

## Dependencies

- **Core**: zero (stdlib `ast` only)
- **Analysis**: networkx (optional, for community detection)
- **Visualization**: 3d-force-graph + highlight.js (CDN, no install)
- **Watch**: watchdog (optional, for real-time file monitoring)
- **MCP**: mcp (optional, for AI agent integration)

## License

MIT
