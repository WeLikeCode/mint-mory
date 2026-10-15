# Design: MCP resources + prompts (MM-40)

Additive only — no existing tool/behaviour changes. FastMCP 3.4.2:
`@mcp.resource(uri, ...)` (handler returns str / bytes / JSON-able; sync or async;
URI templates `mintmory://x/{param}` supported) and `@mcp.prompt()` (returns `str`
→ single user message, or `list[str|Message]`; params become prompt arguments).

## 1. Resources — main server (`server.py`)

### `mintmory://schema`
A small helper (e.g. `mcp/schema_resource.py`) builds a dict from the enums in
`core/types.py` plus a curated one-line description per value (the descriptions
already exist as inline comments next to each enum member — copy them into a
`dict[str, str]` kept beside the enums so names stay code-derived and descriptions
stay in sync):
```json
{ "categories": [{"value": "fact", "description": "World-state facts, config, URLs"}, ...8],
  "link_types": [{"value": "relates_to", "description": "General connection (symmetric)"}, ...12],
  "sources": ["user","agent","document","inference"],
  "memory_record_fields": ["id","content","category","entity_ids", ...] }
```
Returns a dict (FastMCP auto-JSON-serialises). Zero PII, deterministic. Names are
produced by iterating `MemoryCategory`/`ConceptLinkType`/`MemorySource`; a
`KeyError`-style guard ensures every enum value has a curated description (a unit
test asserts coverage so adding an enum value without a description fails CI).

### `mintmory://capabilities`
Reads `load_settings()` and returns ONLY non-secret fields:
```json
{ "embedding_provider": "hashing", "llm_provider": "ollama", "llm_enabled": true,
  "llm_model": "gemma4:e4b-it-qat", "vision_provider": "agent",
  "dreaming_llm_steps": false }
```
**Redaction is mandatory:** never include `llm.api_key`, `embed.api_key`, or any
absolute DB path. `llm_enabled` = `settings.llm.provider is not NONE`;
`dreaming_llm_steps` = same. Model name IS exposed (non-secret, useful).

## 2. Resource — history server (`history_server.py`, read-only)

### `mintmory://history/sources`
Reuses the `history_stats` aggregation body (already implemented at
history_server.py:136-188) refactored into a shared helper so both the tool and the
resource call it: returns `{by_collection, total_sessions, total_segments,
earliest, latest}` (no per-session content → low PII). Read-only.

## 3. Prompts — main server (`mintmory_` prefix)

Each returns a `str` (becomes a single user message) or a short `list[str]`.

- `mintmory_recall_before_task(intent: str, link_types: str = "")` — returns guidance:
  call `memory_search(query=intent, search_around_link_types=...)`, KEEP the returned
  `session_id`, and after acting call `session_feedback(session_id, useful_ids=...)`.
  Source policy: hermes-onboarding.md:67-75.
- `mintmory_onboard(db_path: str = "", llm_enabled: bool = False)` — the onboarding
  Part-1 policy (hermes-onboarding.md:14-91) rendered as a prompt; parameters lightly
  customise the text. Points the agent at `mintmory://schema` for the taxonomy.
- `mintmory_session_closeout(session_id: str, useful_ids: str = "", stale_ids: str = "")`
  — instructs the close-the-loop `session_feedback` call with the given ids.

## 4. Prompt — history server (read-only)

- `mintmory_changelog(repo: str = "", since: str = "90d", kind: str = "")` — returns
  guidance to call `history_timeline(since=since, repo=repo or None, kind=kind or None)`
  and read newest-first. MUST NOT suggest any write/mutate action (read-only server
  invariant).

## 5. Token / manifest discipline

Only `resources/list` + `prompts/list` manifests are always paid (~25-40 tok/item →
~7 items ≈ 200-280 tok across both servers). Bodies are pulled/invoked on demand.
Keep descriptions one line each. Do NOT trim `instructions` (decision) — accept the
small taxonomy duplication so non-resource clients keep inline guidance. Do not
exceed ~7-8 listed items without re-measuring (MM-38 discipline).

## 6. Edge cases / safety

- `capabilities`: settings load failure → return a minimal `{error: "...", ...}`
  without leaking; never raise into the client. Secrets never serialised (unit test
  greps the output for `api_key`/path).
- `schema`: every enum value must have a description (coverage test).
- History prompts/resources must reference only the 3 read tools (a test asserts no
  write-tool name appears in their text).
- Client without resource/prompt support: items simply aren't listed; tools
  unaffected; no tool depends on any resource/prompt.
- Prompt args are strings (MCP prompt args are strings); comma-lists like
  `useful_ids` are documented as comma-separated.

## 7. Testing

- Resource tests (FastMCP `Client`): `mintmory://schema` lists all 8 categories +
  12 link types each with a non-empty description + sources + field list; coverage
  test (every enum value described). `mintmory://capabilities` returns provider/flags
  and **contains no `api_key` and no absolute path** (assert). `mintmory://history/
  sources` returns by_collection + date range and no per-session content.
- Prompt tests: each prompt is listed with the `mintmory_` prefix; invoking returns
  messages mentioning the right tool(s); history prompts mention only read tools;
  parameters flow into the text.
- Manifest sanity: total new listed items ≤ 8.

## 8. Gates

`ruff` + `ruff format` clean; `mypy packages` clean (CI command); `pytest -q` ≥ 80%
full suite green (`--extra cochange` env); `openspec validate
add-mcp-resources-prompts --strict`.
