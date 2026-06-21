"""
MintMory CLI — direct stdio usage.

Commands:
  mintmory add <content> --category fact
  mintmory ingest <paths...> --category fact      # bulk-ingest files/dirs (chunked)
  mintmory search <query> [--around contradicts]
  mintmory dream [--full]
  mintmory stats
  mintmory doctor                 # one-shot health check (DB, embedder, LLM tier)
  mintmory serve [--port 8080]    # start HTTP API
  mintmory mcp                    # start MCP server (stdio)
  mintmory note <content> [--about ...] [--when ISO] [--until ISO] [--category ...]
  mintmory notes [--about ...] [--upcoming] [--overdue] [--limit N]
  mintmory summary-jobs [--all/--needed] [--limit N] [--json]
  mintmory summary-put CONCEPT [TEXT] [--file PATH]
  mintmory image-jobs [--all/--needed] [--bytes/--no-bytes] [--limit N] [--json]
  mintmory image-caption-put FILE_OR_ID [DESCRIPTION] [--file PATH]
  mintmory vision-run [--limit N] [--budget MB] [--all/--needed]
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from mintmory.core.types import ConceptLinkType, MemoryCategory, MemorySource
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter

app = typer.Typer(name="mintmory", help="MintMory — typed memory for LLM agents")
console = Console()


def _get_store() -> StorageAdapter:
    from mintmory.core.config import load_settings
    from mintmory.core.embedder import embedder_from_settings
    from mintmory.core.storage import StorageAdapter

    db_path = os.environ.get("MINTMORY_DB", str(Path.home() / ".mintmory" / "memories.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store = StorageAdapter(db_path, embedder=embedder_from_settings(load_settings().embed))
    store.initialise()
    return store


def _parse_category(category: str) -> MemoryCategory:
    """Coerce a raw string into a MemoryCategory or raise a clear typer error."""
    try:
        return MemoryCategory(category)
    except ValueError as exc:
        valid = ", ".join(c.value for c in MemoryCategory)
        raise typer.BadParameter(f"invalid category {category!r}; choose one of: {valid}") from exc


def _parse_source(source: str) -> MemorySource:
    """Coerce a raw string into a MemorySource or raise a clear typer error."""
    try:
        return MemorySource(source)
    except ValueError as exc:
        valid = ", ".join(s.value for s in MemorySource)
        raise typer.BadParameter(f"invalid source {source!r}; choose one of: {valid}") from exc


def _parse_link_type(link_type: str) -> ConceptLinkType:
    """Coerce a raw string into a ConceptLinkType or raise a clear typer error."""
    try:
        return ConceptLinkType(link_type)
    except ValueError as exc:
        valid = ", ".join(lt.value for lt in ConceptLinkType)
        raise typer.BadParameter(
            f"invalid link type {link_type!r}; choose one of: {valid}"
        ) from exc


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 date/datetime string or raise ``typer.BadParameter``.

    Returns ``None`` when ``value`` is ``None``. The agent/caller is expected to
    supply a valid ISO string; MintMory does no natural-language date parsing.
    """
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"invalid ISO date/datetime {value!r}; expected e.g. '2026-07-01' or '2026-07-01T09:00'"
        ) from exc


@app.command()
def add(
    content: str = typer.Argument(..., help="Memory content"),
    category: str = typer.Option("fact", help="Memory category"),
    source: str = typer.Option("user", help="Memory source"),
    verified: bool = typer.Option(False, "--verified/--unverified"),
) -> None:
    """Add a new memory."""
    cat = _parse_category(category)
    src = _parse_source(source)
    store = _get_store()
    record = store.add_memory(
        content=content,
        category=cat,
        source=src,
        verified=verified,
    )
    console.print(f"[green]Added memory[/green] [bold]{record.id}[/bold]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results"),
    around: str | None = typer.Option(None, help="Link type for graph traversal"),
    category: str | None = typer.Option(None, help="Filter by category"),
) -> None:
    """Search memories. Use --around to traverse the concept graph."""
    from mintmory.core.types import (
        MemoryFilter,
        SearchAroundSpec,
        SearchRequest,
    )

    mem_filter: MemoryFilter | None = None
    if category is not None:
        mem_filter = MemoryFilter(category=_parse_category(category))

    search_around: SearchAroundSpec | None = None
    if around is not None:
        search_around = SearchAroundSpec(link_types=[_parse_link_type(around)])

    store = _get_store()
    response = store.search(
        SearchRequest(
            query=query,
            limit=limit,
            filter=mem_filter,
            search_around=search_around,
        )
    )

    table = Table(title=f"Search results for {query!r}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("category", style="magenta")
    table.add_column("content")
    for mem in response.memories:
        table.add_row(mem.id, mem.category.value, mem.content)
    console.print(table)
    console.print(f"[dim]{response.total_found} result(s)[/dim]")


@app.command()
def dream(
    full: bool = typer.Option(False, "--full/--light", help="Full vs light dreaming"),
) -> None:
    """Run the dreaming consolidation process (uses the configured LLM tier for L3)."""
    from mintmory.core.config import load_settings
    from mintmory.core.llm import build_dreaming_engine

    settings = load_settings()
    store = _get_store()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    report = engine.run_full() if full else engine.run_light()

    table = Table(title=f"Dream report ({report.intensity.value})")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right", style="green")
    table.add_row("duration_ms", f"{report.duration_ms:.1f}")
    table.add_row("new_links", str(report.new_links))
    table.add_row("new_summaries", str(report.new_summaries))
    table.add_row("contradictions_resolved", str(report.contradictions_resolved))
    table.add_row("memories_archived", str(report.memories_archived))
    table.add_row("memories_rehabilitated", str(report.memories_rehabilitated))
    console.print(table)


@app.command()
def stats() -> None:
    """Show memory health statistics."""
    store = _get_store()
    s = store.get_stats()

    table = Table(title="Memory statistics")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right", style="green")
    table.add_row("total_memories", str(s.total_memories))
    table.add_row("active", str(s.active))
    table.add_row("stale", str(s.stale))
    table.add_row("archived", str(s.archived))
    table.add_row("concept_links", str(s.concept_links))
    table.add_row("memory_summaries", str(s.memory_summaries))
    table.add_row("avg_usefulness_score", f"{s.avg_usefulness_score:.2f}")
    table.add_row("avg_staleness_score", f"{s.avg_staleness_score:.2f}")
    console.print(table)
    if s.top_concepts:
        concepts = ", ".join(f"{name} ({count})" for name, count in s.top_concepts)
        console.print(f"[dim]top concepts: {concepts}[/dim]")


@app.command()
def serve(
    port: int = typer.Option(8080, help="HTTP port"),
    host: str = typer.Option("0.0.0.0", help="Bind host"),
) -> None:
    """Start the HTTP API server."""
    import uvicorn

    uvicorn.run("mintmory.api.app:app", host=host, port=port, reload=True)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into <= max_chars chunks, preferring paragraph boundaries.

    Hard-capped at MemoryRecord's 10_000-char limit; an oversized single paragraph
    is split on character boundaries as a last resort.
    """
    text = text.strip()
    if not text:
        return []
    hard = max(1, min(max_chars, 10_000))
    chunks: list[str] = []
    buf = ""
    for para in (p.strip() for p in text.split("\n\n") if p.strip()):
        if len(para) > hard:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(para[i : i + hard] for i in range(0, len(para), hard))
        elif buf and len(buf) + 2 + len(para) > hard:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def _resolve_files(paths: list[str], globs: list[str]) -> list[Path]:
    """Expand files + directories (recursive glob) into a deduplicated file list."""
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            candidates = sorted({f for g in globs for f in p.rglob(g) if f.is_file()})
        elif p.is_file():
            candidates = [p]
        else:
            raise typer.BadParameter(f"path not found: {raw}")
        for f in candidates:
            rp = f.resolve()
            if rp not in seen:
                seen.add(rp)
                out.append(f)
    return out


@app.command()
def ingest(
    paths: list[str] = typer.Argument(..., help="Files or directories to ingest"),
    category: str = typer.Option("fact", help="Category for ingested memories"),
    source: str = typer.Option("document", help="Memory source"),
    glob: str = typer.Option(
        "*.md,*.txt,*.pdf,*.docx,*.pptx,*.xlsx,*.csv,*.html",
        help="Comma-separated globs for directory paths",
    ),
    chunk_chars: int = typer.Option(4000, help="Approx chars per chunk for large files"),
    skip_duplicates: bool = typer.Option(
        True, "--skip-duplicates/--allow-duplicates", help="Skip chunks whose exact content exists"
    ),
    convert: bool = typer.Option(
        True,
        "--convert/--no-convert",
        help=(
            "Auto-convert PDF/DOCX/XLSX/PPTX/etc to markdown via markitdown "
            "(needs the 'docs' extra)"
        ),
    ),
    dream: bool = typer.Option(False, "--dream/--no-dream", help="Run a light dream after ingest"),
) -> None:
    """Bulk-ingest files or directories as memories (chunked + entity-extracted).

    Idempotent by default: re-running skips chunks whose exact content already
    exists (--allow-duplicates to force). Use this instead of hand-rolling an
    add-per-file script.
    """
    from mintmory.core.config import load_settings
    from mintmory.core.conversion import ConversionError, extract_markdown

    cat = _parse_category(category)
    src = _parse_source(source)
    globs = [g.strip() for g in glob.split(",") if g.strip()]
    files = _resolve_files(paths, globs)
    if not files:
        console.print("[yellow]No matching files to ingest.[/yellow]")
        raise typer.Exit(code=1)

    settings = load_settings()
    conv = settings.convert
    store = _get_store()
    conn = store.connect()
    added = skipped = converted = failed = 0
    for f in files:
        try:
            result = extract_markdown(
                f,
                convert=convert and conv.enabled,
                max_bytes=conv.max_bytes,
                extra_text_suffixes=conv.extra_text_suffixes,
                enable_plugins=conv.enable_plugins,
                timeout_s=conv.timeout_s,
                max_output_bytes=conv.max_output_bytes,
            )
        except ConversionError as exc:
            console.print(f"[red]skip[/red] {f}: {exc}")
            failed += 1
            continue
        chunks = _chunk_text(result.text, chunk_chars)
        if not chunks:
            console.print(f"[yellow]+0[/yellow] {f}: produced no extractable text")
            failed += 1
            continue
        if result.method == "markitdown":
            converted += 1
        n_added = 0
        for i, chunk in enumerate(chunks):
            if (
                skip_duplicates
                and conn.execute(
                    "SELECT 1 FROM memories WHERE content = ? LIMIT 1", (chunk,)
                ).fetchone()
            ):
                skipped += 1
                continue
            store.add_memory(
                content=chunk,
                category=cat,
                source=src,
                metadata={
                    "source_file": str(f),
                    "chunk": i,
                    "chunks": len(chunks),
                    "converter": result.method,
                },
            )
            added += 1
            n_added += 1
        dup_note = " [dim](dups skipped)[/dim]" if n_added < len(chunks) else ""
        console.print(f"[green]+{n_added}[/green] {f}{dup_note}")
    console.print(
        f"[bold green]Ingested {added} memory-chunk(s)[/bold green] from "
        f"{len(files)} file(s) as [magenta]{cat.value}[/magenta]"
        + (f"; skipped {skipped} duplicate(s)" if skipped else "")
        + (f"; skipped {failed} file(s)" if failed else "")
        + (f" ({converted} via markitdown)" if converted else "")
        + "."
    )
    if dream:
        from mintmory.core.llm import build_dreaming_engine

        report = build_dreaming_engine(
            store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
        ).run_light()
        console.print(
            f"[dim]dream: +{report.new_links} links, +{report.new_summaries} summaries[/dim]"
        )


@app.command()
def doctor() -> None:
    """One-shot health check of the MintMory deployment (DB, embedder, LLM tier)."""
    from mintmory.core.config import load_settings

    settings = load_settings()
    table = Table(title="MintMory doctor")
    table.add_column("check", style="cyan")
    table.add_column("status")
    healthy = True

    db_path = os.environ.get("MINTMORY_DB", str(Path.home() / ".mintmory" / "memories.db"))
    try:
        store = _get_store()
        s = store.get_stats()
    except Exception as exc:  # noqa: BLE001 — doctor must report, not raise
        table.add_row("database", f"[red]FAIL[/red] {db_path}: {exc}")
        console.print(table)
        raise typer.Exit(code=1) from exc
    table.add_row(
        "database",
        f"[green]ok[/green] {db_path} "
        f"({s.total_memories} mem, {s.concept_links} links, {s.memory_summaries} summaries)",
    )

    emb = store.embedder
    table.add_row(
        "embedder",
        f"[green]{settings.embed.provider.value}[/green] (dim {emb.dimensions})"
        if emb is not None
        else "[yellow]none (FTS-only)[/yellow]",
    )
    table.add_row(
        "vector search",
        "[green]available[/green] (sqlite-vec)"
        if store._vector_search_available()
        else "[yellow]FTS-only[/yellow] (sqlite-vec not loaded)",
    )

    if settings.llm.enabled:
        from mintmory.core.llm import LLMClient

        reachable = LLMClient(settings.llm).ping()
        healthy = healthy and reachable
        verdict = "[green]reachable[/green]" if reachable else "[red]UNREACHABLE[/red]"
        table.add_row(
            "llm tier",
            f"{settings.llm.provider.value} {settings.llm.model} @ "
            f"{settings.llm.base_url} — {verdict}",
        )
    else:
        table.add_row("llm tier", "[yellow]disabled[/yellow] (provider=none; L3 + resolution off)")

    table.add_row(
        "linking",
        f"min_shared={settings.link.min_shared_entities} "
        f"max_per_node={settings.link.max_per_node} stoplist={len(settings.link.stoplist)}",
    )

    from mintmory.core.conversion import CONVERTIBLE_SUFFIXES, markitdown_available

    if markitdown_available():
        table.add_row(
            "conversion",
            f"[green]markitdown available[/green] "
            f"({len(CONVERTIBLE_SUFFIXES)} convertible formats)",
        )
    else:
        table.add_row(
            "conversion",
            "[yellow]not installed — `uv sync --extra docs` for PDF/DOCX/XLSX[/yellow]",
        )
    console.print(table)
    if not healthy:
        raise typer.Exit(code=2)


@app.command()
def index_tree(
    roots: list[str] = typer.Argument(..., help="Root folder(s) to index recursively"),
    collection: str = typer.Option(
        "default", help="Collection tag stamped on every memory + manifest row"
    ),
    include: str = typer.Option("*", help="Comma-separated include globs (filename or rel-path)"),
    exclude: str = typer.Option("", help="Comma-separated exclude globs, e.g. 'Personal/**,*.tmp'"),
    db: str | None = typer.Option(None, help="Target DB path (overrides MINTMORY_DB)"),
    text_content: bool = typer.Option(
        True,
        "--text-content/--no-text-content",
        help="Full-text small plain-text files (.txt/.md/.log/.rst) inline — cheap, no budget",
    ),
    text_max_kb: int = typer.Option(
        2048, help="Max size (KB) for inline text-content; larger text files stay metadata-only"
    ),
    content: bool = typer.Option(
        False,
        "--content/--no-content",
        help="Also download+markitdown-convert selected binary docs (pdf/docx/...) to full text",
    ),
    content_types: str = typer.Option(
        "pdf,docx,doc,xlsx,pptx,html,csv", help="Binary suffixes eligible for full-text extraction"
    ),
    max_download_mb: float = typer.Option(
        200.0, help="Download budget for the binary content pass (0 = unlimited)"
    ),
    chunk_chars: int = typer.Option(4000, help="Approx chars per content chunk"),
    prune: bool = typer.Option(
        False, "--prune/--no-prune", help="Archive memories for files that disappeared"
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-index every file even if unchanged (b: force everything)"
    ),
    dream: bool = typer.Option(
        False, "--dream/--no-dream", help="Run a light dream after indexing"
    ),
    limit: int = typer.Option(0, help="Stop after N files (0 = all; for smoke tests)"),
    vision: bool = typer.Option(
        False,
        "--vision/--no-vision",
        help=(
            "Describe image files: extract SVG text inline; queue raster images as "
            "agent jobs (provider=agent) or run the configured vision provider "
            "(llm/ocr, future). Records index_mode='vision'."
        ),
    ),
) -> None:
    """Recurrently index a directory tree.

    Writes one metadata + folder-context memory per file (stat-only for the walk),
    full-texts small plain-text files inline by default (cheap — .txt/.md/.log/.rst),
    and optionally downloads+converts heavy binary docs with ``--content`` (bounded
    by ``--max-download-mb``). Idempotent via a per-path manifest: re-runs skip
    unchanged files and replace changed ones. Designed for cloud-backed
    (online-only) libraries.

    Pass ``--vision`` to also handle image files: SVG text is extracted inline
    (pure-Python, no model); raster images (png/jpg/etc) are queued as agent jobs
    for provider=agent, or described inline for future llm/ocr providers. Records
    ``index_mode='vision'`` in the manifest. Without ``--vision`` this command is
    byte-for-byte unchanged.
    """
    import hashlib
    import json

    from mintmory.core.config import load_settings
    from mintmory.core.conversion import TEXT_SUFFIXES, ConversionError, extract_markdown
    from mintmory.core.tree_index import human_size, iter_dir_groups, render_file_record

    if db:
        os.environ["MINTMORY_DB"] = db
    inc = [g.strip() for g in include.split(",") if g.strip()] or ["*"]
    exc = [g.strip() for g in exclude.split(",") if g.strip()]
    ctypes = {f".{t.strip().lstrip('.').lower()}" for t in content_types.split(",") if t.strip()}
    budget = int(max_download_mb * 1024 * 1024) if max_download_mb > 0 else None
    text_max_bytes = text_max_kb * 1024 if text_max_kb > 0 else None

    settings = load_settings()
    conv = settings.convert
    store = _get_store()

    # Vision: lazily import + validate the provider once before the walk, so
    # a misconfigured llm/ocr provider fails fast with a clear message rather
    # than a stack trace mid-walk.  ``vision_mod`` is only ever referenced
    # inside the ``if vision:`` / ``elif want_vision:`` branches, so mypy can
    # see the import is guarded. We import it into a local name to satisfy
    # type checkers that the name is always defined when used.
    if vision:
        from mintmory.core import vision as vision_mod

        try:
            captioner = vision_mod.captioner_from_settings(settings.vision)
        except NotImplementedError as _nie:
            console.print(f"[red]error[/red]: {_nie}")
            raise typer.Exit(code=1) from _nie
    else:
        vision_mod = None  # type: ignore[assignment]  # never accessed when vision=False
        captioner = None

    scanned = added = updated = unchanged = converted = failed = pruned = 0
    downloaded = 0
    budget_hit = False
    # Vision-specific counters (only relevant when --vision)
    svg_described = 0
    images_queued = 0
    images_described = 0
    vision_skipped = 0
    seen: set[str] = set()
    # Size cap for raster images (used when captioner is not None).
    max_image_bytes: int | None = settings.vision.max_image_bytes if vision else None

    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            raise typer.BadParameter(f"not a directory: {root}")
        root_label = root_path.name
        for group in iter_dir_groups(root_path, include=inc, exclude=exc):
            for entry in group.entries:
                if limit and scanned >= limit:
                    break
                scanned += 1
                path_str = str(entry.path)
                seen.add(path_str)
                # Plain-text files are cheap to read -> full-text them inline by
                # default (no markitdown, no download budget). Heavy binary docs
                # need --content and consume the download budget.
                text_eligible = (
                    text_content
                    and entry.suffix in TEXT_SUFFIXES
                    and (text_max_bytes is None or entry.size <= text_max_bytes)
                )
                want_binary = content and entry.suffix in ctypes and not budget_hit
                do_content = text_eligible or want_binary

                # Vision: third content mode — separate from text/binary.
                # Proprietary formats (xd/vsdx/dwg/psd/eps) are skip-and-flagged.
                # ``vision_mod`` is not None when vision=True (guard above).
                want_vision = (
                    vision
                    and vision_mod is not None
                    and entry.suffix in vision_mod.IMAGE_SUFFIXES
                    and entry.suffix not in vision_mod.PROPRIETARY_IMAGE_SUFFIXES
                )

                if (
                    vision
                    and vision_mod is not None
                    and entry.suffix in vision_mod.PROPRIETARY_IMAGE_SUFFIXES
                ):
                    vision_skipped += 1

                # desired_mode: 'content' wins over 'vision' (an image that is
                # also full-text converted keeps 'content'); 'vision' beats
                # 'metadata' for image suffixes handled by --vision.
                if do_content:
                    desired_mode = "content"
                elif want_vision:
                    desired_mode = "vision"
                else:
                    desired_mode = "metadata"

                existing = store.manifest_get(path_str)
                if existing is not None and not force:
                    same = (
                        existing["size"] == entry.size
                        and abs(existing["mtime"] - entry.mtime) < 1e-6
                    )
                    # 'content' and 'vision' are both richer than 'metadata';
                    # 'content' > 'vision' (if already content, don't downgrade).
                    existing_mode = existing["index_mode"]
                    covered = existing_mode in ("content", "vision") or desired_mode == "metadata"
                    if same and covered:
                        unchanged += 1
                        continue

                new_ids: list[str] = []
                file_record = store.add_memory(
                    content=render_file_record(entry, group, root_label),
                    category="context",
                    source="document",
                    metadata={
                        "collection": collection,
                        "path": path_str,
                        "rel": entry.rel,
                        "ext": entry.suffix,
                        "size": entry.size,
                        "mtime": entry.mtime,
                        "online_only": entry.online_only,
                        "folder": str(Path(entry.rel).parent),
                        "index_mode": "metadata",
                    },
                )
                new_ids.append(file_record.id)
                mode = "metadata"
                content_hash: str | None = None

                if do_content:
                    try:
                        result = extract_markdown(
                            entry.path,
                            convert=True,
                            max_bytes=conv.max_bytes,
                            timeout_s=conv.timeout_s,
                            max_output_bytes=conv.max_output_bytes,
                            enable_plugins=conv.enable_plugins,
                        )
                        if want_binary:
                            downloaded += entry.size  # only heavy docs count toward the budget
                        for i, chunk in enumerate(_chunk_text(result.text, chunk_chars)):
                            crec = store.add_memory(
                                content=chunk,
                                category="fact",
                                source="document",
                                metadata={
                                    "collection": collection,
                                    "source_file": path_str,
                                    "rel": entry.rel,
                                    "chunk": i,
                                    "converter": result.method,
                                },
                            )
                            new_ids.append(crec.id)
                        if len(new_ids) > 1:
                            mode = "content"
                            content_hash = hashlib.blake2b(
                                result.text.encode("utf-8"), digest_size=16
                            ).hexdigest()
                            converted += 1
                        if want_binary and budget is not None and downloaded >= budget:
                            budget_hit = True
                    except ConversionError as exc:
                        console.print(f"[yellow]content skip[/yellow] {entry.name}: {exc}")
                        failed += 1
                elif want_vision:
                    # Vision branch: SVG → inline extraction; raster → queue for agent.
                    # ``want_vision`` is True only when vision_mod is not None (see above).
                    assert vision_mod is not None  # noqa: S101
                    mode = "vision"
                    if entry.suffix in vision_mod.SVG_SUFFIXES:
                        # SVG: read bytes (counts against download budget for online-only),
                        # extract embedded text via pure stdlib, store description inline.
                        try:
                            svg_bytes: bytes = b""
                            if entry.online_only:
                                if budget is not None and downloaded >= budget:
                                    # budget exhausted; skip this SVG's byte read
                                    mode = "metadata"
                                    console.print(
                                        f"[yellow]vision skip[/yellow] {entry.name}: "
                                        "download budget exhausted"
                                    )
                                    failed += 1
                                else:
                                    svg_bytes = entry.path.read_bytes()
                                    downloaded += len(svg_bytes)
                                    if budget is not None and downloaded >= budget:
                                        budget_hit = True
                            else:
                                svg_bytes = entry.path.read_bytes()
                            if mode == "vision":
                                svg_text = vision_mod.extract_svg_text(svg_bytes)
                                if svg_text:
                                    desc = vision_mod.image_caption_put(
                                        store, file_record.id, svg_text, settings=settings.vision
                                    )
                                    new_ids.append(desc.record.id)
                                    content_hash = hashlib.blake2b(
                                        svg_text.encode("utf-8"), digest_size=16
                                    ).hexdigest()
                                    svg_described += 1
                                # Empty SVG text: mode stays 'vision' (manifest marks it
                                # as vision-attempted so a re-run doesn't re-attempt unless
                                # the file changes). No description created.
                        except OSError as exc:
                            console.print(
                                f"[yellow]vision skip[/yellow] {entry.name}: read error {exc}"
                            )
                            mode = "metadata"
                            failed += 1
                    else:
                        # Raster image: queue for agent OR caption inline.
                        # captioner is None  →  provider=agent (UNCHANGED MM-18 behaviour):
                        #     count the job and move on; the agent loop will describe it later.
                        # captioner is not None  →  provider=llm (or future):
                        #     caption inline under the SAME budget + manifest.
                        assert vision_mod is not None  # noqa: S101 — want_vision guard
                        if captioner is None:
                            images_queued += 1
                            # mode already 'vision'; no bytes read, no description yet.
                        else:
                            # Inline captioning under the shared download budget.
                            try:
                                if max_image_bytes is not None and entry.size > max_image_bytes:
                                    # Oversized: skip this image.
                                    vision_skipped += 1
                                elif (
                                    entry.online_only
                                    and budget is not None
                                    and downloaded >= budget
                                ):
                                    # Budget exhausted for online-only images.
                                    vision_skipped += 1
                                else:
                                    raw = entry.path.read_bytes()
                                    if entry.online_only:
                                        downloaded += len(raw)
                                        if budget is not None and downloaded >= budget:
                                            budget_hit = True
                                    desc = captioner.describe(
                                        vision_mod.ImageInput(
                                            file_id=file_record.id,
                                            path=path_str,
                                            mime=vision_mod._mime_for(entry.suffix),
                                            data=raw,
                                        )
                                    )
                                    put = vision_mod.image_caption_put(
                                        store,
                                        file_record.id,
                                        desc.record.content,
                                        settings=settings.vision,
                                    )
                                    new_ids.append(put.record.id)
                                    content_hash = hashlib.blake2b(
                                        desc.record.content.encode("utf-8"), digest_size=16
                                    ).hexdigest()
                                    images_described += 1
                            except vision_mod.VisionError as exc:
                                console.print(f"[yellow]vision skip[/yellow] {entry.name}: {exc}")
                                vision_skipped += 1
                            except OSError as exc:
                                console.print(
                                    f"[yellow]vision skip[/yellow] {entry.name}: read error {exc}"
                                )
                                vision_skipped += 1
                        # mode stays 'vision' in all cases (manifest records the attempt).

                if existing is not None:
                    for old_id in json.loads(existing["memory_ids"]):
                        store.archive_memory(old_id)
                    updated += 1
                else:
                    added += 1
                store.manifest_upsert(
                    path_str,
                    collection,
                    size=entry.size,
                    mtime=entry.mtime,
                    online_only=entry.online_only,
                    index_mode=mode,
                    memory_ids=new_ids,
                    content_hash=content_hash,
                )
            if limit and scanned >= limit:
                break
        if limit and scanned >= limit:
            break

    if prune:
        for gone in store.manifest_paths(collection) - seen:
            row = store.manifest_get(gone)
            if row is not None:
                for old_id in json.loads(row["memory_ids"]):
                    store.archive_memory(old_id)
                store.manifest_delete(gone)
                pruned += 1

    table = Table(title=f"index-tree [{collection}]")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right")
    base_rows: list[tuple[str, str]] = [
        ("scanned", str(scanned)),
        ("new", str(added)),
        ("updated", str(updated)),
        ("unchanged", str(unchanged)),
        ("full-text", str(converted)),
        ("content-failed", str(failed)),
        ("pruned", str(pruned)),
        ("downloaded", human_size(downloaded)),
    ]
    for label, value in base_rows:
        table.add_row(label, value)
    if vision:
        table.add_row("svg-described", str(svg_described))
        if captioner is not None:
            table.add_row("images-described", str(images_described))
        else:
            table.add_row("images-queued", str(images_queued))
        if vision_skipped:
            table.add_row("vision-skipped", str(vision_skipped))
    if budget_hit:
        table.add_row("budget", "[yellow]reached — remaining files metadata-only[/yellow]")
    console.print(table)

    if dream:
        from mintmory.core.llm import build_dreaming_engine

        report = build_dreaming_engine(
            store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
        ).run_light()
        console.print(
            f"[dim]dream: +{report.new_links} links, +{report.new_summaries} summaries[/dim]"
        )


@app.command()
def note(
    content: str = typer.Argument(..., help="The thing to remember"),
    about: str | None = typer.Option(None, help="What this note is about (anchor)"),
    when: str | None = typer.Option(None, help="ISO date this note is salient (e.g. 2026-07-01)"),
    until: str | None = typer.Option(None, help="ISO deadline"),
    category: str | None = typer.Option(None, help="Override category (default temporal/episodic)"),
) -> None:
    """Capture a user-authored note ('remember this about X')."""
    from mintmory.core import notes as notes_mod

    when_dt = _parse_iso(when)
    until_dt = _parse_iso(until)
    cat = _parse_category(category) if category is not None else None
    store = _get_store()
    result = notes_mod.create_note(
        store,
        content=content,
        about=about,
        when=when_dt,
        until=until_dt,
        category=cat,
    )
    console.print(f"[green]Added note[/green] [bold]{result.note.id}[/bold]")
    if result.anchor_kind == "memory":
        console.print(f"  [dim]-> annotates [cyan]{result.anchor_memory_id}[/cyan][/dim]")
    elif result.anchor_kind == "topic":
        entities_str = ", ".join(result.anchor_entities) if result.anchor_entities else "(none)"
        console.print(f"  [dim]-> topic: {entities_str}[/dim]")


@app.command()
def notes(
    about: str | None = typer.Option(None, help="Filter by subject/entity"),
    upcoming: bool = typer.Option(False, "--upcoming", help="Future-dated notes, soonest first"),
    overdue: bool = typer.Option(False, "--overdue", help="Past-due notes (valid_from < now)"),
    limit: int = typer.Option(50, help="Max notes"),
) -> None:
    """List user-authored notes. Use --upcoming / --overdue for time views."""
    from mintmory.core import notes as notes_mod

    store = _get_store()
    try:
        records = notes_mod.notes_list(
            store,
            about=about,
            upcoming=upcoming,
            overdue=overdue,
            limit=limit,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    table = Table(title="Notes")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("category", style="magenta")
    table.add_column("valid_from", style="yellow")
    table.add_column("content")
    for mem in records:
        valid_from_str = mem.valid_from.isoformat() if mem.valid_from is not None else ""
        table.add_row(mem.id, mem.category.value, valid_from_str, mem.content)
    console.print(table)
    console.print(f"[dim]{len(records)} note(s)[/dim]")


@app.command()
def summary_jobs(
    include_all: bool = typer.Option(
        False, "--all/--needed", help="All qualifying concepts vs only those needing a (re)summary"
    ),
    limit: int = typer.Option(0, help="Max jobs (0 = no cap)"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
) -> None:
    """List L3 concept-summary jobs for the agent to write (agent-supplied L3)."""
    from mintmory.core.config import load_settings
    from mintmory.core.llm import build_dreaming_engine

    settings = load_settings()
    store = _get_store()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]

    if json_out:
        import json as _json

        console.print_json(_json.dumps([j.model_dump(mode="json") for j in jobs]))
        return

    table = Table(title="Summary jobs")
    table.add_column("concept", style="cyan", no_wrap=True)
    table.add_column("memories", justify="right", style="green")
    table.add_column("has_summary", style="magenta")
    for j in jobs:
        table.add_row(j.concept, str(j.memory_count), "yes" if j.current_summary else "no")
    console.print(table)
    console.print(f"[dim]{len(jobs)} job(s)[/dim]")


@app.command()
def summary_put(
    concept: str = typer.Argument(..., help="Concept/entity name"),
    text: str | None = typer.Argument(None, help="Summary text (omit to read --file or stdin)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="Read summary text from a file"),
) -> None:
    """Store an agent-supplied summary for a concept (text arg, --file, or stdin)."""
    import sys

    from mintmory.core.config import load_settings
    from mintmory.core.llm import build_dreaming_engine

    if text is not None:
        summary_text = text
    elif file is not None:
        summary_text = file.read_text()
    else:
        summary_text = sys.stdin.read()
    summary_text = summary_text.strip()
    if not summary_text:
        raise typer.BadParameter("empty summary text (provide TEXT, --file, or stdin)")

    settings = load_settings()
    store = _get_store()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    summary = engine.apply_summary(concept, summary_text)
    console.print(
        f"[green]Stored summary[/green] for [cyan]{summary.concept}[/cyan] "
        f"[dim]({summary.memory_count} memories)[/dim]"
    )


@app.command()
def image_jobs(
    include_all: bool = typer.Option(
        False,
        "--all/--needed",
        help="All raster images vs only those needing a description",
    ),
    include_bytes: bool = typer.Option(
        False,
        "--bytes/--no-bytes",
        help="Force-embed base64 for local files too (use when agent runs on a different host)",
    ),
    limit: int = typer.Option(0, help="Max jobs (0 = no cap)"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a rich table"),
) -> None:
    """List image-description jobs for the agent (agent-supplied vision).

    Returns raster image file-records from the index that need an agent-supplied
    description (or all raster images with ``--all``). Each job carries the
    image path, rel, mime, size, online_only flag, and optionally an inline
    base64 payload (``--bytes`` or when the image is online-only). SVG and
    proprietary image formats are never returned as agent jobs.

    After describing an image, store the result with ``image-caption-put``.
    """
    import json as _json

    from mintmory.core import vision as vision_mod
    from mintmory.core.config import load_settings

    settings = load_settings()
    store = _get_store()
    jobs = vision_mod.image_jobs(
        store,
        include_all=include_all,
        include_bytes=include_bytes,
        limit=limit,
        settings=settings.vision,
    )

    if json_out:
        console.print_json(_json.dumps([j.model_dump(mode="json") for j in jobs]))
        return

    table = Table(title="Image jobs")
    table.add_column("file_id", style="cyan", no_wrap=True)
    table.add_column("rel", style="white")
    table.add_column("mime", style="magenta")
    table.add_column("online_only", style="yellow")
    table.add_column("has_desc", style="green")
    table.add_column("bytes", style="blue")
    for j in jobs:
        table.add_row(
            j.file_id,
            j.rel,
            j.mime,
            "yes" if j.online_only else "no",
            "yes" if j.current_description else "no",
            "yes" if j.image_b64 else ("oversized" if j.oversized else "no"),
        )
    console.print(table)
    console.print(f"[dim]{len(jobs)} image job(s)[/dim]")


@app.command()
def image_caption_put(
    file_id_or_path: str = typer.Argument(..., help="Image file-record id or path"),
    text: str | None = typer.Argument(None, help="Description (omit to read from --file or stdin)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="Read description from a file"),
) -> None:
    """Store an agent-supplied image description (text arg, --file, or stdin).

    Persists the description as a context memory ANNOTATES-linked to the image
    file-record. Idempotent: re-putting replaces the prior description, and the
    image then drops out of the default ``image-jobs`` work-list. No vision
    backend is required.

    ``FILE_OR_ID`` may be the ``file_id`` from ``image-jobs`` (preferred) or
    the image's absolute path. Description text may be given inline, read from
    ``--file``, or piped via stdin.
    """
    import sys

    from mintmory.core import vision as vision_mod
    from mintmory.core.config import load_settings

    if text is not None:
        description = text
    elif file is not None:
        description = file.read_text()
    else:
        description = sys.stdin.read()

    description = description.strip()
    if not description:
        raise typer.BadParameter(
            "empty description (provide TEXT argument, --file, or pipe via stdin)"
        )

    settings = load_settings()
    store = _get_store()
    try:
        result = vision_mod.image_caption_put(
            store, file_id_or_path, description, settings=settings.vision
        )
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(
        f"[green]Stored description[/green] [bold]{result.record.id}[/bold] "
        f"for [cyan]{result.source_image}[/cyan]"
    )
    if result.replaced_description_id is not None:
        console.print(
            f"  [dim]-> replaced (archived) [yellow]{result.replaced_description_id}[/yellow][/dim]"
        )


@app.command()
def vision_run(
    limit: int = typer.Option(0, help="Max images to caption (0 = no cap)"),
    budget_mb: float = typer.Option(
        0.0, "--budget", help="Download budget MB for online-only images (0 = settings default)"
    ),
    include_all: bool = typer.Option(
        False, "--all/--needed", help="Re-caption all raster images vs only pending"
    ),
) -> None:
    """Caption already-indexed pending images with the configured vision provider.

    Requires MINTMORY_VISION_PROVIDER=llm (a reachable OpenAI-compatible vision
    model). With provider=agent this is a no-op (use the image-jobs/image-caption-put
    agent loop instead). Does NOT re-walk the tree — it processes the pending
    image_jobs in place. Per-image failures are skipped and counted; one bad image
    never aborts the run.
    """
    from mintmory.core import vision as vision_mod
    from mintmory.core.config import load_settings

    settings = load_settings()
    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)
    except NotImplementedError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc

    if captioner is None:
        console.print(
            "[dim]provider=agent: nothing to run (use image-jobs/image-caption-put)[/dim]"
        )
        return

    store = _get_store()
    budget: int | None = int(budget_mb * 1024 * 1024) if budget_mb > 0 else None
    report = vision_mod.caption_pending_images(
        store,
        captioner=captioner,
        limit=limit,
        budget=budget,
        include_all=include_all,
        settings=settings.vision,
    )

    table = Table(title="vision-run")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right", style="green")
    table.add_row("described", str(report.described))
    table.add_row("skipped", str(report.skipped))
    table.add_row("failed", str(report.failed))
    table.add_row("budget_hit", "yes" if report.budget_hit else "no")
    console.print(table)

    if report.items:
        items_table = Table(title="items", show_header=True)
        items_table.add_column("file_id", style="cyan", no_wrap=True)
        items_table.add_column("rel")
        items_table.add_column("status", style="magenta")
        items_table.add_column("note", style="dim")
        for item in report.items:
            items_table.add_row(item.file_id, item.rel, item.status, item.note)
        console.print(items_table)


@app.command()
def mcp_serve(
    transport: str = typer.Option("stdio", help="stdio or sse"),
    port: int = typer.Option(8081, help="Port for SSE transport"),
) -> None:
    """Start the MCP server."""
    os.environ.setdefault("MINTMORY_TRANSPORT", transport)
    from mintmory.mcp.server import main as mcp_main

    mcp_main()


# ---------------------------------------------------------------------------
# mintmory history — agent-history sub-commands
# ---------------------------------------------------------------------------

history_app = typer.Typer(name="history", help="Agent-history index commands")
app.add_typer(history_app)


def _get_history_store(db_path: str) -> StorageAdapter:
    """Open the dedicated history DB (not the working store)."""
    from mintmory.core.history.ingest import _assert_not_working_db
    from mintmory.core.storage import StorageAdapter

    _assert_not_working_db(db_path)
    expanded = os.path.expanduser(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(expanded)), exist_ok=True)
    store = StorageAdapter(expanded)
    store.initialise()
    return store


def _parse_since(since: str) -> datetime:
    """Parse --since like '75d', '8w', '3m' into an absolute UTC datetime."""
    import re

    m = re.fullmatch(r"(\d+)([dwm])", since.strip())
    if not m:
        raise typer.BadParameter(f"invalid --since {since!r}; expected e.g. '60d', '8w', '3m'")
    n = int(m.group(1))
    unit = m.group(2)

    now = datetime.now(UTC).replace(tzinfo=None)
    if unit == "d":
        from datetime import timedelta

        return now - timedelta(days=n)
    elif unit == "w":
        from datetime import timedelta

        return now - timedelta(weeks=n)
    else:  # 'm'
        # Approximate: 1 month ~ 30 days
        from datetime import timedelta

        return now - timedelta(days=n * 30)


@history_app.command("backfill")
def history_backfill(
    source: list[str] = typer.Option(
        [], "--source", help="Adapter(s) to run: claude_code, codex, kiro (repeatable)"
    ),
    db: str = typer.Option("", "--db", help="History DB path (default: agent-history.db)"),
    limit: int = typer.Option(0, "--limit", help="Cap sessions per source (0 = unlimited)"),
    max_llm_calls: int = typer.Option(
        0, "--max-llm-calls", help="Max LLM distiller calls (0=unlimited)"
    ),
    llm_only_since: str | None = typer.Option(
        None, "--llm-only-since", help="Only use LLM for sessions on/after DATE (ISO)"
    ),
    allow_cloud_llm: bool = typer.Option(
        False,
        "--allow-cloud-llm/--no-allow-cloud-llm",
        help="Allow non-localhost LLM endpoint for distillation",
    ),
) -> None:
    """Backfill all sessions from agent adapters into the history DB."""
    from mintmory.core.config import load_settings
    from mintmory.core.history.ingest import (
        DEFAULT_HISTORY_DB,
        HermesGuardError,
        LLMBudget,
        backfill,
    )
    from mintmory.core.llm import build_history_distiller

    db_path = db if db else DEFAULT_HISTORY_DB
    settings = load_settings()

    seg_settings = (
        settings.seg.model_copy(update={"allow_cloud_llm": True})
        if allow_cloud_llm
        else settings.seg
    )

    distiller = build_history_distiller(settings.llm, seg_settings)
    budget = LLMBudget(max_calls=max_llm_calls) if max_llm_calls > 0 else None

    llm_since_dt: datetime | None = None
    if llm_only_since:
        try:
            llm_since_dt = datetime.fromisoformat(llm_only_since)
        except ValueError as exc:
            raise typer.BadParameter(
                f"invalid --llm-only-since {llm_only_since!r}; expected ISO date"
            ) from exc

    try:
        report = backfill(
            db_path=db_path,
            sources=list(source) if source else None,
            limit=limit,
            seg_settings=seg_settings,
            distiller=distiller,
            budget=budget,
            llm_only_since=llm_since_dt,
            max_concurrency=settings.llm.max_concurrency,
        )
    except HermesGuardError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="history backfill")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right", style="green")
    table.add_row("scanned", str(report.scanned))
    table.add_row("written", str(report.written))
    table.add_row("updated", str(report.updated))
    table.add_row("skipped", str(report.skipped))
    table.add_row("segments_written", str(report.segments_written))
    table.add_row("llm_calls", str(report.llm_calls))
    table.add_row("llm_cache_hits", str(report.llm_cache_hits))
    table.add_row("llm_fallbacks", str(report.llm_fallbacks))
    for src_name, count in report.by_source.items():
        table.add_row(f"  {src_name}", str(count))
    console.print(table)


@history_app.command("sync")
def history_sync(
    source: list[str] = typer.Option(
        [], "--source", help="Adapter(s): claude_code, codex, kiro (repeatable)"
    ),
    db: str = typer.Option("", "--db", help="History DB path"),
    max_llm_calls: int = typer.Option(
        0, "--max-llm-calls", help="Max LLM distiller calls (0=unlimited)"
    ),
    llm_only_since: str | None = typer.Option(
        None, "--llm-only-since", help="Only use LLM for sessions on/after DATE (ISO)"
    ),
    allow_cloud_llm: bool = typer.Option(
        False,
        "--allow-cloud-llm/--no-allow-cloud-llm",
        help="Allow non-localhost LLM endpoint for distillation",
    ),
) -> None:
    """Sync new/changed sessions only (skip unchanged files per manifest)."""
    from mintmory.core.config import load_settings
    from mintmory.core.history.ingest import (
        DEFAULT_HISTORY_DB,
        HermesGuardError,
        LLMBudget,
        sync,
    )
    from mintmory.core.llm import build_history_distiller

    db_path = db if db else DEFAULT_HISTORY_DB
    settings = load_settings()

    seg_settings = (
        settings.seg.model_copy(update={"allow_cloud_llm": True})
        if allow_cloud_llm
        else settings.seg
    )

    distiller = build_history_distiller(settings.llm, seg_settings)
    budget = LLMBudget(max_calls=max_llm_calls) if max_llm_calls > 0 else None

    llm_since_dt: datetime | None = None
    if llm_only_since:
        try:
            llm_since_dt = datetime.fromisoformat(llm_only_since)
        except ValueError as exc:
            raise typer.BadParameter(
                f"invalid --llm-only-since {llm_only_since!r}; expected ISO date"
            ) from exc

    try:
        report = sync(
            db_path=db_path,
            sources=list(source) if source else None,
            seg_settings=seg_settings,
            distiller=distiller,
            budget=budget,
            llm_only_since=llm_since_dt,
            max_concurrency=settings.llm.max_concurrency,
        )
    except HermesGuardError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="history sync")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right", style="green")
    table.add_row("scanned", str(report.scanned))
    table.add_row("written", str(report.written))
    table.add_row("skipped", str(report.skipped))
    table.add_row("segments_written", str(report.segments_written))
    table.add_row("llm_calls", str(report.llm_calls))
    table.add_row("llm_cache_hits", str(report.llm_cache_hits))
    table.add_row("llm_fallbacks", str(report.llm_fallbacks))
    for src_name, count in report.by_source.items():
        table.add_row(f"  {src_name}", str(count))
    console.print(table)


@history_app.command("timeline")
def history_timeline(
    since: str | None = typer.Option(
        None, "--since", help="Window like '75d', '8w', '3m' (mutual excl. with --from/--to)"
    ),
    from_date: str | None = typer.Option(None, "--from", help="ISO start date/datetime"),
    to_date: str | None = typer.Option(None, "--to", help="ISO end date/datetime"),
    repo: str | None = typer.Option(None, "--repo", help="Filter by repo name"),
    kind: str | None = typer.Option(None, "--kind", help="Filter by kind (fix/feature/...)"),
    limit: int = typer.Option(50, "--limit", help="Max rows"),
    db: str = typer.Option("", "--db", help="History DB path"),
    group_by_session: bool = typer.Option(
        False,
        "--group-by-session/--no-group-by-session",
        help="Group multi-segment sessions together",
    ),
) -> None:
    """Print a dated changelog of sessions within the time window."""
    from mintmory.core.history.ingest import DEFAULT_HISTORY_DB, HermesGuardError
    from mintmory.core.history.query import timeline as _timeline

    db_path = db if db else DEFAULT_HISTORY_DB
    try:
        rows = _timeline(
            db_path,
            since=since,
            from_iso=from_date,
            to_iso=to_date,
            repo=repo,
            kind=kind,
            limit=limit,
            group_by_session=group_by_session,
        )
    except HermesGuardError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    table = Table(title="history timeline")
    table.add_column("date", style="yellow", no_wrap=True)
    table.add_column("repo", style="cyan")
    table.add_column("kind", style="magenta")
    table.add_column("title")
    table.add_column("summary")
    for row in rows:
        seg_count = row.get("segment_count", 1)
        seg_idx = row.get("segment_index", 0)
        marker = f"[{seg_idx + 1}/{seg_count}] " if seg_count > 1 else ""
        title_cell = f"{marker}{row.get('title', '')}"
        table.add_row(
            row["date"],
            row["repo"],
            row["kind"],
            title_cell,
            row["summary"][:100],
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} segment(s)[/dim]")


@history_app.command("search")
def history_search(
    query: str = typer.Argument(..., help="Search query"),
    repo: str | None = typer.Option(None, "--repo", help="Filter by repo name"),
    since: str | None = typer.Option(None, "--since", help="Only sessions within window"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
    db: str = typer.Option("", "--db", help="History DB path"),
) -> None:
    """Hybrid search over session summaries in the history DB."""
    from mintmory.core.history.ingest import DEFAULT_HISTORY_DB, HermesGuardError
    from mintmory.core.history.query import search as _search

    db_path = db if db else DEFAULT_HISTORY_DB
    try:
        results = _search(db_path, query, repo=repo, since=since, limit=limit)
    except HermesGuardError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    table = Table(title=f"history search: {query!r}")
    table.add_column("date", style="yellow", no_wrap=True)
    table.add_column("repo", style="cyan")
    table.add_column("kind", style="magenta")
    table.add_column("summary")
    for row in results:
        table.add_row(
            row["date"],
            row["repo"],
            row["kind"],
            row["summary"][:120],
        )
    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/dim]")


@history_app.command("scrub")
def history_scrub(
    db: str = typer.Option("", "--db", help="History DB path"),
) -> None:
    """Scan stored summaries for residual secrets; exit non-zero if any found."""

    from mintmory.core.history.ingest import DEFAULT_HISTORY_DB, HermesGuardError
    from mintmory.core.history.redact import scan

    db_path = db if db else DEFAULT_HISTORY_DB
    try:
        store = _get_history_store(db_path)
    except HermesGuardError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc

    conn = store.connect()
    rows = conn.execute(
        "SELECT id, content FROM memories "
        "WHERE json_extract(metadata, '$.record_type') = 'session_summary' "
        "  AND is_archived = 0"
    ).fetchall()

    total_hits: dict[str, int] = {}
    flagged = 0
    for row in rows:
        hits = scan(row["content"] or "")
        if hits:
            flagged += 1
            for label, count in hits.items():
                total_hits[label] = total_hits.get(label, 0) + count

    # (summary_text/title live in `content`, already scanned above — the envelope
    # metadata carries no free-text secret-bearing fields, so no second pass.)

    table = Table(title="history scrub")
    table.add_column("pattern", style="cyan")
    table.add_column("occurrences", justify="right", style="red")
    for label, count in total_hits.items():
        table.add_row(label, str(count))
    console.print(table)

    if total_hits:
        console.print(
            f"[red]FAIL[/red] {flagged} record(s) contain residual secrets "
            f"({sum(total_hits.values())} total hit(s))"
        )
        raise typer.Exit(code=1)
    else:
        console.print("[green]ok[/green] no residual secrets found")


if __name__ == "__main__":
    app()
