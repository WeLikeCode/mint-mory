# Change (FUTURE-TRACK STUB — not for implementation yet): MCP code-execution mode

> Status: **deferred / design note only.** This is a placeholder capturing the
> "Code execution with MCP" article's larger idea so we can revisit it. It has no
> `specs/` delta and is intentionally NOT `openspec validate --strict`-complete.
> Do not implement without re-scoping. Companion to the shipped, high-ROI change
> `optimize-mcp-token-usage` (MM-38), which already captured ~80-90% of the win.

## Why (and why deferred)

Anthropic's "Code execution with MCP" reports up to a 98.7% token reduction
(150k→2k) by exposing MCP servers as a **code API the agent calls from a sandbox**,
so (a) tool definitions load on demand instead of all upfront, and (b) large
intermediate results stay in the execution environment and only distilled output
returns to the model.

That win scales with *many* servers and *huge* intermediate payloads. MintMory is
two small servers whose token cost is dominated by verbose per-hit JSON and broad
default limits — already addressed by MM-38's opt-in concise projections at Small
effort with zero new infrastructure. Full code-execution mode requires "a secure
execution environment with appropriate sandboxing, resource limits, and
monitoring" (the article's own stated cost) plus client support most MCP clients
(including Claude Code today) do not provide. So the marginal gain here is small
and the cost is large — defer.

## Sketch (when revisited)

- A generated, typed code API over the MintMory store/MCP tools the agent can
  import (progressive disclosure: load only the tool modules a task needs).
- A sandboxed executor (resource/time/memory limits, no network, read-scoped to
  the store) that runs agent-authored code which queries the store and returns only
  the distilled result — large intermediate sets never enter the model context.
- Reuse the existing query/search layer as the API surface; emit per-tool stubs.

## Revisit when

MintMory grows to many tools/servers, or starts returning genuinely large
multi-thousand-row payloads, or a target client gains first-class code-execution
support. Until then, prefer leaner results (MM-38) and pagination.
