"""Dual-index symbol table.

Ported from GitNexus symbol-table.ts.

Indexes:
- _file_index:    dict[str, dict[str, list[SymbolDef]]]  file -> name -> defs
- _global_index:  dict[str, list[SymbolDef]]             name -> all defs
- _field_index:   dict[str, list[SymbolDef]]             "owner_id\\0name" -> defs
- _callable_index lazily maintained: Function/Method only
"""

from __future__ import annotations

from collections import defaultdict

from vector_graph._types import NodeLabel, SymbolDef

_CALLABLE_LABELS: frozenset[NodeLabel] = frozenset(
    {NodeLabel.FUNCTION, NodeLabel.METHOD}
)

_FIELD_SEP = "\0"


class SymbolTable:
    """Thread-unsafe, in-memory symbol table with three access patterns."""

    def __init__(self) -> None:
        # file_path -> { name -> [SymbolDef, ...] }
        self._file_index: dict[str, dict[str, list[SymbolDef]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # name -> [SymbolDef, ...]  (across all files)
        self._global_index: dict[str, list[SymbolDef]] = defaultdict(list)
        # "owner_id\0name" -> [SymbolDef, ...]
        self._field_index: dict[str, list[SymbolDef]] = defaultdict(list)
        # callable subset: name -> [SymbolDef, ...]
        self._callable_index: dict[str, list[SymbolDef]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def register(self, sym: SymbolDef) -> None:
        """Register a symbol into all applicable indexes."""
        self._file_index[sym.file_path][sym.name].append(sym)
        self._global_index[sym.name].append(sym)
        if sym.label in _CALLABLE_LABELS:
            self._callable_index[sym.name].append(sym)
        if sym.owner_id is not None:
            key = sym.owner_id + _FIELD_SEP + sym.name
            self._field_index[key].append(sym)

    def remove_file(self, file_path: str) -> None:
        """Remove all symbols registered from file_path."""
        if file_path not in self._file_index:
            return
        name_map = self._file_index.pop(file_path)
        for name, defs in name_map.items():
            for sym in defs:
                # Remove from global index
                if name in self._global_index:
                    self._global_index[name] = [
                        s for s in self._global_index[name] if s is not sym
                    ]
                    if not self._global_index[name]:
                        del self._global_index[name]
                # Remove from callable index
                if sym.label in _CALLABLE_LABELS and name in self._callable_index:
                    self._callable_index[name] = [
                        s for s in self._callable_index[name] if s is not sym
                    ]
                    if not self._callable_index[name]:
                        del self._callable_index[name]
                # Remove from field index
                if sym.owner_id is not None:
                    key = sym.owner_id + _FIELD_SEP + name
                    if key in self._field_index:
                        self._field_index[key] = [
                            s for s in self._field_index[key] if s is not sym
                        ]
                        if not self._field_index[key]:
                            del self._field_index[key]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def lookup_exact(self, file_path: str, name: str) -> list[SymbolDef]:
        """Return all defs with this name in this file (exact match)."""
        return list(self._file_index.get(file_path, {}).get(name, []))

    def lookup_global(self, name: str) -> list[SymbolDef]:
        """Return all defs with this name across all files."""
        return list(self._global_index.get(name, []))

    def lookup_fuzzy_callable(self, name: str) -> list[SymbolDef]:
        """Return Function/Method defs whose name contains name as a substring."""
        results: list[SymbolDef] = []
        for sym_name, defs in self._callable_index.items():
            if name in sym_name:
                results.extend(defs)
        return results

    def lookup_field_by_owner(self, owner_id: str, field_name: str) -> list[SymbolDef]:
        """Return field defs by owner node id and field name."""
        key = owner_id + _FIELD_SEP + field_name
        return list(self._field_index.get(key, []))
