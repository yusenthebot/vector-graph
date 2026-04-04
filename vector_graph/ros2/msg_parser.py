"""ROS2 message definition parser (.msg / .srv / .action files).

Parses ROS2 IDL-like files using line-by-line text processing (no external deps).

Format rules:
- Lines starting with # are comments — ignored
- Empty lines are ignored
- Fields are: <type> <name> [= <default>]
- .srv files use --- to separate request and response sections
- .action files use --- to separate goal, result, and feedback sections
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types (all frozen)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MsgField:
    """A single field in a message definition."""

    type_name: str
    field_name: str
    default_value: str | None = None


@dataclass(frozen=True)
class MsgDefinition:
    """Parsed .msg file."""

    name: str
    file_path: str
    fields: tuple[MsgField, ...]


@dataclass(frozen=True)
class SrvDefinition:
    """Parsed .srv file with request and response sections."""

    name: str
    file_path: str
    request_fields: tuple[MsgField, ...]
    response_fields: tuple[MsgField, ...]


@dataclass(frozen=True)
class ActionDefinition:
    """Parsed .action file with goal, result, and feedback sections."""

    name: str
    file_path: str
    goal_fields: tuple[MsgField, ...]
    result_fields: tuple[MsgField, ...]
    feedback_fields: tuple[MsgField, ...]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_msg_file(file_path: str) -> MsgDefinition:
    """Parse a ROS2 .msg file.

    Args:
        file_path: Absolute path to the .msg file.

    Returns:
        MsgDefinition with the file's fields.
    """
    source = Path(file_path).read_text(encoding="utf-8")
    name = Path(file_path).stem
    fields = _parse_fields(source)
    return MsgDefinition(name=name, file_path=file_path, fields=tuple(fields))


def parse_srv_file(file_path: str) -> SrvDefinition:
    """Parse a ROS2 .srv file.

    The file is split on --- into request and response sections.

    Args:
        file_path: Absolute path to the .srv file.

    Returns:
        SrvDefinition with request_fields and response_fields.
    """
    source = Path(file_path).read_text(encoding="utf-8")
    name = Path(file_path).stem
    sections = _split_sections(source)
    request_fields = _parse_fields(sections[0]) if len(sections) > 0 else []
    response_fields = _parse_fields(sections[1]) if len(sections) > 1 else []
    return SrvDefinition(
        name=name,
        file_path=file_path,
        request_fields=tuple(request_fields),
        response_fields=tuple(response_fields),
    )


def parse_action_file(file_path: str) -> ActionDefinition:
    """Parse a ROS2 .action file.

    The file is split on --- into goal, result, and feedback sections.

    Args:
        file_path: Absolute path to the .action file.

    Returns:
        ActionDefinition with goal_fields, result_fields, feedback_fields.
    """
    source = Path(file_path).read_text(encoding="utf-8")
    name = Path(file_path).stem
    sections = _split_sections(source)
    goal_fields = _parse_fields(sections[0]) if len(sections) > 0 else []
    result_fields = _parse_fields(sections[1]) if len(sections) > 1 else []
    feedback_fields = _parse_fields(sections[2]) if len(sections) > 2 else []
    return ActionDefinition(
        name=name,
        file_path=file_path,
        goal_fields=tuple(goal_fields),
        result_fields=tuple(result_fields),
        feedback_fields=tuple(feedback_fields),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SEPARATOR = "---"


def _split_sections(source: str) -> list[str]:
    """Split source text on --- separators into sections."""
    sections: list[str] = []
    current: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped == _SEPARATOR:
            sections.append("\n".join(current))
            current = []
        else:
            current.append(line)
    sections.append("\n".join(current))
    return sections


def _parse_fields(section: str) -> list[MsgField]:
    """Parse field lines from a section of a .msg / .srv / .action file."""
    fields: list[MsgField] = []
    for line in section.splitlines():
        # Strip inline comments
        if "#" in line:
            line = line[: line.index("#")]
        line = line.strip()
        if not line:
            continue
        field = _parse_field_line(line)
        if field is not None:
            fields.append(field)
    return fields


def _parse_field_line(line: str) -> MsgField | None:
    """Parse a single field line: <type> <name> [= <default>]."""
    # Split on '=' to check for default value
    if "=" in line:
        decl, _, default = line.partition("=")
        decl = decl.strip()
        default = default.strip()
    else:
        decl = line.strip()
        default = None

    parts = decl.split()
    if len(parts) < 2:
        return None

    type_name = parts[0]
    field_name = parts[1]
    return MsgField(type_name=type_name, field_name=field_name, default_value=default or None)
