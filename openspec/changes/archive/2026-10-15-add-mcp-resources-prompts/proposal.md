# Change: Expose MCP resources + prompts (MM-40)

## Why

MintMory's two MCP servers expose only **tools** — no MCP **resources** (readable
data pulled on demand) or **prompts** (pre-authored, parameterized templates
invoked like slash-commands). FastMCP 3.4.2 supports both first-class
(`@mcp.resource`, `@mcp.prompt`).

Two concrete gaps an Opus deep-dive surfaced:
1. The memory **taxonomy** (8 categories, 12 link types, with descriptions) and the
   server **capabilities** (which providers/LLM are configured) are only available
   as prose in the `instructions` block or by reading the source — not as
   structured, pull-on-demand resources.
2. We have **already hand-written agent policy** in `docs/hermes-onboarding.md` (the
   recall→`session_feedback` discipline, the "remember this" rules, onboarding) that
   users currently **copy-paste**. That belongs as MCP **prompts** — discoverable
   slash-commands, not a doc to paste.

## What changes (static-first, token-disciplined)

**Resources (3, read-on-demand — no always-on body cost):**
- `mintmory://schema` (main) — the `MemoryCategory` / `ConceptLinkType` /
  `MemorySource` values WITH one-line descriptions; the `MemoryRecord` field list.
  Names are code-derived (iterate the enums); descriptions are a curated map kept
  beside the enums. Zero PII, self-maintaining.
- `mintmory://capabilities` (main) — config summary from `load_settings()`: embedding
  provider, LLM provider + enabled flag + model name, vision provider, dreaming
  LLM-on/off. **NEVER exposes `api_key` or absolute DB paths.**
- `mintmory://history/sources` (history server) — collections + per-collection counts
  + earliest/latest date (the read-only orientation view).

**Prompts (4, `mintmory_` prefixed to avoid cross-server collisions):**
- `mintmory_recall_before_task(intent, link_types?)` (main) — search first, thread
  the `session_id`, close with `session_feedback`. Formalizes
  hermes-onboarding.md:67-75.
- `mintmory_onboard(db_path?, llm_enabled?)` (main) — the onboarding Part-1 policy as
  a prompt. (The doc is KEPT as-is too, by decision — the prompt is a convenience.)
- `mintmory_session_closeout(session_id, useful_ids?, stale_ids?)` (main) — the
  feedback-loop discipline.
- `mintmory_changelog(repo?, since?, kind?)` (history) — the canonical
  `history_timeline` "what changed in repo X over N days" call.

Decisions baked in: **static-first** (no PII-bearing stats/memory-map/changelog
*resources* in v1); **keep the `instructions` block + onboarding doc unchanged**
(small manifest duplication accepted so non-resource clients keep inline guidance);
**read-only history server** gets only read-only resources/prompts (no
write-suggesting prompts there).

Out of scope: dynamic content resources (`stats`, `memory-map`, recent-changelog as
a *resource*) — deferred behind a future opt-in; the `what_cochanged_with` prompt
(the history MCP doesn't expose `changed-with` yet); trimming `instructions`.

## Impact

- Affected specs: **mcp** (new capability: resources + prompts surface).
- Affected code: `packages/mcp/src/mintmory/mcp/server.py` (2 resources + 3 prompts),
  `packages/mcp/src/mintmory/mcp/history_server.py` (1 resource + 1 prompt), a small
  `mcp/_schema.py`-style helper for the curated taxonomy map; tests.
- Token budget: only the manifest (names + one-line descriptions) is always paid —
  ~200-280 tokens across ~7 new items; bodies cost nothing until pulled/invoked.
  Respects MM-38. Clients without resource/prompt support simply don't list them
  (no breakage); all tools remain standalone (no tool depends on a resource/prompt).
- Migrations: none. Purely additive.
