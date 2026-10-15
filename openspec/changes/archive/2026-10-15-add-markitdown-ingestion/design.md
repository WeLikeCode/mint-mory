# Design & FROZEN interface contract — `add-markitdown-ingestion`

This is the build contract. Implementation agents MUST match these signatures,
names, env prefixes, and behaviours **exactly** so that work on disjoint files
integrates without re-derivation. Where this document and intuition disagree,
this document wins.

---

## 1. New module: `packages/core/src/mintmory/core/conversion.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Plain-text suffixes: read directly, never routed through markitdown.
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".markdown", ".txt", ".text", ".rst", ".log"}
)

# Binary/office suffixes markitdown handles. Routed through markitdown.
CONVERTIBLE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
        ".csv", ".tsv", ".html", ".htm", ".xml", ".json",
        ".epub", ".rtf", ".odt", ".msg",
    }
)

DEFAULT_MAX_FILE_MB: float = 25.0


class ConversionError(RuntimeError):
    """Base for any ingest-time conversion failure (caller skips the file)."""


class MarkitdownNotInstalled(ConversionError):
    """A convertible binary was given but the `docs` extra is not installed."""


class FileTooLarge(ConversionError):
    """File exceeds the configured byte cap."""


@dataclass(frozen=True)
class ExtractResult:
    text: str                          # cleaned markdown/text, ready to chunk
    method: Literal["text", "markitdown"]
    path: Path


def markitdown_available() -> bool:
    """True iff `import markitdown` succeeds. Never raises."""


def supported_suffixes() -> frozenset[str]:
    """TEXT_SUFFIXES | CONVERTIBLE_SUFFIXES (lowercase, dot-prefixed)."""


def is_convertible(path: str | Path) -> bool:
    """True iff the suffix (lowercased) is in CONVERTIBLE_SUFFIXES."""


def clean_markdown(text: str) -> str:
    """Conservative formatting normaliser — see §3. Pure, total, idempotent."""


def extract_markdown(
    path: str | Path,
    *,
    convert: bool = True,
    max_bytes: int | None = None,
    extra_text_suffixes: frozenset[str] = frozenset(),
    enable_plugins: bool = False,
) -> ExtractResult:
    """Resolve one file to cleaned markdown. Dispatch rules in §2."""
```

### Lazy import requirement
`markitdown` MUST be imported **inside** the functions that need it
(`markitdown_available`, the markitdown branch of `extract_markdown`), never at
module top level. This keeps `mintmory.core` importable without the extra and
lets tests inject a fake `markitdown` module into `sys.modules`.

---

## 2. `extract_markdown` dispatch (exact order)

Let `p = Path(path).expanduser()`, `suffix = p.suffix.lower()`,
`text_suffixes = TEXT_SUFFIXES | extra_text_suffixes`.

1. If `not p.is_file()` → raise `ConversionError(f"not a file: {p}")`.
2. If `max_bytes is not None and max_bytes > 0`: stat the size; if
   `size > max_bytes` → raise `FileTooLarge(f"{p} is {size} bytes > cap {max_bytes}")`.
   (`max_bytes` None or `<= 0` ⇒ no limit.)
3. If `suffix in text_suffixes` → read `p.read_text("utf-8", errors="replace")`,
   `clean_markdown(...)`, return `method="text"`.
4. If `suffix in CONVERTIBLE_SUFFIXES`:
   - If `not convert` → raise `ConversionError` (binary, conversion disabled —
     message must name `--convert`).
   - If `not markitdown_available()` → raise `MarkitdownNotInstalled` with the
     install hint `uv sync --extra docs` (or `pip install 'markitdown[all]'`).
   - Else: `MarkItDown(enable_plugins=enable_plugins).convert(str(p))`, take
     `result.text_content` (it is the markdown), `clean_markdown(...)`, return
     `method="markitdown"`. Wrap **any** markitdown exception in
     `ConversionError(f"markitdown failed on {p}: {exc}") from exc`.
5. Else (unknown suffix) → behave like a text file (read utf-8/replace + clean,
   `method="text"`). This preserves today's "read anything" behaviour for
   suffixes the user explicitly globbed in; it is the caller's responsibility
   via `--glob`.

`extract_markdown` must NEVER return a non-`ExtractResult` and must never leak a
raw markitdown exception type to the caller.

---

## 3. `clean_markdown` — the "fix formatting" pass

Conservative and **idempotent** (`clean(clean(x)) == clean(x)`). It must not
reflow prose, touch indentation inside fenced code blocks, or alter table
pipes. It MUST:

1. Normalise line endings: `\r\n` and `\r` → `\n`.
2. Strip trailing whitespace from each line.
3. Collapse 3+ consecutive blank lines to exactly one blank line.
4. Strip leading and trailing blank lines (final result has no trailing newline;
   storage strips anyway).
5. Remove HTML comments `<!-- ... -->` (markitdown sometimes emits them),
   including multi-line ones, non-greedily.

It must NOT: collapse multiple spaces within a line, lowercase, de-dupe, or
remove non-comment HTML. Empty/whitespace input → `""`.

---

## 4. `ConversionSettings` in `packages/core/src/mintmory/core/config.py`

Add a group mirroring the existing ones, and wire it into `Settings`:

```python
class ConversionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_CONVERT_", extra="ignore")

    enabled: bool = True                       # global off-switch (ANDed with the CLI --convert flag)
    max_file_mb: float = Field(default=25.0, ge=0.0)    # on-disk size cap; 0 = no limit
    max_output_mb: float = Field(default=50.0, ge=0.0)  # DECOMPRESSED output cap; 0 = no limit
    timeout_s: float = Field(default=120.0, ge=0.0)     # per-file conversion wall-clock; 0 = no bound
    extra_text_suffixes_csv: str = ""          # extra suffixes treated as plain text
    enable_plugins: bool = False               # markitdown 3rd-party plugins

    @property
    def extra_text_suffixes(self) -> frozenset[str]: ...   # lowercase, single leading dot, drop blanks

    @property
    def max_bytes(self) -> int | None: ...                 # None if max_file_mb <= 0

    @property
    def max_output_bytes(self) -> int | None: ...          # None if max_output_mb <= 0
```

**Robustness (added in review):** `max_file_mb` caps the *on-disk* size, which is
the **compressed** size for zip/PDF formats — a small file can decompress to GBs.
So `extract_markdown` ALSO bounds the decompressed markitdown output
(`max_output_bytes`, raising `FileTooLarge`) and runs `convert()` in a **daemon
thread** bounded by `timeout_s` (raising `ConversionError` on expiry) so one
hostile file cannot hang the serial ingest run or block process exit.

Add to `Settings`: `convert: ConversionSettings = Field(default_factory=ConversionSettings)`.
Place the enum-free group near the others; keep the module's "defaults reproduce
today's behaviour" rule — the only new behaviour (auto-convert) is gated by the
CLI flag + presence of the optional extra.

---

## 5. `pyproject` extras

`packages/core/pyproject.toml`, under `[project.optional-dependencies]`:

```toml
docs = ["markitdown[all]>=0.1.0"]   # MS markitdown: docx/pdf/xlsx/pptx/... → markdown (imported lazily)
```

`packages/cli/pyproject.toml`, add an `[project.optional-dependencies]` table:

```toml
[project.optional-dependencies]
docs = ["mintmory-core[docs]"]
```

Do **not** add markitdown to any `dependencies` list. Do not run `uv lock`/`uv
sync --extra docs` as part of the change (network); the default test env never
imports markitdown.

---

## 6. CLI wiring — `packages/cli/src/mintmory/cli/main.py`

In `ingest`:
- Add option:
  `convert: bool = typer.Option(True, "--convert/--no-convert", help="Auto-convert PDF/DOCX/XLSX/PPTX/etc to markdown via markitdown (needs the 'docs' extra)")`.
- Extend the default `glob` to:
  `"*.md,*.txt,*.pdf,*.docx,*.pptx,*.xlsx,*.csv,*.html"`.
- Load `settings = load_settings()` once; read `conv = settings.convert`.
- Replace the `text = f.read_text(...)` block with a call to
  `extract_markdown(f, convert=convert and conv.enabled, max_bytes=conv.max_bytes,
  extra_text_suffixes=conv.extra_text_suffixes, enable_plugins=conv.enable_plugins,
  timeout_s=conv.timeout_s, max_output_bytes=conv.max_output_bytes)`, catching
  `ConversionError` → print `[red]skip[/red] {f}: {exc}`, increment a `failed`
  counter, and `continue` (the whole run keeps going). `enabled` is ANDed so
  `MINTMORY_CONVERT_ENABLED=false` is a global off-switch.
- Add `"converter": result.method` to each chunk's metadata dict.
- If conversion succeeds but yields no extractable text (empty after cleaning →
  0 chunks), print a "produced no extractable text" note, count it as a skipped
  file, and do NOT add it to the markitdown tally.
- Count files converted via markitdown; surface the markitdown count and the
  `failed` count in the final summary line, e.g.
  `... ; skipped 1 file(s) (3 via markitdown).`.

In `doctor`: add a non-fatal row before/after `linking`:
```
conversion | markitdown available (N convertible formats)     # green, N = len(CONVERTIBLE_SUFFIXES)
           | not installed — `uv sync --extra docs` for PDF/DOCX/XLSX   # yellow
```
Use `mintmory.core.conversion.markitdown_available()` and
`len(CONVERTIBLE_SUFFIXES)` (the markitdown-routed formats — NOT the text
suffixes). Do not change the `healthy` flag.

---

## 7. Tests (contract)

**`packages/core/tests/test_conversion.py`** must cover: `clean_markdown`
(CRLF, trailing ws, 3+ blank-line collapse, HTML-comment removal, idempotence,
empty input); `is_convertible`/`supported_suffixes`; `extract_markdown` for a
`.txt` (method=text) and unknown suffix (method=text); `.docx` with markitdown
absent → `MarkitdownNotInstalled` (monkeypatch `markitdown_available` → False);
markitdown present path via a **fake `markitdown` module injected into
`sys.modules`** (assert `method=="markitdown"` and the fake's text flows through
`clean_markdown`); `FileTooLarge` when `max_bytes` exceeded; `convert=False` on
a `.pdf` → `ConversionError`.

**`packages/cli/tests/test_cli.py`** (extend): ingest a fake `.docx` with a fake
`markitdown` module injected (assert the converted markdown is stored and
metadata `converter=="markitdown"`); ingest a `.pdf` with markitdown absent →
exit 0, that file skipped, sibling `.md` still ingested; `doctor` prints a
`conversion` row. Keep using the `MINTMORY_DB` tmp fixture; no network.

All gates must pass: `pytest` (coverage ≥ 80 overall), `ruff check`,
`ruff format --check`, `mypy` strict.
