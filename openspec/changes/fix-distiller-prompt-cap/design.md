# Design: fix-distiller-prompt-cap

## Decisions

- **MODIFIED, not ADDED.** The base spec requirement `Bounded LLM distiller prompt`
  (`openspec/specs/agent-history/spec.md`) says "plus a small elision marker" and
  "the first ask and last turn SHALL always survive". Both are superseded, so the delta
  replaces that requirement and its scenario in full.
- **Cap floor.** `max_prompt_chars >= 100` is the supported range (default 12,000). Below it the
  final-guard arithmetic can go negative; the trailing `[:max_prompt_chars]` still keeps
  the length bound, which is all that is promised there.
- **Complexity.** The render-per-candidate checks are O(n^2) in the number of turns. Accepted:
  turns are already truncated to `max_turn_chars` and segments are bounded; the largest
  fixture is 400 turns.
- **OpenSpec validation is not a task gate**, as in `deployment-hardening` (its design.md
  `## Decisions`): the gates are the four Python commands of `.l4/config.yaml`.
