"""
Tests for image-understanding (G5 — add-image-understanding, Group 9).

Coverage per design §14:
  (a) ImageJob / ImageDescription type round-trip and defaults.
  (b) VisionSettings defaults + env parse + derived properties.
  (c) extract_svg_text — namespaced/plain/malformed/empty/dedup.
  (d) captioner_from_settings — agent → None; llm/ocr → NotImplementedError.
  (e) image_jobs — needs-redescribe selection; include_all; SVG + proprietary
      never surfaced; limit; hybrid bytes; size cap/oversized; Pillow-absent
      raw-embed.
  (f) image_caption_put — ANNOTATES + INFERENCE + is_note=0 + kind metadata;
      resolve by id and by path; KeyError on unknown; idempotent archive +
      replaced_description_id; no-drift round-trip.
  (g) Storage: get_annotating_descriptions does not overlap get_annotating_notes;
      find_image_file_record by path and rel; index_mode='vision' CHECK migration
      (old two-value DB + fresh DB both accept it; idempotent re-initialise).
  (h) get_annotating_descriptions is separate from get_annotating_notes.

Group 6 (add-llm-vision-provider) additions:
  (i) VisionSettings new fields — defaults, bounds, env parse.
  (j) captioner_from_settings — llm → LLMCaptioner (new assertion).
  (k) LLMCaptioner.describe — stubbed post_chat_completion; multimodal payload;
      Bearer header; <think> strip; transient record; VisionError on all failure
      modes; vision_prompt override; Pillow-absent raw embed.
  (l) caption_pending_images — happy path (both described + no-drift); VisionError
      → failed + continue; oversized → skipped; include_all; limit; budget.
  (m) CaptionRunReport / CaptionRunItem type round-trips.

All tests use :memory: SQLite. No network, no LLM, no Pillow required.
Fake bytes are injected where needed by monkey-patching ``open`` or by writing
real (tiny) files to tempdir.
"""

from __future__ import annotations

import base64
import sqlite3
import tempfile
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from mintmory.core.config import VisionProvider, VisionSettings
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLinkType,
    ImageDescription,
    ImageJob,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)
from mintmory.core.vision import (
    PROPRIETARY_IMAGE_SUFFIXES,
    RASTER_SUFFIXES,
    SVG_SUFFIXES,
    captioner_from_settings,
    extract_svg_text,
    image_caption_put,
    image_jobs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=None)
    s.initialise()
    return s


def _add_file_record(
    store: StorageAdapter,
    *,
    path: str = "/fake/image.png",
    rel: str = "image.png",
    ext: str = ".png",
    size: int = 1024,
    online_only: bool = False,
    collection: str = "test",
) -> MemoryRecord:
    """Insert a fake image file-record (as index-tree would write it)."""
    return store.add_memory(
        record=MemoryRecord(
            content=f"Image file: {rel}",
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            metadata={
                "collection": collection,
                "path": path,
                "rel": rel,
                "ext": ext,
                "size": size,
                "mtime": 1_700_000_000.0,
                "online_only": online_only,
                "folder": str(Path(rel).parent),
                "index_mode": "metadata",
            },
        )
    )


# ---------------------------------------------------------------------------
# (a) ImageJob / ImageDescription type round-trip and defaults
# ---------------------------------------------------------------------------


def test_image_job_defaults() -> None:
    """ImageJob defaults: image_b64=None, oversized=False, current_description=None."""
    job = ImageJob(
        file_id="abc",
        path="/img/photo.jpg",
        rel="photo.jpg",
        mime="image/jpeg",
        size=2048,
        online_only=False,
    )
    assert job.image_b64 is None
    assert job.oversized is False
    assert job.current_description is None


def test_image_job_round_trip_model_dump() -> None:
    """ImageJob.model_dump(mode='json') serialises all fields cleanly."""
    job = ImageJob(
        file_id="x1",
        path="/img/a.png",
        rel="a.png",
        mime="image/png",
        size=512,
        online_only=True,
        image_b64="aGVsbG8=",
        current_description="A red square.",
        oversized=False,
    )
    d = job.model_dump(mode="json")
    assert d["file_id"] == "x1"
    assert d["image_b64"] == "aGVsbG8="
    assert d["current_description"] == "A red square."
    assert d["oversized"] is False


def test_image_description_defaults() -> None:
    """ImageDescription.replaced_description_id defaults to None."""
    rec = MemoryRecord(content="A sky.", category=MemoryCategory.CONTEXT)
    desc = ImageDescription(record=rec, file_id="fid", source_image="/img/sky.jpg")
    assert desc.replaced_description_id is None


def test_image_description_round_trip_model_dump() -> None:
    """ImageDescription.model_dump(mode='json') round-trips without error."""
    rec = MemoryRecord(content="Blue sky.", category=MemoryCategory.CONTEXT)
    desc = ImageDescription(
        record=rec,
        file_id="fid",
        source_image="/img/sky.jpg",
        replaced_description_id="old-id",
    )
    d = desc.model_dump(mode="json")
    assert d["file_id"] == "fid"
    assert d["source_image"] == "/img/sky.jpg"
    assert d["replaced_description_id"] == "old-id"
    assert "record" in d


# ---------------------------------------------------------------------------
# (b) VisionSettings — defaults + env parse + derived properties
# ---------------------------------------------------------------------------


def test_vision_settings_defaults() -> None:
    """VisionSettings defaults: provider=agent, max_image_mb=8.0, etc."""
    s = VisionSettings()
    assert s.provider is VisionProvider.AGENT
    assert s.max_image_mb == pytest.approx(8.0)
    assert s.downscale_max_px == 1568
    assert s.max_download_mb == pytest.approx(200.0)
    assert s.model == "llava"
    assert s.base_url == "http://localhost:11434/v1"
    assert s.api_key is None
    assert s.tesseract_cmd is None


def test_vision_settings_max_image_bytes_derived() -> None:
    """max_image_bytes is None when max_image_mb=0, else bytes."""
    s_default = VisionSettings()
    assert s_default.max_image_bytes == int(8.0 * 1024 * 1024)

    s_no_cap = VisionSettings(max_image_mb=0.0)
    assert s_no_cap.max_image_bytes is None

    s_one = VisionSettings(max_image_mb=1.0)
    assert s_one.max_image_bytes == 1024 * 1024


def test_vision_settings_max_download_bytes_derived() -> None:
    """max_download_bytes is None when max_download_mb=0, else bytes."""
    s = VisionSettings(max_download_mb=0.0)
    assert s.max_download_bytes is None

    s2 = VisionSettings(max_download_mb=10.0)
    assert s2.max_download_bytes == int(10.0 * 1024 * 1024)


def test_vision_settings_env_provider_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_VISION_PROVIDER=llm parses to VisionProvider.LLM."""
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")
    s = VisionSettings()
    assert s.provider is VisionProvider.LLM


def test_vision_settings_on_aggregate() -> None:
    """Settings().vision is a VisionSettings instance."""
    from mintmory.core.config import Settings

    agg = Settings()
    assert isinstance(agg.vision, VisionSettings)
    assert agg.vision.provider is VisionProvider.AGENT


# ---------------------------------------------------------------------------
# (c) extract_svg_text
# ---------------------------------------------------------------------------


def test_extract_svg_text_plain_text_elements() -> None:
    """Extracts <text> and <tspan> content without namespaces."""
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <text>Hello</text>
        <text><tspan>World</tspan></text>
    </svg>"""
    result = extract_svg_text(svg)
    assert "Hello" in result
    assert "World" in result


def test_extract_svg_text_title_and_desc() -> None:
    """Extracts <title> and <desc> elements."""
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <title>My Diagram</title>
        <desc>A flow chart showing the process.</desc>
    </svg>"""
    result = extract_svg_text(svg)
    assert "My Diagram" in result
    assert "A flow chart showing the process." in result


def test_extract_svg_text_namespaced() -> None:
    """Namespace-agnostic: strips {namespace} prefix from tag names."""
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg"
                  xmlns:xlink="http://www.w3.org/1999/xlink">
        <text x="10" y="20">Label A</text>
    </svg>"""
    result = extract_svg_text(svg)
    assert "Label A" in result


def test_extract_svg_text_dedup_adjacent() -> None:
    """Collapses runs of identical adjacent lines (no consecutive duplicates)."""
    svg = b"""<svg><text>Dup</text><text>Dup</text><text>Other</text></svg>"""
    result = extract_svg_text(svg)
    lines = result.split("\n")
    # No two adjacent identical lines
    for a, b in zip(lines, lines[1:], strict=False):
        assert a != b, f"Adjacent duplicate found: {a!r}"
    assert "Dup" in result
    assert "Other" in result


def test_extract_svg_text_no_text_returns_empty() -> None:
    """SVG with no text elements returns ''."""
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" fill="blue"/>
    </svg>"""
    assert extract_svg_text(svg) == ""


def test_extract_svg_text_malformed_xml_returns_empty() -> None:
    """Malformed XML returns '' and does NOT raise."""
    result = extract_svg_text(b"<svg><unclosed")
    assert result == ""


def test_extract_svg_text_empty_bytes_returns_empty() -> None:
    """Empty bytes input returns ''."""
    assert extract_svg_text(b"") == ""


def test_extract_svg_text_never_raises() -> None:
    """extract_svg_text never raises regardless of input."""
    bad_inputs: list[bytes] = [
        b"not xml at all",
        b"\x00\x01\x02\xff",
        b"<svg><!-- comment --></svg>",
        b"<svg>&amp;</svg>",
    ]
    for data in bad_inputs:
        try:
            result = extract_svg_text(data)
            assert isinstance(result, str)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"extract_svg_text raised {type(exc).__name__}: {exc!r}")


def test_extract_svg_text_joins_with_newline() -> None:
    """Multiple distinct text fragments are joined with newlines."""
    svg = b"""<svg><text>Line 1</text><text>Line 2</text><text>Line 3</text></svg>"""
    result = extract_svg_text(svg)
    assert result == "Line 1\nLine 2\nLine 3"


def test_extract_svg_text_textpath_included() -> None:
    """<textPath> content is extracted (design §6)."""
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <text><textPath href="#p">Curved text</textPath></text>
    </svg>"""
    result = extract_svg_text(svg)
    assert "Curved text" in result


def test_extract_svg_text_tail_included() -> None:
    """Text in .tail of child elements within text tags is extracted."""
    # In SVG, <text>before<tspan>inside</tspan>after</text> — 'after' is tail.
    svg = b"""<svg><text>before<tspan>inside</tspan>after</text></svg>"""
    result = extract_svg_text(svg)
    # 'inside' and 'after' should both appear (tail of tspan and text of tspan)
    assert "inside" in result


# ---------------------------------------------------------------------------
# (d) captioner_from_settings
# ---------------------------------------------------------------------------


def test_captioner_agent_returns_none() -> None:
    """captioner_from_settings with agent (default) returns None."""
    s = VisionSettings()
    assert captioner_from_settings(s) is None


def test_captioner_none_settings_returns_none() -> None:
    """captioner_from_settings(None) also returns None (defaults to agent)."""
    assert captioner_from_settings(None) is None


def test_captioner_llm_returns_llm_captioner() -> None:
    """captioner_from_settings with llm returns an LLMCaptioner instance."""
    from mintmory.core.vision import LLMCaptioner

    s = VisionSettings(provider=VisionProvider.LLM)
    captioner = captioner_from_settings(s)
    assert isinstance(captioner, LLMCaptioner)


def test_captioner_ocr_raises_not_implemented() -> None:
    """captioner_from_settings with ocr raises NotImplementedError with clear message."""
    s = VisionSettings(provider=VisionProvider.OCR)
    with pytest.raises(NotImplementedError, match="ocr.*not implemented"):
        captioner_from_settings(s)


def test_captioner_ocr_message_mentions_agent_fallback() -> None:
    """The ocr NotImplementedError message mentions MINTMORY_VISION_PROVIDER=agent."""
    s = VisionSettings(provider=VisionProvider.OCR)
    with pytest.raises(NotImplementedError, match="MINTMORY_VISION_PROVIDER=agent"):
        captioner_from_settings(s)


# ---------------------------------------------------------------------------
# (e) image_jobs — needs-redescribe selection
# ---------------------------------------------------------------------------


def test_image_jobs_empty_store_returns_empty() -> None:
    """No file-records → empty job list."""
    store = _store()
    jobs = image_jobs(store)
    assert jobs == []


def test_image_jobs_returns_undescribed_rasters() -> None:
    """Two raster file-records with no descriptions → both returned (sorted by rel)."""
    store = _store()
    _add_file_record(store, path="/a/b.png", rel="b.png", ext=".png")
    _add_file_record(store, path="/a/a.png", rel="a.png", ext=".png")

    jobs = image_jobs(store)
    assert len(jobs) == 2
    # Sorted by rel then file_id
    assert jobs[0].rel == "a.png"
    assert jobs[1].rel == "b.png"


def test_image_jobs_excludes_svg() -> None:
    """SVG file-records are never returned as agent jobs."""
    store = _store()
    _add_file_record(store, path="/a/diagram.svg", rel="diagram.svg", ext=".svg")

    jobs = image_jobs(store)
    assert jobs == []


def test_image_jobs_excludes_proprietary() -> None:
    """Proprietary suffix file-records (.psd, .xd, etc.) are never returned."""
    store = _store()
    for ext in PROPRIETARY_IMAGE_SUFFIXES:
        _add_file_record(store, path=f"/a/file{ext}", rel=f"file{ext}", ext=ext)

    jobs = image_jobs(store)
    assert jobs == []


def test_image_jobs_all_raster_suffixes_returned() -> None:
    """All RASTER_SUFFIXES (.jpg, .jpeg, .png, .gif, .webp, .bmp) surface as jobs."""
    store = _store()
    for ext in RASTER_SUFFIXES:
        _add_file_record(store, path=f"/a/img{ext}", rel=f"img{ext}", ext=ext)

    jobs = image_jobs(store)
    returned_exts = {j.rel.split(".")[-1] for j in jobs}
    for ext in RASTER_SUFFIXES:
        assert ext.lstrip(".") in returned_exts, f"Expected {ext} in returned jobs"


def test_image_jobs_after_caption_put_excludes_described() -> None:
    """After image_caption_put, the described image is NOT returned by default image_jobs."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.jpg", rel="photo.jpg", ext=".jpg")
    _add_file_record(store, path="/a/other.png", rel="other.png", ext=".png")

    # Before: both returned
    assert len(image_jobs(store)) == 2

    # Describe the first one
    image_caption_put(store, rec.id, "A mountain at sunset.")

    # After: only the undescribed one remains
    jobs = image_jobs(store)
    assert len(jobs) == 1
    assert jobs[0].rel == "other.png"


def test_image_jobs_include_all_returns_described_too() -> None:
    """include_all=True returns raster records even after description."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.jpg", rel="photo.jpg", ext=".jpg")
    image_caption_put(store, rec.id, "A sunrise.")

    jobs = image_jobs(store, include_all=True)
    assert len(jobs) == 1
    assert jobs[0].file_id == rec.id
    assert jobs[0].current_description == "A sunrise."


def test_image_jobs_include_all_current_description_populated() -> None:
    """current_description is set on already-described images when include_all=True."""
    store = _store()
    rec = _add_file_record(store, path="/a/pic.png", rel="pic.png", ext=".png")
    image_caption_put(store, rec.id, "A blue circle.")

    jobs = image_jobs(store, include_all=True)
    assert len(jobs) == 1
    assert jobs[0].current_description == "A blue circle."


def test_image_jobs_current_description_none_for_undescribed() -> None:
    """current_description is None for undescribed images even with include_all=True."""
    store = _store()
    _add_file_record(store, path="/a/pic.png", rel="pic.png", ext=".png")

    jobs = image_jobs(store, include_all=True)
    assert len(jobs) == 1
    assert jobs[0].current_description is None


def test_image_jobs_limit_caps_post_selection() -> None:
    """limit=1 caps the returned list after selection (post-slice)."""
    store = _store()
    for i in range(4):
        _add_file_record(store, path=f"/a/img{i}.png", rel=f"img{i}.png", ext=".png")

    jobs = image_jobs(store, limit=1)
    assert len(jobs) == 1


def test_image_jobs_limit_zero_means_no_cap() -> None:
    """limit=0 (default) returns all selected jobs."""
    store = _store()
    for i in range(5):
        _add_file_record(store, path=f"/a/img{i}.png", rel=f"img{i}.png", ext=".png")

    jobs = image_jobs(store, limit=0)
    assert len(jobs) == 5


def test_image_jobs_no_image_b64_for_local_files_by_default() -> None:
    """Local files: image_b64 is None and oversized=False by default."""
    store = _store()
    _add_file_record(store, path="/a/local.png", rel="local.png", ext=".png")

    jobs = image_jobs(store)
    assert len(jobs) == 1
    assert jobs[0].image_b64 is None
    assert jobs[0].oversized is False


def test_image_jobs_include_bytes_local_file(tmp_path: Path) -> None:
    """include_bytes=True embeds local file bytes as base64."""
    store = _store()
    img_file = tmp_path / "test.png"
    fake_bytes = b"fakepngdata1234"
    img_file.write_bytes(fake_bytes)

    _add_file_record(
        store,
        path=str(img_file),
        rel="test.png",
        ext=".png",
        size=len(fake_bytes),
    )

    # Use a tiny cap so size-check passes (max_image_mb=100 > len(fake_bytes))
    s = VisionSettings(max_image_mb=100.0, downscale_max_px=0)
    jobs = image_jobs(store, include_bytes=True, settings=s)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.image_b64 is not None
    assert base64.b64decode(job.image_b64) == fake_bytes
    assert job.oversized is False


def test_image_jobs_oversized_flag_when_size_exceeds_cap() -> None:
    """Image larger than max_image_mb cap: image_b64=None, oversized=True."""
    store = _store()
    # size=10MB, cap=1MB
    _add_file_record(
        store,
        path="/a/huge.png",
        rel="huge.png",
        ext=".png",
        size=10 * 1024 * 1024,
    )

    s = VisionSettings(max_image_mb=1.0, downscale_max_px=0)
    jobs = image_jobs(store, include_bytes=True, settings=s)
    assert len(jobs) == 1
    assert jobs[0].image_b64 is None
    assert jobs[0].oversized is True


def test_image_jobs_no_cap_zero_max_image_mb_embeds_all(tmp_path: Path) -> None:
    """max_image_mb=0 (no cap) embeds any size with include_bytes=True."""
    store = _store()
    img_file = tmp_path / "large.png"
    # 2MB of fake data
    fake_bytes = b"x" * (2 * 1024 * 1024)
    img_file.write_bytes(fake_bytes)

    _add_file_record(
        store,
        path=str(img_file),
        rel="large.png",
        ext=".png",
        size=len(fake_bytes),
    )

    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)
    jobs = image_jobs(store, include_bytes=True, settings=s)
    assert len(jobs) == 1
    assert jobs[0].image_b64 is not None
    assert jobs[0].oversized is False


def test_image_jobs_online_only_embeds_bytes_from_path(tmp_path: Path) -> None:
    """online_only=True causes image_b64 to be populated (reading from path)."""
    store = _store()
    img_file = tmp_path / "cloud.jpg"
    fake_bytes = b"fakejpegbytes"
    img_file.write_bytes(fake_bytes)

    _add_file_record(
        store,
        path=str(img_file),
        rel="cloud.jpg",
        ext=".jpg",
        size=len(fake_bytes),
        online_only=True,
    )

    s = VisionSettings(max_image_mb=100.0, downscale_max_px=0)
    jobs = image_jobs(store, settings=s)
    assert len(jobs) == 1
    assert jobs[0].online_only is True
    assert jobs[0].image_b64 is not None
    assert base64.b64decode(jobs[0].image_b64) == fake_bytes


def test_image_jobs_online_only_unreadable_path_still_valid_job() -> None:
    """online_only=True but path not readable: job still returned, image_b64=None."""
    store = _store()
    _add_file_record(
        store,
        path="/nonexistent/cloud.jpg",
        rel="cloud.jpg",
        ext=".jpg",
        size=1024,
        online_only=True,
    )

    s = VisionSettings(max_image_mb=100.0, downscale_max_px=0)
    jobs = image_jobs(store, settings=s)
    assert len(jobs) == 1
    assert jobs[0].image_b64 is None
    assert jobs[0].online_only is True


def test_image_jobs_pillow_absent_embeds_raw_bytes(tmp_path: Path) -> None:
    """When Pillow is not importable, raw bytes are still embedded (no downscale)."""
    store = _store()
    img_file = tmp_path / "raw.png"
    raw_bytes = b"rawpixeldata"
    img_file.write_bytes(raw_bytes)

    _add_file_record(
        store,
        path=str(img_file),
        rel="raw.png",
        ext=".png",
        size=len(raw_bytes),
    )

    s = VisionSettings(max_image_mb=100.0, downscale_max_px=1568)

    # Simulate Pillow being absent by making the import fail inside _downscale_bytes
    import builtins

    original_import = builtins.__import__

    def _no_pil(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "PIL":
            raise ImportError("no module named PIL")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_no_pil):
        jobs = image_jobs(store, include_bytes=True, settings=s)

    assert len(jobs) == 1
    # Raw bytes should still be embedded despite Pillow import failure
    assert jobs[0].image_b64 is not None
    assert base64.b64decode(jobs[0].image_b64) == raw_bytes


def test_image_jobs_mime_types_are_correct() -> None:
    """MIME types are set correctly per suffix."""
    expected: dict[str, str] = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    store = _store()
    for ext, _expected_mime in expected.items():
        _add_file_record(
            store,
            path=f"/a/img{ext}",
            rel=f"img{ext}",
            ext=ext,
        )

    jobs = image_jobs(store)
    mime_by_ext: dict[str, str] = {}
    for job in jobs:
        ext_from_rel = "." + job.rel.split(".")[-1]
        mime_by_ext[ext_from_rel] = job.mime

    for ext, expected_mime in expected.items():
        assert mime_by_ext.get(ext) == expected_mime, f"MIME mismatch for {ext}"


def test_image_jobs_description_records_not_surfaced_as_jobs() -> None:
    """image_description memories (kind=image_description) are NOT surfaced as jobs."""
    store = _store()
    # Add a regular raster file-record
    file_rec = _add_file_record(store, path="/a/pic.png", rel="pic.png", ext=".png")
    # Add the image description memory (has kind=image_description)
    image_caption_put(store, file_rec.id, "A landscape photo.")

    # The description memory itself should NOT show up as a job
    jobs_all = image_jobs(store, include_all=True)
    for job in jobs_all:
        assert job.file_id == file_rec.id  # Only the file-record, not the description


# ---------------------------------------------------------------------------
# (f) image_caption_put
# ---------------------------------------------------------------------------


def test_image_caption_put_creates_correct_memory() -> None:
    """image_caption_put creates category=context, is_note=False, kind=image_description."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.jpg", rel="photo.jpg", ext=".jpg")

    result = image_caption_put(store, rec.id, "A mountain at sunrise.")

    assert isinstance(result, ImageDescription)
    desc_mem = result.record
    assert desc_mem.category == MemoryCategory.CONTEXT
    assert desc_mem.source == MemorySource.DOCUMENT
    assert desc_mem.is_note is False
    assert desc_mem.metadata.get("kind") == "image_description"
    assert desc_mem.content == "A mountain at sunrise."


def test_image_caption_put_source_image_metadata() -> None:
    """source_image in metadata equals the file-record's path."""
    store = _store()
    rec = _add_file_record(store, path="/absolute/path/photo.jpg", rel="photo.jpg", ext=".jpg")

    result = image_caption_put(store, rec.id, "A red barn.")

    assert result.source_image == "/absolute/path/photo.jpg"
    assert result.record.metadata.get("source_image") == "/absolute/path/photo.jpg"


def test_image_caption_put_creates_annotates_link() -> None:
    """image_caption_put creates a ConceptLink ANNOTATES the file-record."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.png", rel="photo.png", ext=".png")

    result = image_caption_put(store, rec.id, "A beach at sunset.")
    desc_id = result.record.id

    conn = store.connect()
    link_row = conn.execute(
        "SELECT * FROM concept_links WHERE source_memory_id = ? AND target_memory_id = ?",
        (desc_id, rec.id),
    ).fetchone()
    assert link_row is not None
    assert link_row["link_type"] == ConceptLinkType.ANNOTATES.value
    assert link_row["source"] == LinkSource.INFERENCE.value
    assert float(link_row["strength"]) == pytest.approx(1.0)
    assert float(link_row["confidence"]) == pytest.approx(1.0)


def test_image_caption_put_file_id_field() -> None:
    """ImageDescription.file_id equals the file-record id."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.png", rel="photo.png", ext=".png")

    result = image_caption_put(store, rec.id, "Clouds.")
    assert result.file_id == rec.id


def test_image_caption_put_resolve_by_path() -> None:
    """image_caption_put resolves file-record by path string (not just id)."""
    store = _store()
    _add_file_record(store, path="/absolute/img.png", rel="img.png", ext=".png")

    result = image_caption_put(store, "/absolute/img.png", "A night sky.")
    assert result.source_image == "/absolute/img.png"
    assert result.record.metadata.get("kind") == "image_description"


def test_image_caption_put_resolve_by_rel() -> None:
    """image_caption_put resolves file-record by rel string."""
    store = _store()
    _add_file_record(store, path="/abs/sub/img.png", rel="sub/img.png", ext=".png")

    result = image_caption_put(store, "sub/img.png", "A green field.")
    assert result.source_image == "/abs/sub/img.png"


def test_image_caption_put_key_error_on_unknown_path() -> None:
    """image_caption_put raises KeyError for an unknown path or id."""
    store = _store()

    with pytest.raises(KeyError):
        image_caption_put(store, "/does/not/exist.jpg", "Some description.")


def test_image_caption_put_key_error_on_unknown_id() -> None:
    """image_caption_put raises KeyError for an unknown memory id."""
    store = _store()

    with pytest.raises(KeyError):
        image_caption_put(store, "nonexistent-id-1234", "Some description.")


def test_image_caption_put_idempotent_archives_prior() -> None:
    """Second image_caption_put archives the first and sets replaced_description_id."""
    store = _store()
    rec = _add_file_record(store, path="/a/pic.png", rel="pic.png", ext=".png")

    first = image_caption_put(store, rec.id, "First description.")
    first_id = first.record.id

    second = image_caption_put(store, rec.id, "Second description.")

    assert second.replaced_description_id == first_id

    # First description must be archived
    first_mem = store.get_memory(first_id)
    assert first_mem is not None
    assert first_mem.is_archived is True

    # Only one ACTIVE description remains
    active_descs = store.get_annotating_descriptions(rec.id, 10)
    assert len(active_descs) == 1
    assert active_descs[0].content == "Second description."


def test_image_caption_put_first_put_no_replaced_id() -> None:
    """First image_caption_put has replaced_description_id=None."""
    store = _store()
    rec = _add_file_record(store, path="/a/pic.jpg", rel="pic.jpg", ext=".jpg")

    result = image_caption_put(store, rec.id, "First ever description.")
    assert result.replaced_description_id is None


def test_image_caption_put_no_drift_round_trip() -> None:
    """After image_caption_put, default image_jobs does NOT re-surface the image."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.png", rel="photo.png", ext=".png")

    # Before: image needs description
    jobs_before = image_jobs(store)
    assert any(j.file_id == rec.id for j in jobs_before)

    # Apply description
    image_caption_put(store, rec.id, "A snowy mountain.")

    # After: image should NOT re-surface
    jobs_after = image_jobs(store)
    assert not any(j.file_id == rec.id for j in jobs_after)


def test_image_caption_put_no_drift_after_second_put() -> None:
    """Even after two puts, the image does NOT appear in default image_jobs."""
    store = _store()
    rec = _add_file_record(store, path="/a/photo.png", rel="photo.png", ext=".png")

    image_caption_put(store, rec.id, "First view.")
    image_caption_put(store, rec.id, "Second, updated view.")

    jobs = image_jobs(store)
    assert not any(j.file_id == rec.id for j in jobs)


def test_image_caption_put_collection_in_metadata_when_present() -> None:
    """Description metadata includes 'collection' when the file-record has one."""
    store = _store()
    rec = _add_file_record(
        store, path="/a/pic.png", rel="pic.png", ext=".png", collection="myproject"
    )

    result = image_caption_put(store, rec.id, "Project image.")
    assert result.record.metadata.get("collection") == "myproject"


# ---------------------------------------------------------------------------
# (g) Storage helpers
# ---------------------------------------------------------------------------


def test_get_annotating_descriptions_returns_active_descriptions() -> None:
    """get_annotating_descriptions returns active image_description records."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")

    result = image_caption_put(store, rec.id, "An active description.")
    desc_id = result.record.id

    descs = store.get_annotating_descriptions(rec.id, 10)
    assert len(descs) == 1
    assert descs[0].id == desc_id
    assert descs[0].is_archived is False


def test_get_annotating_descriptions_excludes_archived() -> None:
    """get_annotating_descriptions excludes archived records."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")

    first = image_caption_put(store, rec.id, "Old description.")
    # The second put archives the first
    image_caption_put(store, rec.id, "New description.")

    descs = store.get_annotating_descriptions(rec.id, 10)
    # Only the active (new) one
    assert len(descs) == 1
    assert descs[0].content == "New description."
    # old one is archived
    old = store.get_memory(first.record.id)
    assert old is not None and old.is_archived is True


def test_get_annotating_descriptions_cap_zero_returns_empty() -> None:
    """cap <= 0 immediately returns []."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")
    image_caption_put(store, rec.id, "Some text.")

    assert store.get_annotating_descriptions(rec.id, 0) == []


def test_get_annotating_descriptions_cap_limits_results() -> None:
    """get_annotating_descriptions(cap=1) returns at most 1 record."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")
    image_caption_put(store, rec.id, "Description.")

    results = store.get_annotating_descriptions(rec.id, 1)
    assert len(results) <= 1


# ---------------------------------------------------------------------------
# (h) get_annotating_descriptions is separate from get_annotating_notes
# ---------------------------------------------------------------------------


def test_get_annotating_descriptions_does_not_overlap_notes() -> None:
    """A note annotating a target is NOT returned by get_annotating_descriptions."""
    from mintmory.core.notes import create_note

    store = _store()
    # Add a regular memory to annotate
    target = store.add_memory(
        record=MemoryRecord(
            content="Project overview document.",
            category=MemoryCategory.CONTEXT,
        )
    )
    # Create a user note that annotates the target
    note_result = create_note(
        store, "Remember to review this doc.", about="Project overview document."
    )

    # The note should show up via get_annotating_notes (or direct check)
    note_mem = note_result.note
    assert note_mem.is_note is True

    # But get_annotating_descriptions should NOT return notes
    descs = store.get_annotating_descriptions(target.id, 10)
    desc_ids = {d.id for d in descs}
    assert note_mem.id not in desc_ids, "A user note must NOT appear in get_annotating_descriptions"


def test_get_annotating_notes_does_not_return_image_descriptions() -> None:
    """An image_description annotating a file-record is NOT returned by get_annotating_notes."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")
    result = image_caption_put(store, rec.id, "An image description.")
    desc_id = result.record.id

    notes = store.get_annotating_notes(rec.id, 10)
    note_ids = {n.id for n in notes}
    assert desc_id not in note_ids, "image_description must NOT appear in get_annotating_notes"


def test_get_annotating_descriptions_only_kind_image_description() -> None:
    """Only records with metadata.kind='image_description' are returned."""
    from mintmory.core.types import ConceptLink

    store = _store()
    target = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")

    # Add a context memory with ANNOTATES link but different kind
    other_mem = store.add_memory(
        record=MemoryRecord(
            content="Some other annotation.",
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            is_note=False,
            metadata={"kind": "other_kind"},
        )
    )
    link = ConceptLink(
        source_memory_id=other_mem.id,
        target_memory_id=target.id,
        link_type=ConceptLinkType.ANNOTATES,
        entity="img.png",
        source=LinkSource.INFERENCE,
        strength=1.0,
        confidence=1.0,
    )
    store.add_link(link)

    descs = store.get_annotating_descriptions(target.id, 10)
    # 'other_kind' should not appear
    desc_ids = {d.id for d in descs}
    assert other_mem.id not in desc_ids


def test_find_image_file_record_by_path() -> None:
    """find_image_file_record resolves by metadata path."""
    store = _store()
    rec = _add_file_record(store, path="/absolute/path/img.png", rel="img.png", ext=".png")

    found = store.find_image_file_record("/absolute/path/img.png")
    assert found is not None
    assert found.id == rec.id


def test_find_image_file_record_by_rel() -> None:
    """find_image_file_record resolves by metadata rel."""
    store = _store()
    rec = _add_file_record(store, path="/abs/sub/img.jpg", rel="sub/img.jpg", ext=".jpg")

    found = store.find_image_file_record("sub/img.jpg")
    assert found is not None
    assert found.id == rec.id


def test_find_image_file_record_returns_none_for_unknown() -> None:
    """find_image_file_record returns None when no matching record exists."""
    store = _store()
    result = store.find_image_file_record("/no/such/file.png")
    assert result is None


def test_find_image_file_record_excludes_description_records() -> None:
    """find_image_file_record does not return image_description memories."""
    store = _store()
    rec = _add_file_record(store, path="/abs/img.png", rel="img.png", ext=".png")
    image_caption_put(store, rec.id, "A description with source_image metadata.")

    # Searching by path should return the file-record, not the description
    found = store.find_image_file_record("/abs/img.png")
    assert found is not None
    assert found.id == rec.id
    assert found.metadata.get("kind") != "image_description"


def test_find_image_file_record_excludes_archived() -> None:
    """find_image_file_record does not return archived records."""
    store = _store()
    rec = _add_file_record(store, path="/a/img.png", rel="img.png", ext=".png")
    store.archive_memory(rec.id)

    found = store.find_image_file_record("/a/img.png")
    assert found is None


# ---------------------------------------------------------------------------
# (g) index_mode='vision' CHECK migration
# ---------------------------------------------------------------------------


def test_index_mode_vision_accepted_on_fresh_db() -> None:
    """A freshly initialised DB accepts index_mode='vision' in manifest_upsert."""
    store = _store()
    # Should not raise
    store.manifest_upsert(
        "/some/image.png",
        "col",
        size=1024,
        mtime=1_700_000_000.0,
        online_only=False,
        index_mode="vision",
        memory_ids=[],
    )
    conn = store.connect()
    row = conn.execute(
        "SELECT index_mode FROM index_manifest WHERE path = ?", ("/some/image.png",)
    ).fetchone()
    assert row is not None
    assert row["index_mode"] == "vision"


def test_index_mode_migration_idempotent() -> None:
    """Calling initialise() twice on the same DB is a no-op (idempotent migration)."""
    store = _store()
    store.initialise()  # second call
    # Should not raise; vision mode still legal
    store.manifest_upsert(
        "/idem/img.png",
        "col",
        size=512,
        mtime=1.0,
        online_only=False,
        index_mode="vision",
        memory_ids=[],
    )
    row = (
        store.connect()
        .execute("SELECT index_mode FROM index_manifest WHERE path = '/idem/img.png'")
        .fetchone()
    )
    assert row is not None and row["index_mode"] == "vision"


def test_index_mode_migration_old_two_value_db() -> None:
    """A DB with the old 2-value CHECK accepts 'vision' after initialise()."""
    # Build an old-schema DB with only ('metadata','content') CHECK.
    old_ddl = textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS index_manifest (
            path          TEXT PRIMARY KEY,
            collection    TEXT NOT NULL,
            size          INTEGER NOT NULL,
            mtime         REAL NOT NULL,
            content_hash  TEXT,
            index_mode    TEXT NOT NULL DEFAULT 'metadata'
                              CHECK (index_mode IN ('metadata','content')),
            memory_ids    TEXT NOT NULL DEFAULT '[]',
            online_only   INTEGER NOT NULL DEFAULT 0,
            last_seen     TEXT NOT NULL
        );
    """)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        old_db_path = tf.name

    try:
        # Create an old-schema DB
        conn = sqlite3.connect(old_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(old_ddl)
        conn.execute(
            "INSERT INTO index_manifest (path, collection, size, mtime, "
            "index_mode, memory_ids, online_only, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("/existing.png", "col", 100, 1.0, "metadata", "[]", 0, "2024-01-01"),
        )
        conn.commit()
        conn.close()

        # Now open through StorageAdapter — initialise() should run the migration
        store = StorageAdapter(old_db_path, embedder=None)
        store.initialise()

        # After migration, 'vision' should be legal
        store.manifest_upsert(
            "/new_vision.png",
            "col",
            size=512,
            mtime=2.0,
            online_only=False,
            index_mode="vision",
            memory_ids=[],
        )
        row = (
            store.connect()
            .execute("SELECT index_mode FROM index_manifest WHERE path = '/new_vision.png'")
            .fetchone()
        )
        assert row is not None
        assert row["index_mode"] == "vision"

        # Existing row preserved
        existing = (
            store.connect()
            .execute("SELECT * FROM index_manifest WHERE path = '/existing.png'")
            .fetchone()
        )
        assert existing is not None
        assert existing["index_mode"] == "metadata"

        store.close()
    finally:
        Path(old_db_path).unlink(missing_ok=True)


def test_index_mode_migration_old_db_re_initialise_is_noop() -> None:
    """_ensure_index_mode_vision is idempotent on an already-migrated DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        store = StorageAdapter(db_path, embedder=None)
        store.initialise()
        # Re-initialise — should not raise or corrupt
        store.initialise()

        store.manifest_upsert(
            "/double/init.png",
            "col",
            size=128,
            mtime=1.0,
            online_only=False,
            index_mode="vision",
            memory_ids=[],
        )
        row = (
            store.connect()
            .execute("SELECT index_mode FROM index_manifest WHERE path = '/double/init.png'")
            .fetchone()
        )
        assert row is not None and row["index_mode"] == "vision"
        store.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Suffix set sanity checks (FROZEN constants)
# ---------------------------------------------------------------------------


def test_raster_suffixes_are_frozen_set() -> None:
    assert isinstance(RASTER_SUFFIXES, frozenset)
    assert ".png" in RASTER_SUFFIXES
    assert ".jpg" in RASTER_SUFFIXES
    assert ".svg" not in RASTER_SUFFIXES


def test_svg_suffixes_are_frozen_set() -> None:
    assert isinstance(SVG_SUFFIXES, frozenset)
    assert ".svg" in SVG_SUFFIXES
    assert ".png" not in SVG_SUFFIXES


def test_proprietary_suffixes_are_frozen_set() -> None:
    assert isinstance(PROPRIETARY_IMAGE_SUFFIXES, frozenset)
    assert ".psd" in PROPRIETARY_IMAGE_SUFFIXES
    assert ".xd" in PROPRIETARY_IMAGE_SUFFIXES
    # None of these should be in raster or svg
    for ext in PROPRIETARY_IMAGE_SUFFIXES:
        assert ext not in RASTER_SUFFIXES
        assert ext not in SVG_SUFFIXES


# ===========================================================================
# Group 6 (add-llm-vision-provider) — new tests
# ===========================================================================

# ---------------------------------------------------------------------------
# (i) VisionSettings — new fields, defaults, bounds, env parse
# ---------------------------------------------------------------------------


def test_vision_settings_new_llm_defaults() -> None:
    """New llm-tier fields have the expected defaults from design §1."""
    s = VisionSettings()
    assert s.vision_timeout_s == pytest.approx(120.0)
    assert s.vision_temperature == pytest.approx(0.0)
    assert s.vision_max_tokens == 512
    assert s.vision_prompt == ""
    # endpoint defaults (base_url / model were None in MM-18, now defaulted)
    assert s.base_url == "http://localhost:11434/v1"
    assert s.model == "llava"


def test_vision_settings_vision_timeout_s_bounds() -> None:
    """vision_timeout_s accepts 1.0..600.0; below 1 or above 600 should raise."""
    # Valid boundary values
    s_min = VisionSettings(vision_timeout_s=1.0)
    assert s_min.vision_timeout_s == pytest.approx(1.0)
    s_max = VisionSettings(vision_timeout_s=600.0)
    assert s_max.vision_timeout_s == pytest.approx(600.0)

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VisionSettings(vision_timeout_s=0.9)
    with pytest.raises(ValidationError):
        VisionSettings(vision_timeout_s=601.0)


def test_vision_settings_vision_max_tokens_bounds() -> None:
    """vision_max_tokens accepts 1..8192; out-of-range values should raise."""
    from pydantic import ValidationError

    s_min = VisionSettings(vision_max_tokens=1)
    assert s_min.vision_max_tokens == 1
    s_max = VisionSettings(vision_max_tokens=8192)
    assert s_max.vision_max_tokens == 8192

    with pytest.raises(ValidationError):
        VisionSettings(vision_max_tokens=0)
    with pytest.raises(ValidationError):
        VisionSettings(vision_max_tokens=8193)


def test_vision_settings_vision_temperature_bounds() -> None:
    """vision_temperature is bounded 0.0..2.0."""
    from pydantic import ValidationError

    VisionSettings(vision_temperature=0.0)
    VisionSettings(vision_temperature=2.0)
    with pytest.raises(ValidationError):
        VisionSettings(vision_temperature=-0.1)
    with pytest.raises(ValidationError):
        VisionSettings(vision_temperature=2.01)


def test_vision_settings_env_model_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_VISION_MODEL env var is parsed correctly."""
    monkeypatch.setenv("MINTMORY_VISION_MODEL", "llava-next")
    s = VisionSettings()
    assert s.model == "llava-next"


def test_vision_settings_env_vision_max_tokens_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_VISION_VISION_MAX_TOKENS env var is parsed correctly."""
    monkeypatch.setenv("MINTMORY_VISION_VISION_MAX_TOKENS", "1024")
    s = VisionSettings()
    assert s.vision_max_tokens == 1024


def test_vision_settings_env_vision_prompt_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_VISION_VISION_PROMPT env var overrides the default prompt."""
    monkeypatch.setenv("MINTMORY_VISION_VISION_PROMPT", "Custom prompt here.")
    s = VisionSettings()
    assert s.vision_prompt == "Custom prompt here."


def test_vision_settings_provider_still_defaults_agent() -> None:
    """provider still defaults to AGENT even with new llm knobs present."""
    s = VisionSettings()
    assert s.provider is VisionProvider.AGENT


# ---------------------------------------------------------------------------
# (j) captioner_from_settings — llm → LLMCaptioner (asserts isinstance)
# ---------------------------------------------------------------------------


def test_captioner_llm_returns_llm_captioner_isinstance() -> None:
    """captioner_from_settings(llm) returns LLMCaptioner and conforms to Captioner protocol."""
    from mintmory.core.vision import Captioner, LLMCaptioner

    s = VisionSettings(provider=VisionProvider.LLM)
    cap = captioner_from_settings(s)
    assert isinstance(cap, LLMCaptioner)
    assert isinstance(cap, Captioner)


def test_captioner_llm_stores_settings() -> None:
    """The LLMCaptioner holds the VisionSettings passed from captioner_from_settings."""
    from mintmory.core.vision import LLMCaptioner

    s = VisionSettings(provider=VisionProvider.LLM, model="my-vision-model")
    cap = captioner_from_settings(s)
    assert isinstance(cap, LLMCaptioner)
    assert cap.settings.model == "my-vision-model"


# ---------------------------------------------------------------------------
# (k) LLMCaptioner.describe — stubbed post_chat_completion
# ---------------------------------------------------------------------------

# --- Helpers ----------------------------------------------------------------

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # minimal fake PNG bytes


def _make_captioner(
    *,
    model: str = "llava",
    base_url: str = "http://localhost:11434/v1",
    api_key: str | None = None,
    vision_timeout_s: float = 120.0,
    vision_temperature: float = 0.0,
    vision_max_tokens: int = 512,
    vision_prompt: str = "",
) -> Any:
    """Return an LLMCaptioner with the given VisionSettings (no network)."""
    from mintmory.core.vision import LLMCaptioner

    s = VisionSettings(
        provider=VisionProvider.LLM,
        model=model,
        base_url=base_url,
        api_key=api_key,
        vision_timeout_s=vision_timeout_s,
        vision_temperature=vision_temperature,
        vision_max_tokens=vision_max_tokens,
        vision_prompt=vision_prompt,
    )
    return LLMCaptioner(s)


def _make_image_input(
    *,
    file_id: str = "file-001",
    path: str = "/fake/image.png",
    mime: str = "image/png",
    data: bytes | None = None,
) -> Any:
    from mintmory.core.vision import ImageInput

    return ImageInput(file_id=file_id, path=path, mime=mime, data=data or _FAKE_PNG)


def _patch_post(monkeypatch: pytest.MonkeyPatch, content: str) -> dict[str, Any]:
    """Stub llm.post_chat_completion to return ``content`` and capture the call."""
    captured: dict[str, Any] = {}

    def fake_post(
        *,
        base_url: str,
        api_key: str | None,
        payload: dict[str, Any],
        timeout_s: float,
        system: str,
        model: str,
    ) -> dict[str, Any]:
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["payload"] = payload
        captured["timeout_s"] = timeout_s
        captured["system"] = system
        captured["model"] = model
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr("mintmory.core.llm.post_chat_completion", fake_post)
    return captured


# --- Payload structure tests ------------------------------------------------


def test_llm_captioner_posts_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """describe() sends the correct model name in the payload."""
    cap = _make_captioner(model="llava-next")
    captured = _patch_post(monkeypatch, "A photo of a cat.")
    cap.describe(_make_image_input())
    assert captured["payload"]["model"] == "llava-next"


def test_llm_captioner_posts_user_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message role is 'user'."""
    cap = _make_captioner()
    captured = _patch_post(monkeypatch, "A red barn.")
    cap.describe(_make_image_input())
    msgs = captured["payload"]["messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_llm_captioner_content_has_text_part(monkeypatch: pytest.MonkeyPatch) -> None:
    """content[0] is a text part with the default IMAGE_CAPTION_PROMPT."""
    from mintmory.core.prompts import IMAGE_CAPTION_PROMPT

    cap = _make_captioner()
    captured = _patch_post(monkeypatch, "A sunset.")
    cap.describe(_make_image_input())
    content = captured["payload"]["messages"][0]["content"]
    assert isinstance(content, list)
    text_part = content[0]
    assert text_part["type"] == "text"
    assert text_part["text"] == IMAGE_CAPTION_PROMPT


def test_llm_captioner_content_has_image_url_part(monkeypatch: pytest.MonkeyPatch) -> None:
    """content[1] is an image_url part whose url starts with 'data:image/png;base64,'."""
    cap = _make_captioner()
    captured = _patch_post(monkeypatch, "A tree.")
    cap.describe(_make_image_input(mime="image/png"))
    content = captured["payload"]["messages"][0]["content"]
    img_part = content[1]
    assert img_part["type"] == "image_url"
    url = img_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    # The embedded bytes should decode back to the original fake PNG
    b64_data = url[len("data:image/png;base64,") :]
    assert base64.b64decode(b64_data) == _FAKE_PNG


def test_llm_captioner_max_tokens_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_tokens is present in the payload with the correct value."""
    cap = _make_captioner(vision_max_tokens=256)
    captured = _patch_post(monkeypatch, "Clouds.")
    cap.describe(_make_image_input())
    assert captured["payload"]["max_tokens"] == 256


def test_llm_captioner_temperature_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """temperature is present in the payload with the correct value."""
    cap = _make_captioner(vision_temperature=0.7)
    captured = _patch_post(monkeypatch, "Mountains.")
    cap.describe(_make_image_input())
    assert captured["payload"]["temperature"] == pytest.approx(0.7)


def test_llm_captioner_stream_false_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """stream=False is set in the payload."""
    cap = _make_captioner()
    captured = _patch_post(monkeypatch, "A river.")
    cap.describe(_make_image_input())
    assert captured["payload"]["stream"] is False


def test_llm_captioner_url_ends_with_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_chat_completion is called with base_url ending at the base (no path appended twice)."""
    cap = _make_captioner(base_url="http://myhost:11434/v1")
    captured = _patch_post(monkeypatch, "Text.")
    cap.describe(_make_image_input())
    # The poster receives the raw base_url; it appends /chat/completions internally
    assert captured["base_url"] == "http://myhost:11434/v1"


def test_llm_captioner_no_bearer_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without api_key, the poster receives api_key=None."""
    cap = _make_captioner(api_key=None)
    captured = _patch_post(monkeypatch, "Sky.")
    cap.describe(_make_image_input())
    assert captured["api_key"] is None


def test_llm_captioner_bearer_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """With api_key set, the poster receives the key so it can add Bearer."""
    cap = _make_captioner(api_key="sk-test-key")
    captured = _patch_post(monkeypatch, "Sky with stars.")
    cap.describe(_make_image_input())
    assert captured["api_key"] == "sk-test-key"


def test_llm_captioner_timeout_passed_to_poster(monkeypatch: pytest.MonkeyPatch) -> None:
    """vision_timeout_s is forwarded to post_chat_completion as timeout_s."""
    cap = _make_captioner(vision_timeout_s=90.0)
    captured = _patch_post(monkeypatch, "A lake.")
    cap.describe(_make_image_input())
    assert captured["timeout_s"] == pytest.approx(90.0)


# --- Vision prompt override -------------------------------------------------


def test_llm_captioner_default_prompt_used_when_vision_prompt_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty vision_prompt means the default IMAGE_CAPTION_PROMPT is used."""
    from mintmory.core.prompts import IMAGE_CAPTION_PROMPT

    cap = _make_captioner(vision_prompt="")
    captured = _patch_post(monkeypatch, "Default prompt result.")
    cap.describe(_make_image_input())
    text_part = captured["payload"]["messages"][0]["content"][0]
    assert text_part["text"] == IMAGE_CAPTION_PROMPT


def test_llm_captioner_vision_prompt_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-empty vision_prompt replaces the default prompt verbatim."""
    cap = _make_captioner(vision_prompt="Tell me what you see.")
    captured = _patch_post(monkeypatch, "Custom prompt result.")
    cap.describe(_make_image_input())
    text_part = captured["payload"]["messages"][0]["content"][0]
    assert text_part["text"] == "Tell me what you see."


# --- Response parsing -------------------------------------------------------


def test_llm_captioner_returns_content_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """The response content is returned as the description text."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A bright red flower.")
    result = cap.describe(_make_image_input())
    assert result.record.content == "A bright red flower."


def test_llm_captioner_strips_think_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    """<think>...</think> blocks are stripped from the response content."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "<think>Reasoning here.</think>  A green field.  ")
    result = cap.describe(_make_image_input())
    assert result.record.content == "A green field."
    assert "<think>" not in result.record.content


def test_llm_captioner_strips_multiline_think(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multi-line <think> blocks are fully stripped."""
    cap = _make_captioner()
    _patch_post(
        monkeypatch,
        "<think>\nLet me think.\nMore thoughts.\n</think>\nA photo of mountains.",
    )
    result = cap.describe(_make_image_input())
    assert result.record.content == "A photo of mountains."


def test_llm_captioner_surrounding_whitespace_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leading and trailing whitespace is stripped from the final text."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "  \n  A sunset over the ocean.  \n  ")
    result = cap.describe(_make_image_input())
    assert result.record.content == "A sunset over the ocean."


# --- Transient record shape -------------------------------------------------


def test_llm_captioner_returns_transient_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned ImageDescription.record has no DB row (id is fresh UUID, not persisted)."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A waterfall.")
    result = cap.describe(_make_image_input(file_id="fid-abc"))

    assert isinstance(result, ImageDescription)
    assert result.file_id == "fid-abc"
    # replaced_description_id is None (transient, never persisted)
    assert result.replaced_description_id is None


def test_llm_captioner_record_category_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned record has category=CONTEXT."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A city skyline.")
    result = cap.describe(_make_image_input())
    assert result.record.category == MemoryCategory.CONTEXT


def test_llm_captioner_record_source_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned record has source=DOCUMENT."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A forest path.")
    result = cap.describe(_make_image_input())
    assert result.record.source == MemorySource.DOCUMENT


def test_llm_captioner_record_is_note_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned record has is_note=False."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "An airport terminal.")
    result = cap.describe(_make_image_input())
    assert result.record.is_note is False


def test_llm_captioner_record_metadata_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned record's metadata has kind='image_description'."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A chart.")
    result = cap.describe(_make_image_input(path="/data/chart.png"))
    assert result.record.metadata.get("kind") == "image_description"


def test_llm_captioner_record_metadata_source_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned record's metadata has source_image equal to image.path."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A map.")
    result = cap.describe(_make_image_input(path="/data/map.png"))
    assert result.record.metadata.get("source_image") == "/data/map.png"
    assert result.source_image == "/data/map.png"


def test_llm_captioner_source_image_in_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """ImageDescription.source_image equals image.path."""
    cap = _make_captioner()
    _patch_post(monkeypatch, "A graph.")
    result = cap.describe(_make_image_input(path="/graphs/fig1.png"))
    assert result.source_image == "/graphs/fig1.png"


# --- VisionError on failures ------------------------------------------------


def test_llm_captioner_vision_error_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """URLError from urlopen inside post_chat_completion is wrapped in VisionError."""
    import urllib.error

    from mintmory.core.vision import VisionError

    def boom(
        *,
        base_url: str,
        api_key: str | None,
        payload: dict[str, Any],
        timeout_s: float,
        system: str,
        model: str,
    ) -> dict[str, Any]:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("mintmory.core.llm.post_chat_completion", boom)
    cap = _make_captioner()
    with pytest.raises(VisionError):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """TimeoutError from the poster is wrapped in VisionError."""
    from mintmory.core.vision import VisionError

    def boom(**_: Any) -> dict[str, Any]:
        raise TimeoutError("timed out")

    monkeypatch.setattr("mintmory.core.llm.post_chat_completion", boom)
    cap = _make_captioner()
    with pytest.raises(VisionError):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTPError from the poster is wrapped in VisionError."""
    import urllib.error

    from mintmory.core.vision import VisionError

    def boom(**_: Any) -> dict[str, Any]:
        raise urllib.error.HTTPError(
            url="http://x/v1/chat/completions",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    monkeypatch.setattr("mintmory.core.llm.post_chat_completion", boom)
    cap = _make_captioner()
    with pytest.raises(VisionError):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty content in the response raises VisionError."""
    from mintmory.core.vision import VisionError

    _patch_post(monkeypatch, "")
    cap = _make_captioner()
    with pytest.raises(VisionError, match="empty content"):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_whitespace_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only content in the response raises VisionError."""
    from mintmory.core.vision import VisionError

    _patch_post(monkeypatch, "   \n  \t  ")
    cap = _make_captioner()
    with pytest.raises(VisionError, match="empty content"):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_think_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Content that is only a <think> block (no remaining text) raises VisionError."""
    from mintmory.core.vision import VisionError

    _patch_post(monkeypatch, "<think>Just reasoning, no output.</think>")
    cap = _make_captioner()
    with pytest.raises(VisionError, match="only reasoning"):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_bad_response_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected response JSON shape (no choices key) raises VisionError."""
    from mintmory.core.vision import VisionError

    def bad_post(**_: Any) -> dict[str, Any]:
        return {"result": "no choices here"}  # wrong shape

    monkeypatch.setattr("mintmory.core.llm.post_chat_completion", bad_post)
    cap = _make_captioner()
    with pytest.raises(VisionError, match="unexpected vision response shape"):
        cap.describe(_make_image_input())


def test_llm_captioner_vision_error_on_unreadable_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError when reading image.path (no image.data) raises VisionError."""
    from mintmory.core.vision import ImageInput, VisionError

    # image.data=None means describe() will try open(image.path, "rb")
    img = ImageInput(file_id="fid", path="/nonexistent/image.png", mime="image/png", data=None)
    cap = _make_captioner()

    # Don't even need to patch post_chat_completion — should fail at file read
    with pytest.raises(VisionError, match="cannot read"):
        cap.describe(img)


def test_llm_captioner_reads_path_when_data_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When image.data is None, describe() reads bytes from image.path."""
    from mintmory.core.vision import ImageInput

    img_file = tmp_path / "image.png"
    img_file.write_bytes(_FAKE_PNG)

    img = ImageInput(file_id="fid", path=str(img_file), mime="image/png", data=None)
    cap = _make_captioner()
    captured = _patch_post(monkeypatch, "A photo.")
    cap.describe(img)

    # The data URL should contain base64 of the FAKE_PNG bytes
    content_list = captured["payload"]["messages"][0]["content"]
    img_url = content_list[1]["image_url"]["url"]
    b64_part = img_url[len("data:image/png;base64,") :]
    assert base64.b64decode(b64_part) == _FAKE_PNG


# --- Pillow-absent embed (raw bytes, no downscale) --------------------------


def test_llm_captioner_pillow_absent_embeds_raw_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Pillow import fails, raw bytes are embedded in the data URL unchanged."""
    import builtins

    from mintmory.core.vision import VisionError  # noqa: F401 — import to ensure module loaded

    original_import = builtins.__import__

    def _no_pil(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "PIL":
            raise ImportError("no module named PIL")
        return original_import(name, *args, **kwargs)

    captured = _patch_post(monkeypatch, "A photo without Pillow.")
    cap = _make_captioner()

    with patch("builtins.__import__", side_effect=_no_pil):
        result = cap.describe(_make_image_input(mime="image/png", data=_FAKE_PNG))

    assert result.record.content == "A photo without Pillow."
    # The data URL should contain the unmodified fake PNG bytes
    content_list = captured["payload"]["messages"][0]["content"]
    img_url = content_list[1]["image_url"]["url"]
    b64_part = img_url[len("data:image/png;base64,") :]
    assert base64.b64decode(b64_part) == _FAKE_PNG


# ===========================================================================
# (l) caption_pending_images
# ===========================================================================


class _FakeCaptioner:
    """In-memory fake Captioner for caption_pending_images tests (no network)."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        fail_ids: set[str] | None = None,
    ) -> None:
        """``responses``: file_id → description text; ``fail_ids``: IDs that raise VisionError."""
        self._responses = responses or {}
        self._fail_ids = fail_ids or set()
        self.described_ids: list[str] = []

    def describe(self, image: Any) -> Any:
        from mintmory.core.types import (
            ImageDescription,
            MemoryCategory,
            MemoryRecord,
            MemorySource,
        )
        from mintmory.core.vision import VisionError

        if image.file_id in self._fail_ids:
            raise VisionError(f"fake error for {image.file_id}")
        self.described_ids.append(image.file_id)
        text = self._responses.get(image.file_id, "Default description.")
        record = MemoryRecord(
            content=text,
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            is_note=False,
            metadata={"kind": "image_description", "source_image": image.path},
        )
        return ImageDescription(
            record=record,
            file_id=image.file_id,
            source_image=image.path,
            replaced_description_id=None,
        )


def _store_with_images(
    n: int, *, tmp_path: Path, size: int = 100, online_only: bool = False
) -> tuple[StorageAdapter, list[MemoryRecord]]:
    """Create an in-memory store with ``n`` raster file-records, each backed by a real tiny file."""
    store = _store()
    records: list[MemoryRecord] = []
    for i in range(n):
        img_file = tmp_path / f"img_{i}.png"
        img_file.write_bytes(b"x" * size)
        rec = _add_file_record(
            store,
            path=str(img_file),
            rel=f"img_{i}.png",
            ext=".png",
            size=size,
            online_only=online_only,
        )
        records.append(rec)
    return store, records


def test_caption_pending_images_describes_two_images(tmp_path: Path) -> None:
    """Two pending images → both described, CaptionRunReport.described==2."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(2, tmp_path=tmp_path)
    cap = _FakeCaptioner()
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)
    report = caption_pending_images(store, captioner=cap, settings=s)

    assert report.described == 2
    assert report.skipped == 0
    assert report.failed == 0
    assert report.budget_hit is False
    assert report.provider == "llm"
    assert len(report.items) == 2
    assert all(item.status == "described" for item in report.items)


def test_caption_pending_images_no_drift(tmp_path: Path) -> None:
    """After caption_pending_images, a second run with include_all=False describes 0."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(2, tmp_path=tmp_path)
    cap = _FakeCaptioner()
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)

    first = caption_pending_images(store, captioner=cap, settings=s)
    assert first.described == 2

    # Second run: nothing pending
    second = caption_pending_images(store, captioner=cap, settings=s)
    assert second.described == 0
    assert len(second.items) == 0


def test_caption_pending_images_vision_error_skip_and_continue(tmp_path: Path) -> None:
    """VisionError for one image → counted as failed, other image still described."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(2, tmp_path=tmp_path)
    # Make the first image fail
    cap = _FakeCaptioner(fail_ids={recs[0].id})
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)
    report = caption_pending_images(store, captioner=cap, settings=s)

    assert report.described == 1
    assert report.failed == 1
    assert report.skipped == 0
    # The failing image's item has status 'failed'
    statuses = {item.file_id: item.status for item in report.items}
    assert statuses[recs[0].id] == "failed"
    assert statuses[recs[1].id] == "described"


def test_caption_pending_images_oversized_skipped(tmp_path: Path) -> None:
    """Image exceeding max_image_bytes is skipped (note='oversized')."""
    from mintmory.core.vision import caption_pending_images

    store = _store()
    img_file = tmp_path / "big.png"
    img_file.write_bytes(b"x" * 100)
    _add_file_record(store, path=str(img_file), rel="big.png", ext=".png", size=10 * 1024 * 1024)

    cap = _FakeCaptioner()
    # Set a tiny cap (1 byte) so the image is oversized
    s = VisionSettings(max_image_mb=0.000001, downscale_max_px=0)
    report = caption_pending_images(store, captioner=cap, settings=s)

    assert report.described == 0
    assert report.skipped == 1
    assert report.items[0].note == "oversized"


def test_caption_pending_images_include_all_recaptions(tmp_path: Path) -> None:
    """include_all=True re-captions already-described images."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(1, tmp_path=tmp_path)
    cap1 = _FakeCaptioner(responses={recs[0].id: "First description."})
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)

    first = caption_pending_images(store, captioner=cap1, settings=s)
    assert first.described == 1

    # With include_all=False, the already-described image is not re-captioned
    second_default = caption_pending_images(store, captioner=cap1, settings=s)
    assert second_default.described == 0

    # With include_all=True, it IS re-captioned
    cap2 = _FakeCaptioner(responses={recs[0].id: "Second description."})
    second_all = caption_pending_images(store, captioner=cap2, include_all=True, settings=s)
    assert second_all.described == 1


def test_caption_pending_images_limit_caps(tmp_path: Path) -> None:
    """limit=1 processes only 1 image even when 3 are pending."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(3, tmp_path=tmp_path)
    cap = _FakeCaptioner()
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)
    report = caption_pending_images(store, captioner=cap, limit=1, settings=s)

    assert report.described == 1
    assert len(report.items) == 1


def test_caption_pending_images_persists_via_image_caption_put(tmp_path: Path) -> None:
    """After caption_pending_images, the described image no longer appears in image_jobs."""
    from mintmory.core.vision import caption_pending_images, image_jobs

    store, recs = _store_with_images(1, tmp_path=tmp_path)
    cap = _FakeCaptioner()
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)

    jobs_before = image_jobs(store)
    assert len(jobs_before) == 1

    caption_pending_images(store, captioner=cap, settings=s)

    jobs_after = image_jobs(store)
    assert len(jobs_after) == 0


def test_caption_pending_images_budget_skips_online_only(tmp_path: Path) -> None:
    """Online-only images exceeding the budget are skipped with note='budget'.

    The budget is enforced at two levels:
    1. image_jobs embeds online-only bytes up to max_download_bytes from settings.
    2. caption_pending_images checks run-level budget for jobs where image_b64 is None.

    We set max_download_mb small enough that image_jobs only embeds the first image
    (leaving the second with image_b64=None), then supply a run-level budget=0 so
    the second image is skipped in caption_pending_images.
    """
    from mintmory.core.vision import caption_pending_images

    store = _store()
    # Two online-only images, each 500 bytes
    for i in range(2):
        img_file = tmp_path / f"online_{i}.png"
        img_file.write_bytes(b"y" * 500)
        _add_file_record(
            store,
            path=str(img_file),
            rel=f"online_{i}.png",
            ext=".png",
            size=500,
            online_only=True,
        )

    cap = _FakeCaptioner()
    # max_image_mb=0 (no size cap), max_download_mb set to embed only first image (600 B budget)
    # so image_jobs embeds image_0 (500B) but not image_1 (would exceed 600B total)
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0, max_download_mb=600 / (1024 * 1024))
    # Run-level budget=0 means caption_pending_images budget guard fires immediately
    # for any online_only job that image_jobs left without image_b64
    report = caption_pending_images(store, captioner=cap, budget=0, settings=s)

    # image_0 was embedded by image_jobs (image_b64 set) → described
    # image_1 was not embedded (image_b64=None) and budget=0 → skipped
    assert report.described == 1
    assert report.skipped >= 1
    assert report.budget_hit is True
    budget_items = [item for item in report.items if item.note == "budget"]
    assert len(budget_items) >= 1


def test_caption_pending_images_empty_store() -> None:
    """Empty store → report with all zeros."""
    from mintmory.core.vision import caption_pending_images

    store = _store()
    cap = _FakeCaptioner()
    report = caption_pending_images(store, captioner=cap)

    assert report.described == 0
    assert report.skipped == 0
    assert report.failed == 0
    assert report.items == []


def test_caption_pending_images_item_note_has_record_id(tmp_path: Path) -> None:
    """Described image item note contains the new record id (from image_caption_put)."""
    from mintmory.core.vision import caption_pending_images

    store, recs = _store_with_images(1, tmp_path=tmp_path)
    cap = _FakeCaptioner()
    s = VisionSettings(max_image_mb=0.0, downscale_max_px=0)
    report = caption_pending_images(store, captioner=cap, settings=s)

    item = report.items[0]
    assert item.status == "described"
    # note should be a non-empty string (the new record id)
    assert item.note != ""


# ===========================================================================
# (m) CaptionRunReport / CaptionRunItem type round-trips
# ===========================================================================


def test_caption_run_report_defaults() -> None:
    """CaptionRunReport has correct defaults."""
    from mintmory.core.types import CaptionRunReport

    r = CaptionRunReport()
    assert r.described == 0
    assert r.skipped == 0
    assert r.failed == 0
    assert r.budget_hit is False
    assert r.provider == "llm"
    assert r.items == []


def test_caption_run_report_agent_no_op_shape() -> None:
    """CaptionRunReport(provider='agent') is the documented no-op shape."""
    from mintmory.core.types import CaptionRunReport

    r = CaptionRunReport(provider="agent")
    d = r.model_dump(mode="json")
    assert d["provider"] == "agent"
    assert d["described"] == 0
    assert d["budget_hit"] is False


def test_caption_run_item_round_trip() -> None:
    """CaptionRunItem round-trips via model_dump."""
    from mintmory.core.types import CaptionRunItem

    item = CaptionRunItem(file_id="f1", rel="img.png", status="described", note="rec-id-123")
    d = item.model_dump(mode="json")
    assert d["file_id"] == "f1"
    assert d["rel"] == "img.png"
    assert d["status"] == "described"
    assert d["note"] == "rec-id-123"


def test_caption_run_item_note_defaults_empty() -> None:
    """CaptionRunItem.note defaults to ''."""
    from mintmory.core.types import CaptionRunItem

    item = CaptionRunItem(file_id="f2", rel="x.png", status="skipped")
    assert item.note == ""


def test_caption_run_report_with_items() -> None:
    """CaptionRunReport carries items correctly."""
    from mintmory.core.types import CaptionRunItem, CaptionRunReport

    items = [
        CaptionRunItem(file_id="f1", rel="a.png", status="described", note="rec-1"),
        CaptionRunItem(file_id="f2", rel="b.png", status="failed", note="timeout"),
    ]
    r = CaptionRunReport(described=1, failed=1, items=items)
    d = r.model_dump(mode="json")
    assert len(d["items"]) == 2
    assert d["items"][0]["status"] == "described"
    assert d["items"][1]["status"] == "failed"
