"""Import resolution for Python files.

Ported from GitNexus python.ts import resolver logic.
"""

from __future__ import annotations

from pathlib import Path

from vector_graph._types import ExtractedImport


def resolve_import(
    import_info: ExtractedImport,
    from_file: str,
    project_root: str,
    all_files: set[str],
) -> str | None:
    """Resolve an import to a file path within the project.

    Algorithm:
    1. Relative imports (level > 0): navigate up from from_file directory.
    2. Package path: join project_root + module.replace('.', '/') + .py
    3. Proximity bare: check from_file's directory for name.py or name/__init__.py
    4. Suffix match: match against all_files by module path suffix
    5. Return None if unresolvable (stdlib etc.)

    Args:
        import_info:  The import statement to resolve.
        from_file:    Absolute path of the file that contains the import.
        project_root: Absolute path of the project root.
        all_files:    Set of all Python file paths in the project.

    Returns:
        Absolute path of the resolved file, or None.
    """
    if import_info.level > 0:
        return _resolve_relative(import_info, from_file, all_files)

    # Absolute import — try several strategies in order
    result = _resolve_package_path(import_info.module, project_root, all_files)
    if result:
        return result

    result = _resolve_proximity(import_info.module, from_file, all_files)
    if result:
        return result

    result = _resolve_suffix(import_info.module, all_files)
    if result:
        return result

    return None


# ---------------------------------------------------------------------------
# Strategy 1: relative imports (level > 0)
# ---------------------------------------------------------------------------

def _resolve_relative(
    import_info: ExtractedImport,
    from_file: str,
    all_files: set[str],
) -> str | None:
    """Resolve a relative import (from . import X, from .. import Y, etc.)."""
    from_path = Path(from_file)
    # Navigate up `level` directories from from_file's directory
    base = from_path.parent
    for _ in range(import_info.level - 1):
        base = base.parent

    module = import_info.module

    if not module:
        # `from . import something` -> package __init__.py
        candidate = base / "__init__.py"
        if str(candidate) in all_files:
            return str(candidate)
        return None

    # `from .sub.module import X` -> base/sub/module.py or base/sub/module/__init__.py
    parts = module.replace(".", "/")
    for suffix in (f"{parts}.py", f"{parts}/__init__.py"):
        candidate = base / suffix
        if str(candidate) in all_files:
            return str(candidate)

    return None


# ---------------------------------------------------------------------------
# Strategy 2: package path from project root
# ---------------------------------------------------------------------------

def _resolve_package_path(
    module: str,
    project_root: str,
    all_files: set[str],
) -> str | None:
    """Try project_root / module_path.py or module_path/__init__.py."""
    if not module:
        return None
    root = Path(project_root)
    parts = module.replace(".", "/")
    for suffix in (f"{parts}.py", f"{parts}/__init__.py"):
        candidate = root / suffix
        if str(candidate) in all_files:
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Strategy 3: proximity — look in the same directory
# ---------------------------------------------------------------------------

def _resolve_proximity(
    module: str,
    from_file: str,
    all_files: set[str],
) -> str | None:
    """Check from_file's directory for module.py or module/__init__.py."""
    if not module:
        return None
    from_dir = Path(from_file).parent
    # Only the last segment for bare import names like "models"
    name = module.split(".")[-1]
    for suffix in (f"{name}.py", f"{name}/__init__.py"):
        candidate = from_dir / suffix
        if str(candidate) in all_files:
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Strategy 4: suffix match
# ---------------------------------------------------------------------------

def _resolve_suffix(module: str, all_files: set[str]) -> str | None:
    """Match any file in all_files whose path ends with the module path."""
    if not module:
        return None
    # Convert dotted module to path fragment
    suffix_py = module.replace(".", "/") + ".py"
    suffix_init = module.replace(".", "/") + "/__init__.py"

    for file_path in all_files:
        normalized = file_path.replace("\\", "/")
        if normalized.endswith(suffix_py) or normalized.endswith(suffix_init):
            return file_path

    # Try matching only the last component (e.g. "something.models" -> "models.py")
    last = module.split(".")[-1]
    for file_path in all_files:
        normalized = file_path.replace("\\", "/")
        if normalized.endswith(f"/{last}.py"):
            return file_path

    return None
