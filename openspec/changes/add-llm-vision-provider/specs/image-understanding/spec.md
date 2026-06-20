# Capability: image-understanding (delta)

## ADDED Requirements

### Requirement: Automated `llm` vision provider
The system SHALL implement the `llm` vision provider as a concrete `Captioner`
(`LLMCaptioner`) that captions a raster image by calling an OpenAI-compatible
**vision** model, reusing the stdlib-`urllib` `/chat/completions` machinery of the
configured-LLM tier (`core/llm.py`) — with NO new required dependency (no `openai`
SDK). This SHALL be opt-in via `MINTMORY_VISION_PROVIDER=llm`; the default provider
SHALL remain `agent`, so every existing path is unchanged when `llm` is not
selected. The `ocr` provider SHALL remain a stub.

`captioner_from_settings(settings)` SHALL return an `LLMCaptioner` instance when
`provider=llm` (it SHALL NO LONGER raise for `llm`); it SHALL still return `None`
for `agent` and still raise `NotImplementedError` for `ocr`. The factory SHALL
remain the only place that branches on the provider; `image_jobs` and
`image_caption_put` SHALL NOT call it.

`LLMCaptioner.describe(image: ImageInput) -> ImageDescription` SHALL:
- obtain the image bytes from `image.data` when present, else by reading
  `image.path`; an unreadable path SHALL raise `VisionError`;
- downscale oversized bytes via the existing lazy-Pillow helper (the SAME
  `downscale_max_px` cap the agent path uses), never raising on a corrupt image;
- build a `data:<mime>;base64,<…>` URL and POST an OpenAI-compatible
  `/chat/completions` request whose user message `content` is a multimodal list:
  a `{"type":"text","text":<prompt>}` part (the prompt being
  `MINTMORY_VISION_VISION_PROMPT` when set, else a built-in default that asks for a
  description plus verbatim legible text) and a
  `{"type":"image_url","image_url":{"url":<data-url>}}` part — including `model`,
  `temperature` (`MINTMORY_VISION_VISION_TEMPERATURE`), `max_tokens`
  (`MINTMORY_VISION_VISION_MAX_TOKENS`), and `stream:false`, with an
  `Authorization: Bearer <api_key>` header iff `MINTMORY_VISION_API_KEY` is set, to
  `MINTMORY_VISION_BASE_URL` + `/chat/completions`, under
  `MINTMORY_VISION_VISION_TIMEOUT_S`;
- read `choices[0].message.content`, strip `<think>…</think>` reasoning blocks, and
  return the trimmed combined text as the description;
- raise `VisionError` (a clear core exception) on any network error, timeout,
  non-2xx HTTP status, unparseable JSON, unexpected response shape, or
  empty/whitespace/reasoning-only content — so callers SKIP the one image and
  continue.

`describe()` SHALL produce the description TEXT only; it SHALL return an
`ImageDescription` whose `record` is a **transient** (un-persisted) `MemoryRecord`
(`category=context`, `source=document`, `is_note=false`,
`metadata.kind="image_description"`). Persistence SHALL go through the unchanged
`image_caption_put` path (archive-then-add, `ANNOTATES` `LinkSource.INFERENCE`,
no-drift), invoked by the apply paths — `describe()` itself SHALL NOT write a row.

A new `VisionSettings` group SHALL gain the llm-tier knobs (env
`MINTMORY_VISION_*`, mirroring `LLMSettings`): defaulted `base_url`
(`http://localhost:11434/v1`) and `model` (a vision-model default), plus
`vision_timeout_s` (default 120, bounds 1..600), `vision_temperature` (default 0),
`vision_max_tokens` (default 512, bounds 1..8192), and `vision_prompt` (default
empty = use the built-in). These SHALL affect only the `llm` path; `provider` SHALL
default to `agent`. The vision tier SHALL read its OWN `MINTMORY_VISION_*` settings,
NOT `MINTMORY_LLM_*` (no `LLMSettings` change).

#### Scenario: agent stays the default (no behaviour change)
- **WHEN** `captioner_from_settings()` is called with the default settings
  (`provider=agent`)
- **THEN** it returns `None` (the agent-supplied loop is used), exactly as before
  this change.

#### Scenario: llm provider returns a captioner
- **WHEN** `captioner_from_settings()` is called with
  `MINTMORY_VISION_PROVIDER=llm`
- **THEN** it returns an `LLMCaptioner` instance (it does NOT raise).

#### Scenario: ocr provider still raises
- **WHEN** `captioner_from_settings()` is called with
  `MINTMORY_VISION_PROVIDER=ocr`
- **THEN** it raises `NotImplementedError` directing the operator to
  `MINTMORY_VISION_PROVIDER=agent`.

#### Scenario: describe posts a multimodal vision request
- **WHEN** `LLMCaptioner.describe(image)` is called for a raster image (with the
  HTTP poster stubbed)
- **THEN** the request body's user message `content` is a list containing a text
  part (the caption prompt) and an `image_url` part whose URL is a
  `data:<mime>;base64,…` data URL, and the body carries `model`, `max_tokens`,
  `temperature`, and `stream:false`.

#### Scenario: describe returns the model's combined text with reasoning stripped
- **WHEN** the stubbed vision model replies with
  `"<think>plan</think>A login screen titled 'Sign in'."`
- **THEN** `describe()` returns an `ImageDescription` whose `record.content` is
  `"A login screen titled 'Sign in'."` (the `<think>` block removed, trimmed) and
  whose `record` is transient (`is_note=false`, `metadata.kind="image_description"`).

#### Scenario: a failed vision call raises VisionError
- **WHEN** the vision endpoint times out, returns a non-2xx status, returns
  unparseable JSON, or returns empty/reasoning-only content
- **THEN** `describe()` raises `VisionError` (and does not return a description).

#### Scenario: Pillow absent still yields a data URL
- **WHEN** the optional `[image]` extra is not installed and `describe()` is called
- **THEN** the image bytes are embedded un-downscaled in the data URL and the
  request is still well-formed (no crash).

### Requirement: Automated caption run over pending images
The system SHALL provide a core function `caption_pending_images(adapter, *,
captioner, limit=0, budget=None, include_all=False, settings=None) ->
CaptionRunReport` that captions already-indexed PENDING raster images with a
server-side `captioner` and persists each via `image_caption_put`, WITHOUT
re-walking the filesystem. It SHALL discover work through `image_jobs` (the SAME
no-drift predicate as the agent loop), and for each job SHALL:
- skip an oversized job (no embeddable bytes within the size cap), counting it as
  skipped;
- obtain the image bytes (the job's embedded base64 when present, else by reading
  the path); online-only downloads SHALL count against `budget` (falling back to
  `MINTMORY_VISION_MAX_DOWNLOAD_MB` when `budget` is `None`), and once the budget is
  exhausted further online-only images SHALL be skipped (the report's `budget_hit`
  SHALL be set);
- call `captioner.describe(...)`; a `VisionError` SHALL be caught and counted as a
  failure, and the run SHALL continue to the next image (one bad image SHALL NOT
  abort the run);
- on success, persist the description via `image_caption_put` and count it as
  described.

`include_all=false` (default) SHALL process only pending images (already-described
images are absent from `image_jobs`), making re-runs incremental; `include_all=true`
SHALL re-caption every raster image. `limit > 0` SHALL cap the work AFTER selection.
The function SHALL return a `CaptionRunReport` (`described`, `skipped`, `failed`,
`budget_hit`, `provider`, and per-image `items`).

A new `CaptionRunReport` model (and `CaptionRunItem`) SHALL carry the run result;
they are transport data and are NOT persisted.

#### Scenario: pending images are captioned and persisted
- **WHEN** `caption_pending_images(adapter, captioner=<server-side captioner>)` is
  called and the store has two pending raster image file-records
- **THEN** both images get an `image_description` memory persisted (ANNOTATES-linked
  to their file-records), the report's `described` is 2, and a subsequent default
  `image_jobs()` returns neither image (no-drift).

#### Scenario: one failing image does not abort the run
- **WHEN** the captioner raises `VisionError` for one of several pending images
- **THEN** that image is counted under `failed`, the remaining images are still
  captioned, and the run completes (it does not raise).

#### Scenario: oversized image is skipped
- **WHEN** a pending raster image exceeds `MINTMORY_VISION_MAX_IMAGE_MB`
- **THEN** it is counted under `skipped` (not described) and the run continues.

#### Scenario: online-only budget caps the run
- **WHEN** several online-only images are pending and `budget` is smaller than their
  combined size
- **THEN** images beyond the budget are skipped, `budget_hit` is true, and the
  images within budget are captioned.

### Requirement: Server-side caption-run transports
The automated caption run SHALL be reachable through three thin transports that
build the captioner from `VisionSettings` and call `caption_pending_images`:

- CLI: `mintmory vision-run` (`--limit`, `--budget`, `--all/--needed`).
- MCP: `vision_run(limit=0, budget_mb=0.0, include_all=false) -> dict`.
- HTTP: `POST /images/caption-run` (body `{limit, budget_mb, include_all}` →
  `CaptionRunReport`). `docs/openapi/mintmory.yaml` SHALL define the path and the
  `CaptionRunRequest` / `CaptionRunReport` / `CaptionRunItem` schemas.

When the configured provider is `agent` (no server-side captioner), these entries
SHALL NOT call `caption_pending_images`; they SHALL no-op cleanly — returning a
`CaptionRunReport` with `provider="agent"` and zero counts (CLI: a clear message +
zero exit), since captioning requires a server-side backend. When the provider is
`ocr` (a stub), they SHALL surface the `NotImplementedError` clearly (CLI non-zero
exit; MCP `{"error":"not_implemented", …}`; HTTP 422 with the message). The
existing image-understanding endpoints/tools (`image_jobs`, `image_caption_put`,
`GET /images/jobs`, `PUT /images/{file_id}`) SHALL be unchanged.

#### Scenario: caption-run is a no-op under the default provider
- **WHEN** `POST /images/caption-run` is called with `MINTMORY_VISION_PROVIDER=agent`
  (the default)
- **THEN** the response is 200 with `provider="agent"` and `described=0`, and no
  vision model is called.

#### Scenario: MCP vision_run captions then the image drops from default jobs
- **WHEN** `vision_run()` is called with `provider=llm` (the vision HTTP poster
  stubbed) and pending raster images exist, then `image_jobs()` (default) is called
- **THEN** the captioned images are not present in the returned jobs.

#### Scenario: caption-run surfaces the ocr stub clearly
- **WHEN** `POST /images/caption-run` is called with `MINTMORY_VISION_PROVIDER=ocr`
- **THEN** the response is 422 with a clear "ocr is not implemented" message (not a
  500).

## MODIFIED Requirements

### Requirement: Vision provider seam (llm implemented; ocr stub in v1)
The system SHALL provide a `Captioner` protocol (`describe(image: ImageInput) ->
ImageDescription`) and a single factory `captioner_from_settings(settings) ->
Captioner | None` selected by `MINTMORY_VISION_PROVIDER`, so that backends drop in
without changing any caller. With this change:

- `agent` (DEFAULT) SHALL resolve to `None` (no server-side backend; the
  agent-supplied prepare/apply loop is used instead).
- `llm` SHALL resolve to a concrete `LLMCaptioner` that calls an OpenAI-compatible
  vision tier (`MINTMORY_VISION_BASE_URL` / `_MODEL` / `_API_KEY` plus the
  `vision_*` tuning knobs). It SHALL NO LONGER raise.
- `ocr` SHALL raise a clear `NotImplementedError` (local tesseract behind the
  optional `[ocr]` extra remains a future drop-in).

The factory SHALL be the only place that branches on the provider; `image_jobs` and
`image_caption_put` SHALL NOT call it (the agent path needs no captioner). Neither
Pillow (`[image]`) nor pytesseract (`[ocr]`) SHALL be a required dependency; both
SHALL be lazy-imported, and the agent path SHALL function without them. The `llm`
path SHALL add NO new required dependency — it reuses the stdlib-`urllib`
`/chat/completions` poster from `core/llm.py`.

#### Scenario: agent provider has no backend
- **WHEN** `captioner_from_settings()` is called with the default settings
  (`provider=agent`)
- **THEN** it returns `None` (and the agent-supplied loop is used).

#### Scenario: llm provider resolves to LLMCaptioner
- **WHEN** `captioner_from_settings()` is called with
  `MINTMORY_VISION_PROVIDER=llm`
- **THEN** it returns an `LLMCaptioner` (a concrete `Captioner`), and no exception
  is raised.

#### Scenario: ocr provider raises clearly
- **WHEN** `captioner_from_settings()` is called with
  `MINTMORY_VISION_PROVIDER=ocr`
- **THEN** it raises `NotImplementedError` with a message directing the operator to
  use `MINTMORY_VISION_PROVIDER=agent`.
