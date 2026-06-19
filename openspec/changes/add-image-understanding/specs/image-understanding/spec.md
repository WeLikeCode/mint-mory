# Capability: image-understanding (delta)

## ADDED Requirements

### Requirement: Agent-supplied image descriptions (BYO-vision)
The system SHALL support describing already-indexed images from text supplied by
the active (vision-capable) agent, as the default and only v1 implementation of
image understanding. This SHALL NOT require any configured vision backend: it MUST
work with the defaults (`MINTMORY_VISION_PROVIDER=agent`) and no optional extras
installed, and MUST NOT call any model in the agent path. A description SHALL be
ONE combined blob (what the image depicts together with any legible text); a
structured OCR/caption split is out of scope.

Discovery SHALL operate on the already-indexed image FILE-RECORDS (the
`category=context, source=document` memories the tree indexer writes, whose
`metadata.ext` is a raster image suffix) and SHALL NOT walk the filesystem. The
system SHALL expose two core functions:

- `image_jobs(adapter, *, include_all=False, include_bytes=False, limit=0,
  settings=None) -> list[ImageJob]` — returns the raster image file-records the
  agent should describe. By default (`include_all=False`) it SHALL return only
  raster images that NEED a (re)description (the predicate below). With
  `include_all=True` it SHALL return every raster image file-record regardless of
  existing descriptions. SVG file-records and proprietary-format file-records
  SHALL NEVER be returned as agent jobs. Results SHALL be in a deterministic order
  (by `rel` then `file_id`); `limit > 0` SHALL cap the list AFTER selection.
- `image_caption_put(adapter, file_id_or_path, description, *, settings=None) ->
  ImageDescription` — persists the agent's combined text as a new
  `MemoryRecord` (`category=context`, `source=document`, `is_note=false`,
  `metadata.kind="image_description"`, `metadata.source_image=<path>`) and
  `ANNOTATES`-links it to the image file-record. It SHALL NOT call any model. It
  SHALL store `description` verbatim. It SHALL be idempotent (see the no-drift
  requirement).

`file_id_or_path` SHALL resolve to the file-record by memory id when it matches an
existing memory, otherwise by `metadata.path` or `metadata.rel`; an unresolvable
argument SHALL raise `KeyError` (mapped to 404 / a clear CLI/MCP error at the
transports).

#### Scenario: Jobs are produced with no vision backend configured
- **WHEN** `image_jobs()` is called with `provider=agent` (the default) and the
  store has indexed raster image file-records with no descriptions
- **THEN** an `ImageJob` is returned per raster image (carrying `file_id`, `path`,
  `rel`, `mime`, `size`, `online_only`), and no vision model is called.

#### Scenario: SVG and proprietary formats are never agent jobs
- **WHEN** the store contains indexed `.svg`, `.png`, and `.xd` file-records and
  `image_jobs()` is called
- **THEN** only the `.png` is returned; the `.svg` (self-described from embedded
  text) and the `.xd` (proprietary, metadata-only) are not.

#### Scenario: Description is stored and linked
- **WHEN** `image_caption_put(file_id, "a whiteboard listing Q3 OKRs …")` is
  called for a raster image file-record
- **THEN** a new `context` memory with `is_note=false` and
  `metadata.kind="image_description"` is stored with that text, and an `ANNOTATES`
  link is created from the new memory to the image file-record.

### Requirement: No-drift incremental describe (MM-17 property)
The default image job list SHALL be stable on an unchanged tree. A raster image
file-record SHALL be considered to NEED a (re)description if and only if there is
NO active (non-archived) `image_description` memory that `ANNOTATES` it.
`image_caption_put` SHALL, before adding the new description, ARCHIVE every
existing active `image_description` memory that annotates the same file-record, so
that re-putting REPLACES the prior description rather than accumulating duplicates.
Consequently, after `image_caption_put` for an image, a default `image_jobs()`
call SHALL NOT return that image again on an unchanged tree.

#### Scenario: A described image drops out of the default work-list
- **WHEN** `image_caption_put(F, "…")` is called and then `image_jobs()` (default)
  is called on the unchanged store
- **THEN** `F` is NOT present in the returned jobs, while
  `image_jobs(include_all=True)` still includes `F` (with its
  `current_description` populated).

#### Scenario: Re-putting replaces, not duplicates
- **WHEN** `image_caption_put(F, "first")` then `image_caption_put(F, "second")`
  are called
- **THEN** exactly one active `image_description` annotates `F` (the "second"
  text), the prior one is archived, and the result's `replaced_description_id`
  identifies the archived record.

#### Scenario: Re-indexing a changed image re-surfaces it
- **WHEN** a described image's bytes change and the tree is re-indexed (producing a
  new file-record id for that path with no description yet)
- **THEN** the new file-record is returned by a default `image_jobs()` call.

### Requirement: Hybrid image-byte payload
For each returned raster job, the system SHALL populate `image_b64` (base64 of the
image bytes) when the file is online-only OR `include_bytes=true`, and otherwise
SHALL leave `image_b64=null` (the agent reads the file at `path`). Online-only
files SHALL be downloaded to obtain bytes, and that download SHALL count against a
download budget (`MINTMORY_VISION_MAX_DOWNLOAD_MB`, shared semantics with the tree
indexer's budget); once the budget is exhausted further online-only payloads SHALL
be omitted (`image_b64=null`) while the jobs remain valid. Files larger than the
size cap (`MINTMORY_VISION_MAX_IMAGE_MB`) SHALL NOT be embedded: `image_b64=null`
and `oversized=true`. When the optional `[image]` extra (Pillow) is present and
`downscale_max_px > 0`, embedded payloads MAY be downscaled so their longest edge
fits, to keep payloads small; when the extra is absent, embedding SHALL fall back
to the raw bytes (still subject to the size cap). The downscale path SHALL NOT
raise on a corrupt image.

#### Scenario: Online-only image is embedded; local image uses path
- **WHEN** `image_jobs()` returns a job for an online-only image and a job for a
  local image, with `include_bytes=false`
- **THEN** the online-only job has `image_b64` populated (within budget/size cap)
  and the local job has `image_b64=null`.

#### Scenario: Oversized image is flagged, not embedded
- **WHEN** a raster image larger than `MINTMORY_VISION_MAX_IMAGE_MB` is selected
  with `include_bytes=true`
- **THEN** its job has `image_b64=null` and `oversized=true`.

#### Scenario: Pillow absent still yields a payload
- **WHEN** the `[image]` extra is not installed and an under-cap online-only image
  is selected
- **THEN** the job's `image_b64` contains the raw (un-downscaled) image bytes,
  base64-encoded.

### Requirement: SVG self-description (pure-Python)
The system SHALL extract the visible text of an SVG image from its
`<text>/<tspan>/<title>/<desc>/<textPath>` elements using a pure-Python,
stdlib-only extractor (no model, no agent, no new dependency), namespace-agnostic,
returning a single newline-joined blob (empty when there is no extractable text).
The extractor SHALL NOT raise on malformed XML (it SHALL return an empty string).
An SVG with extractable text SHALL be given an `image_description` memory directly
(handled automatically during tree indexing with `--vision`); an SVG with no
extractable text SHALL get no description and SHALL NOT be surfaced as an agent
job.

#### Scenario: SVG text becomes a description without an agent
- **WHEN** an `.svg` file containing `<text>Login</text><text>Submit</text>` is
  indexed with vision enabled
- **THEN** an `image_description` memory whose content includes "Login" and
  "Submit" is created and `ANNOTATES`-linked to the SVG file-record, with no agent
  round-trip and no model call.

#### Scenario: Malformed or text-free SVG yields no description
- **WHEN** `extract_svg_text` is given malformed XML or an SVG with no text
  elements
- **THEN** it returns an empty string (without raising) and no description is
  created.

### Requirement: Vision provider seam (agent only in v1)
The system SHALL provide a `Captioner` protocol (`describe(image: ImageInput) ->
ImageDescription`) and a single factory `captioner_from_settings(settings) ->
Captioner | None` selected by `MINTMORY_VISION_PROVIDER`, so that future `llm` and
`ocr` backends drop in without changing any caller. In v1:

- `agent` (DEFAULT) SHALL resolve to `None` (no server-side backend; the
  agent-supplied prepare/apply loop is used instead).
- `llm` SHALL raise a clear `NotImplementedError` (an OpenAI-compatible vision
  tier via `MINTMORY_VISION_BASE_URL/_MODEL/_API_KEY` is a future drop-in).
- `ocr` SHALL raise a clear `NotImplementedError` (local tesseract behind the
  optional `[ocr]` extra is a future drop-in).

The factory SHALL be the only place that branches on the provider; `image_jobs`
and `image_caption_put` SHALL NOT call it (the agent path needs no captioner).
Neither Pillow (`[image]`) nor pytesseract (`[ocr]`) SHALL be a required
dependency; both SHALL be lazy-imported, and the v1 path SHALL function without
them.

#### Scenario: agent provider has no backend
- **WHEN** `captioner_from_settings()` is called with the default settings
  (`provider=agent`)
- **THEN** it returns `None` (and the agent-supplied loop is used).

#### Scenario: llm/ocr providers raise clearly in v1
- **WHEN** `captioner_from_settings()` is called with
  `MINTMORY_VISION_PROVIDER=llm` (or `=ocr`)
- **THEN** it raises `NotImplementedError` with a message directing the operator
  to use `MINTMORY_VISION_PROVIDER=agent`.

### Requirement: Image-understanding transports
The agent-supplied image methods SHALL be reachable through three thin transports
that marshal `types.py` models and call `core.vision` directly with the configured
`VisionSettings` (`MINTMORY_VISION_*`):

- MCP: `image_jobs(include_all=false, include_bytes=false, limit=0) ->
  list[dict]` and `image_caption_put(file_id_or_path, description) -> dict`
  (`limit=0` = no cap, applied after selection; empty description → a
  `bad_request` error dict; unresolvable target → a `not_found` error dict). The
  FastMCP `instructions` SHALL mention the agent-supplied vision loop and that no
  vision backend is required.
- CLI: `mintmory image-jobs` (rich table by default, `--json`, `--all/--needed`,
  `--bytes/--no-bytes`, `--limit`) and `mintmory image-caption-put
  <file_id_or_path> [text]` (text from the positional argument, else `--file`,
  else stdin; empty text rejected; unresolvable target → a clear error).
- HTTP: `GET /images/jobs` (query `include_all`, `include_bytes`, `limit`; →
  `list[ImageJob]`) and `PUT /images/{file_id}` (body `{ "description": "…" }` →
  `ImageDescription`; unresolvable id → 404). `docs/openapi/mintmory.yaml` SHALL
  define both paths and the `ImageJob` / `ImageDescription` / `ImageCaptionPut`
  schemas.

The existing search, notes, and summary endpoints/tools SHALL be unchanged by
these additions.

#### Scenario: MCP put then the image drops from default jobs
- **WHEN** `image_caption_put(file_id, "…")` is called over MCP and then
  `image_jobs()` (default) is called
- **THEN** that image is not present in the returned jobs.

#### Scenario: HTTP unknown file id is 404
- **WHEN** a client calls `PUT /images/{file_id}` with an id that resolves to no
  image file-record
- **THEN** the response is 404 (not a 500).

#### Scenario: CLI image-caption-put reads text from stdin
- **WHEN** `mintmory image-caption-put <file_id>` is run with the description
  piped on stdin (no positional text, no `--file`)
- **THEN** the piped text is stored as that image's description.

### Requirement: Image descriptions are ordinary searchable memories, not notes
An `image_description` memory SHALL be a normal `category=context`,
`is_note=false` memory: it SHALL be full-text / vector indexed like any other
content (entity extraction runs over its blob) and SHALL be reachable by ordinary
search. The reverse-`ANNOTATES` traversal used for descriptions
(`get_annotating_descriptions`) SHALL filter `metadata.kind="image_description"`
and `is_note=0`, distinct from the notes traversal (`get_annotating_notes`, which
filters `is_note=1`); image descriptions SHALL NOT appear in the notes
auto-include channel (`notes_on_results`). This change SHALL NOT modify `search()`
nor add any field to `SearchResponse`.

#### Scenario: A description is found by ordinary search
- **WHEN** an image is described with text containing "parking settings screen"
  and a user searches for "parking settings"
- **THEN** the `image_description` memory is eligible to match like any other
  `context` memory.

#### Scenario: Descriptions do not leak into the notes channel
- **WHEN** a search result has an `image_description` annotating it (but no user
  note)
- **THEN** the result's `notes_on_results` entry is empty (descriptions are not
  notes).
