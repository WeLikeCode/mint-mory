"""
MintMory image-understanding (G5 — agent-supplied vision).

Design rules (design.md §§1-7):
  * No LLM, no network in the ``agent`` (default) path.  ``image_jobs`` /
    ``image_caption_put`` / ``extract_svg_text`` work with ZERO extras installed
    and ZERO environment variables set.
  * Pillow ([image] extra) is lazy-imported ONLY inside the downscale helper.
    Absent → raw bytes are embedded at full size (subject to the on-disk size cap).
  * SVG text extraction is pure stdlib (xml.etree.ElementTree).
  * ``llm`` / ``ocr`` providers are STUBS that raise ``NotImplementedError`` with
    a clear message; a future change replaces those branches with concrete classes
    WITHOUT touching any caller.
  * No-drift guarantee (§5a): after ``image_caption_put(F, …)``, a subsequent
    default ``image_jobs()`` MUST NOT re-surface ``F``.  Achieved by the
    archive-then-add discipline in ``image_caption_put`` and the existence-only
    predicate in ``image_jobs``.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mintmory.core.types import (
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
    """Server-side image-to-text backend (the SEAM for future llm/ocr providers).

    v1 has NO implementation: the ``agent`` provider returns ``None`` from the
    factory (the agent supplies text via image_jobs/image_caption_put), and
    ``llm``/``ocr`` raise NotImplementedError.  A future change adds concrete
    classes here WITHOUT changing image_jobs/image_caption_put or any caller.
    """

    def describe(self, image: ImageInput) -> ImageDescription:
        """Describe *image* and return the persisted ``ImageDescription``."""
        ...


def captioner_from_settings(settings: VisionSettings | None = None) -> Captioner | None:
    """Resolve the configured vision backend.

    - ``agent`` (DEFAULT): returns ``None`` — there is no server-side backend;
      callers use the image_jobs/image_caption_put prepare/apply loop instead.
    - ``llm``: v1 raises ``NotImplementedError`` with a clear message.
    - ``ocr``: v1 raises ``NotImplementedError`` likewise.

    A future change replaces the two ``raise`` branches with real classes; the
    ``agent``→``None`` branch and every caller stay unchanged.
    """
    from mintmory.core.config import VisionProvider  # noqa: PLC0415
    from mintmory.core.config import VisionSettings as _VisionSettings  # noqa: PLC0415

    s: VisionSettings = settings if settings is not None else _VisionSettings()
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
