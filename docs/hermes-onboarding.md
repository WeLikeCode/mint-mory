# Onboarding Hermes (or any MCP agent) to MintMory

MintMory is a local, typed, graph-linked memory system (SQLite + pure-Python
embeddings; optional LLM tier for summaries/contradictions). It speaks **MCP**, so
any MCP-capable agent — Hermes, Claude Code, Cursor, OpenCode — can use it.

This doc has two parts: a **paste-into-the-agent prompt** that makes the agent
install + verify + adopt MintMory autonomously, and the **reference details** behind
it. There is a one-shot health check (`mintmory doctor`) and a bulk loader
(`mintmory ingest`) so agents never hand-roll an add-per-file script.

---

## Part 1 — paste this into Hermes

```text
TASK: Add the MintMory typed-memory MCP server to yourself and start using it as
your persistent memory. MintMory is local, at
/path/to/mint-mory, with a populated DB at
~/.mintmory/hermes.db. Do the steps IN ORDER and prove each with real output.
Never claim success you have not verified.

STEP 1 — Pre-flight (no changes). Use the built-in health check:
  MINTMORY_DB=~/.mintmory/hermes.db \
    uv run --project /path/to/mint-mory mintmory doctor
  Expect: database ok, embedder hashing, vector search available. (LLM tier shows
  "disabled" unless MINTMORY_LLM_* is set — that is fine for read/write.)
  If `database` is FAIL, STOP and report.

STEP 2 — Register the MCP server. Edit ~/.hermes/config.yaml and add this block
under the existing `mcp_servers:` map (alphabetical, between `minimax:` and
`romania-memory:`). Match indentation EXACTLY (2 spaces for the name, 4 for keys).
Do NOT touch any other entry or secret:

  mintmory:
    command: uv
    args:
    - run
    - --project
    - /path/to/mint-mory
    - mintmory-mcp
    enabled: true
    env:
      MINTMORY_DB: /Users/you/.mintmory/hermes.db
      MINTMORY_EMBED_PROVIDER: hashing
      MINTMORY_LLM_PROVIDER: openai
      MINTMORY_LLM_BASE_URL: http://localhost:8789/v1
      MINTMORY_LLM_API_KEY: hermes-agent
      MINTMORY_LLM_MODEL: MiniMax-M2.7

Then verify the file still parses:
  python3 -c "import yaml; yaml.safe_load(open('/Users/you/.hermes/config.yaml')); print('yaml ok')"
If it does not print "yaml ok", restore your edit and stop.

STEP 3 — Load it. MCP servers load at startup; restart your Hermes session (or
reload MCP config). Confirm these tools appear: memory_add, memory_search,
memory_get, memory_archive, memory_stats, memory_dream, session_feedback,
summary_list, summary_get.

STEP 4 — Smoke-test (via tool calls):
  memory_stats()                                  -> total_memories > 0
  memory_search(query="iOS cancel endpoint bug")  -> memories + a session_id
  memory_add(content="Hermes connected to MintMory on <today>", category="episodic")
  memory_get(<id from memory_add>)                -> echoes it back
Report the session_id and the new id.

STEP 5 — Adopt this memory policy every task:
  • RECALL FIRST: memory_search(query=<intent>) before acting; for related items
    pass search_around_link_types=["relates_to"]; KEEP the returned session_id.
  • WRITE durable knowledge: memory_add(content, category) where category is one of
    identity | preference | skill | context | fact | episodic | temporal |
    relationship. One idea per memory; preserve concrete names/numbers/dates.
  • CLOSE THE LOOP: after answering, session_feedback(session_id, useful_ids=[...],
    stale_ids=[...], confidence_rating=1..5, reasoning="..."). The memory
    self-improves from this — no human needed.
  • CONSOLIDATE: when idle, memory_dream(intensity="full") to build links +
    summaries and resolve contradictions (uses MiniMax-M2.7 via the gateway; minute-
    scale — run off the hot path).
  • BULK LOAD: to ingest many files, do NOT script add-per-file — run
    `mintmory ingest <paths...> --category <cat>` (chunks + dedups automatically).
    PDF/DOCX/XLSX/PPTX/HTML/CSV are auto-converted to markdown via markitdown when
    the optional `docs` extra is installed (`uv sync --extra docs`); toggle with
    `--convert/--no-convert`. Without the extra, binary docs are skipped with an
    install hint and text/markdown files still ingest.

NOTES:
  • Model id is MiniMax-M2.7 (with the "MiniMax-" prefix); bare "M2.7" is rejected.
  • Embeddings are local/pure-Python; only summaries + resolution use the gateway.
  • The DB is single-writer: with parallel sub-agents let one own writes.
  • VERIFY, DON'T ASSERT: show real output per step; if a step fails, stop and say so.
```

---

## Part 2 — reference

**Tools (9):** `memory_add`, `memory_search`, `memory_get`, `memory_archive`,
`memory_stats`, `memory_dream`, `session_feedback`, `summary_list`, `summary_get`.
The MCP server self-describes via its FastMCP `instructions` (the 8 categories, 11
link types, `search_around`, the feedback loop, dreaming).

**CLI helpers an agent can shell out to:**
- `mintmory doctor` — one-shot health board (DB, embedder, vector search, LLM tier,
  linking config). Exit 0 healthy, 1 DB-broken, 2 LLM-unreachable.
- `mintmory ingest <paths...> [--category fact] [--glob "*.md,*.txt"] [--chunk-chars 4000] [--convert/--no-convert] [--dream]`
  — bulk-load files/dirs; chunks large files (≤10k-char limit) and **skips exact
  duplicates by default** (idempotent re-runs; `--allow-duplicates` to force).
  With the optional `docs` extra (`uv sync --extra docs`), PDF/DOCX/XLSX/PPTX/HTML/CSV
  are auto-converted to markdown via markitdown; `--no-convert` disables this. Without
  the extra, binary docs are skipped with an install hint while text/markdown still ingest.

**Config (all env, read by the server/CLI):** `MINTMORY_DB`, `MINTMORY_EMBED_PROVIDER`
(default `hashing`), and the LLM tier `MINTMORY_LLM_PROVIDER|BASE_URL|MODEL|API_KEY`
(default `provider=none` = fully offline, L3 disabled). Point the LLM tier at the
self-hosted Portkey gateway (`http://localhost:8789/v1`, a `pk-…`/`hermes-agent`
key, model `MiniMax-M2.7`) for the cloud quality tier.

**Caveats:** session discipline (thread `session_id` search→feedback) and explicit
`memory_add` are on the agent; contradiction *detection* runs during dreaming, not
at add-time; SQLite is single-writer.

---

## Personal notes (`memory_note`)

A **note** is a user-authored memory with elevated authority. Use it only when the
user explicitly asks you to remember something ("remember that...", "note that...",
"don't forget..."). For facts you inferred or extracted, use `memory_add` —
notes carry different guarantees and should not be used as a general capture sink.

### Capture guardrail

Call `memory_note` only on EXPLICIT remember-this requests. The tool docstring
enforces this in prose; the agent must also enforce it in behaviour. Using
`memory_note` for every observation degrades the authority guarantee and clutters
the notes surface.

### Time semantics — ISO dates, agent-supplied

MintMory does **no date parsing**. If the user says "remind me next Tuesday" or
"note this for the sprint starting July 1st", YOU convert the natural-language
expression to an ISO-8601 date string (`2026-07-01`) before calling the tool.
Pass the result as `when` (salience date, stored in `valid_from`) or `until`
(deadline). When `when` is provided the note is automatically categorised
`temporal`; otherwise it defaults to `episodic`.

```
memory_note(
    content="Review the AXIS 524 edge-case before go-live",
    when="2026-07-01",          # you converted "July 1st" to ISO
    until="2026-07-05",         # optional deadline
)
```

### Anchoring to existing memories

The optional `about` parameter anchors a note to an existing memory. MintMory
resolves the anchor phrase **conservatively**: it searches existing memories for
the phrase and creates a hard `ANNOTATES` link only if one memory is clearly
dominant (holds ≥ 60% of candidate relevance). If the match is ambiguous it falls
back to a topic anchor (folding the phrase's entities into the note) and stores the
raw phrase for filtering. This means an anchor is never guessed wildly; when in
doubt, the note is still stored and findable via entity/topic recall.

```
memory_note(
    content="The iOS cancel-endpoint race was fixed in AXIS-524",
    about="iOS cancel endpoint bug",   # anchors to the relevant memory if confident
)
```

The `NoteResult` returned by the tool tells you which path was taken:
`anchor_kind`: `"memory"` (hard link created), `"topic"` (entities folded, no
link), or `"none"` (no `about` supplied). The `anchor_memory_id` field gives the
linked memory's id when a hard link was made.

### Auto-include on search

When a search result has annotating notes, `memory_search` returns them in
`notes_on_results` (a separate field, keyed by result memory id). Notes in this
field are context, not direct hits — they do not consume result slots or affect
`total_found`. Inspect this field to surface relevant user notes alongside the
primary results without extra tool calls.

### Listing and filtering notes

```
notes_list()                        # all notes, newest first
notes_list(about="Tokyo trip")      # notes anchored to or mentioning "Tokyo trip"
notes_list(upcoming=True)           # future-dated (valid_from > now), soonest first
notes_list(overdue=True)            # past-due and not archived, oldest first
```

`upcoming` and `overdue` are mutually exclusive — the tool raises an error if
both are set. Archived notes are excluded from all views by default.

### Done = archive

Marking a note done means archiving it: call `memory_archive(<note_id>)`. An
archived note drops out of `notes_list`, out of auto-include, and out of the
authority scoring path. It is NOT deleted — the record and its `ANNOTATES` links
remain for audit/lineage. A note is **never** auto-archived by the staleness or
dreaming pipeline; only an explicit archive call (or a contradiction resolved by
another note with higher authority) removes it from the active surface.
</content>
