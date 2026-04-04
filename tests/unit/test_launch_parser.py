"""L3 unit tests for ROS2 launch file parser (ast-based)."""

from __future__ import annotations

import textwrap

import pytest

from vector_graph.ros2.launch_parser import (
    LaunchNodeInfo,
    LaunchFileInfo,
    parse_launch_file,
)


# ---------------------------------------------------------------------------
# Fixtures / source strings
# ---------------------------------------------------------------------------

BASIC_LAUNCH_SRC = textwrap.dedent("""\
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
""")

MULTI_NODE_LAUNCH_SRC = textwrap.dedent("""\
    from launch import LaunchDescription
    from launch_ros.actions import Node

    def generate_launch_description():
        return LaunchDescription([
            Node(
                package='my_robot',
                executable='sensor_node',
                name='sensor',
            ),
            Node(
                package='my_robot',
                executable='controller_node',
                name='controller',
            ),
        ])
""")

REMAPPING_LAUNCH_SRC = textwrap.dedent("""\
    from launch import LaunchDescription
    from launch_ros.actions import Node

    def generate_launch_description():
        return LaunchDescription([
            Node(
                package='my_robot',
                executable='sensor_node',
                remappings=[('/scan', '/robot/scan')],
            ),
        ])
""")

NON_LAUNCH_SRC = textwrap.dedent("""\
    def some_function():
        return 42

    class MyClass:
        pass
""")

NO_NAME_LAUNCH_SRC = textwrap.dedent("""\
    from launch import LaunchDescription
    from launch_ros.actions import Node

    def generate_launch_description():
        return LaunchDescription([
            Node(
                package='my_pkg',
                executable='my_node',
            ),
        ])
""")


# ---------------------------------------------------------------------------
# Tests — top-level structure
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_parse_returns_launch_file_info() -> None:
    """parse_launch_file returns a LaunchFileInfo instance."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    assert isinstance(result, LaunchFileInfo)


@pytest.mark.level3
def test_file_path_preserved() -> None:
    """file_path attribute matches the path argument."""
    result = parse_launch_file("/my/launch/robot.launch.py", source=BASIC_LAUNCH_SRC)
    assert result.file_path == "/my/launch/robot.launch.py"


@pytest.mark.level3
def test_non_launch_file_returns_empty() -> None:
    """Files without generate_launch_description() return empty nodes/arguments."""
    result = parse_launch_file("/fake/not_launch.py", source=NON_LAUNCH_SRC)
    assert result.nodes == ()
    assert result.arguments == ()


# ---------------------------------------------------------------------------
# Tests — node extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_single_node_extracted() -> None:
    """Single Node() call is extracted from launch file."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    assert len(result.nodes) == 1


@pytest.mark.level3
def test_node_package_and_executable() -> None:
    """package and executable are extracted from Node() keyword args."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    node = result.nodes[0]
    assert node.package == "my_robot"
    assert node.executable == "sensor_node"


@pytest.mark.level3
def test_node_name_extracted() -> None:
    """name keyword from Node() is extracted."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    node = result.nodes[0]
    assert node.name == "sensor"


@pytest.mark.level3
def test_node_name_none_when_missing() -> None:
    """name is None when Node() has no name keyword."""
    result = parse_launch_file("/fake/robot.launch.py", source=NO_NAME_LAUNCH_SRC)
    assert result.nodes[0].name is None


@pytest.mark.level3
def test_multiple_nodes_extracted() -> None:
    """Multiple Node() calls are all extracted."""
    result = parse_launch_file("/fake/multi.launch.py", source=MULTI_NODE_LAUNCH_SRC)
    assert len(result.nodes) == 2
    executables = {n.executable for n in result.nodes}
    assert executables == {"sensor_node", "controller_node"}


@pytest.mark.level3
def test_remappings_extracted() -> None:
    """remappings list is extracted from Node() call."""
    result = parse_launch_file("/fake/remap.launch.py", source=REMAPPING_LAUNCH_SRC)
    node = result.nodes[0]
    assert len(node.remappings) == 1
    assert node.remappings[0] == ("/scan", "/robot/scan")


# ---------------------------------------------------------------------------
# Tests — argument extraction
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_launch_argument_extracted() -> None:
    """DeclareLaunchArgument() names are collected in arguments."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    assert "use_sim" in result.arguments


# ---------------------------------------------------------------------------
# Tests — result is frozen / immutable
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_launch_file_info_is_frozen() -> None:
    """LaunchFileInfo is a frozen dataclass."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    with pytest.raises((AttributeError, TypeError)):
        result.file_path = "mutated"  # type: ignore[misc]


@pytest.mark.level3
def test_launch_node_info_is_frozen() -> None:
    """LaunchNodeInfo is a frozen dataclass."""
    result = parse_launch_file("/fake/robot.launch.py", source=BASIC_LAUNCH_SRC)
    node = result.nodes[0]
    with pytest.raises((AttributeError, TypeError)):
        node.package = "mutated"  # type: ignore[misc]


@pytest.mark.level3
def test_syntax_error_returns_empty() -> None:
    """Malformed source returns empty LaunchFileInfo (no exception)."""
    result = parse_launch_file("/fake/bad.py", source="def generate_launch_description(\n")
    assert result.nodes == ()
