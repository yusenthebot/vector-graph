"""Core data types for vector-graph. All frozen dataclasses, zero external deps."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Node labels
# ---------------------------------------------------------------------------

class NodeLabel(str, Enum):
    FILE = "File"
    FOLDER = "Folder"
    FUNCTION = "Function"
    CLASS = "Class"
    METHOD = "Method"
    VARIABLE = "Variable"
    MODULE = "Module"
    PROPERTY = "Property"
    DECORATOR = "Decorator"
    # ROS2 extensions
    ROS2_NODE = "ROS2Node"
    TOPIC = "Topic"
    SERVICE = "Service"
    ACTION = "Action"
    PARAMETER = "Parameter"
    # Analysis
    COMMUNITY = "Community"
    PROCESS = "Process"


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

class EdgeType(str, Enum):
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    HAS_METHOD = "HAS_METHOD"
    HAS_PROPERTY = "HAS_PROPERTY"
    DECORATES = "DECORATES"
    # ROS2 extensions
    PUBLISHES_TO = "PUBLISHES_TO"
    SUBSCRIBES_TO = "SUBSCRIBES_TO"
    PROVIDES_SERVICE = "PROVIDES_SERVICE"
    CALLS_SERVICE = "CALLS_SERVICE"
    PROVIDES_ACTION = "PROVIDES_ACTION"
    CALLS_ACTION = "CALLS_ACTION"
    USES_PARAMETER = "USES_PARAMETER"
    # Analysis
    STEP_IN_PROCESS = "STEP_IN_PROCESS"
    MEMBER_OF = "MEMBER_OF"


# ---------------------------------------------------------------------------
# Resolution tiers (ported from GitNexus resolution-context.ts)
# ---------------------------------------------------------------------------

class ResolutionTier(str, Enum):
    SAME_FILE = "same-file"
    IMPORT_SCOPED = "import-scoped"
    GLOBAL = "global"


TIER_CONFIDENCE: dict[ResolutionTier, float] = {
    ResolutionTier.SAME_FILE: 0.95,
    ResolutionTier.IMPORT_SCOPED: 0.9,
    ResolutionTier.GLOBAL: 0.5,
}


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeProperties:
    """Properties attached to a graph node."""

    name: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    is_exported: bool = False
    is_async: bool = False
    return_type: str | None = None
    declared_type: str | None = None
    parameter_count: int | None = None
    parameters: tuple[str, ...] = ()
    decorators: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    docstring: str | None = None
    # ROS2
    topic_name: str | None = None
    msg_type: str | None = None
    qos_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != () and v != ""}


@dataclass(frozen=True)
class GraphNode:
    """A node in the knowledge graph."""

    id: str
    label: NodeLabel
    properties: NodeProperties

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label.value, "properties": self.properties.to_dict()}


@dataclass(frozen=True)
class Edge:
    """A directed edge in the knowledge graph."""

    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = 0.9
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "confidence": self.confidence,
        }
        if self.reason:
            d["reason"] = self.reason
        return d


# ---------------------------------------------------------------------------
# Symbol table types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SymbolDef:
    """A symbol definition registered in the symbol table."""

    node_id: str
    name: str
    file_path: str
    label: NodeLabel
    parameter_count: int | None = None
    required_parameter_count: int | None = None
    parameter_types: tuple[str, ...] | None = None
    return_type: str | None = None
    declared_type: str | None = None
    owner_id: str | None = None


@dataclass(frozen=True)
class TieredCandidates:
    """Resolution result: candidates grouped by tier."""

    candidates: tuple[SymbolDef, ...]
    tier: ResolutionTier

    @property
    def confidence(self) -> float:
        return TIER_CONFIDENCE[self.tier]

    @property
    def is_empty(self) -> bool:
        return len(self.candidates) == 0


# ---------------------------------------------------------------------------
# Parser extraction types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractedFunction:
    """A function/method extracted from source."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    is_method: bool = False
    is_async: bool = False
    is_exported: bool = False
    owner_class: str | None = None
    parameters: tuple[str, ...] = ()
    parameter_types: tuple[str, ...] = ()
    return_type: str | None = None
    decorators: tuple[str, ...] = ()
    docstring: str | None = None


@dataclass(frozen=True)
class ExtractedClass:
    """A class extracted from source."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    bases: tuple[str, ...] = ()
    is_exported: bool = False
    decorators: tuple[str, ...] = ()
    docstring: str | None = None


@dataclass(frozen=True)
class ExtractedImport:
    """An import statement extracted from source."""

    module: str
    names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    is_from: bool = False
    level: int = 0  # relative import dots
    file_path: str = ""
    line: int = 0


@dataclass(frozen=True)
class ExtractedCall:
    """A function call extracted from source."""

    callee_name: str
    file_path: str
    line: int
    caller_name: str | None = None
    caller_class: str | None = None
    arg_count: int = 0
    is_attribute: bool = False
    receiver: str | None = None  # for obj.method() calls


@dataclass(frozen=True)
class ExtractedAssignment:
    """A variable assignment with type info."""

    name: str
    file_path: str
    line: int
    declared_type: str | None = None
    value_type: str | None = None  # inferred from RHS


@dataclass(frozen=True)
class FileParseResult:
    """Complete parse result for a single file."""

    file_path: str
    functions: tuple[ExtractedFunction, ...] = ()
    classes: tuple[ExtractedClass, ...] = ()
    imports: tuple[ExtractedImport, ...] = ()
    calls: tuple[ExtractedCall, ...] = ()
    assignments: tuple[ExtractedAssignment, ...] = ()


# ---------------------------------------------------------------------------
# Analysis result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ImpactEntry:
    """A single impacted symbol in blast radius analysis."""

    node_id: str
    name: str
    file_path: str
    depth: int
    edge_type: str
    confidence: float


@dataclass(frozen=True)
class ImpactResult:
    """Result of blast radius analysis."""

    target_name: str
    target_file: str
    direction: str
    risk: str  # LOW, MEDIUM, HIGH, CRITICAL
    entries: tuple[ImpactEntry, ...] = ()

    @property
    def impacted_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target_name,
            "file": self.target_file,
            "direction": self.direction,
            "risk": self.risk,
            "impacted_count": self.impacted_count,
            "entries": [
                {"name": e.name, "file": e.file_path, "depth": e.depth, "edge_type": e.edge_type}
                for e in self.entries
            ],
        }


@dataclass(frozen=True)
class ProcessTrace:
    """An execution flow trace."""

    id: str
    label: str
    entry_point_id: str
    terminal_id: str
    step_count: int
    trace: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "steps": self.step_count, "trace": list(self.trace)}


@dataclass(frozen=True)
class CommunityInfo:
    """A detected code community/cluster."""

    id: str
    label: str
    cohesion: float
    members: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass(frozen=True)
class TypeBinding:
    """Inferred type for a variable in a scope."""

    variable_name: str
    inferred_type: str
    source_file: str
    scope: str
    line: int
    confidence: float = 0.9


@dataclass(frozen=True)
class QueryResult:
    """Result of a graph query."""

    query_type: str
    params: dict[str, str]
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[Edge, ...] = ()

    @property
    def count(self) -> int:
        return len(self.nodes)


@dataclass(frozen=True)
class AnalysisResult:
    """Complete analysis result from CodeGraph.analyze()."""

    root: str
    node_count: int = 0
    edge_count: int = 0
    file_count: int = 0
    function_count: int = 0
    class_count: int = 0
    import_count: int = 0
    call_count: int = 0
    community_count: int = 0
    process_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
