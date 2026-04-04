"""Type environment extraction from parsed Python files.

Builds a mapping of variable names to inferred types based on:
- Parameter type annotations
- Return type annotations
- Assignment type annotations
- Constructor calls: `x = MyClass()` -> x: MyClass
"""

from __future__ import annotations

from vector_graph._types import FileParseResult


def extract_type_env(parse_result: FileParseResult) -> dict[str, str]:
    """Build a type environment from a parse result.

    Maps variable names to their inferred types.

    Sources of type information (in priority order):
    1. Annotated assignments (`x: int = 5`)
    2. Constructor calls (`u = User()`)
    3. Import-aware constructor calls (`from .models import User; u = User()`)

    Args:
        parse_result: The result of parsing a single file.

    Returns:
        dict mapping variable name -> type string.
    """
    env: dict[str, str] = {}

    # Collect class names defined in this file
    local_classes: set[str] = {cls.name for cls in parse_result.classes}

    # Collect imported names that look like classes (capitalized)
    imported_classes: set[str] = set()
    for imp in parse_result.imports:
        for name in imp.names:
            if name and name[0].isupper():
                imported_classes.add(name)

    all_known_classes = local_classes | imported_classes

    # 1. Annotated assignments
    for assign in parse_result.assignments:
        if assign.declared_type:
            env[assign.name] = assign.declared_type

    # 2. Unannotated assignments with constructor calls
    for assign in parse_result.assignments:
        if assign.declared_type is None and assign.value_type is not None:
            if assign.value_type in all_known_classes:
                env[assign.name] = assign.value_type

    return env
