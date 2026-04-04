"""Intra-procedural type inference for Python.

Propagates types through assignments and annotations within function scopes.
Used by call_graph.py to resolve obj.method() calls to the correct class.
"""

from __future__ import annotations

from vector_graph._types import (
    ExtractedAssignment,
    ExtractedFunction,
    FileParseResult,
    NodeLabel,
    TypeBinding,
)
from vector_graph.graph.symbol_table import SymbolTable


# ---------------------------------------------------------------------------
# TypeMap
# ---------------------------------------------------------------------------

class TypeMap:
    """Lookup structure for inferred variable types.

    Keys: (file_path, scope, variable_name) -> TypeBinding
    For self.attr lookups: (file_path, class_name, "self.attr") -> TypeBinding
    """

    def __init__(self) -> None:
        # (file, scope, var) -> TypeBinding  (last-write-wins)
        self._bindings: dict[tuple[str, str, str], TypeBinding] = {}

    def add(self, binding: TypeBinding) -> None:
        key = (binding.source_file, binding.scope, binding.variable_name)
        self._bindings[key] = binding

    def lookup(self, file_path: str, scope: str, variable: str) -> TypeBinding | None:
        """Look up type for variable in scope, fall back to module scope."""
        result = self._bindings.get((file_path, scope, variable))
        if result is not None:
            return result
        # Fall back to module scope
        if scope != "<module>":
            return self._bindings.get((file_path, "<module>", variable))
        return None

    def lookup_attribute(
        self, file_path: str, scope: str, receiver: str
    ) -> str | None:
        """Resolve receiver type for attribute calls.

        For 'self.graph', looks up bindings keyed under the class scope.
        For a plain variable 'x', looks up its type in scope.
        Returns None when the type cannot be resolved.
        """
        # Handle 'self' — caller handles 'self.method()' differently
        if receiver == "self":
            return None

        # Handle 'self.attr' — look up under class scope
        if receiver.startswith("self."):
            for (fp, sc, var), binding in self._bindings.items():
                if fp == file_path and var == receiver:
                    return binding.inferred_type
            return None

        # Handle plain variable — look up its type in scope
        binding = self.lookup(file_path, scope, receiver)
        if binding is not None:
            return binding.inferred_type
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_known_class(name: str, symbol_table: SymbolTable) -> bool:
    """Return True when name is registered as a CLASS in the symbol table."""
    for sym in symbol_table.lookup_global(name):
        if sym.label == NodeLabel.CLASS:
            return True
    return False


def _infer_assignments(
    file_path: str,
    scope: str,
    assignments: tuple[ExtractedAssignment, ...],
    symbol_table: SymbolTable,
    type_map: TypeMap,
) -> None:
    """Infer types from a sequence of assignments and add them to type_map."""
    for assignment in assignments:
        if assignment.declared_type:
            # Explicit annotation wins with high confidence
            type_map.add(
                TypeBinding(
                    variable_name=assignment.name,
                    inferred_type=assignment.declared_type,
                    source_file=file_path,
                    scope=scope,
                    line=assignment.line,
                    confidence=0.95,
                )
            )
        elif assignment.value_type and _is_known_class(
            assignment.value_type, symbol_table
        ):
            # Constructor call to a known class
            type_map.add(
                TypeBinding(
                    variable_name=assignment.name,
                    inferred_type=assignment.value_type,
                    source_file=file_path,
                    scope=scope,
                    line=assignment.line,
                    confidence=0.9,
                )
            )


def _infer_init_self_attrs(
    file_path: str,
    class_name: str,
    init_fn: ExtractedFunction,
    result: FileParseResult,
    symbol_table: SymbolTable,
    type_map: TypeMap,
) -> None:
    """Bind self.X -> ClassName for assignments inside __init__.

    The parser records 'self.graph = KG()' as ExtractedAssignment(name='graph',
    value_type='KG').  We re-key these as (file, class_name, 'self.graph') so
    that lookup_attribute('self.graph') can find them.
    """
    # Collect assignments whose line falls inside __init__
    start = init_fn.start_line
    end = init_fn.end_line

    for assignment in result.assignments:
        if not (start <= assignment.line <= end):
            continue
        if not assignment.value_type:
            continue
        if not _is_known_class(assignment.value_type, symbol_table):
            continue

        # Store as 'self.<name>' under the class scope
        self_attr = f"self.{assignment.name}"
        type_map.add(
            TypeBinding(
                variable_name=self_attr,
                inferred_type=assignment.value_type,
                source_file=file_path,
                scope=class_name,
                line=assignment.line,
                confidence=0.9,
            )
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_type_map(
    parse_results: dict[str, FileParseResult],
    symbol_table: SymbolTable,
) -> TypeMap:
    """Build an intra-procedural type map from parse results.

    Phase 3c in the pipeline: runs after symbols are registered,
    before call resolution.

    Args:
        parse_results: Mapping of file_path -> FileParseResult.
        symbol_table:  Populated symbol table used to distinguish class
                       constructors from ordinary function calls.

    Returns:
        TypeMap containing all inferred variable-type bindings.
    """
    type_map = TypeMap()

    for file_path, result in parse_results.items():
        # 1. Module-level assignments
        _infer_assignments(
            file_path, "<module>", result.assignments, symbol_table, type_map
        )

        # 2. Function/method parameter annotations and body assignments
        for fn in result.functions:
            scope = fn.name

            # Parameter annotations (skip self/cls — they carry no useful type)
            for param, ptype in zip(fn.parameters, fn.parameter_types):
                if ptype and param not in ("self", "cls"):
                    type_map.add(
                        TypeBinding(
                            variable_name=param,
                            inferred_type=ptype,
                            source_file=file_path,
                            scope=scope,
                            line=fn.start_line,
                            confidence=0.95,
                        )
                    )

            # self.attr assignments in __init__
            if fn.name == "__init__" and fn.owner_class:
                _infer_init_self_attrs(
                    file_path,
                    fn.owner_class,
                    fn,
                    result,
                    symbol_table,
                    type_map,
                )

    return type_map
