# Design & FROZEN interface contract — `add-image-understanding`

Implementers MUST match these signatures, names, return shapes, and behaviours
exactly. Where intuition and this doc disagree, this doc wins. Overarching
invariants (the MintMory house rules):

- **Every default reproduces today's behaviour.** The whole change is additive.
  `MINTMORY_VISION_PROVIDER` defaults to `agent`; `index-tree` without `--vision`
  is byte-for-byte unchanged; `image_jobs`/`image_caption_put` are only reached
  when explicitly called.
- **One core, three transports.** All domain logic lives in `mintmory.core`
  (`core/vision.py`); MCP / CLI / API are thin wrappers that serialise `types.py`
  models. They build nothing the core does not own.
- **No new REQUIRED runtime dependency. No network in the v1 (`agent`) path.**
  `image_jobs` / `image_caption_put` / `extract_svg_text` MUST NOT call any model
  and MUST work with the defaults (no `MINTMORY_VISION_*`, no extras installed).
  Pillow (`[image]`) and pytesseract (`[ocr]`) are optional and lazy-imported.
- **Reuse, don't reinvent.** The `ANNOTATES` edge + `LinkSource` (MM-16) and the
  prepare/apply + no-drift discipline (MM-17) are REUSED. The
  `manifest_upsert(index_mode=...)` flow and the file-record metadata shape from
  `index-tree` are REUSED.
- Gates for every package touched: `pytest` (cov ≥ 80), `ruff check`,
  `ruff format --check`, `mypy --strict` (line-length 100).

The load-bearing claims of this change are:
1. **No-drift parity (MM-17):** after `image_caption_put(img, …)`, a default
   `image_jobs()` MUST NOT re-surface `img` on an unchanged tree.
2. **Defaults reproduce today:** the existing `index-tree` / `ingest` tests stay
   green WITHOUT edits; the metadata file-record path is untouched.
3. **`agent` is the only implemented provider:** `llm`/`ocr` are a compile-time
   seam whose factory raises clearly.

---

## 0. Ground truth — what `index-tree` already writes (DO NOT CHANGE)

From `cli/main.py::index_tree` + `core/tree_index.py`, every file becomes a
**file-record** memory:

```python
store.add_memory(
    content=render_file_record(entry, group, root_label),
    category="context",
    source="document",
    metadata={
        "collection": collection,
        "path": path_str,        # str(absolute Path)
        "rel": entry.rel,        # POSIX-style path relative to the walk root
        "ext": entry.suffix,     # lowercased, e.g. ".png"
        "size": entry.size,
        "mtime": entry.mtime,
        "online_only": entry.online_only,
        "folder": str(Path(entry.rel).parent),
        "index_mode": "metadata",
    },
)
```

and a manifest row via `manifest_upsert(path, collection, size=, mtime=,
online_only=, index_mode=, memory_ids=[…], content_hash=)`. The image file-record
this change operates on is THIS record — discovery reads it by its
`metadata.ext` ∈ the raster set, NOT by re-walking the filesystem.

`_TYPE_LABELS` in `tree_index.py` already labels `.jpg/.jpeg/.png/.gif` as
"image" and `.svg/.eps` as "vector image". This change does not touch
`render_file_record` or the labels.

> Subtle invariant: discovery operates on **already-indexed file-records**, so the
> agent can describe images even for a tree that is offline at describe-time
> (the metadata is in SQLite). Online-only download is a SEPARATE, budgeted,
> opt-in concern (see §5, hybrid bytes).

---

## 1. Suffix sets (FROZEN, in `core/vision.py`)

```python
# Raster images that need the agent/provider to describe.
RASTER_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
)
# Vector images we can self-describe from embedded <text> (pure-Python).
SVG_SUFFIXES: frozenset[str] = frozenset({".svg"})
# All image suffixes index-tree's --vision flag treats as the third content mode.
IMAGE_SUFFIXES: frozenset[str] = RASTER_SUFFIXES | SVG_SUFFIXES
# Proprietary design formats — OUT OF SCOPE for v1 (metadata-only). Listed only so
# index-tree --vision can explicitly skip-and-flag them (not silently treat as raster).
PROPRIETARY_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".xd", ".vsdx", ".dwg", ".psd", ".eps"}
)
```

Suffix comparisons are always lowercased (`entry.suffix` already is; `metadata.ext`
is stored lowercased). `image_jobs` discovery considers a file-record an **image**
iff `metadata.get("ext")` ∈ `IMAGE_SUFFIXES`.

---

## 2. Config — `VisionSettings` (`core/config.py`)

A new `BaseSettings` group with env prefix `MINTMORY_VISION_`, mirroring
`NoteSettings` / `ConversionSettings`. Add a `VisionProvider` enum next to the
existing `EmbeddingProvider` / `LLMProvider` enums.

```python
class VisionProvider(str, Enum):
    AGENT = "agent"  # default — no backend; the active agent supplies the text
    LLM = "llm"      # SEAM/STUB v1 — OpenAI-compatible vision tier (raises in v1)
    OCR = "ocr"      # SEAM/STUB v1 — local tesseract behind [ocr] (raises in v1)


class VisionSettings(BaseSettings):
    """Image-understanding (G5). Defaults reproduce today's behaviour: provider
    defaults to ``agent`` (no backend; agent-supplied prepare/apply loop) and
    nothing is described unless ``index-tree --vision`` or ``image_jobs`` is
    explicitly invoked. ``llm``/``ocr`` are a seam: selecting them raises a clear
    NotImplementedError in v1."""

    model_config = SettingsConfigDict(env_prefix="MINTMORY_VISION_", extra="ignore")

    provider: VisionProvider = VisionProvider.AGENT
    # Per-image on-disk byte cap for the hybrid-bytes payload. Files larger than
    # this are NOT base64-embedded — image_b64 stays None and oversized=True is
    # flagged so the agent can fall back to ``path`` (0 = no cap).
    max_image_mb: float = Field(default=8.0, ge=0.0)
    # Longest-edge pixel target for the optional Pillow downscale of embedded
    # payloads (keeps base64 small). Only used when the [image] extra is present;
    # 0 = never downscale (just size-cap/skip).
    downscale_max_px: int = Field(default=1568, ge=0)
    # Download budget (bytes-equivalent in MB) for online-only images fetched to
    # build the base64 payload. Shares the SAME semantics as index-tree's
    # --max-download-mb (0 = unlimited). Used by image_jobs(include_bytes/online).
    max_download_mb: float = Field(default=200.0, ge=0.0)
    # provider-specific (llm/ocr) — unused by the agent path, present so the seam
    # is complete and llm/ocr drop in without a config change:
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    tesseract_cmd: str | None = None  # ocr: explicit tesseract binary path

    @property
    def max_image_bytes(self) -> int | None:
        return None if self.max_image_mb <= 0 else int(self.max_image_mb * 1024 * 1024)

    @property
    def max_download_bytes(self) -> int | None:
        return None if self.max_download_mb <= 0 else int(self.max_download_mb * 1024 * 1024)
```

Register it on the aggregate:

```python
class Settings(BaseSettings):
    ...
    note: NoteSettings = Field(default_factory=NoteSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)  # NEW
```

> `downscale_max_px=1568` matches the long-edge most vision tiers downsize to
> anyway; it only affects the *embedded* payload, never the on-disk file.

---

## 3. Types — `ImageJob` and `ImageDescription` (`core/types.py`)

Add a new "Image understanding types" block (after the "Dreaming process types"
block, next to `SummaryJob`). Match the existing Pydantic style (no validators
needed). `ImageJob` is the prepare-step carrier (mirrors `SummaryJob`);
`ImageDescription` is the result carrier returned by `image_caption_put`.

```python
class ImageJob(BaseModel):
    """One indexed image the active agent should describe (agent-supplied vision).

    Produced by ``vision.image_jobs`` and exposed over the transports. Mirrors
    ``SummaryJob``: a pure data carrier (NOT persisted) describing one unit of
    work. ``image_b64`` is populated (hybrid bytes) only when the file is
    online-only OR ``include_bytes=True`` AND the file is within the size cap;
    otherwise it is ``None`` and the agent reads the file at ``path``.
    """

    file_id: str  # the image FILE-RECORD memory id (what the description ANNOTATES)
    path: str  # absolute source path (str), from the file-record metadata
    rel: str  # POSIX path relative to the walk root, from the file-record metadata
    mime: str  # best-effort MIME from the suffix, e.g. "image/png"
    size: int  # on-disk byte size, from the file-record metadata
    online_only: bool  # cloud placeholder (not downloaded locally)
    image_b64: str | None = None  # base64 payload (hybrid rule §5); None => use path
    current_description: str | None = None  # existing image_description text, if any
    oversized: bool = False  # True when image_b64 omitted because size > cap


class ImageDescription(BaseModel):
    """The stored description of one image (the result of ``image_caption_put``).

    Wraps the created/updated ``image_description`` MemoryRecord plus the linkage
    facts, mirroring ``NoteResult``'s shape (record + what-it-anchored-to).
    """

    record: MemoryRecord  # the image_description memory (category=context, is_note=False)
    file_id: str  # the image file-record this description ANNOTATES
    source_image: str  # the image's absolute path (== file-record metadata["path"])
    replaced_description_id: str | None = None  # prior description archived on re-put, if any
```

> `ImageDescription.record` is a full `MemoryRecord` (the description content is
> the agent's combined blob). `replaced_description_id` makes the idempotent
> archive auditable. Both models are transport data; only the wrapped
> `MemoryRecord` is persisted.

---

## 4. The provider seam — `Captioner` protocol + factory (`core/vision.py`)

The seam exists so `llm`/`ocr` drop in later without touching callers. v1
implements ONLY `agent` (which has **no** captioner object — the agent supplies
text out-of-band via prepare/apply). `llm`/`ocr` are stubs that raise.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Captioner(Protocol):
    """Server-side image-to-text backend (the SEAM for future llm/ocr providers).

    v1 has NO implementation: the ``agent`` provider returns ``None`` from the
    factory (the agent supplies text via image_jobs/image_caption_put), and
    ``llm``/``ocr`` raise NotImplementedError. A future change adds concrete
    classes here WITHOUT changing image_jobs/image_caption_put or any caller.
    """

    def describe(self, image: ImageInput) -> ImageDescription: ...


@dataclass(frozen=True)
class ImageInput:
    """Inputs a Captioner needs to describe one image (path and/or bytes)."""

    file_id: str
    path: str
    mime: str
    data: bytes | None = None  # in-memory bytes when already loaded/downloaded


def captioner_from_settings(settings: VisionSettings | None = None) -> Captioner | None:
    """Resolve the configured vision backend.

    - ``agent`` (DEFAULT): returns ``None`` — there is no server-side backend;
      callers use the image_jobs/image_caption_put prepare/apply loop instead.
    - ``llm``: v1 raises ``NotImplementedError`` with a clear message
      ("vision provider 'llm' is not implemented in this version; set
      MINTMORY_VISION_PROVIDER=agent for the agent-supplied loop").
    - ``ocr``: v1 raises ``NotImplementedError`` likewise (and would require the
      optional [ocr] extra / tesseract).

    A future change replaces the two ``raise`` branches with real classes; the
    ``agent``→``None`` branch and every caller stay unchanged.
    """
    s = settings if settings is not None else VisionSettings()
    if s.provider is VisionProvider.AGENT:
        return None
    if s.provider is VisionProvider.LLM:
        raise NotImplementedError(
            "vision provider 'llm' is not implemented in this version; "
            "set MINTMORY_VISION_PROVIDER=agent for the agent-supplied loop"
        )
    if s.provider is VisionProvider.OCR:
        raise NotImplementedError(
            "vision provider 'ocr' is not implemented in this version; "
            "set MINTMORY_VISION_PROVIDER=agent for the agent-supplied loop"
        )
    raise NotImplementedError(f"unknown vision provider {s.provider!r}")  # defensive
```

> The factory is the ONLY place that branches on `provider`. `image_jobs` /
> `image_caption_put` never call it (the agent path needs no captioner).
> `index-tree --vision` calls it ONLY to decide "inline-describe (llm/ocr) vs
> queue-for-agent (agent)" — and in v1, llm/ocr raise before any file is touched,
> which is the intended "configure it first" behaviour.

---

## 5. Core — `image_jobs` (discovery; mirrors `collect_summary_jobs`)

```python
def image_jobs(
    adapter: StorageAdapter,
    *,
    include_all: bool = False,
    include_bytes: bool = False,
    limit: int = 0,
    settings: VisionSettings | None = None,
) -> list[ImageJob]:
    """Return the image file-records the active agent should describe.

    DISCOVERY operates on already-indexed image FILE-RECORDS — the
    ``category=context, source=document`` memories ``index-tree`` writes whose
    ``metadata["ext"]`` is in ``IMAGE_SUFFIXES``. It does NOT walk the filesystem
    and does NOT call any model (works with the defaults / provider=agent).

    Selection (the needs-redescribe predicate, §5a):
      * By DEFAULT (``include_all=False``) returns only RASTER image file-records
        that NEED a (re)description — i.e. those with NO active (non-archived)
        ``image_description`` memory ANNOTATES-linking them.
      * SVG file-records are NEVER returned as agent jobs: they are self-described
        from embedded text (§6) during index-tree --vision. (An SVG with no
        extractable text simply has no description and is not an agent job either —
        v1 does not ask the agent to describe SVGs.)
      * Proprietary suffixes (PROPRIETARY_IMAGE_SUFFIXES) are NEVER returned.
      * ``include_all=True`` returns every RASTER image file-record regardless of
        existing descriptions.

    Hybrid bytes (the approved option C): ``image_b64`` is populated (base64 of
    the file bytes) when the file is ``online_only`` OR ``include_bytes=True``,
    subject to the size cap and budget (§5b). Otherwise ``image_b64`` is ``None``
    and the agent reads the file at ``path``.

    Order is deterministic: image file-records sorted by ``rel`` then ``file_id``.
    ``limit`` (>0) caps the returned list AFTER selection (post-slice).
    """
```

### 5a. The needs-redescribe predicate (FROZEN — the no-drift property)

A raster image file-record `F` (an `image_description` memory `D` ANNOTATES `F`
when there is a `ConceptLink(source=D.id, target=F.id, link_type=ANNOTATES)`):

> **`F` needs a (re)description ⇔ there is NO active (`is_archived=0`)
> `MemoryRecord` `D` with `D.metadata.get("kind") == "image_description"` that
> `ANNOTATES` `F`.**

This is the image analogue of MM-17's "no current summary OR memory_count drift",
restricted to the **existence** test (there is no count to drift — one image, one
description). The predicate is **stable on an unchanged tree**: after
`image_caption_put(F, …)` creates an active description `D` linking `F`, a default
`image_jobs()` MUST NOT return `F` again until that `D` is archived (or the file
is re-indexed, producing a *new* file-record id with no description). The
backing query is a reverse-`ANNOTATES` traversal that — unlike
`get_annotating_notes` — filters `m.metadata kind = 'image_description'` and
`m.is_note = 0` (it MUST NOT reuse the notes helper, which filters `is_note=1`).

Implement via a new storage read helper (§8): `get_annotating_descriptions(
file_id, cap) -> list[MemoryRecord]` (active, kind=image_description, ANNOTATES
`file_id`). `needs = not get_annotating_descriptions(file_id, 1)`.
`current_description` on the job = the first such record's `content` (when
`include_all=True` surfaces an already-described image) else `None`.

### 5b. Hybrid-bytes rule (FROZEN)

For each selected raster file-record, decide `image_b64`:

1. `want_bytes = include_bytes or online_only`. If not `want_bytes`:
   `image_b64=None`, `oversized=False` (agent uses `path`).
2. If `want_bytes`: determine the source bytes:
   - If `online_only`: the file must be **downloaded** to read it; the download
     size counts against `settings.max_download_bytes` (shared budget semantics
     with `index-tree --max-download-mb`). When the budget is exhausted, STOP
     embedding further online-only payloads — set `image_b64=None` for the rest
     (they remain valid jobs with `path`; the agent can be re-polled later).
   - Else (local file): read it directly (no budget consumed; local reads are
     free, matching `index-tree`'s text_eligible policy).
3. **Size cap:** if `settings.max_image_bytes is not None and size >
   max_image_bytes`, do NOT embed: `image_b64=None`, `oversized=True` (skip+flag).
4. **Optional downscale (lazy Pillow):** if bytes were obtained and the `[image]`
   extra is importable AND `settings.downscale_max_px > 0`, downscale so the
   longest edge ≤ `downscale_max_px` and re-encode (preserving format; PNG/JPEG)
   before base64. The Pillow import MUST be **lazy and guarded**
   (`try: import PIL … except ImportError:`); absent → skip downscaling and use
   the raw bytes (still subject to the size cap in step 3, which is applied to the
   **on-disk** size, so an absent Pillow just means a large-but-under-cap image is
   embedded at full size). Downscaling MUST NOT raise on a corrupt image — on any
   Pillow error, fall back to the raw bytes.
5. `image_b64 = base64.b64encode(bytes).decode("ascii")`.

`mime` is a best-effort map from the suffix (`{".jpg":"image/jpeg",
".jpeg":"image/jpeg", ".png":"image/png", ".gif":"image/gif", ".webp":"image/webp",
".bmp":"image/bmp"}`; default `"application/octet-stream"`).

> Rationale for hybrid (approved option C): online-only files have no local bytes,
> so the agent literally cannot read them from `path` on this host — those MUST be
> embedded (within budget). Local files default to `path` (cheap, no payload
> bloat) unless the caller forces `include_bytes=True` (e.g. an agent on a
> different host than the DB).

---

## 6. SVG self-description — `extract_svg_text` (`core/vision.py`)

SVG embedded text is just XML. A small **pure-Python** extractor (no model, no
agent, no new dependency — `xml.etree.ElementTree` from the stdlib):

```python
def extract_svg_text(svg_bytes: bytes) -> str:
    """Extract the visible text of an SVG from its <text>/<tspan>/<title>/<desc>
    elements (namespace-agnostic, pure stdlib). Returns a single newline-joined
    blob of the non-empty trimmed strings in document order, deduplicated of
    consecutive duplicates, or "" when the SVG has no extractable text or is not
    parseable. MUST NOT raise on malformed XML (return "" instead)."""
```

Implementation notes (FROZEN behaviour):
- Parse defensively: `try: ElementTree.fromstring(svg_bytes) except
  ElementTree.ParseError: return ""`. Guard against XXE by NOT resolving external
  entities (stdlib `ElementTree` does not expand external general entities by
  default; do not switch to a parser that does).
- Collect `.text` and `.tail` of every element whose **local** tag (after
  stripping any `{namespace}` prefix) is one of `text`, `tspan`, `title`, `desc`,
  `textPath`. Strip each; drop empties; join with `"\n"`; collapse runs of
  identical adjacent lines.
- The result is the **combined description blob** for an SVG (it IS "what the
  image depicts + legible text" for a vector diagram — the labels ARE the content).

`index-tree --vision` (and an explicit SVG path passed to
`image_caption_put`'s SVG fast-path, if implemented) uses this to create the
`image_description` record DIRECTLY, with no agent round-trip. An SVG whose
`extract_svg_text` returns `""` gets **no** description (and is not surfaced as an
agent job — v1 does not agent-describe SVGs).

---

## 7. Core — `image_caption_put` (apply; mirrors `apply_summary` + MM-16 anchoring)

```python
def image_caption_put(
    adapter: StorageAdapter,
    file_id_or_path: str,
    description: str,
    *,
    settings: VisionSettings | None = None,
) -> ImageDescription:
    """Persist an agent-supplied (or SVG-extracted) description for one image.

    ``file_id_or_path`` resolves to the image FILE-RECORD: if it is the id of an
    existing memory it is used directly; otherwise it is treated as a path and the
    most recent ACTIVE file-record whose ``metadata["path"]`` equals it (or whose
    ``metadata["rel"]`` equals it) is used. Raises ``KeyError`` if no image
    file-record can be resolved.

    Creates a new ``MemoryRecord`` whose ``content`` is ``description`` (the
    agent's COMBINED blob = what the image depicts + any legible text), with
    ``category=context``, ``source=document``, ``is_note=False``, and
    ``metadata = {"kind": "image_description", "source_image": <path>,
    "collection": <file-record collection if present>}``; then ANNOTATES-links it
    to the file-record (reusing the MM-16 edge):
        ConceptLink(source_memory_id=<new description id>,
                    target_memory_id=<file_id>,
                    link_type=ConceptLinkType.ANNOTATES,
                    entity=<rel or path>,
                    source=LinkSource.INFERENCE,  # agent-derived, not a user note
                    strength=1.0, confidence=1.0)

    Idempotent (the no-drift guarantee §5a): BEFORE adding the new description,
    every existing ACTIVE ``image_description`` memory that ANNOTATES this
    file-record is ARCHIVED (``adapter.archive_memory``). So re-putting REPLACES
    the prior description (archive old → add new), and a subsequent default
    ``image_jobs()`` does NOT re-surface the image. ``replaced_description_id`` is
    set to the archived record's id (the first one, if several existed).

    Calls no model/LLM; works with the defaults. ``description`` is stored
    verbatim (no stripping); the caller owns whitespace. An empty/whitespace-only
    ``description`` is rejected with ``ValueError`` at the transport boundary
    (the core MAY also guard).
    """
```

Behaviour details (FROZEN):
- **Resolution order:** try `adapter.get_memory(file_id_or_path)` first; if it
  returns a record, use it as the file-record (it SHOULD be a `context`/`document`
  image file-record, but the function does not hard-validate the category — it
  trusts an explicit id). Else resolve by metadata path via the new storage finder
  `find_image_file_record(path_or_rel)` (§8). `KeyError` if unresolved.
- **`source_image`** is the resolved file-record's `metadata["path"]` (fall back
  to `file_id_or_path` if the record somehow lacks it).
- **`LinkSource.INFERENCE`** (not `USER`): an image description is agent/extractor
  derived, not a user "remember this" note. (Notes use `USER`; this is the
  documented split.) The `entity` field carries `rel` (or `path`) so the link is
  human-auditable.
- **Archive-then-add ordering** is mandatory for no-drift: if you add the new
  description first and then archive "old" ones, you risk archiving the just-added
  record. Archive ALL pre-existing active descriptions for the file-record FIRST,
  THEN add the new one and its link.
- The new description is an ordinary searchable memory: it is FTS/vector indexed
  by `add_memory` like any other `context` content (entity extraction runs over
  the blob), and it auto-includes on the file-record via the existing reverse
  traversal mechanism (the parallel description helper, §8/§9d) — no bespoke
  ranking.

> Why a separate memory rather than mutating the file-record's content: keeps the
> deterministic stat-only file-record (which `index-tree` re-renders idempotently)
> pristine, exactly as MM-16 keeps notes separate from the memories they annotate.
> Re-running `index-tree` (metadata mode) replaces the file-record but does NOT
> touch description memories; re-running `--vision` re-evaluates the predicate.

---

## 8. Storage helpers (`core/storage.py`) — additive, reuse-first

Three additive changes. NONE alters an existing method's behaviour.

### 8a. `index_mode` CHECK migration (the ONE schema delta)

`schema.sql` line widens:
`index_mode TEXT NOT NULL DEFAULT 'metadata' CHECK (index_mode IN
('metadata','content','vision'))`. Because SQLite cannot `ALTER` a CHECK
constraint in place, pre-existing databases need a migration. Add a best-effort,
idempotent helper called from `initialise()` AFTER `executescript(ddl)`, mirroring
`_ensure_is_note_column` / `_ensure_trigram`:

```python
def _ensure_index_mode_vision(self, conn: sqlite3.Connection) -> None:
    """Best-effort, idempotent widening of index_manifest.index_mode to allow
    'vision'. Fresh DBs already allow it from schema.sql. On a pre-existing DB
    whose CHECK only allows ('metadata','content'), rebuild the table with the
    wider CHECK (CREATE new → INSERT SELECT → DROP old → RENAME), preserving all
    rows. Detects the need by inspecting the stored CREATE sql for the table; a
    re-run after migration is a no-op. Any sqlite3.OperationalError degrades to
    'no vision index_mode' (callers still write 'metadata'/'content')."""
```

Detection: read `SELECT sql FROM sqlite_master WHERE type='table' AND
name='index_manifest'`; migrate only when the stored sql contains the
two-value CHECK and not `'vision'`. Wrap the whole body in
`try/except sqlite3.OperationalError`. Call it in `initialise()` right after
`_ensure_is_note_column(conn)`.

> `manifest_upsert` itself needs NO change — it already takes `index_mode: str`.
> After the migration, `index_mode="vision"` is a legal value to write.

### 8b. `get_annotating_descriptions` (reverse ANNOTATES for descriptions)

A SIBLING of `get_annotating_notes`, but for image-description records (NOT
notes). It MUST NOT modify `get_annotating_notes`.

```python
def get_annotating_descriptions(self, memory_id: str, cap: int) -> list[MemoryRecord]:
    """Return up to ``cap`` ACTIVE image_description memories that ANNOTATE
    ``memory_id`` (the reverse ANNOTATES traversal, MM-16 pattern). Filters
    ``m.is_note = 0`` AND ``m.is_archived = 0`` AND ``json_extract(m.metadata,
    '$.kind') = 'image_description'``. Ordered by created_at DESC. ``cap <= 0``
    returns []. This is the description analogue of get_annotating_notes and does
    NOT overlap it (notes are is_note=1; descriptions are is_note=0)."""
```

SQL mirrors `get_annotating_notes` but swaps the predicate:
`... JOIN memories m ON m.id = l.source_memory_id WHERE l.target_memory_id = ?
AND l.link_type = 'annotates' AND m.is_note = 0 AND m.is_archived = 0 AND
json_extract(m.metadata, '$.kind') = 'image_description' ORDER BY m.created_at
DESC LIMIT ?`. (`json_extract` is available in the SQLite builds MintMory already
relies on for FTS5; if a build lacks it, the helper MAY fall back to loading rows
and filtering `metadata` in Python — but the SQL form is preferred.)

### 8c. `find_image_file_record` (resolve a path → file-record)

```python
def find_image_file_record(self, path_or_rel: str) -> MemoryRecord | None:
    """Find the most recent ACTIVE file-record memory whose metadata['path'] OR
    metadata['rel'] equals ``path_or_rel`` AND whose metadata['ext'] is an image
    suffix. Returns None if not found. Used by image_caption_put to resolve a
    path argument to the file-record it should ANNOTATE."""
```

Implement with `json_extract(metadata,'$.path')` / `'$.rel'` and an `IN` over the
image suffix set (or load candidates and filter in Python). Order by `created_at
DESC LIMIT 1`. Active = `is_archived = 0`.

> Decision: discovery in `image_jobs` may also use a single broad query —
> `SELECT * FROM memories WHERE is_archived = 0 AND
> json_extract(metadata,'$.kind') IS NULL AND json_extract(metadata,'$.ext') IN
> (…raster…)` then filter — OR a small dedicated finder
> `iter_image_file_records()`; EITHER is acceptable. The file-record is
> distinguished from a description by `metadata.kind`: a file-record has NO
> `kind` (or `kind != 'image_description'`); a description has
> `kind='image_description'`. Discovery MUST exclude description records.

---

## 9. Optional auto-include on search (REUSE MM-16 mechanism, opt-in, default-off)

`search()` already auto-includes annotating **notes** via
`get_annotating_notes` into `notes_on_results` (capped by
`NoteSettings.auto_include_cap`). Image descriptions are a DIFFERENT channel and
are already directly searchable (they are `context` memories), so the FOCUS of
this change is discovery + describe, NOT changing search ranking.

**v1 decision (FROZEN): do NOT modify `search()`.** Image descriptions surface in
search results on their own merits (FTS/vector over the blob). Auto-including the
*file-record* alongside a matched description (or vice versa) is a possible future
enhancement and is OUT OF SCOPE here, to keep `search()` byte-for-byte unchanged
(no new SearchResponse field, no new cap). `get_annotating_descriptions` exists
for the predicate in §5a and for transports/tests; it is not wired into
`search()` in this change.

> This keeps `add-image-understanding` strictly additive on the read path: zero
> change to `SearchResponse`, `notes_on_results`, or scoring.

---

## 10. `index-tree --vision` integration (`cli/main.py`)

Add ONE flag and a THIRD content mode, under the SAME budget + manifest, without
disturbing the existing `text_eligible` / `want_binary` gating.

New option on `index_tree`:
```python
vision: bool = typer.Option(
    False, "--vision/--no-vision",
    help="Describe image files: extract SVG text inline; queue raster images as "
         "agent jobs (provider=agent) or run the configured vision provider "
         "(llm/ocr, future). Records index_mode='vision'.",
),
```

Per-entry logic, added beside `text_eligible` / `want_binary` (FROZEN shape):

```python
want_vision = (
    vision
    and entry.suffix in IMAGE_SUFFIXES
    and entry.suffix not in PROPRIETARY_IMAGE_SUFFIXES
)
```

`do_content = text_eligible or want_binary` is UNCHANGED. `want_vision` is a
SEPARATE branch (an image can be want_vision without being do_content). The
`desired_mode` becomes `"vision"` when `want_vision and not do_content` (an image
that is ALSO converted as a binary doc — not typical — keeps `"content"`; vision
is for image suffixes that are otherwise metadata-only). The manifest
change-detection `covered` test extends to treat `index_mode in ('content',
'vision')` as "already richer than metadata".

After the file-record is written (the existing metadata path is unchanged), when
`want_vision`:
- **SVG (`entry.suffix in SVG_SUFFIXES`):** read the file bytes (local read; if
  `online_only`, this is a download that counts against the existing
  `--max-download-mb` budget exactly like `want_binary` does — reuse the same
  `downloaded`/`budget`/`budget_hit` accounting). Call `extract_svg_text(bytes)`;
  if non-empty, call `vision.image_caption_put(store, file_record.id, text)` and
  append the created description id to `new_ids`; set `mode="vision"`. Empty text
  → no description, `mode` stays `"metadata"` (still record the manifest row so it
  is not re-attempted every run; the file is "seen as vision-attempted").
- **Raster (`entry.suffix in RASTER_SUFFIXES`):** dispatch on the provider via
  `captioner_from_settings(settings.vision)`:
  - `agent` (factory → `None`): do NOT call any model. COUNT it as a queued job
    (`vision_queued += 1`); the agent will pick it up via `image_jobs`. `mode`
    stays `"vision"` so the manifest records that this file is in the vision set
    (the description does not exist yet; `image_jobs` default will return it).
  - `llm`/`ocr` (factory raises): the raise propagates (intended "configure it
    first" behaviour) — OR the CLI MAY catch `NotImplementedError` once at the top
    and print a clear message then exit non-zero. Pick the catch-and-exit form so
    `index-tree --vision` with an unconfigured provider fails fast with guidance,
    not a stack trace.

Manifest: write `index_mode="vision"` (via the existing `manifest_upsert`) for
files handled by the vision branch; reuse `content_hash=None` for queued rasters
and `content_hash = blake2b(svg_text)` for SVGs (so a changed SVG re-extracts).
The report table gains rows: `svg-described`, `images-queued`,
`vision-skipped` (proprietary/oversized). Without `--vision`, NONE of this runs
and the table is unchanged.

> The budget is SHARED with `--content`: SVG/online-only image downloads consume
> the same `--max-download-mb`. This matches the proposal's "under the SAME
> download budget".

---

## 11. Transports (thin wrappers; built like MM-17)

All three call the `core/vision.py` functions directly with a `StorageAdapter`
and `VisionSettings` from `load_settings().vision`. (Unlike summaries, vision has
no `build_*_engine`; the functions take the adapter + settings explicitly.)

### 11a. MCP — `packages/mcp/src/mintmory/mcp/server.py`

```python
@mcp.tool()
def image_jobs(
    include_all: bool = False, include_bytes: bool = False, limit: int = 0
) -> list[dict[str, Any]]:
    """List indexed images for YOU (the agent) to describe (agent-supplied vision).

    MintMory does NOT call a vision model for these — you are the vision-capable
    model. Each job carries the image file-record id, its path/rel/mime/size, the
    online_only flag, and EITHER an inline base64 ``image_b64`` (when the file is
    online-only or include_bytes=True and within the size cap) OR ``image_b64:
    null`` meaning you should read the file at ``path``. Write ONE combined
    description per image (what it depicts + any legible text) and send it back
    with image_caption_put.

    Args:
        include_all: when False (default), only raster images that still NEED a
            description are returned; when True, every raster image file-record.
        include_bytes: force-embed base64 even for local files (use when you run
            on a different host than the MintMory DB and cannot read ``path``).
        limit: max jobs (0 = no cap), applied after selection.
    Returns: a list of ImageJob dicts.
    """
    store = _get_store()
    settings = load_settings()
    from mintmory.core import vision as vision_mod
    jobs = vision_mod.image_jobs(
        store, include_all=include_all, include_bytes=include_bytes,
        limit=limit, settings=settings.vision,
    )
    return [j.model_dump(mode="json") for j in jobs]


@mcp.tool()
def image_caption_put(file_id_or_path: str, description: str) -> dict[str, Any]:
    """Store YOUR description for one indexed image (agent-supplied vision).

    Persists ``description`` (your combined "what it depicts + legible text" blob)
    as a context memory ANNOTATES-linked to the image file-record. Idempotent:
    re-putting replaces the prior description (the image then drops out of the
    default image_jobs work-list). No vision backend is required.

    Args:
        file_id_or_path: the ImageJob ``file_id`` (preferred) or the image path.
        description: your one-blob description (non-empty).
    Returns: an ImageDescription dict (the stored record + linkage facts).
    """
    if not description.strip():
        return {"error": "bad_request", "message": "description must be non-empty"}
    store = _get_store()
    settings = load_settings()
    from mintmory.core import vision as vision_mod
    try:
        result = vision_mod.image_caption_put(
            store, file_id_or_path, description, settings=settings.vision
        )
    except KeyError as exc:
        return {"error": "not_found", "message": str(exc)}
    return result.model_dump(mode="json")
```

Update the FastMCP `instructions` string with a sentence on the loop ("For
indexed images you can supply the description yourself: call image_jobs to get the
images needing a description, read each (inline base64 or via its path), write one
combined description, and send it back with image_caption_put — no vision backend
required."), and the tool-map comment block at the top of the file.

### 11b. CLI — `packages/cli/src/mintmory/cli/main.py`

Two `@app.command()`s, Typer-exposed as `image-jobs` / `image-caption-put`. Match
the `summary-jobs` / `summary-put` style.

```python
@app.command()
def image_jobs(
    include_all: bool = typer.Option(False, "--all/--needed",
        help="All raster images vs only those needing a description"),
    include_bytes: bool = typer.Option(False, "--bytes/--no-bytes",
        help="Force-embed base64 for local files too"),
    limit: int = typer.Option(0, help="Max jobs (0 = no cap)"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
) -> None:
    """List image-description jobs for the agent (agent-supplied vision)."""
    # _get_store(); from mintmory.core import vision; load_settings().vision;
    # vision.image_jobs(...); --json => model_dump list; else a rich table with
    # columns: file_id, rel, mime, online_only, has_desc, bytes (yes if image_b64).


@app.command()
def image_caption_put(
    file_id_or_path: str = typer.Argument(..., help="Image file-record id or path"),
    text: str | None = typer.Argument(None, help="Description (omit to read --file/stdin)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="Read description from a file"),
) -> None:
    """Store an agent-supplied image description (text arg, --file, or stdin)."""
    # text -> --file -> stdin; strip; reject empty (typer.BadParameter);
    # vision.image_caption_put(store, file_id_or_path, text, settings=...);
    # KeyError -> typer.BadParameter; print the stored description id + source_image.
```

Update the module docstring command list (top of `main.py`) to add
`mintmory image-jobs` and `mintmory image-caption-put`.

### 11c. HTTP API — `packages/api`

`schemas.py` — one request body:
```python
class ImageCaptionPut(BaseModel):
    """Request body for ``PUT /images/{file_id}`` (agent-supplied image description)."""
    description: str = Field(..., min_length=1)
```

`app.py` — two routes (new "Images" tag). Response models are the core types
(`ImageJob`, `ImageDescription`). Import `vision`, `ImageJob`, `ImageDescription`,
`ImageCaptionPut`, and `load_settings` (already imported).

```python
@app.get("/images/jobs", response_model=list[ImageJob], tags=["Images"])
async def list_image_jobs(
    include_all: Annotated[bool, Query()] = False,
    include_bytes: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=0)] = 0,
) -> list[ImageJob]:
    """Image-description jobs for an agent (agent-supplied vision)."""
    from mintmory.core import vision as vision_mod
    settings = load_settings()
    return vision_mod.image_jobs(
        get_store(), include_all=include_all, include_bytes=include_bytes,
        limit=limit, settings=settings.vision,
    )


@app.put("/images/{file_id}", response_model=ImageDescription, tags=["Images"])
async def put_image_caption(file_id: str, body: ImageCaptionPut) -> ImageDescription:
    """Store an agent-supplied description for the image file-record ``file_id``."""
    from mintmory.core import vision as vision_mod
    settings = load_settings()
    try:
        return vision_mod.image_caption_put(
            get_store(), file_id, body.description, settings=settings.vision
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

> Route ordering: declare `GET /images/jobs` BEFORE any `GET /images/{file_id}`
> (there is no GET-by-id in v1, so no shadowing — but keep `jobs` literal first if
> one is added later). `PUT /images/{file_id}` takes the path id directly (the
> HTTP transport uses the file-record id, not a path, to avoid URL-encoding the
> path; the CLI/MCP accept either).

`docs/openapi/mintmory.yaml` — add under a new "Images" tag:
- `GET /images/jobs` (operationId `listImageJobs`, query `include_all`,
  `include_bytes`, `limit`; 200 → array of `ImageJob`);
- `PUT /images/{file_id}` (operationId `putImageCaption`, path param `file_id`,
  requestBody `ImageCaptionPut`, 200 → `ImageDescription`, 404 NotFound);
- component schemas `ImageJob` (file_id, path, rel, mime, size, online_only,
  image_b64 nullable, current_summary→`current_description` nullable, oversized),
  `ImageDescription` (record → `$ref MemoryRecord`, file_id, source_image,
  replaced_description_id nullable), `ImageCaptionPut` (description, required,
  minLength 1). Mirror the `SummaryJob` / `SummaryPut` YAML style.

---

## 12. Optional extras (`packages/core/pyproject.toml`)

Mirror the `[docs]` / `[otel]` extras pattern. Both lazy-imported, NOT required:

```toml
image = ["Pillow>=10.0"]        # downscale large image payloads (lazy import; absent -> size-cap/skip)
ocr = ["pytesseract>=0.3.10"]   # local OCR for the future 'ocr' vision provider (stubbed in v1)
```

Pillow is imported lazily ONLY inside the downscale path in `core/vision.py`
(`try: from PIL import Image except ImportError: …`). pytesseract is referenced
ONLY by the future `ocr` provider (the v1 `captioner_from_settings` raises before
importing it), so the `ocr` extra ships nothing reachable in v1 beyond the error
message.

---

## 13. Determinism / invariants the implementer MUST preserve

- **No-drift (MM-17):** after `image_caption_put(F, …)`, a default `image_jobs()`
  MUST NOT return `F` on an unchanged tree. Guaranteed by §5a (existence of an
  active `image_description` ANNOTATES `F`) + §7's archive-then-add ordering.
- **Defaults reproduce today:** the existing `index-tree`/`ingest`/search tests
  pass unedited; the metadata file-record path, `render_file_record`, and
  `_TYPE_LABELS` are untouched; `get_annotating_notes` and `search()` are
  unchanged. `--vision` off ⇒ no new code runs.
- **`agent` is the only implemented provider:** `captioner_from_settings` returns
  `None` for `agent` and raises `NotImplementedError` for `llm`/`ocr`. No model is
  called in v1. The seam is the protocol + factory; concrete backends are a future
  drop-in with NO caller changes.
- **No new REQUIRED dependency / no network in the agent path:**
  `image_jobs`/`image_caption_put`/`extract_svg_text` work with the defaults and
  no extras. Pillow is lazy + guarded; absent ⇒ raw bytes (size-cap still applies).
  SVG extraction is stdlib only.
- **Combined text, not structured:** a description is ONE blob; no `{ocr, caption}`
  split. Raster + SVG only; proprietary suffixes are skip-and-flagged.
- **The ONE schema delta is idempotent:** widening `index_mode`'s CHECK to add
  `'vision'`, applied via a best-effort startup migration (mirrors
  `_ensure_is_note_column`). Old DBs keep working; `'vision'` is only ever written
  by `--vision`. The `ANNOTATES` link type already exists in the schema CHECK —
  no link-type schema change.
- **Descriptions are `is_note=False`:** they use a SEPARATE reverse-ANNOTATES
  helper (`get_annotating_descriptions`, filtering `kind='image_description'`),
  never the notes helper, so they never leak into `notes_on_results`.
- **Transports are thin:** they only marshal types and call `core/vision.py`.
  `limit` is applied AFTER selection (post-slice), `0` = no cap (matching MM-17).

---

## 14. Tests (contract)

Group by ownership (see tasks.md). Minimum coverage:

- **core types (`tests/test_types.py` or `test_schema.py`):** `ImageJob` /
  `ImageDescription` round-trip `model_dump(mode="json")`; defaults
  (`image_b64=None`, `oversized=False`, `current_description=None`,
  `replaced_description_id=None`).
- **core config (`tests/test_config.py`):** `VisionSettings` defaults
  (`provider=agent`, caps); `MINTMORY_VISION_PROVIDER=llm` parses to the enum;
  `max_image_bytes`/`max_download_bytes` derivations; `Settings().vision` present.
- **core vision — SVG (`tests/test_vision.py`):** `extract_svg_text` pulls
  `<text>/<tspan>/<title>/<desc>` (namespaced and not), joins/dedups, returns `""`
  on malformed XML and on a text-free SVG; does NOT raise.
- **core vision — provider seam:** `captioner_from_settings()` returns `None` for
  `agent`; raises `NotImplementedError` (clear message) for `llm` and `ocr`.
- **core vision — `image_jobs`:** with two indexed raster file-records and no
  descriptions, default returns both (sorted by `rel`); after
  `image_caption_put` on one, default returns only the other but `include_all=True`
  returns both (the described one carries `current_description`); SVG file-records
  and proprietary suffixes never appear; `limit` caps post-selection; hybrid bytes
  — an `online_only` record gets `image_b64` populated (mock the byte source),
  a local record gets `None` unless `include_bytes=True`; an oversized file (size >
  `max_image_mb`) gets `image_b64=None` + `oversized=True`; Pillow-absent path
  still embeds raw bytes within cap.
- **core vision — `image_caption_put`:** creates a `context`/`is_note=False`
  memory with `metadata.kind='image_description'` and an ANNOTATES link
  (`LinkSource.INFERENCE`) to the file-record; resolves by id AND by path;
  `KeyError` on an unknown path; **idempotent replace** — second put archives the
  first (`replaced_description_id` set) and `get_annotating_descriptions` returns
  exactly one active record; **no-drift round-trip** — put then default
  `image_jobs()` omits the image.
- **core storage:** `get_annotating_descriptions` returns active
  `image_description` records (not notes, not archived); does not overlap
  `get_annotating_notes` (a note ANNOTATES the same target is NOT returned);
  `find_image_file_record` resolves by path and by rel; the `index_mode='vision'`
  CHECK migration — a DB created with the old two-value CHECK accepts a
  `manifest_upsert(..., index_mode='vision')` AFTER `initialise()` (and a fresh DB
  does too); migration is idempotent on re-`initialise`.
- **CLI:** `index-tree --vision` on a tiny tree with one `.svg` (with text), one
  `.png`, one `.xd` → svg-described=1, images-queued=1 (provider=agent),
  vision-skipped=1; manifest rows show `index_mode='vision'` for the svg+png; a
  re-run is incremental (no re-describe of the SVG); `index-tree` WITHOUT
  `--vision` is unchanged. `image-jobs` (table/`--json`/`--all`/`--bytes`/
  `--limit`); `image-caption-put` (text arg/`--file`/stdin/empty rejection/unknown
  path error). `MINTMORY_VISION_PROVIDER=llm` + `index-tree --vision` exits
  non-zero with the clear message.
- **MCP (`tests/test_tools.py`):** `image_jobs` returns job dicts (incl.
  `include_all`/`limit`); `image_caption_put` stores and the image then drops from
  default `image_jobs`; empty description → `bad_request`; unknown path →
  `not_found`; both with provider=agent (no backend).
- **API (`tests/test_routes.py`):** `GET /images/jobs` 200 (query params);
  `PUT /images/{file_id}` 200 returns `ImageDescription`; unknown id → 404; the
  put removes the image from the default `GET /images/jobs`.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`,
`mypy --strict`.
