"""L3 unit tests for ROS2 node extractor (ast-based, no rclpy dependency)."""

from __future__ import annotations

import textwrap

import pytest

from vector_graph.ros2.node_extractor import (
    PublisherInfo,
    SubscriberInfo,
    ServiceInfo,
    ActionInfo,
    ParameterInfo,
    ROS2NodeInfo,
    extract_ros2_nodes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SENSOR_NODE_SRC = textwrap.dedent("""\
    from __future__ import annotations
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import Twist
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy

    class SensorNode(Node):
        def __init__(self):
            super().__init__('sensor_node')
            self.declare_parameter('scan_topic', '/scan')
            self.declare_parameter('cmd_topic', '/cmd_vel')

            sensor_qos = QoSProfile(
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
                depth=5,
            )

            self._scan_pub = self.create_publisher(
                LaserScan, '/scan', qos_profile=sensor_qos
            )
            self._cmd_sub = self.create_subscription(
                Twist, '/cmd_vel', self._cmd_callback, 10
            )

        def _cmd_callback(self, msg: Twist) -> None:
            self.get_logger().info(f"Received cmd: {msg}")

        def publish_scan(self, scan: LaserScan) -> None:
            self._scan_pub.publish(scan)
""")

NON_ROS_SRC = textwrap.dedent("""\
    class PlainClass:
        def __init__(self):
            self.value = 42

    def standalone_function():
        pass
""")

SERVICE_NODE_SRC = textwrap.dedent("""\
    from rclpy.node import Node
    from std_srvs.srv import SetBool

    class ServiceNode(Node):
        def __init__(self):
            super().__init__('service_node')
            self._srv = self.create_service(SetBool, '/set_bool', self._handle_set)

        def _handle_set(self, request, response):
            response.success = True
            return response
""")

ACTION_NODE_SRC = textwrap.dedent("""\
    from rclpy.node import Node
    from rclpy.action import ActionServer
    from my_pkg.action import Navigate

    class NavNode(Node):
        def __init__(self):
            super().__init__('nav_node')
            self._action_server = ActionServer(
                self, Navigate, 'navigate', self._execute_cb
            )
""")

MULTI_PUB_SUB_SRC = textwrap.dedent("""\
    from rclpy.node import Node
    from std_msgs.msg import String, Float32, Bool

    class MultiNode(Node):
        def __init__(self):
            super().__init__('multi_node')
            self.pub1 = self.create_publisher(String, '/topic_a', 10)
            self.pub2 = self.create_publisher(Float32, '/topic_b', 10)
            self.sub1 = self.create_subscription(Bool, '/input_a', self._cb_a, 10)
            self.sub2 = self.create_subscription(String, '/input_b', self._cb_b, 10)
""")


# ---------------------------------------------------------------------------
# Tests — class detection
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_detect_ros2_node_class() -> None:
    """Class inheriting from Node is detected as a ROS2 node."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    assert len(nodes) == 1
    assert nodes[0].class_name == "SensorNode"


@pytest.mark.level3
def test_non_ros2_class_ignored() -> None:
    """Classes not inheriting from Node are not returned."""
    nodes = extract_ros2_nodes("/fake/plain.py", source=NON_ROS_SRC)
    assert nodes == []


@pytest.mark.level3
def test_node_name_extracted_from_super_init() -> None:
    """Node name is extracted from super().__init__('node_name') call."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    assert nodes[0].node_name == "sensor_node"


@pytest.mark.level3
def test_file_path_preserved() -> None:
    """file_path is set to the path passed to extract_ros2_nodes."""
    nodes = extract_ros2_nodes("/my/robot/sensor_node.py", source=SENSOR_NODE_SRC)
    assert nodes[0].file_path == "/my/robot/sensor_node.py"


# ---------------------------------------------------------------------------
# Tests — publisher extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_publisher_extracted() -> None:
    """create_publisher() calls produce PublisherInfo entries."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    assert len(nodes[0].publishers) == 1
    pub = nodes[0].publishers[0]
    assert pub.topic == "/scan"
    assert pub.msg_type == "LaserScan"


@pytest.mark.level3
def test_multiple_publishers() -> None:
    """Multiple create_publisher() calls are all captured."""
    nodes = extract_ros2_nodes("/fake/multi.py", source=MULTI_PUB_SUB_SRC)
    topics = {p.topic for p in nodes[0].publishers}
    assert topics == {"/topic_a", "/topic_b"}


# ---------------------------------------------------------------------------
# Tests — subscriber extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_subscriber_extracted() -> None:
    """create_subscription() calls produce SubscriberInfo entries."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    assert len(nodes[0].subscribers) == 1
    sub = nodes[0].subscribers[0]
    assert sub.topic == "/cmd_vel"
    assert sub.msg_type == "Twist"
    assert sub.callback == "_cmd_callback"


@pytest.mark.level3
def test_multiple_subscribers() -> None:
    """Multiple create_subscription() calls are all captured."""
    nodes = extract_ros2_nodes("/fake/multi.py", source=MULTI_PUB_SUB_SRC)
    topics = {s.topic for s in nodes[0].subscribers}
    assert topics == {"/input_a", "/input_b"}


# ---------------------------------------------------------------------------
# Tests — parameter extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_parameter_extracted() -> None:
    """declare_parameter() calls produce ParameterInfo entries."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    param_names = {p.param_name for p in nodes[0].parameters}
    assert param_names == {"scan_topic", "cmd_topic"}


@pytest.mark.level3
def test_parameter_default_value() -> None:
    """declare_parameter() default value is captured."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    by_name = {p.param_name: p for p in nodes[0].parameters}
    assert by_name["scan_topic"].default_value == "'/scan'"


# ---------------------------------------------------------------------------
# Tests — service extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_service_extracted() -> None:
    """create_service() calls produce ServiceInfo entries."""
    nodes = extract_ros2_nodes("/fake/service_node.py", source=SERVICE_NODE_SRC)
    assert len(nodes) == 1
    assert len(nodes[0].services) == 1
    svc = nodes[0].services[0]
    assert svc.service_name == "/set_bool"
    assert svc.srv_type == "SetBool"


# ---------------------------------------------------------------------------
# Tests — action extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_action_server_extracted() -> None:
    """ActionServer() instantiation produces ActionInfo entries."""
    nodes = extract_ros2_nodes("/fake/nav_node.py", source=ACTION_NODE_SRC)
    assert len(nodes) == 1
    assert len(nodes[0].actions) == 1
    action = nodes[0].actions[0]
    assert action.action_name == "navigate"
    assert action.action_type == "Navigate"


# ---------------------------------------------------------------------------
# Tests — result is frozen / immutable
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_ros2_node_info_is_frozen() -> None:
    """ROS2NodeInfo and sub-types are frozen dataclasses."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    info = nodes[0]
    with pytest.raises((AttributeError, TypeError)):
        info.class_name = "mutated"  # type: ignore[misc]


@pytest.mark.level3
def test_publishers_is_tuple() -> None:
    """publishers field is a tuple (immutable)."""
    nodes = extract_ros2_nodes("/fake/sensor_node.py", source=SENSOR_NODE_SRC)
    assert isinstance(nodes[0].publishers, tuple)


@pytest.mark.level3
def test_empty_source_returns_empty() -> None:
    """Empty source returns no nodes."""
    nodes = extract_ros2_nodes("/fake/empty.py", source="")
    assert nodes == []


@pytest.mark.level3
def test_syntax_error_returns_empty() -> None:
    """Malformed source returns no nodes (no exception raised)."""
    nodes = extract_ros2_nodes("/fake/bad.py", source="class Broken(\n")
    assert nodes == []
