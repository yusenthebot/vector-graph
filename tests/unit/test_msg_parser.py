"""L3 unit tests for ROS2 .msg / .srv / .action file parser."""

from __future__ import annotations

import pytest

from vector_graph.ros2.msg_parser import (
    MsgField,
    MsgDefinition,
    SrvDefinition,
    ActionDefinition,
    parse_msg_file,
    parse_srv_file,
    parse_action_file,
)


# ---------------------------------------------------------------------------
# .msg parsing
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_parse_msg_basic_fields(tmp_path) -> None:
    """Basic .msg with primitive fields is parsed correctly."""
    msg_file = tmp_path / "Sensor.msg"
    msg_file.write_text("float64 range\nfloat64 angle\nstring frame_id\n")
    result = parse_msg_file(str(msg_file))
    assert isinstance(result, MsgDefinition)
    assert result.name == "Sensor"
    assert len(result.fields) == 3


@pytest.mark.level3
def test_parse_msg_field_names(tmp_path) -> None:
    """Field names are extracted correctly from .msg file."""
    msg_file = tmp_path / "Point.msg"
    msg_file.write_text("float64 x\nfloat64 y\nfloat64 z\n")
    result = parse_msg_file(str(msg_file))
    field_names = [f.field_name for f in result.fields]
    assert field_names == ["x", "y", "z"]


@pytest.mark.level3
def test_parse_msg_field_types(tmp_path) -> None:
    """Field types are extracted correctly from .msg file."""
    msg_file = tmp_path / "Point.msg"
    msg_file.write_text("float64 x\nfloat64 y\nfloat64 z\n")
    result = parse_msg_file(str(msg_file))
    field_types = [f.type_name for f in result.fields]
    assert field_types == ["float64", "float64", "float64"]


@pytest.mark.level3
def test_parse_msg_comments_ignored(tmp_path) -> None:
    """Comment lines (# ...) are ignored in .msg files."""
    msg_file = tmp_path / "Annotated.msg"
    msg_file.write_text("# This is a comment\nfloat64 value\n# Another comment\nstring label\n")
    result = parse_msg_file(str(msg_file))
    assert len(result.fields) == 2


@pytest.mark.level3
def test_parse_msg_empty_lines_ignored(tmp_path) -> None:
    """Empty lines are ignored in .msg files."""
    msg_file = tmp_path / "Spaced.msg"
    msg_file.write_text("float64 x\n\nfloat64 y\n\n")
    result = parse_msg_file(str(msg_file))
    assert len(result.fields) == 2


@pytest.mark.level3
def test_parse_msg_complex_type(tmp_path) -> None:
    """Complex (namespaced) types like std_msgs/Header are preserved."""
    msg_file = tmp_path / "Stamped.msg"
    msg_file.write_text("std_msgs/Header header\nfloat64 value\n")
    result = parse_msg_file(str(msg_file))
    assert result.fields[0].type_name == "std_msgs/Header"
    assert result.fields[0].field_name == "header"


@pytest.mark.level3
def test_parse_msg_array_type(tmp_path) -> None:
    """Array types like float64[] are preserved."""
    msg_file = tmp_path / "Array.msg"
    msg_file.write_text("float64[] ranges\nfloat32[] intensities\n")
    result = parse_msg_file(str(msg_file))
    assert result.fields[0].type_name == "float64[]"
    assert result.fields[0].field_name == "ranges"


# ---------------------------------------------------------------------------
# .srv parsing
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_parse_srv_request_and_response(tmp_path) -> None:
    """SrvDefinition has separate request and response field lists."""
    srv_file = tmp_path / "Command.srv"
    srv_file.write_text("float64 speed\nfloat64 turn\n---\nbool success\nstring message\n")
    result = parse_srv_file(str(srv_file))
    assert isinstance(result, SrvDefinition)
    assert result.name == "Command"
    assert len(result.request_fields) == 2
    assert len(result.response_fields) == 2


@pytest.mark.level3
def test_parse_srv_field_names(tmp_path) -> None:
    """Request/response field names are correctly parsed."""
    srv_file = tmp_path / "SetBool.srv"
    srv_file.write_text("bool data\n---\nbool success\nstring message\n")
    result = parse_srv_file(str(srv_file))
    assert result.request_fields[0].field_name == "data"
    assert result.response_fields[0].field_name == "success"
    assert result.response_fields[1].field_name == "message"


@pytest.mark.level3
def test_parse_srv_file_path_preserved(tmp_path) -> None:
    """SrvDefinition.file_path matches the path passed in."""
    srv_file = tmp_path / "Command.srv"
    srv_file.write_text("float64 speed\n---\nbool success\n")
    result = parse_srv_file(str(srv_file))
    assert result.file_path == str(srv_file)


# ---------------------------------------------------------------------------
# .action parsing  (goal --- result --- feedback sections)
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_parse_action_three_sections(tmp_path) -> None:
    """ActionDefinition has goal, result, feedback sections."""
    action_file = tmp_path / "Navigate.action"
    action_file.write_text(
        "float64 target_x\nfloat64 target_y\n"
        "---\n"
        "bool success\n"
        "---\n"
        "float64 progress\n"
    )
    result = parse_action_file(str(action_file))
    assert isinstance(result, ActionDefinition)
    assert result.name == "Navigate"
    assert len(result.goal_fields) == 2
    assert len(result.result_fields) == 1
    assert len(result.feedback_fields) == 1


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

@pytest.mark.level3
def test_msg_field_is_frozen() -> None:
    """MsgField is a frozen dataclass."""
    field = MsgField(type_name="float64", field_name="x")
    with pytest.raises((AttributeError, TypeError)):
        field.field_name = "mutated"  # type: ignore[misc]
