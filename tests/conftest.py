"""Shared test fixtures for vector-graph."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal Python project for testing."""
    pkg = tmp_path / "myproject"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    (pkg / "models.py").write_text(textwrap.dedent("""\
        from __future__ import annotations
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class User:
            name: str
            email: str

            def full_name(self) -> str:
                return self.name

        @dataclass(frozen=True)
        class Post:
            title: str
            author: User

            def summary(self) -> str:
                return f"{self.title} by {self.author.full_name()}"
    """))

    (pkg / "utils.py").write_text(textwrap.dedent("""\
        from __future__ import annotations
        import logging

        logger = logging.getLogger(__name__)

        def validate_email(email: str) -> bool:
            return "@" in email

        def format_name(first: str, last: str) -> str:
            return f"{first} {last}"

        def _internal_helper() -> None:
            pass
    """))

    (pkg / "views.py").write_text(textwrap.dedent("""\
        from __future__ import annotations
        from .models import User, Post
        from .utils import validate_email, format_name

        def create_user(name: str, email: str) -> User:
            if not validate_email(email):
                raise ValueError("Invalid email")
            return User(name=name, email=email)

        def create_post(title: str, author: User) -> Post:
            return Post(title=title, author=author)

        def render_feed(users: list[User]) -> list[str]:
            results = []
            for user in users:
                name = format_name(user.name, "")
                results.append(name)
            return results
    """))

    (pkg / "orphan.py").write_text(textwrap.dedent("""\
        from __future__ import annotations

        def unreachable_function() -> None:
            pass

        class UnusedClass:
            def unused_method(self) -> None:
                pass
    """))

    return tmp_path


@pytest.fixture
def ros2_project(tmp_path: Path) -> Path:
    """Create a minimal ROS2-like Python project for testing."""
    pkg = tmp_path / "my_robot"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    (pkg / "sensor_node.py").write_text(textwrap.dedent("""\
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
    """))

    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()
    (launch_dir / "robot.launch.py").write_text(textwrap.dedent("""\
        from launch import LaunchDescription
        from launch_ros.actions import Node
        from launch.actions import DeclareLaunchArgument
        from launch.substitutions import LaunchConfiguration

        def generate_launch_description():
            use_sim = LaunchConfiguration('use_sim', default='true')
            return LaunchDescription([
                DeclareLaunchArgument('use_sim', default_value='true'),
                Node(
                    package='my_robot',
                    executable='sensor_node',
                    name='sensor',
                    parameters=[{'use_sim': use_sim}],
                ),
            ])
    """))

    msg_dir = tmp_path / "msg"
    msg_dir.mkdir()
    (msg_dir / "Sensor.msg").write_text("float64 range\nfloat64 angle\nstring frame_id\n")
    (msg_dir / "Command.srv").write_text("float64 speed\nfloat64 turn\n---\nbool success\nstring message\n")

    return tmp_path
