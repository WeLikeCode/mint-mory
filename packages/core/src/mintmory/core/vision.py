"""
MintMory image-understanding (G5 — agent-supplied + automated llm vision).

Design rules (design.md §§1-7):
  * No LLM, no network in the ``agent`` (default) path.  ``image_jobs`` /
    ``image_caption_put`` / ``extract_svg_text`` work with ZERO extras installed
    and ZERO environment variables set.
  * Pillow ([image] extra) is lazy-imported ONLY inside the downscale helper.
    Absent → raw bytes are embedded at full size (subject to the on-disk size cap).
  * SVG text extraction is pure stdlib (xml.etree.ElementTree).
  * ``llm`` provider: implemented as ``LLMCaptioner`` — calls the configured
    OpenAI-compatible vision model via the shared ``core/llm.py`` urllib poster.
    Any per-image failure raises ``VisionError`` so the apply paths skip and continue.
  * ``ocr`` provider stays a stub (raises ``NotImplementedError``).
  * No-drift guarantee (§5a): after ``image_caption_put(F, …)``, a subsequent
    default ``image_jobs()`` MUST NOT re-surface ``F``.  Achieved by the
    archive-then-add discipline in ``image_caption_put`` and the existence-only
    predicate in ``image_jobs``.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from mintmory.core.types import (
    CaptionRunItem,
    CaptionRunReport,
    ConceptLink,
    ConceptLinkType,
    ImageDescription,
    ImageJob,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)

if TYPE_CHECKING:
    from mintmory.core.config import VisionSettings
    from mintmory.core.storage import StorageAdapter


# ---------------------------------------------------------------------------
# §1 — Suffix sets (FROZEN)
# ---------------------------------------------------------------------------

# Raster images that need the agent/provider to describe.
RASTER_SUFFIXES: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
# Vector images we can self-describe from embedded <text> (pure-Python).
SVG_SUFFIXES: frozenset[str] = frozenset({".svg"})
# All image suffixes index-tree's --vision flag treats as the third content mode.
IMAGE_SUFFIXES: frozenset[str] = RASTER_SUFFIXES | SVG_SUFFIXES
# Proprietary design formats — OUT OF SCOPE for v1 (metadata-only).
PROPRIETARY_IMAGE_SUFFIXES: frozenset[str] = frozenset({".xd", ".vsdx", ".dwg", ".psd", ".eps"})

# Best-effort MIME type from suffix.
_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}


def _mime_for(suffix: str) -> str:
    """Return the best-effort MIME type for *suffix* (lowercased, with leading dot)."""
    return _MIME_MAP.get(suffix, "application/octet-stream")


# ---------------------------------------------------------------------------
# §2a — VisionError: per-image failure that callers catch and skip
# ---------------------------------------------------------------------------


class VisionError(RuntimeError):
    """A vision-provider call failed for one image (network/timeout/HTTP/empty
    response/decode). Callers (caption_pending_images, index-tree --vision) catch
    this, skip the single image, and continue — one bad image never aborts a run."""


# ---------------------------------------------------------------------------
# §4 — Provider seam: Captioner protocol + ImageInput + factory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageInput:
    """Inputs a Captioner needs to describe one image (path and/or bytes)."""

    file_id: str
    path: str
    mime: str
    data: bytes | None = None  # in-memory bytes when already loaded/downloaded


@runtime_checkable
class Captioner(Protocol):
    """Server-side image-to-text backend.

    The ``agent`` provider returns ``None`` from the factory (the agent supplies
    text via image_jobs/image_caption_put). ``llm`` is implemented as
    ``LLMCaptioner``. ``ocr`` raises ``NotImplementedError``.
    """

    def describe(self, image: ImageInput) -> ImageDescription:
        """Describe *image* and return a transient ``ImageDescription``."""
        ...


# ---------------------------------------------------------------------------
# §2c — LLMCaptioner: automated Captioner via OpenAI-compatible vision model
# ---------------------------------------------------------------------------


class LLMCaptioner:
    """Automated Captioner: caption a raster image via an OpenAI-compatible VISION
    model. Reuses the core/llm.py stdlib-urllib /chat/completions machinery (Bearer
    api_key, timeout, gen_ai OTel span, <think> stripping) with a multimodal user
    message. No new dependency; no openai SDK. Raises VisionError on any failure so
    the caller skips the one image and continues."""

    def __init__(self, settings: VisionSettings) -> None:
        self.settings = settings

    def describe(self, image: ImageInput) -> ImageDescription:  # noqa: C901
        """Describe *image* and return a TRANSIENT ``ImageDescription``.

        The returned record is NOT persisted — callers must call
        ``image_caption_put`` to persist (archive-then-add, no-drift).
        Raises ``VisionError`` on any network/timeout/HTTP/empty/decode failure.
        """
        from mintmory.core import llm as llm_mod  # noqa: PLC0415 — avoid circular at import time
        from mintmory.core.prompts import IMAGE_CAPTION_PROMPT  # noqa: PLC0415

        # 1. Get bytes.
        if image.data is not None:
            raw: bytes = image.data
        else:
            try:
                with open(image.path, "rb") as fh:  # noqa: PTH123
                    raw = fh.read()
            except OSError as exc:
                raise VisionError(f"cannot read {image.path}: {exc}") from exc

        # 2. Downscale (reuse existing lazy-Pillow helper).
        raw = _downscale_bytes(raw, image.mime, self.settings.downscale_max_px)

        # 3. Build data URL.
        b64 = base64.b64encode(raw).decode("ascii")
        data_url = f"data:{image.mime};base64,{b64}"

        # 4. Build the multimodal /chat/completions payload.
        prompt = self.settings.vision_prompt or IMAGE_CAPTION_PROMPT
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": self.settings.vision_temperature,
            "max_tokens": self.settings.vision_max_tokens,
            "stream": False,
        }

        # 5. POST via shared poster; wrap all errors in VisionError.
        try:
            data = llm_mod.post_chat_completion(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                payload=payload,
                timeout_s=self.settings.vision_timeout_s,
                system=f"vision:{self.settings.provider.value}",
                model=self.settings.model,
            )
            try:
                content: str = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise VisionError("unexpected vision response shape") from exc
        except VisionError:
            raise
        except Exception as exc:
            raise VisionError(str(exc)) from exc

        if not content or not content.strip():
            raise VisionError("vision model returned empty content")

        # 6. Strip <think> blocks.
        text = llm_mod._THINK_RE.sub("", content).strip()  # noqa: SLF001
        if not text:
            raise VisionError("vision model returned only reasoning")

        # 7. Return a TRANSIENT ImageDescription (not persisted).
        record = MemoryRecord(
            content=text,
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            is_note=False,
            metadata={
                "kind": "image_description",
                "source_image": image.path,
            },
        )
        return ImageDescription(
            record=record,
            file_id=image.file_id,
            source_image=image.path,
            replaced_description_id=None,
        )


def captioner_from_settings(settings: VisionSettings | None = None) -> Captioner | None:
    """Resolve the configured vision backend.

    - ``agent`` (DEFAULT): returns ``None`` — there is no server-side backend;
      callers use the image_jobs/image_caption_put prepare/apply loop instead.
    - ``llm``: returns an ``LLMCaptioner`` for the configured vision model.
    - ``ocr``: raises ``NotImplementedError`` (stub; not yet implemented).

    The ``agent``→``None`` branch and every caller are unchanged by this factory.
    """
    from mintmory.core.config import VisionProvider  # noqa: PLC0415
    from mintmory.core.config import VisionSettings as _VisionSettings  # noqa: PLC0415

    s: VisionSettings = settings if settings is not None else _VisionSettings()
    if s.provider is VisionProvider.AGENT:
        return None
    if s.provider is VisionProvider.LLM:
        return LLMCaptioner(s)  # CHANGED — was: raise NotImplementedError(...)
    if s.provider is VisionProvider.OCR:
        raise NotImplementedError(
            "vision provider 'ocr' is not implemented in this version; "
            "set MINTMORY_VISION_PROVIDER=agent for the agent-supplied loop"
        )
    raise NotImplementedError(f"unknown vision provider {s.provider!r}")  # defensive


# ---------------------------------------------------------------------------
# §6 — SVG self-description (pure stdlib, no model, no agent)
# ---------------------------------------------------------------------------

# Local tag names from which visible text is extracted.
_SVG_TEXT_TAGS: frozenset[str] = frozenset({"text", "tspan", "title", "desc", "textpath"})


def extract_svg_text(svg_bytes: bytes) -> str:
    """Extract visible text from an SVG via its embedded XML elements.

    Collects ``.text`` and ``.tail`` of every element whose **local** tag
    (after stripping any ``{namespace}`` prefix) is one of ``text``, ``tspan``,
    ``title``, ``desc``, ``textPath``.  Strips each fragment; drops empties;
    joins with ``"\\n"``; collapses runs of identical adjacent lines.

    Returns ``""`` when the SVG contains no extractable text, is not parseable,
    or *svg_bytes* is empty.  NEVER raises.

    Uses ``xml.etree.ElementTree`` (stdlib) — does NOT expand external general
    entities (the stdlib default), so no XXE risk.
    """
    if not svg_bytes:
        return ""
    try:
        root = ET.fromstring(svg_bytes)  # noqa: S314 — stdlib ET, no ext entities
    except ET.ParseError:
        return ""

    fragments: list[str] = []
    for elem in root.iter():
        # Strip namespace prefix: "{http://www.w3.org/2000/svg}text" → "text"
        local = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
        if local in _SVG_TEXT_TAGS:
            if elem.text:
                stripped = elem.text.strip()
                if stripped:
                    fragments.append(stripped)
            if elem.tail:
                stripped = elem.tail.strip()
                if stripped:
                    fragments.append(stripped)

    if not fragments:
        return ""

    # Collapse runs of identical adjacent lines.
    deduped: list[str] = [fragments[0]]
    for line in fragments[1:]:
        if line != deduped[-1]:
            deduped.append(line)
    return "\n".join(deduped)


# ---------------------------------------------------------------------------
# §5b — Lazy Pillow downscale helper
# ---------------------------------------------------------------------------


def _downscale_bytes(
    data: bytes,
    mime: str,
    max_px: int,
) -> bytes:
    """Downscale *data* so the longest edge ≤ *max_px* (Pillow, lazy-imported).

    Returns *data* unchanged when:
    - Pillow is not installed (lazy import fails).
    - *max_px* ≤ 0.
    - The image is already within the pixel budget.
    - Any Pillow error is raised (corrupt image, unsupported format, etc.).

    The output format is preserved (PNG → PNG; JPEG/JPG → JPEG).  Other formats
    fall back to PNG for lossless round-trip.  NEVER raises.
    """
    if max_px <= 0:
        return data
    try:
        from PIL import Image  # noqa: PLC0415 — lazy, optional [image] extra
    except ImportError:
        return data
    try:
        import io  # noqa: PLC0415

        img: Image.Image = Image.open(io.BytesIO(data))
        w, h = img.size
        if max(w, h) <= max_px:
            return data  # already small enough

        # Compute new size preserving aspect ratio.
        scale = max_px / max(w, h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        # Image.Resampling.LANCZOS is the canonical constant on Pillow >=9.1
        # (the [image] extra pins Pillow>=10.0, so the enum is always present).
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        fmt: str
        if mime in ("image/jpeg",):
            fmt = "JPEG"
            # JPEG doesn't support transparency — convert if needed.
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
        else:
            fmt = "PNG"
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — any Pillow error: fall back to raw bytes
        return data


# ---------------------------------------------------------------------------
# §5 — image_jobs (discovery)
# ---------------------------------------------------------------------------


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
    ``metadata["ext"]`` is in ``IMAGE_SUFFIXES``.  Does NOT walk the filesystem
    and does NOT call any model (works with the defaults / provider=agent).

    Selection (the needs-redescribe predicate, §5a):
      * By DEFAULT (``include_all=False``) returns only RASTER image file-records
        that NEED a (re)description — i.e. those with NO active (non-archived)
        ``image_description`` memory ANNOTATES-linking them.
      * SVG file-records are NEVER returned as agent jobs.
      * Proprietary suffixes are NEVER returned.
      * ``include_all=True`` returns every RASTER image file-record regardless of
        existing descriptions.

    Hybrid bytes (§5b): ``image_b64`` is populated when ``online_only OR
    include_bytes``, subject to size cap and download budget.

    Order: image file-records sorted by ``rel`` then ``file_id``.
    ``limit`` (>0) caps the returned list AFTER selection (post-slice).
    """
    from mintmory.core.config import VisionSettings as _VisionSettings  # noqa: PLC0415

    s: VisionSettings = settings if settings is not None else _VisionSettings()
    max_image_bytes: int | None = s.max_image_bytes
    max_download_bytes: int | None = s.max_download_bytes
    downscale_max_px: int = s.downscale_max_px

    conn = adapter.connect()
    # Fetch all active, non-archived memories whose metadata has an 'ext' key
    # that falls in IMAGE_SUFFIXES.  We load candidates and filter in Python —
    # SQLite's json_extract can do this but the suffix set is small enough that
    # Python post-filtering is straightforward and avoids a long IN(…) literal.
    rows = conn.execute(
        "SELECT * FROM memories "
        "WHERE is_archived = 0 "
        "AND json_extract(metadata, '$.kind') IS NULL "
        "AND json_extract(metadata, '$.ext') IS NOT NULL "
        "ORDER BY json_extract(metadata, '$.rel'), id"
    ).fetchall()

    candidates: list[MemoryRecord] = []
    for row in rows:
        rec = adapter._row_to_memory(row)
        ext: str = rec.metadata.get("ext", "")
        if ext not in IMAGE_SUFFIXES:
            continue
        if ext in PROPRIETARY_IMAGE_SUFFIXES:
            continue
        if ext in SVG_SUFFIXES:
            # SVGs are self-described during index-tree --vision; never an agent job.
            continue
        # ext must be in RASTER_SUFFIXES now.
        candidates.append(rec)

    # Apply the needs-redescribe predicate (§5a).
    selected: list[MemoryRecord] = []
    for rec in candidates:
        if include_all:
            selected.append(rec)
        else:
            has_desc = bool(adapter.get_annotating_descriptions(rec.id, 1))
            if not has_desc:
                selected.append(rec)

    # Apply limit after selection.
    if limit > 0:
        selected = selected[:limit]

    # Build ImageJob objects with the hybrid-bytes rule (§5b).
    jobs: list[ImageJob] = []
    download_budget_used: int = 0

    for rec in selected:
        ext = rec.metadata.get("ext", "")
        path: str = rec.metadata.get("path", "")
        rel: str = rec.metadata.get("rel", "")
        size: int = int(rec.metadata.get("size", 0))
        online_only: bool = bool(rec.metadata.get("online_only", False))
        mime: str = _mime_for(ext)

        # Retrieve current_description when include_all surfaces described images.
        current_description: str | None = None
        if include_all:
            descs = adapter.get_annotating_descriptions(rec.id, 1)
            if descs:
                current_description = descs[0].content

        want_bytes: bool = include_bytes or online_only
        image_b64: str | None = None
        oversized: bool = False

        if want_bytes:
            # Step 3 (size cap): check BEFORE reading bytes.
            if max_image_bytes is not None and size > max_image_bytes:
                oversized = True
                # Do NOT embed; agent falls back to path.
            else:
                raw: bytes | None = None
                if online_only:
                    # Download budget gate.
                    budget_remaining = (
                        max_download_bytes - download_budget_used
                        if max_download_bytes is not None
                        else None
                    )
                    # Skip embedding further online-only payloads when budget exhausted.
                    if budget_remaining is not None and size > budget_remaining:
                        # Budget hit — leave image_b64=None; job remains valid via path.
                        raw = None
                    else:
                        try:
                            with open(path, "rb") as fh:  # noqa: PTH123
                                raw = fh.read()
                            download_budget_used += len(raw)
                        except OSError:
                            raw = None
                else:
                    # Local file — free read, no budget.
                    try:
                        with open(path, "rb") as fh:  # noqa: PTH123
                            raw = fh.read()
                    except OSError:
                        raw = None

                if raw is not None:
                    # Step 4: optional Pillow downscale.
                    raw = _downscale_bytes(raw, mime, downscale_max_px)
                    # Step 5: base64 encode.
                    image_b64 = base64.b64encode(raw).decode("ascii")

        jobs.append(
            ImageJob(
                file_id=rec.id,
                path=path,
                rel=rel,
                mime=mime,
                size=size,
                online_only=online_only,
                image_b64=image_b64,
                current_description=current_description,
                oversized=oversized,
            )
        )

    return jobs


# ---------------------------------------------------------------------------
# §7 — image_caption_put (apply; mirrors apply_summary + MM-16 anchoring)
# ---------------------------------------------------------------------------


def image_caption_put(
    adapter: StorageAdapter,
    file_id_or_path: str,
    description: str,
    *,
    settings: VisionSettings | None = None,  # noqa: ARG001 — reserved for future providers
) -> ImageDescription:
    """Persist an agent-supplied (or SVG-extracted) description for one image.

    ``file_id_or_path`` resolves to the image FILE-RECORD: if it is the id of an
    existing memory it is used directly; otherwise it is treated as a path and the
    most recent ACTIVE file-record whose ``metadata["path"]`` or ``metadata["rel"]``
    equals it is used.  Raises ``KeyError`` if no image file-record can be resolved.

    Creates a new ``MemoryRecord`` with:
        category=context, source=document, is_note=False,
        metadata={"kind": "image_description", "source_image": <path>,
                  "collection": <file-record collection if present>}

    Then ANNOTATES-links it to the file-record via ``ConceptLink`` with
    ``LinkSource.INFERENCE``, ``strength=1.0``, ``confidence=1.0``.

    Idempotent / no-drift (§5a, §7): BEFORE adding the new description, ALL existing
    ACTIVE ``image_description`` memories that ANNOTATE this file-record are ARCHIVED
    (``adapter.archive_memory``).  So re-putting REPLACES the prior description
    (archive old → add new).  A subsequent default ``image_jobs()`` will NOT
    re-surface the image.

    ``description`` is stored verbatim; the caller owns whitespace.  The core does
    NOT guard against whitespace-only content (that check belongs at transport level).
    """
    # ------------------------------------------------------------------
    # Step 1: resolve file-record.
    # ------------------------------------------------------------------
    file_record: MemoryRecord | None = adapter.get_memory(file_id_or_path)
    if file_record is None:
        # Try path/rel resolution.
        file_record = adapter.find_image_file_record(file_id_or_path)
    if file_record is None:
        raise KeyError(
            f"no active image file-record found for {file_id_or_path!r}; "
            "ensure the file has been indexed with 'mintmory index-tree' first"
        )

    file_id: str = file_record.id
    source_image: str = file_record.metadata.get("path", file_id_or_path)
    rel: str = file_record.metadata.get("rel", source_image)
    collection: str | None = file_record.metadata.get("collection")

    # ------------------------------------------------------------------
    # Step 2: archive existing active descriptions FIRST (no-drift guarantee).
    # ------------------------------------------------------------------
    existing_descs: list[MemoryRecord] = adapter.get_annotating_descriptions(file_id, 100)
    replaced_description_id: str | None = None
    for desc in existing_descs:
        if replaced_description_id is None:
            replaced_description_id = desc.id
        adapter.archive_memory(desc.id)

    # ------------------------------------------------------------------
    # Step 3: add the new description memory.
    # ------------------------------------------------------------------
    desc_metadata: dict[str, object] = {
        "kind": "image_description",
        "source_image": source_image,
    }
    if collection is not None:
        desc_metadata["collection"] = collection

    new_desc: MemoryRecord = adapter.add_memory(
        record=MemoryRecord(
            content=description,
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            is_note=False,
            metadata=desc_metadata,
        )
    )

    # ------------------------------------------------------------------
    # Step 4: ANNOTATES-link the description to the file-record.
    # ------------------------------------------------------------------
    link = ConceptLink(
        source_memory_id=new_desc.id,
        target_memory_id=file_id,
        link_type=ConceptLinkType.ANNOTATES,
        entity=rel,
        source=LinkSource.INFERENCE,
        strength=1.0,
        confidence=1.0,
    )
    adapter.add_link(link)

    return ImageDescription(
        record=new_desc,
        file_id=file_id,
        source_image=source_image,
        replaced_description_id=replaced_description_id,
    )


# ---------------------------------------------------------------------------
# §3 — caption_pending_images (automated apply path)
# ---------------------------------------------------------------------------


def caption_pending_images(
    adapter: StorageAdapter,
    *,
    captioner: Captioner,
    limit: int = 0,
    budget: int | None = None,
    include_all: bool = False,
    settings: VisionSettings | None = None,
) -> CaptionRunReport:
    """Caption pending raster images with a server-side ``captioner`` and persist
    each via image_caption_put.

    Walks ``image_jobs(adapter, include_all=include_all, include_bytes=True,
    limit=limit, settings=settings)`` — the SAME discovery + no-drift predicate
    as the agent loop — and for each job:

    * if the job is oversized (image_b64 is None AND oversized=True): SKIP
      (count skipped, note 'oversized').
    * obtain bytes: prefer the job's already-embedded image_b64 (base64-decode);
      else read job.path. For online_only files with no embedded bytes, the byte
      read counts against ``budget``; once the running total exceeds budget, STOP
      captioning further online-only images (count skipped, note 'budget');
      set budget_hit. Local reads do not consume budget.
    * call ``captioner.describe(ImageInput(…))``; on ``VisionError``, SKIP
      (count failed, note = error text); continue.
    * on success, persist via ``image_caption_put`` and count described.

    Returns a ``CaptionRunReport``. Per-image failures NEVER abort the run.
    """
    from mintmory.core.config import VisionSettings as _VisionSettings  # noqa: PLC0415

    s: VisionSettings = settings if settings is not None else _VisionSettings()

    # Resolve effective budget: caller-supplied > settings default.
    effective_budget: int | None = budget if budget is not None else s.max_download_bytes

    jobs: list[ImageJob] = image_jobs(
        adapter,
        include_all=include_all,
        include_bytes=True,
        limit=limit,
        settings=s,
    )

    described = 0
    skipped = 0
    failed = 0
    budget_hit = False
    download_used: int = 0
    items: list[CaptionRunItem] = []

    for job in jobs:
        # ------------------------------------------------------------------
        # Oversized check (image_jobs already set oversized=True when so).
        # ------------------------------------------------------------------
        if job.oversized:
            skipped += 1
            items.append(
                CaptionRunItem(file_id=job.file_id, rel=job.rel, status="skipped", note="oversized")
            )
            continue

        # ------------------------------------------------------------------
        # Obtain bytes.
        # ------------------------------------------------------------------
        raw: bytes | None = None

        if job.image_b64 is not None:
            # image_jobs already read & embedded (include_bytes=True).
            raw = base64.b64decode(job.image_b64)
        elif job.online_only:
            # online_only + no image_b64 means budget was already exhausted
            # inside image_jobs, or the read failed. Check our run-level budget.
            if effective_budget is not None and download_used >= effective_budget:
                budget_hit = True
                skipped += 1
                items.append(
                    CaptionRunItem(
                        file_id=job.file_id, rel=job.rel, status="skipped", note="budget"
                    )
                )
                continue
            # Try to read (online_only path is a local mirror path).
            try:
                with open(job.path, "rb") as fh:  # noqa: PTH123
                    raw = fh.read()
                download_used += len(raw)
                if effective_budget is not None and download_used >= effective_budget:
                    budget_hit = True
            except OSError:
                # Unreadable online-only: count as failed.
                failed += 1
                items.append(
                    CaptionRunItem(
                        file_id=job.file_id,
                        rel=job.rel,
                        status="failed",
                        note="cannot read online_only path",
                    )
                )
                continue
        else:
            # Local file not embedded (include_bytes=True but image_jobs couldn't read it).
            try:
                with open(job.path, "rb") as fh:  # noqa: PTH123
                    raw = fh.read()
            except OSError as exc:
                failed += 1
                items.append(
                    CaptionRunItem(
                        file_id=job.file_id,
                        rel=job.rel,
                        status="failed",
                        note=f"cannot read: {exc}",
                    )
                )
                continue

        if raw is None:
            # Shouldn't normally reach here, but guard defensively.
            skipped += 1
            items.append(
                CaptionRunItem(file_id=job.file_id, rel=job.rel, status="skipped", note="no bytes")
            )
            continue

        # ------------------------------------------------------------------
        # Describe.
        # ------------------------------------------------------------------
        img_input = ImageInput(file_id=job.file_id, path=job.path, mime=job.mime, data=raw)
        try:
            description = captioner.describe(img_input)
        except VisionError as exc:
            failed += 1
            items.append(
                CaptionRunItem(file_id=job.file_id, rel=job.rel, status="failed", note=str(exc))
            )
            continue

        # ------------------------------------------------------------------
        # Persist.
        # ------------------------------------------------------------------
        put = image_caption_put(adapter, job.file_id, description.record.content, settings=s)
        described += 1
        note = put.record.id
        if put.replaced_description_id is not None:
            note = f"{put.record.id} (replaced {put.replaced_description_id})"
        items.append(
            CaptionRunItem(file_id=job.file_id, rel=job.rel, status="described", note=note)
        )

    return CaptionRunReport(
        described=described,
        skipped=skipped,
        failed=failed,
        budget_hit=budget_hit,
        provider="llm",
        items=items,
    )
