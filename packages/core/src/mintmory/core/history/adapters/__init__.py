"""
history/adapters — per-agent session iterators.

Each sub-module exposes:
    iter_sessions(root=None) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]

Adapters are imported LAZILY inside backfill/sync to keep this package
importable before the adapter modules exist or their dependencies are available.
"""
