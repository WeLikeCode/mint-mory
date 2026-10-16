"""
File-to-markdown conversion for MintMory ingestion.

Resolves a single file on disk to cleaned markdown ready to chunk. Plain-text
suffixes are read directly; binary/office suffixes are routed through Microsoft
``markitdown`` (an optional ``docs`` extra). ``markitdown`` is imported lazily
inside the functions that need it, so importing this module never requires the
extra and tests can inject a fake ``markitdown`` into ``sys.modules``.

The ``clean_markdown`` pass is conservative and idempotent: it normalises line
endings and blank runs and strips HTML comments, but never reflows prose or
alters table pipes. Backtick and tilde fenced code blocks are copied
byte-identical, so comments, trailing whitespace and blank lines inside them
survive.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Plain-text suffixes: read directly, never routed through markitdown.
TEXT_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown", ".txt", ".text", ".rst", ".log"})

# Binary/office suffixes markitdown handles. Routed through markitdown.
CONVERTIBLE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".csv",
        ".tsv",
        ".html",
        ".htm",
        ".xml",
        ".json",
        ".epub",
        ".rtf",
        ".odt",
        ".msg",
    }
)

DEFAULT_MAX_FILE_MB: float = 25.0
# Wall-clock bound for a single markitdown conversion (a hostile file must not
# wedge the whole serial ingest run). 0/None ⇒ unbounded.
DEFAULT_TIMEOUT_S: float = 120.0
# Ceiling on the *decompressed* markitdown output. The on-disk size cap is the
# COMPRESSED size for zip/PDF formats, so a small file can expand hugely; this
# bounds the in-memory result (decompression-bomb defence). 0/None ⇒ unbounded.
DEFAULT_MAX_OUTPUT_MB: float = 50.0

# HTML comments, including multi-line ones, matched non-greedily.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class ConversionError(RuntimeError):
    """Base for any ingest-time conversion failure (caller skips the file)."""


class MarkitdownNotInstalled(ConversionError):  # noqa: N818 — frozen contract name
    """A convertible binary was given but the `docs` extra is not installed."""


class FileTooLarge(ConversionError):  # noqa: N818 — frozen contract name
    """File exceeds the configured byte cap."""


@dataclass(frozen=True)
class ExtractResult:
    text: str  # cleaned markdown/text, ready to chunk
    method: Literal["text", "markitdown"]
    path: Path


def markitdown_available() -> bool:
    """True iff `import markitdown` succeeds. Never raises."""
    try:
        import markitdown  # noqa: F401
    except Exception:
        return False
    return True


def supported_suffixes() -> frozenset[str]:
    """TEXT_SUFFIXES | CONVERTIBLE_SUFFIXES (lowercase, dot-prefixed)."""
    return TEXT_SUFFIXES | CONVERTIBLE_SUFFIXES


def is_convertible(path: str | Path) -> bool:
    """True iff the suffix (lowercased) is in CONVERTIBLE_SUFFIXES."""
    return Path(path).suffix.lower() in CONVERTIBLE_SUFFIXES


def clean_markdown(text: str) -> str:
    """Conservative formatting normaliser — see design §3. Pure, total, idempotent.

    Fenced code blocks survive each pass byte-identical (after line-ending
    normalisation); the prose around them is cleaned as before. The pass is
    repeated, re-identifying fences on each pass's input, until a fixed point,
    so the result satisfies ``clean_markdown(out) == out``.
    """
    # 1. Normalise line endings: \r\n and \r -> \n.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    while True:
        cleaned = _clean_pass(text)
        if cleaned == text:
            return cleaned
        text = cleaned


def _convert_with_timeout(path: Path, *, enable_plugins: bool, timeout_s: float | None) -> Any:
    """Run markitdown in a daemon thread bounded by ``timeout_s``.

    A daemon thread is used so a wedged native parser (pdfminer/openpyxl/lxml) on
    a hostile file cannot block process exit; the leaked thread dies with the
    interpreter. ``timeout_s`` None or <= 0 ⇒ no bound. Raises ``ConversionError``
    on timeout or on any markitdown error so the caller can skip the one file.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        from markitdown import MarkItDown

        try:
            box["result"] = MarkItDown(enable_plugins=enable_plugins).convert(str(path))
        except Exception as exc:  # noqa: BLE001 — re-raised as ConversionError below
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout_s if timeout_s and timeout_s > 0 else None)
    if thread.is_alive():
        raise ConversionError(f"markitdown timed out on {path} after {timeout_s}s")
    if "error" in box:
        raise ConversionError(f"markitdown failed on {path}: {box['error']}") from box["error"]
    return box["result"]


def extract_markdown(
    path: str | Path,
    *,
    convert: bool = True,
    max_bytes: int | None = None,
    extra_text_suffixes: frozenset[str] = frozenset(),
    enable_plugins: bool = False,
    timeout_s: float | None = None,
    max_output_bytes: int | None = None,
) -> ExtractResult:
    """Resolve one file to cleaned markdown. Dispatch rules in design §2."""
    p = Path(path).expanduser()
    suffix = p.suffix.lower()
    text_suffixes = TEXT_SUFFIXES | extra_text_suffixes

    # 1. Must be an existing regular file.
    if not p.is_file():
        raise ConversionError(f"not a file: {p}")

    # 2. Size cap (None or <= 0 ⇒ no limit).
    if max_bytes is not None and max_bytes > 0:
        size = p.stat().st_size
        if size > max_bytes:
            raise FileTooLarge(f"{p} is {size} bytes > cap {max_bytes}")

    # 3. Plain-text suffix: read directly.
    if suffix in text_suffixes:
        return ExtractResult(
            text=clean_markdown(p.read_text("utf-8", errors="replace")),
            method="text",
            path=p,
        )

    # 4. Convertible binary/office suffix: route through markitdown.
    if suffix in CONVERTIBLE_SUFFIXES:
        if not convert:
            raise ConversionError(
                f"{p} is a convertible binary but conversion is disabled "
                f"(pass --convert to enable markitdown)"
            )
        if not markitdown_available():
            raise MarkitdownNotInstalled(
                f"cannot convert {p}: markitdown is not installed — run "
                f"`uv sync --extra docs` (or `pip install 'markitdown[all]'`)"
            )
        result = _convert_with_timeout(p, enable_plugins=enable_plugins, timeout_s=timeout_s)
        content = result.text_content or ""
        # The on-disk cap (step 2) is the COMPRESSED size for zip/PDF formats;
        # bound the decompressed output too (decompression-bomb defence).
        # Falsy (None/0) ⇒ no cap; truthiness narrows the Optional to int.
        if max_output_bytes and len(content) > max_output_bytes:
            raise FileTooLarge(
                f"markitdown output for {p} is {len(content)} chars > cap "
                f"{max_output_bytes} (possible decompression bomb)"
            )
        return ExtractResult(text=clean_markdown(content), method="markitdown", path=p)

    # 5. Unknown suffix: behave like a text file ("read anything").
    return ExtractResult(
        text=clean_markdown(p.read_text("utf-8", errors="replace")),
        method="text",
        path=p,
    )


def _clean_pass(text: str) -> str:
    """One cleanup pass: fenced lines copied verbatim, prose cleaned as before.

    Fences are identified on this pass's input (design D1). Leading and trailing
    blank lines are stripped only where they are outside a fence (design D3), so
    an unterminated fence keeps its trailing blank lines.
    """
    lines = text.split("\n")
    mask = _fenced_line_mask(lines)
    out: list[str] = []
    fenced_out: list[bool] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and mask[j] == mask[i]:
            j += 1
        if mask[i]:
            out.extend(lines[i:j])
            fenced_out.extend([True] * (j - i))
        else:
            cleaned = _clean_run_lines(lines[i:j])
            out.extend(cleaned)
            fenced_out.extend([False] * len(cleaned))
        i = j
    while out and not fenced_out[0] and out[0] == "":
        out.pop(0)
        fenced_out.pop(0)
    while out and not fenced_out[-1] and out[-1] == "":
        out.pop()
        fenced_out.pop()
    return "\n".join(out)


# A fence opens on at most 3 spaces then a run of 3+ backticks or 3+ tildes.
_FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
# A fence closes on at most 3 spaces, the same char run, nothing but spaces/tabs.
_FENCE_CLOSE_RE = re.compile(r"^( {0,3})(`+|~+)[ \t]*$")


def _opening_fence(line: str) -> tuple[str, int] | None:
    """``(char, run-length)`` if ``line`` opens a fence, else ``None``.

    A backtick fence's info string may not contain a backtick (CommonMark).
    """
    m = _FENCE_OPEN_RE.match(line)
    if m is None:
        return None
    fence, info = m.group(2), m.group(3)
    if fence[0] == "`" and "`" in info:
        return None
    return fence[0], len(fence)


def _closes_fence(line: str, char: str, min_len: int) -> bool:
    """True iff ``line`` closes a fence opened with ``char`` repeated ``min_len``+."""
    m = _FENCE_CLOSE_RE.match(line)
    if m is None:
        return False
    run = m.group(2)
    return run[0] == char and len(run) >= min_len


def _fenced_line_mask(lines: list[str]) -> list[bool]:
    """True for every line from an opener through its closer (or end of text)."""
    mask = [False] * len(lines)
    i = 0
    while i < len(lines):
        opener = _opening_fence(lines[i])
        if opener is None:
            i += 1
            continue
        char, length = opener
        j = i + 1
        while j < len(lines) and not _closes_fence(lines[j], char, length):
            j += 1
        end = j if j < len(lines) else len(lines) - 1
        for k in range(i, end + 1):
            mask[k] = True
        i = end + 1
    return mask


def _clean_run_lines(lines: list[str]) -> list[str]:
    """Clean a maximal run of non-fenced lines: comments, trailing ws, blank runs."""
    text = _HTML_COMMENT_RE.sub("", "\n".join(lines))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    out: list[str] = []
    blanks = 0
    for line in text.split("\n"):
        if line == "":
            blanks += 1
            continue
        if blanks:
            out.append("")
            blanks = 0
        out.append(line)
    if blanks:
        out.append("")
    return out
