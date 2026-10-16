"""
Unit tests for ``mintmory.core.conversion`` — the markitdown ingest seam.

NONE of these tests hit the network and the default test env never imports the
real ``markitdown``. The markitdown-present path is exercised by injecting a
*fake* ``markitdown`` module into ``sys.modules`` via ``monkeypatch.setitem`` so
it auto-reverts. The markitdown-absent path monkeypatches
``mintmory.core.conversion.markitdown_available`` to ``False``.

The cleaner is asserted to be conservative and idempotent per design §3, and
``extract_markdown`` dispatch is asserted per design §2 (text suffix, unknown
suffix, convertible-with-markitdown, convertible-without-markitdown, size cap,
and ``convert=False``).
"""

from __future__ import annotations

import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import conversion
from mintmory.core.conversion import (
    CONVERTIBLE_SUFFIXES,
    TEXT_SUFFIXES,
    ConversionError,
    ExtractResult,
    FileTooLarge,
    MarkitdownNotInstalled,
    clean_markdown,
    extract_markdown,
    is_convertible,
    supported_suffixes,
)


# ---------------------------------------------------------------------------
# clean_markdown — conservative, total, idempotent (design §3)
# ---------------------------------------------------------------------------
def test_clean_markdown_normalises_crlf_and_cr() -> None:
    assert clean_markdown("a\r\nb\rc") == "a\nb\nc"


def test_clean_markdown_strips_trailing_whitespace_per_line() -> None:
    assert clean_markdown("a   \nb\t\nc") == "a\nb\nc"


def test_clean_markdown_collapses_three_or_more_blank_lines() -> None:
    # 3+ blank lines collapse to exactly one blank line.
    assert clean_markdown("a\n\n\n\n\nb") == "a\n\nb"


def test_clean_markdown_keeps_single_blank_line() -> None:
    # One blank line (a paragraph break) survives unchanged.
    assert clean_markdown("a\n\nb") == "a\n\nb"


def test_clean_markdown_strips_leading_and_trailing_blank_lines() -> None:
    assert clean_markdown("\n\n  \nhello\n\n\n") == "hello"


def test_clean_markdown_removes_html_comment() -> None:
    assert clean_markdown("before<!-- a comment -->after") == "beforeafter"


def test_clean_markdown_removes_multiline_html_comment() -> None:
    text = "before<!-- line one\nline two\nline three -->after"
    assert clean_markdown(text) == "beforeafter"


def test_clean_markdown_removes_html_comment_non_greedily() -> None:
    # Two separate comments must not be eaten as one greedy span.
    text = "a<!-- one -->b<!-- two -->c"
    assert clean_markdown(text) == "abc"


def test_clean_markdown_does_not_collapse_internal_spaces() -> None:
    # It must NOT collapse multiple spaces within a line.
    assert clean_markdown("a    b") == "a    b"


def test_clean_markdown_does_not_remove_non_comment_html() -> None:
    assert clean_markdown("<div>kept</div>") == "<div>kept</div>"


def test_clean_markdown_empty_input_is_empty() -> None:
    assert clean_markdown("") == ""


def test_clean_markdown_whitespace_only_input_is_empty() -> None:
    assert clean_markdown("\n  \r\n\t\n") == ""


def test_clean_markdown_is_idempotent() -> None:
    samples = [
        "a\r\n\r\n\r\n\r\nb   \n\n\n<!-- x -->c",
        "\n\nfoo<!-- multi\nline -->bar  \n\n\n\nbaz\n\n",
        "<div>html</div>\n\n\n\ntext    with    spaces",
        "",
        "\n\n  \n",
    ]
    for s in samples:
        once = clean_markdown(s)
        assert clean_markdown(once) == once


# ---------------------------------------------------------------------------
# clean_markdown — fenced code blocks survive cleanup (design D1-D3)
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-0c0ba143")
def test_clean_markdown_keeps_fenced_content_and_cleans_prose() -> None:
    text = (
        "Intro <!-- drop -->text\n\n\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~\n"
    )
    expected = (
        "Intro text\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~"
    )
    assert clean_markdown(text) == expected


@pytest.mark.l4("C-d06cb587")
def test_clean_markdown_normalises_line_endings_inside_fence() -> None:
    assert clean_markdown("```\r\nx  \r\n```") == "```\nx  \n```"


@pytest.mark.l4("C-99501760")
def test_clean_markdown_fence_grammar() -> None:
    assert clean_markdown("~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->") == "~~~\n```\n<!-- k -->\n~~~"
    assert (
        clean_markdown("````\n```\n<!-- k -->\n````\n<!-- gone -->")
        == "````\n```\n<!-- k -->\n````"
    )
    assert clean_markdown("   ```\n<!-- k -->\n   ```") == "   ```\n<!-- k -->\n   ```"
    assert clean_markdown("    ```\n<!-- x -->") == "    ```"


@pytest.mark.l4("C-637d6041")
def test_clean_markdown_unterminated_fence_runs_to_end_of_text() -> None:
    text = "a\n```\n<!-- c -->\n\n\n\nb"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-279cc124")
def test_clean_markdown_comment_spanning_a_fence_is_not_removed() -> None:
    text = "a <!-- open\n```\nx\n```\nclose --> b"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-bd2b7567")
def test_clean_markdown_unterminated_fence_keeps_trailing_blank_lines() -> None:
    text = "a\n```\nx\n\n\n"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-202c649c")
def test_clean_markdown_collapses_blank_run_before_fence() -> None:
    text = "text\n\n\n\n```\ny\n```"
    expected = "text\n\n```\ny\n```"
    assert conversion._clean_pass(text) == expected
    assert clean_markdown(text) == expected


@pytest.mark.l4("C-67b0056e")
def test_clean_markdown_removed_comment_exposing_opener_needs_one_pass() -> None:
    text = "<!-- c -->```\n<!-- x -->\n\n\n\ny  "
    assert conversion._clean_pass(text) == "```\n\ny"
    assert clean_markdown(text) == "```\n\ny"


@pytest.mark.l4("C-13d0e1ab")
def test_clean_markdown_second_pass_changes_first_pass_output() -> None:
    text = "<!-- c -->```\n```\n<!-- k -->  \n```"
    assert conversion._clean_pass(text) == "```\n```\n<!-- k -->  \n```"
    assert clean_markdown(text) == "```\n```\n\n```"


@pytest.mark.l4("C-c9868a1c")
def test_clean_markdown_is_idempotent_with_fences() -> None:
    samples = [
        (
            "Intro <!-- drop -->text\n\n\n\nmore\n\n```html\n"
            "<!-- keep me -->\nline   \n\n\n\nend\n```\n\n~~~\na\n\n\n\nb  \n~~~\n"
        ),
        "```\r\nx  \r\n```",
        "~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->",
        "````\n```\n<!-- k -->\n````\n<!-- gone -->",
        "    ```\n<!-- x -->",
        "a\n```\n<!-- c -->\n\n\n\nb",
        "a <!-- open\n```\nx\n```\nclose --> b",
        "a\n```\nx\n\n\n",
        "text\n\n\n\n```\ny\n```",
        "<!-- c -->```\n<!-- x -->\n\n\n\ny  ",
        "<!-- c -->```\n```\n<!-- k -->  \n```",
    ]
    for text in samples:
        once = clean_markdown(text)
        assert clean_markdown(once) == once
    assert clean_markdown("text\n\n\n\n```\ny  \n```") == "text\n\n```\ny  \n```"


# ---------------------------------------------------------------------------
# clean_markdown — fence-aware cleanup, pinned independently of the tests above
# (task 2.1: ``_fenced_line_mask`` + the ``_FENCE_OPEN_RE`` fence grammar)
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-0c0ba143")
def test_clean_markdown_fence_prose_around_block_is_cleaned() -> None:
    text = (
        "Intro <!-- drop -->text\n\n\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~\n"
    )
    expected = (
        "Intro text\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~"
    )
    assert clean_markdown(text) == expected


@pytest.mark.l4("C-d06cb587")
def test_clean_markdown_fence_line_endings_normalised_spaces_kept() -> None:
    assert clean_markdown("```\r\nx  \r\n```") == "```\nx  \n```"


@pytest.mark.l4("C-99501760")
def test_clean_markdown_fence_grammar_character_and_length() -> None:
    assert clean_markdown("~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->") == "~~~\n```\n<!-- k -->\n~~~"
    assert (
        clean_markdown("````\n```\n<!-- k -->\n````\n<!-- gone -->")
        == "````\n```\n<!-- k -->\n````"
    )
    assert clean_markdown("   ```\n<!-- k -->\n   ```") == "   ```\n<!-- k -->\n   ```"
    assert clean_markdown("    ```\n<!-- x -->") == "    ```"


@pytest.mark.l4("C-637d6041")
def test_clean_markdown_fence_without_closer_reaches_last_line() -> None:
    text = "a\n```\n<!-- c -->\n\n\n\nb"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-279cc124")
def test_clean_markdown_comment_crossing_fence_boundary_survives() -> None:
    text = "a <!-- open\n```\nx\n```\nclose --> b"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-bd2b7567")
def test_clean_markdown_unclosed_fence_preserves_unique_trailing_blanks() -> None:
    text = "a\n```\nx\n\n\n"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-202c649c")
def test_clean_markdown_blank_run_before_opening_fence_collapses() -> None:
    assert clean_markdown("text\n\n\n\n```\ny\n```") == "text\n\n```\ny\n```"


@pytest.mark.l4("C-67b0056e")
def test_clean_markdown_comment_removal_may_expose_fence_in_one_pass() -> None:
    assert clean_markdown("<!-- c -->```\n<!-- x -->\n\n\n\ny  ") == "```\n\ny"


@pytest.mark.l4("C-13d0e1ab")
def test_clean_markdown_fixed_point_after_second_pass() -> None:
    assert clean_markdown("<!-- c -->```\n```\n<!-- k -->  \n```") == "```\n```\n\n```"


@pytest.mark.l4("C-c9868a1c")
def test_clean_markdown_fence_passes_are_idempotent() -> None:
    samples = [
        "Intro <!-- drop -->text\n\n\n\nmore\n\n```html\n<!-- keep me -->\nline   \n\n\n\nend\n```",
        "```\r\nx  \r\n```",
        "~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->",
        "    ```\n<!-- x -->",
        "a\n```\n<!-- c -->\n\n\n\nb",
        "a <!-- open\n```\nx\n```\nclose --> b",
        "text\n\n\n\n```\ny\n```",
        "<!-- c -->```\n<!-- x -->\n\n\n\ny  ",
        "<!-- c -->```\n```\n<!-- k -->  \n```",
    ]
    for text in samples:
        once = clean_markdown(text)
        assert clean_markdown(once) == once
    assert clean_markdown("text\n\n\n\n```\ny  \n```") == "text\n\n```\ny  \n```"


# ---------------------------------------------------------------------------
# is_convertible / supported_suffixes
# ---------------------------------------------------------------------------
def test_is_convertible_true_for_office_binaries() -> None:
    assert is_convertible("report.pdf")
    assert is_convertible("notes.docx")
    assert is_convertible(Path("/tmp/sheet.XLSX"))  # case-insensitive


def test_is_convertible_false_for_text_suffixes() -> None:
    assert not is_convertible("readme.md")
    assert not is_convertible("notes.txt")
    assert not is_convertible(Path("x.unknown"))


def test_supported_suffixes_is_union_of_text_and_convertible() -> None:
    assert supported_suffixes() == (TEXT_SUFFIXES | CONVERTIBLE_SUFFIXES)
    # All entries are lowercase and dot-prefixed.
    for suffix in supported_suffixes():
        assert suffix == suffix.lower()
        assert suffix.startswith(".")


# ---------------------------------------------------------------------------
# extract_markdown — text + unknown suffix dispatch (method="text")
# ---------------------------------------------------------------------------
def test_extract_markdown_txt_returns_text_method(tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("hello\r\n\r\n\r\n\r\nworld   \n", encoding="utf-8")
    result = extract_markdown(p)
    assert isinstance(result, ExtractResult)
    assert result.method == "text"
    assert result.path == p
    # The content flowed through clean_markdown (CRLF + blank collapse + trim).
    assert result.text == "hello\n\nworld"


def test_extract_markdown_unknown_suffix_is_text(tmp_path: Path) -> None:
    p = tmp_path / "data.weird"
    p.write_text("some\r\ncontent  ", encoding="utf-8")
    result = extract_markdown(p)
    assert result.method == "text"
    assert result.text == "some\ncontent"


def test_extract_markdown_extra_text_suffix_treated_as_text(tmp_path: Path) -> None:
    p = tmp_path / "file.pdf"
    p.write_text("not really a pdf", encoding="utf-8")
    # .pdf is convertible by default, but the caller opted it into text handling.
    result = extract_markdown(p, extra_text_suffixes=frozenset({".pdf"}))
    assert result.method == "text"
    assert result.text == "not really a pdf"


def test_extract_markdown_missing_file_raises_conversion_error(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="not a file"):
        extract_markdown(tmp_path / "nope.txt")


# ---------------------------------------------------------------------------
# extract_markdown — convertible binaries
# ---------------------------------------------------------------------------
def test_extract_markdown_docx_without_markitdown_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conversion, "markitdown_available", lambda: False)
    p = tmp_path / "doc.docx"
    p.write_bytes(b"PK\x03\x04 fake docx bytes")
    with pytest.raises(MarkitdownNotInstalled):
        extract_markdown(p, convert=True)


def test_markitdown_not_installed_is_a_conversion_error() -> None:
    assert issubclass(MarkitdownNotInstalled, ConversionError)
    assert issubclass(FileTooLarge, ConversionError)


def _inject_fake_markitdown(monkeypatch: pytest.MonkeyPatch, text_content: str) -> dict[str, Any]:
    """Inject a fake ``markitdown`` module into ``sys.modules`` (auto-reverts).

    The fake ``MarkItDown.convert`` returns an object whose ``.text_content`` is
    the supplied markdown. ``captured`` records constructor and convert args so
    callers can assert wiring (e.g. ``enable_plugins`` threading).
    """
    captured: dict[str, Any] = {}

    class _FakeResult:
        def __init__(self, text: str) -> None:
            self.text_content = text

    class MarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None:
            captured["enable_plugins"] = enable_plugins

        def convert(self, source: str) -> _FakeResult:
            captured["source"] = source
            return _FakeResult(text_content)

    module = types.ModuleType("markitdown")
    module.MarkItDown = MarkItDown  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "markitdown", module)
    # The contract imports markitdown lazily; ensure availability reports True
    # even though the real package is absent in the test env.
    monkeypatch.setattr(conversion, "markitdown_available", lambda: True)
    return captured


def test_extract_markdown_markitdown_present_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _inject_fake_markitdown(monkeypatch, "# Title\r\n\r\n\r\n\r\nbody text   \n")
    p = tmp_path / "report.docx"
    p.write_bytes(b"PK\x03\x04 fake docx bytes")

    result = extract_markdown(p, convert=True, enable_plugins=True)

    assert result.method == "markitdown"
    assert result.path == p
    # The fake's text flowed through clean_markdown.
    assert result.text == "# Title\n\nbody text"
    # enable_plugins threaded through to the MarkItDown constructor.
    assert captured["enable_plugins"] is True
    assert captured["source"] == str(p)


def test_extract_markdown_markitdown_strips_html_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_fake_markitdown(monkeypatch, "real<!-- markitdown noise -->content")
    p = tmp_path / "deck.pptx"
    p.write_bytes(b"PK\x03\x04 fake pptx")
    result = extract_markdown(p, convert=True)
    assert result.method == "markitdown"
    assert result.text == "realcontent"


def test_extract_markdown_markitdown_exception_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeResult:
        text_content = ""

    class MarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None: ...

        def convert(self, source: str) -> _FakeResult:
            raise ValueError("corrupt office file")

    module = types.ModuleType("markitdown")
    module.MarkItDown = MarkItDown  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "markitdown", module)
    monkeypatch.setattr(conversion, "markitdown_available", lambda: True)

    p = tmp_path / "broken.xlsx"
    p.write_bytes(b"PK\x03\x04 fake xlsx")
    with pytest.raises(ConversionError, match="markitdown failed") as exc_info:
        extract_markdown(p, convert=True)
    # The original markitdown exception is chained, not leaked as the type.
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert not isinstance(exc_info.value, MarkitdownNotInstalled)


# ---------------------------------------------------------------------------
# extract_markdown — size cap + convert=False
# ---------------------------------------------------------------------------
def test_extract_markdown_file_too_large(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(FileTooLarge):
        extract_markdown(p, max_bytes=10)


def test_extract_markdown_max_bytes_zero_means_no_limit(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("x" * 100, encoding="utf-8")
    # max_bytes <= 0 disables the cap.
    result = extract_markdown(p, max_bytes=0)
    assert result.method == "text"
    assert result.text == "x" * 100


def test_extract_markdown_under_cap_is_allowed(tmp_path: Path) -> None:
    p = tmp_path / "small.txt"
    p.write_text("ok", encoding="utf-8")
    result = extract_markdown(p, max_bytes=1024)
    assert result.text == "ok"


def test_extract_markdown_convert_false_on_pdf_raises(tmp_path: Path) -> None:
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ConversionError, match="--convert"):
        extract_markdown(p, convert=False)


# ---------------------------------------------------------------------------
# extract_markdown — decompression-bomb output cap + timeout + empty output
# ---------------------------------------------------------------------------
def test_extract_markdown_output_too_large_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A small on-disk file whose markitdown output is huge (zip/PDF bomb shape).
    _inject_fake_markitdown(monkeypatch, "x" * 5000)
    p = tmp_path / "bomb.docx"
    p.write_bytes(b"PK\x03\x04 tiny on disk")
    with pytest.raises(FileTooLarge, match="decompression bomb"):
        extract_markdown(p, convert=True, max_output_bytes=1000)


def test_extract_markdown_output_cap_zero_means_no_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_fake_markitdown(monkeypatch, "y" * 5000)
    p = tmp_path / "big.docx"
    p.write_bytes(b"PK\x03\x04")
    result = extract_markdown(p, convert=True, max_output_bytes=0)
    assert result.text == "y" * 5000


def test_extract_markdown_empty_markitdown_output_is_empty_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_fake_markitdown(monkeypatch, "")
    p = tmp_path / "empty.docx"
    p.write_bytes(b"PK\x03\x04")
    result = extract_markdown(p, convert=True)
    assert result.method == "markitdown"
    assert result.text == ""


def test_extract_markdown_none_markitdown_output_is_empty_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _NoneResult:
        text_content = None

    class MarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None: ...

        def convert(self, source: str) -> _NoneResult:
            return _NoneResult()

    module = types.ModuleType("markitdown")
    module.MarkItDown = MarkItDown  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "markitdown", module)
    monkeypatch.setattr(conversion, "markitdown_available", lambda: True)

    p = tmp_path / "none.docx"
    p.write_bytes(b"PK\x03\x04")
    result = extract_markdown(p, convert=True)
    assert result.text == ""


def test_extract_markdown_conversion_timeout_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A wedged parser must not hang the run: a bounded convert raises so the
    # caller can skip the one file. The daemon worker is released at teardown.
    release = threading.Event()

    class _LateResult:
        text_content = "eventually"

    class MarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None: ...

        def convert(self, source: str) -> _LateResult:
            release.wait(timeout=5)
            return _LateResult()

    module = types.ModuleType("markitdown")
    module.MarkItDown = MarkItDown  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "markitdown", module)
    monkeypatch.setattr(conversion, "markitdown_available", lambda: True)

    p = tmp_path / "slow.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    try:
        with pytest.raises(ConversionError, match="timed out"):
            extract_markdown(p, convert=True, timeout_s=0.1)
    finally:
        release.set()  # let the daemon thread finish promptly


# ---------------------------------------------------------------------------
# clean_markdown — task 2.2 contract, re-pinned on the public API alone
# (no import of the private pass helpers; real, non-empty expected answers)
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-0c0ba143")
def test_clean_markdown_prose_cleanup_outside_fences_keeps_block() -> None:
    text = (
        "Intro <!-- drop -->text\n\n\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~\n"
    )
    expected = (
        "Intro text\n\nmore\n\n"
        "```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n"
        "~~~\na\n\n\n\nb  \n~~~"
    )
    assert clean_markdown(text) == expected


@pytest.mark.l4("C-d06cb587")
def test_clean_markdown_crlf_in_fence_normalised_spaces_preserved() -> None:
    assert clean_markdown("```\r\nx  \r\n```") == "```\nx  \n```"


@pytest.mark.l4("C-99501760")
def test_clean_markdown_fence_opening_and_closing_grammar() -> None:
    assert clean_markdown("~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->") == "~~~\n```\n<!-- k -->\n~~~"
    assert (
        clean_markdown("````\n```\n<!-- k -->\n````\n<!-- gone -->")
        == "````\n```\n<!-- k -->\n````"
    )
    assert clean_markdown("   ```\n<!-- k -->\n   ```") == "   ```\n<!-- k -->\n   ```"
    assert clean_markdown("    ```\n<!-- x -->") == "    ```"


@pytest.mark.l4("C-637d6041")
def test_clean_markdown_unclosed_fence_spans_to_final_line() -> None:
    text = "a\n```\n<!-- c -->\n\n\n\nb"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-279cc124")
def test_clean_markdown_comment_broken_by_fence_left_intact() -> None:
    text = "a <!-- open\n```\nx\n```\nclose --> b"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-bd2b7567")
def test_clean_markdown_unclosed_fence_retains_trailing_blanks() -> None:
    text = "a\n```\nx\n\n\n"
    assert clean_markdown(text) == text


@pytest.mark.l4("C-202c649c")
def test_clean_markdown_blank_lines_before_fence_collapse_to_one() -> None:
    assert clean_markdown("text\n\n\n\n```\ny\n```") == "text\n\n```\ny\n```"


@pytest.mark.l4("C-67b0056e")
def test_clean_markdown_comment_removal_exposing_fence_is_stable() -> None:
    assert clean_markdown("<!-- c -->```\n<!-- x -->\n\n\n\ny  ") == "```\n\ny"


@pytest.mark.l4("C-13d0e1ab")
def test_clean_markdown_repeated_pass_reaches_fixed_point() -> None:
    assert clean_markdown("<!-- c -->```\n```\n<!-- k -->  \n```") == "```\n```\n\n```"


@pytest.mark.l4("C-c9868a1c")
def test_clean_markdown_with_fences_idempotent() -> None:
    samples = [
        (
            "Intro <!-- drop -->text\n\n\n\nmore\n\n```html\n"
            "<!-- keep me -->\nline   \n\n\n\nend\n```"
        ),
        "```\r\nx  \r\n```",
        "~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->",
        "    ```\n<!-- x -->",
        "a\n```\n<!-- c -->\n\n\n\nb",
        "a <!-- open\n```\nx\n```\nclose --> b",
        "text\n\n\n\n```\ny\n```",
        "<!-- c -->```\n<!-- x -->\n\n\n\ny  ",
        "<!-- c -->```\n```\n<!-- k -->  \n```",
    ]
    for text in samples:
        once = clean_markdown(text)
        assert clean_markdown(once) == once
    assert clean_markdown("text\n\n\n\n```\ny  \n```") == "text\n\n```\ny  \n```"
