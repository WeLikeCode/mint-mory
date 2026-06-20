# Change: Automated `llm` vision provider (implement the Captioner seam)

**ID:** `add-llm-vision-provider`
**Status:** proposed
**Capabilities:** `image-understanding` (modified)
**Owner:** orchestrator (Opus)
**Builds on:** `add-image-understanding` (MM-18 — the Captioner seam, `image_jobs`
/ `image_caption_put`, `index-tree --vision`), mirrors the `MINTMORY_LLM_*` tier
shipped in MM-6 (`core/llm.py::LLMClient`).

## Why — automate G5 captioning

`add-image-understanding` (MM-18) built the whole image-understanding seam but
shipped **only** the `agent` provider: the active vision-capable agent reads each
image and writes the description out-of-band via `image_jobs` →
`image_caption_put`. That is the right default — the calling agent is usually a
better captioner than any small local model, at zero infra cost. But MM-18 left
`MINTMORY_VISION_PROVIDER=llm` as a **stub**: `captioner_from_settings` raises
`NotImplementedError` for `llm`, and `index-tree --vision` only *queues* raster
images as agent jobs.

There are deployments where no vision-capable agent is in the loop — a headless
`mintmory index-tree --vision` cron over the Hermes corpus, or an HTTP/MCP caller
that is text-only — yet a vision model **is** reachable (Ollama `llava`/`qwen2.5vl`
locally, or a Portkey/OpenAI-compatible gateway). For those, the ~12,900 indexed
raster images stay undescribed because nobody completes the agent loop. This change
implements the **automated** `llm` provider so MintMory can caption raster images
itself by calling an OpenAI-compatible **vision** model, reusing the exact
persistence path MM-18 already proved.

The fix mirrors two patterns the codebase already shipped:

- **MM-6 (`core/llm.py::LLMClient`)** — one stdlib-`urllib` OpenAI-compatible
  `/chat/completions` client (Bearer `api_key`, `timeout_s`, `gen_ai.*` OTel spans,
  `<think>` stripping), config-driven behind `LLMSettings`, fully offline by
  default. A vision call is the **same** `/chat/completions` POST with a multimodal
  user message (text part + `image_url` data-URL part). We reuse that machinery —
  **no new dependency**.
- **MM-18 (`image_caption_put`)** — the description is a `category=context,
  source=document, is_note=False` `MemoryRecord` carrying
  `metadata.kind=image_description`, `ANNOTATES`-linked to the file-record, with the
  archive-then-add **no-drift** discipline. The `llm` path produces only the
  description **text**; persistence goes through the unchanged `image_caption_put`.

Defaults reproduce today's behaviour exactly: `MINTMORY_VISION_PROVIDER` stays
`agent`, so `captioner_from_settings` still returns `None`, `index-tree --vision`
still queues agent jobs, and the new entry points no-op when no captioner is
configured. Nothing changes unless an operator opts in with
`MINTMORY_VISION_PROVIDER=llm`.

## What changes

1. **`LLMCaptioner` (the first real `Captioner`).** A concrete
   `core/vision.py::LLMCaptioner` implementing `Captioner.describe(image:
   ImageInput) -> ImageDescription`: build a `data:<mime>;base64,<…>` URL from the
   image bytes (downscaling via the existing lazy-Pillow `_downscale_bytes` helper
   when oversized, the SAME `downscale_max_px` cap MM-18 uses), POST an
   OpenAI-compatible `/chat/completions` request with a multimodal message
   `[{type:"text", text:<prompt>}, {type:"image_url", image_url:{url:<data-url>}}]`,
   read `choices[0].message.content`, strip `<think>`, and return the combined
   text. On any network/timeout/HTTP/empty-content failure it raises a clear
   `VisionError` so callers SKIP that one image and continue. `describe()` returns
   an `ImageDescription` whose `record` is **transient** (not yet persisted) when
   called directly; the apply paths in §3/§4 persist via `image_caption_put`.

2. **`captioner_from_settings` dispatch change.** The `LLM` branch stops raising
   and returns `LLMCaptioner(settings)`. `ocr` STAYS a stub (still raises). `agent`
   STAYS `None`. This is the ONLY behavioural change to the factory; every existing
   caller is untouched (they already handle `Captioner | None`).

3. **Config — `VisionSettings` gains the llm knobs.** Add (env `MINTMORY_VISION_*`,
   mirroring `LLMSettings`): `vision_timeout_s`, `vision_temperature`,
   `vision_max_tokens`, and a `vision_prompt` override. The existing `model`,
   `base_url`, `api_key` fields (added "for the seam" in MM-18) get **sensible
   non-None defaults** for the llm path (`base_url=http://localhost:11434/v1`,
   `model="llava"`, `vision_max_tokens=512`). These only matter when
   `provider=llm`; `provider` stays `agent` by default so every default still
   reproduces today.

4. **Automated apply — `caption_pending_images`.** A new core function
   `caption_pending_images(adapter, *, captioner, limit=0, budget=None,
   include_all=False) -> CaptionRunReport` walks the **pending** `image_jobs`
   (reusing `image_jobs` discovery + the no-drift predicate), obtains bytes per
   image (downloading online-only files under `budget`, honouring the size cap),
   calls `captioner.describe()`, and persists via `image_caption_put`. It
   skip+logs (counts) on `VisionError` or oversized/unreadable images and respects
   the no-drift predicate (already-described images are skipped unless
   `include_all`). Returns a `CaptionRunReport` (`described`, `skipped`, `failed`,
   `budget_hit`, per-image notes).

5. **`index-tree --vision` auto-run.** When `captioner_from_settings(settings.vision)`
   is **not None** (i.e. `llm`/future `ocr`), `index-tree --vision` runs the
   captioner **inline** for each raster image (caption + `image_caption_put`) under
   the SAME download budget + manifest, recording `index_mode='vision'` and a
   `content_hash`. SVG stays self-describing (pure-Python, unchanged). When the
   captioner is `None` (`agent`, the default) it keeps **queuing** raster jobs
   exactly as today. Without `--vision`: byte-for-byte unchanged.

6. **A standalone caption-run entry (no re-walk).** To caption already-indexed
   pending images via the configured provider WITHOUT re-walking the tree:
   - CLI: `mintmory vision-run` (`--limit`, `--budget`, `--all`) → calls
     `caption_pending_images`.
   - MCP: `vision_run(limit=0, budget_mb=0.0, include_all=False) -> dict`.
   - HTTP: `POST /images/caption-run` (body `{limit, budget_mb, include_all}`) →
     `CaptionRunReport`.
   These build the captioner from settings; when `provider=agent` (no captioner)
   they no-op cleanly (return a report with `described=0` and a `provider=agent`
   note) rather than erroring — captioning requires a server-side backend.

7. **Spec delta** — the `image-understanding` capability gains an "Automated `llm`
   vision provider" requirement and an "Automated caption run" requirement, and the
   provider-seam requirement is MODIFIED so `llm` is now implemented (only `ocr`
   remains a stub).

## What this explicitly does NOT do

- **No behaviour change to any existing path.** `MINTMORY_VISION_PROVIDER` defaults
  to `agent`: `captioner_from_settings` still returns `None`, `index-tree --vision`
  still queues agent jobs, `image_jobs` / `image_caption_put` / the agent loop are
  untouched, and `vision-run`/`vision_run`/`POST /images/caption-run` no-op when no
  captioner is configured. Every existing test stays green WITHOUT edits.
- **`ocr` stays a stub.** Only the `llm` branch becomes real;
  `captioner_from_settings` still raises `NotImplementedError` for `ocr`.
- **No new REQUIRED dependency.** The vision HTTP call reuses `core/llm.py`'s
  stdlib `urllib` machinery (no `openai` SDK). Pillow stays the optional `[image]`
  extra, lazy-imported only when downscaling. A `provider=llm` deployment needs only
  a reachable OpenAI-compatible vision endpoint.
- **No structured OCR/caption split.** A description stays ONE combined blob (what
  the image depicts + any legible text) — same contract MM-18 froze.
- **No new persistence shape.** The `llm` path writes the SAME `image_description`
  memory + `ANNOTATES` edge via the unchanged `image_caption_put`; no new table, no
  new column, no `index_mode` value (still `metadata`/`content`/`vision`), no
  `MemoryRecord`/`MemorySummary`/schema change. The single SQLite file is unchanged.
- **No SVG change.** SVGs remain self-describing via the pure-Python
  `extract_svg_text`; the llm provider is for **raster** images only.
- **No new `MINTMORY_LLM_*` coupling.** The vision tier is configured by its OWN
  `MINTMORY_VISION_*` knobs (a vision model is usually different from the text L3
  model), reusing the `LLMClient` *code* but not its *settings object*.

## Impact

- **Core:** `core/vision.py` — `VisionError`, `LLMCaptioner`, the
  `captioner_from_settings` `llm` branch, `caption_pending_images` +
  `CaptionRunReport`, a small shared `_chat_completion` poster (factored from /
  shared with `core/llm.py`); `core/config.py` —
  `VisionSettings.{vision_timeout_s, vision_temperature, vision_max_tokens,
  vision_prompt}` + non-None `model`/`base_url` defaults; `core/types.py` —
  `CaptionRunReport` (+ optional `CaptionRunItem`); `core/prompts.py` —
  `IMAGE_CAPTION_PROMPT` default.
- **CLI:** `packages/cli` — `index-tree --vision` auto-run when captioner not None;
  new `mintmory vision-run` command.
- **Transports:** `packages/mcp` (`vision_run` tool + `instructions` sentence);
  `packages/api` (`POST /images/caption-run` + `CaptionRunReport` response /
  `CaptionRunRequest` request schema); `docs/openapi/mintmory.yaml`.
- **Tests:** core (`LLMCaptioner.describe` request body + response parse + `<think>`
  strip + `VisionError` on network/timeout/empty, all with a stubbed
  `urlopen`/poster — NO real network; `captioner_from_settings` now returns
  `LLMCaptioner` for `llm` and still raises for `ocr`; `caption_pending_images`
  describes pending, skips on `VisionError`/oversized, respects no-drift +
  `include_all` + `limit` + budget; `VisionSettings` llm-field defaults/bounds) +
  each transport + `index-tree --vision` auto-run (captioner stubbed).
- **Docs:** README / agent doc — the `provider=llm` automated path
  (`index-tree --vision` inline + `vision-run`), `MINTMORY_VISION_*` vision-model
  knobs, and that `agent` stays default; `openspec/README.md` bullet.
- **Back-compat:** purely additive. Every new default reproduces today's behaviour;
  no new required dependency; no schema change; `ocr` stays stubbed; `agent` stays
  the default so all of MM-18's invariants hold unchanged.
