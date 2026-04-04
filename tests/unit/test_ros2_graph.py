"""L3 unit tests for ROS2 graph overlay builder."""

from __future__ import annotations

import textwrap

import pytest

from vector_graph._types import EdgeType, NodeLabel
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.ros2.node_extractor import extract_ros2_nodes
from vector_graph.ros2.launch_parser import parse_launch_file
from vector_graph.ros2.msg_parser import parse_msg_file
from vector_graph.ros2.ros2_graph import build_ros2_overlay


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SENSOR_NODE_SRC = textwrap.dedent("""\
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import Twist

    class SensorNode(Node):
        def __init__(self):
            super().__init__('sensor_node')
            self.declare_parameter('scan_topic', '/scan')
            self._scan_pub = self.create_publisher(LaserScan, '/scan', 10)
            self._cmd_sub = self.create_subscription(Twist, '/cmd_vel', self._cb, 10)
""")

CONTROLLER_NODE_SRC = textwrap.dedent("""\
    from rclpy.node import Node
    from geometry_msgs.msg import Twist

    class ControllerNode(Node):
        def __init__(self):
            super().__init__('controller_node')
            self._cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
""")

BASIC_LAUNCH_SRC = textwrap.dedent("""\
    from launch import LaunchDescription
    from launch_ros.actions import Node
    from launch.actions import DeclareLaunchArgument

    def generate_launch_description():
        return LaunchDescription([
            DeclareLaunchArgument('use_sim', default_value='true'),
            Node(
                package='my_robot',
                executable='sensor_node',
                name='sensor',
            ),
        ])
""")


def _build_graph_from_src(*sources: tuple[str, str]) -> tuple[KnowledgeGraph, list]:
    """Build a KnowledgeGraph from (file_path, source) pairs."""
    kg = KnowledgeGraph()
    all_nodes = []
    for file_path, src in sources:
        nodes = extract_ros2_nodes(file_path, source=src)
        all_nodes.extend(nodes)
    build_ros2_overlay(kg, all_nodes)
    return kg, all_nodes


# ---------------------------------------------------------------------------
# Tests — node creation
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_ros2_node_added_to_graph() -> None:
    """extract + build_ros2_overlay adds a ROS2_NODE to the graph."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    ros2_nodes = list(kg.get_nodes_by_label(NodeLabel.ROS2_NODE))
    assert len(ros2_nodes) == 1
    assert ros2_nodes[0].properties.name == "SensorNode"


@pytest.mark.level3
def test_topic_node_added_to_graph() -> None:
    """Published topic creates a TOPIC node in the graph."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    topics = list(kg.get_nodes_by_label(NodeLabel.TOPIC))
    topic_names = {t.properties.topic_name for t in topics}
    assert "/scan" in topic_names


@pytest.mark.level3
def test_parameter_node_added_to_graph() -> None:
    """declare_parameter() creates a PARAMETER node."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    params = list(kg.get_nodes_by_label(NodeLabel.PARAMETER))
    assert len(params) >= 1


# ---------------------------------------------------------------------------
# Tests — edge creation
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_publishes_to_edge_created() -> None:
    """PUBLISHES_TO edge connects ROS2_NODE to its published TOPIC."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    pub_edges = [e for e in kg.iter_edges() if e.edge_type == EdgeType.PUBLISHES_TO]
    assert len(pub_edges) == 1


@pytest.mark.level3
def test_subscribes_to_edge_created() -> None:
    """SUBSCRIBES_TO edge connects ROS2_NODE to subscribed TOPIC."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    sub_edges = [e for e in kg.iter_edges() if e.edge_type == EdgeType.SUBSCRIBES_TO]
    assert len(sub_edges) == 1


@pytest.mark.level3
def test_uses_parameter_edge_created() -> None:
    """USES_PARAMETER edge connects ROS2_NODE to declared PARAMETER."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    param_edges = [e for e in kg.iter_edges() if e.edge_type == EdgeType.USES_PARAMETER]
    assert len(param_edges) == 1


# ---------------------------------------------------------------------------
# Tests — cross-node queries
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_query_topics_published_by_node() -> None:
    """Can query: what topics does sensor_node publish?"""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    # Find the ROS2_NODE node
    ros2_nodes = list(kg.get_nodes_by_label(NodeLabel.ROS2_NODE))
    node_id = ros2_nodes[0].id
    # Follow PUBLISHES_TO edges
    pub_edges = [e for e in kg.get_edges_from(node_id) if e.edge_type == EdgeType.PUBLISHES_TO]
    topic_nodes = [kg.get_node(e.target_id) for e in pub_edges]
    topic_names = [n.properties.topic_name for n in topic_nodes if n]
    assert "/scan" in topic_names


@pytest.mark.level3
def test_query_subscribers_to_topic() -> None:
    """Can query: what subscribes to /cmd_vel?"""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    # Find the /cmd_vel topic node
    topics = list(kg.get_nodes_by_label(NodeLabel.TOPIC))
    cmd_topic = next((t for t in topics if t.properties.topic_name == "/cmd_vel"), None)
    assert cmd_topic is not None
    # Find edges pointing TO the topic (subscribes)
    sub_edges = [e for e in kg.get_edges_to(cmd_topic.id) if e.edge_type == EdgeType.SUBSCRIBES_TO]
    assert len(sub_edges) == 1
    subscriber_node = kg.get_node(sub_edges[0].source_id)
    assert subscriber_node is not None
    assert subscriber_node.properties.name == "SensorNode"


@pytest.mark.level3
def test_shared_topic_links_publisher_and_subscriber() -> None:
    """Same topic shared between publisher and subscriber results in one TOPIC node."""
    kg, _ = _build_graph_from_src(
        ("/fake/sensor_node.py", SENSOR_NODE_SRC),
        ("/fake/controller_node.py", CONTROLLER_NODE_SRC),
    )
    topics = list(kg.get_nodes_by_label(NodeLabel.TOPIC))
    # /cmd_vel should appear exactly once even though both nodes reference it
    cmd_topics = [t for t in topics if t.properties.topic_name == "/cmd_vel"]
    assert len(cmd_topics) == 1


@pytest.mark.level3
def test_msg_type_stored_on_topic_node(tmp_path) -> None:
    """Topic node has msg_type set in properties when extracted."""
    kg, _ = _build_graph_from_src(("/fake/sensor_node.py", SENSOR_NODE_SRC))
    topics = list(kg.get_nodes_by_label(NodeLabel.TOPIC))
    scan_topic = next((t for t in topics if t.properties.topic_name == "/scan"), None)
    assert scan_topic is not None
    assert scan_topic.properties.msg_type == "LaserScan"
