"""Tiered name resolution context.

Ported from GitNexus resolution-context.ts.

Resolution order (first match wins):
  1. Same-file exact match            → SAME_FILE   (0.95)
  2. Named import binding chain       → IMPORT_SCOPED (0.9)
  3. Import-scoped via _import_map    → IMPORT_SCOPED (0.9)
  4. Global fallback                  → GLOBAL      (0.5)

If nothing matches at any tier, returns an empty TieredCandidates
with tier=GLOBAL (confidence 0.5).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from vector_graph._types import ResolutionTier, SymbolDef, TieredCandidates
from vector_graph.graph.symbol_table import SymbolTable


@dataclass(frozen=True)
class NamedImportBinding:
    """Describes a single `from <source_file> import <name>` binding."""

    imported_name: str
    source_file: str


class ResolutionContext:
    """Resolves a name to candidate SymbolDefs using tiered lookup."""

    def __init__(self, symbol_table: SymbolTable) -> None:
        self._symbol_table = symbol_table
        # file -> set of imported file paths (wildcard / star imports)
        self._import_map: dict[str, set[str]] = defaultdict(set)
        # file -> { imported_name -> NamedImportBinding }
        self._named_import_map: dict[str, dict[str, NamedImportBinding]] = defaultdict(dict)

    # ------------------------------------------------------------------
    # Import registration
    # ------------------------------------------------------------------

    def register_import(self, from_file: str, imported_file: str) -> None:
        """Register that from_file imports all exported symbols from imported_file."""
        self._import_map[from_file].add(imported_file)

    def register_named_import(
        self,
        from_file: str,
        imported_name: str,
        source_file: str,
    ) -> None:
        """Register a `from <source_file> import <imported_name>` in from_file."""
        binding = NamedImportBinding(
            imported_name=imported_name,
            source_file=source_file,
        )
        self._named_import_map[from_file][imported_name] = binding

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, name: str, from_file: str) -> TieredCandidates:
        """Resolve name from from_file using tiered lookup.

        Returns TieredCandidates; is_empty is True if no match at any tier.
        """
        # Tier 1: same-file
        same_file = self._symbol_table.lookup_exact(from_file, name)
        if same_file:
            return TieredCandidates(
                candidates=tuple(same_file),
                tier=ResolutionTier.SAME_FILE,
            )

        # Tier 2a: named import binding
        named_bindings = self._named_import_map.get(from_file, {})
        if name in named_bindings:
            binding = named_bindings[name]
            exact = self._symbol_table.lookup_exact(binding.source_file, name)
            if exact:
                return TieredCandidates(
                    candidates=tuple(exact),
                    tier=ResolutionTier.IMPORT_SCOPED,
                )

        # Tier 2b: import-scoped (filter global by import_map)
        imported_files = self._import_map.get(from_file)
        if imported_files:
            scoped = self._filter_by_files(name, imported_files)
            if scoped:
                return TieredCandidates(
                    candidates=tuple(scoped),
                    tier=ResolutionTier.IMPORT_SCOPED,
                )

        # Tier 3: global fallback
        global_defs = self._symbol_table.lookup_global(name)
        # Exclude definitions from from_file (already checked in tier 1)
        global_defs = [s for s in global_defs if s.file_path != from_file]
        return TieredCandidates(
            candidates=tuple(global_defs),
            tier=ResolutionTier.GLOBAL,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_by_files(self, name: str, files: set[str]) -> list[SymbolDef]:
        """Return global defs for name that belong to one of the given files."""
        all_defs = self._symbol_table.lookup_global(name)
        return [s for s in all_defs if s.file_path in files]
