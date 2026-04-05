# TaskFlow — vector-graph Example Project

A minimal task management engine designed to showcase every major feature of
vector-graph in a single, self-contained Python project.

## Analyze with vector-graph

From the repo root:

```bash
vector-graph examples/taskflow --serve --max-nodes 500
```

Or via the Python API:

```python
from vector_graph import CodeGraph
g = CodeGraph.from_directory("examples/taskflow")
g.serve()
```

## Features demonstrated

| Feature | Where |
|---------|-------|
| 6 nebulae (packages) | models/, engine/, storage/, api/, utils/, tests/ |
| Class inheritance | StorageBackend -> InMemoryStore, FileStore (EXTENDS edges) |
| Circular dependency | engine/task_engine.py <-> engine/notifier.py |
| High cyclomatic complexity | scheduler.schedule_tasks() (cc > 15) |
| God class | utils/metrics.py MetricsCollector (30+ methods) |
| Orphan function | utils/dates.py format_iso8601_extended() — never called |
| Type inference | self.store = InMemoryStore() in TaskEngine.__init__ |
| Cross-module call graph | engine -> models, storage, utils |
| Test coverage paths | tests -> engine, models (suggest_tests tracing) |
| Decorator usage | utils/validators.py @validator, used in engine |

## Project structure

```
taskflow/
  models/       task.py, project.py, user.py
  engine/       task_engine.py, project_engine.py, scheduler.py, notifier.py
  storage/      base.py (ABC), memory.py, file_store.py
  api/          cli.py, formatters.py
  utils/        validators.py, dates.py, metrics.py
tests/
  test_task.py, test_project.py, test_engine.py, test_scheduler.py, test_storage.py
```

## Run tests

```bash
cd examples/taskflow
python -m pytest tests/ -v
```

## Run the demo CLI

```bash
cd examples/taskflow
python -m taskflow.api.cli
```
