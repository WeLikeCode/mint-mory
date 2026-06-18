"""
File-to-markdown conversion for MintMory ingestion.

Resolves a single file on disk to cleaned markdown ready to chunk. Plain-text
suffixes are read directly; binary/office suffixes are routed through Microsoft
``markitdown`` (an optional ``docs`` extra). ``markitdown`` is imported lazily
inside the functions that need it, so importing this module never requires the
extra and tests can inject a fake ``markitdown`` into ``sys.modules``.

The ``clean_markdown`` pass is conservative and idempotent: it normalises line
endings and blank runs and strips HTML comments, but never reflows prose, touches
fenced-code indentation, or alters table pipes.
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
# Three or more consecutive blank lines (lines empty after trailing-ws strip).
_BLANK_RUN_RE = re.compile(r"\n{3,}")


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
    """Conservative formatting normaliser — see design §3. Pure, total, idempotent."""
    # 1. Normalise line endings: \r\n and \r -> \n.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 5. Remove HTML comments (multi-line, non-greedy) before blank-run collapse,
    #    so the gaps a removed comment leaves are normalised below.
    text = _HTML_COMMENT_RE.sub("", text)
    # 2. Strip trailing whitespace from each line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # 3. Collapse 3+ consecutive blank lines to exactly one blank line.
    text = _BLANK_RUN_RE.sub("\n\n", text)
    # 4. Strip leading and trailing blank lines (no trailing newline).
    return text.strip("\n")


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
