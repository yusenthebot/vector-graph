"""ROS2 graph overlay builder.

Adds ROS2 nodes, topics, services, actions, and parameters to a KnowledgeGraph
based on extracted ROS2NodeInfo / LaunchFileInfo / MsgDefinition data.

Node ID conventions:
- ROS2_NODE:  "ros2_node::<ClassName>"
- TOPIC:      "topic::<topic_name>"
- SERVICE:    "service::<service_name>"
- ACTION:     "action::<action_name>"
- PARAMETER:  "param::<ClassName>::<param_name>"
"""

from __future__ import annotations

from vector_graph._types import (
    Edge,
    EdgeType,
    GraphNode,
    NodeLabel,
    NodeProperties,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.ros2.launch_parser import LaunchFileInfo
from vector_graph.ros2.msg_parser import MsgDefinition
from vector_graph.ros2.node_extractor import ROS2NodeInfo


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ros2_overlay(
    graph: KnowledgeGraph,
    ros2_nodes: list[ROS2NodeInfo],
    launch_info: list[LaunchFileInfo] | None = None,
    msg_defs: list[MsgDefinition] | None = None,
) -> None:
    """Add ROS2 nodes, topics, services, and parameters to the knowledge graph.

    Creates:
        ROS2_NODE, TOPIC, SERVICE, PARAMETER nodes.

    Links:
        PUBLISHES_TO, SUBSCRIBES_TO, PROVIDES_SERVICE, USES_PARAMETER edges.

    Args:
        graph:      The KnowledgeGraph to mutate.
        ros2_nodes: List of extracted ROS2NodeInfo objects.
        launch_info: Optional list of LaunchFileInfo for launch context.
        msg_defs:   Optional list of MsgDefinition for type enrichment.
    """
    # Build a msg_type -> MsgDefinition lookup for enrichment
    msg_lookup: dict[str, MsgDefinition] = {}
    if msg_defs:
        for md in msg_defs:
            msg_lookup[md.name] = md

    for node_info in ros2_nodes:
        _add_ros2_node(graph, node_info, msg_lookup)


# ---------------------------------------------------------------------------
# Per-node processing
# ---------------------------------------------------------------------------

def _add_ros2_node(
    graph: KnowledgeGraph,
    node_info: ROS2NodeInfo,
    msg_lookup: dict[str, MsgDefinition],
) -> None:
    """Add a single ROS2NodeInfo (and all related entities) to the graph."""
    node_id = _ros2_node_id(node_info.class_name)

    # Create the ROS2_NODE graph node
    node_props = NodeProperties(
        name=node_info.class_name,
        file_path=node_info.file_path,
        topic_name=node_info.node_name,  # runtime node name stored here
    )
    graph.add_node(GraphNode(id=node_id, label=NodeLabel.ROS2_NODE, properties=node_props))

    # Publishers -> TOPIC nodes + PUBLISHES_TO edges
    for pub in node_info.publishers:
        topic_id = _ensure_topic(graph, pub.topic, pub.msg_type, node_info.file_path)
        _ensure_edge(
            graph,
            edge_id=f"pub::{node_id}::{topic_id}",
            source_id=node_id,
            target_id=topic_id,
            edge_type=EdgeType.PUBLISHES_TO,
        )

    # Subscribers -> TOPIC nodes + SUBSCRIBES_TO edges
    for sub in node_info.subscribers:
        topic_id = _ensure_topic(graph, sub.topic, sub.msg_type, node_info.file_path)
        _ensure_edge(
            graph,
            edge_id=f"sub::{node_id}::{topic_id}",
            source_id=node_id,
            target_id=topic_id,
            edge_type=EdgeType.SUBSCRIBES_TO,
        )

    # Services -> SERVICE nodes + PROVIDES_SERVICE edges
    for svc in node_info.services:
        svc_id = _ensure_service(graph, svc.service_name, svc.srv_type, node_info.file_path)
        _ensure_edge(
            graph,
            edge_id=f"svc::{node_id}::{svc_id}",
            source_id=node_id,
            target_id=svc_id,
            edge_type=EdgeType.PROVIDES_SERVICE,
        )

    # Parameters -> PARAMETER nodes + USES_PARAMETER edges
    for param in node_info.parameters:
        param_id = _ensure_parameter(
            graph, node_info.class_name, param.param_name, node_info.file_path
        )
        _ensure_edge(
            graph,
            edge_id=f"param::{node_id}::{param_id}",
            source_id=node_id,
            target_id=param_id,
            edge_type=EdgeType.USES_PARAMETER,
        )

    # Actions -> ACTION nodes + PROVIDES_ACTION / CALLS_ACTION edges
    for action in node_info.actions:
        action_id = _ensure_action(graph, action.action_name, action.action_type, node_info.file_path)
        edge_type = EdgeType.PROVIDES_ACTION if action.is_server else EdgeType.CALLS_ACTION
        _ensure_edge(
            graph,
            edge_id=f"action::{node_id}::{action_id}",
            source_id=node_id,
            target_id=action_id,
            edge_type=edge_type,
        )


# ---------------------------------------------------------------------------
# Node factories (idempotent)
# ---------------------------------------------------------------------------

def _ensure_topic(
    graph: KnowledgeGraph,
    topic_name: str,
    msg_type: str | None,
    file_path: str,
) -> str:
    """Add a TOPIC node if it does not exist; return its id."""
    topic_id = _topic_id(topic_name)
    if graph.get_node(topic_id) is None:
        props = NodeProperties(
            name=topic_name,
            file_path=file_path,
            topic_name=topic_name,
            msg_type=msg_type,
        )
        graph.add_node(GraphNode(id=topic_id, label=NodeLabel.TOPIC, properties=props))
    return topic_id


def _ensure_service(
    graph: KnowledgeGraph,
    service_name: str,
    srv_type: str | None,
    file_path: str,
) -> str:
    """Add a SERVICE node if it does not exist; return its id."""
    svc_id = _service_id(service_name)
    if graph.get_node(svc_id) is None:
        props = NodeProperties(
            name=service_name,
            file_path=file_path,
            msg_type=srv_type,
        )
        graph.add_node(GraphNode(id=svc_id, label=NodeLabel.SERVICE, properties=props))
    return svc_id


def _ensure_parameter(
    graph: KnowledgeGraph,
    class_name: str,
    param_name: str,
    file_path: str,
) -> str:
    """Add a PARAMETER node if it does not exist; return its id."""
    param_id = f"param::{class_name}::{param_name}"
    if graph.get_node(param_id) is None:
        props = NodeProperties(name=param_name, file_path=file_path)
        graph.add_node(GraphNode(id=param_id, label=NodeLabel.PARAMETER, properties=props))
    return param_id


def _ensure_action(
    graph: KnowledgeGraph,
    action_name: str,
    action_type: str | None,
    file_path: str,
) -> str:
    """Add an ACTION node if it does not exist; return its id."""
    action_id = _action_id(action_name)
    if graph.get_node(action_id) is None:
        props = NodeProperties(
            name=action_name,
            file_path=file_path,
            msg_type=action_type,
        )
        graph.add_node(GraphNode(id=action_id, label=NodeLabel.ACTION, properties=props))
    return action_id


# ---------------------------------------------------------------------------
# Edge factory (idempotent)
# ---------------------------------------------------------------------------

def _ensure_edge(
    graph: KnowledgeGraph,
    edge_id: str,
    source_id: str,
    target_id: str,
    edge_type: EdgeType,
) -> None:
    """Add an edge if it does not already exist."""
    if graph.get_edge(edge_id) is None:
        graph.add_edge(
            Edge(
                id=edge_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                confidence=0.95,
            )
        )


# ---------------------------------------------------------------------------
# ID generators
# ---------------------------------------------------------------------------

def _ros2_node_id(class_name: str) -> str:
    return f"ros2_node::{class_name}"


def _topic_id(topic_name: str) -> str:
    return f"topic::{topic_name}"


def _service_id(service_name: str) -> str:
    return f"service::{service_name}"


def _action_id(action_name: str) -> str:
    return f"action::{action_name}"
