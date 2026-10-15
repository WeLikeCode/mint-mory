# Implementation plan — `add-personal-notes` (orchestrator)

The executable contract is `design.md` (frozen) + `tasks.md` (disjoint file
ownership). This file records HOW the orchestrator runs the build.

## Execution strategy
Sonnet sub-agents implement against the frozen contract; an independent Opus
reviewer checks conformance; the Opus orchestrator applies all fixes and commits.

**Phase 1 — Implement (parallel Sonnet, disjoint files).** One agent per owner:
- core types+schema (G1) · storage+scoring (G2) · notes.py (G3) · dreaming (G4) ·
  config (G5) · MCP (G6a) · CLI (G6b) · API+openapi (G6c) · docs (G8).
Each codes against `design.md` only — no agent edits another's file, so the frozen
signatures (esp. the G2 storage helpers G3/G4 call) are the integration surface.

**Phase 2 — Tests (parallel Sonnet, after a barrier).** Test agents read the
*now-written* implementation (not just the contract) so tests match reality:
- core tests (G7.1) · transport tests (G7.2–7.4). Barrier is justified: tests are
  higher-fidelity when they can see the real code.

**Phase 3 — Verify (Sonnet).** `pytest` (cov ≥ 80) · `ruff check` · `ruff format
--check` · `mypy --strict`, repo-wide, via `uv --no-sync`.

**Phase 4 — Review (independent Opus).** Conformance to `design.md` + the §9
invariants: non-note ranking byte-identical at `note_bonus=0.0`; ANNOTATES
reverse-only auto-include; migration idempotent/best-effort; contradiction
authority deterministic offline; the four column lists in lockstep.

**Phase 5 — Orchestrator (Opus) fixes + commit.** Apply every reviewer finding,
re-run all gates, commit as the next MM milestone.

## Risk controls
- Frozen contract is the only cross-agent dependency (no shared-file edits).
- Tests-after-impl barrier cuts test-vs-impl drift.
- Opus review + orchestrator integration catch any residual divergence before commit.
