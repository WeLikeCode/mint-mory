"""CLI root spans and indexing/conversion phase spans (tasks 4.1).

Spec: observability › CLI commands are traced end to end, and observability › Indexing and
conversion phases are traced.

Every CLI command (``add``, ``search``, ``ingest``, ``index-tree``, ``dream``,
``history sync``) runs inside a root span ``mintmory.cli.<command>`` (spaces become dots),
marked with ``mark_error`` only when it exits non-zero. ``index-tree`` reports its file
counters on that root span and hangs ``mintmory.index_tree.scan`` / ``.prune`` / ``.cochange``
under it, with ``mintmory.convert`` per binary conversion and ``mintmory.vision.caption``
around each inline raster caption. The tests initialise telemetry with an in-memory exporter
themselves, so the CLI callback's own init is a no-op.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from mintmory.core import telemetry
from typer.testing import CliRunner

pytest.importorskip("opentelemetry.sdk")

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file and widen the console."""
    db_path = tmp_path / "telemetry_cli.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _init_spans(exporter: Any) -> None:
    assert telemetry.init_telemetry(span_exporter=exporter) is True


def _spans_named(exporter: Any, name: str) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _named(exporter: Any, name: str) -> Any:
    """The single exported span called ``name``; fails by assertion otherwise."""
    spans = _spans_named(exporter, name)
    assert len(spans) == 1, (
        f"expected one {name} span, got {sorted(s.name for s in exporter.get_finished_spans())}"
    )
    return spans[0]


def _attributes(span: Any) -> dict[str, Any]:
    return dict(span.attributes or {})


def _write_tree(root: Path, names: tuple[str, ...]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_text(f"content for {name}\n")
    return root


def _ancestor_span_ids(span: Any, by_id: dict[int, Any]) -> set[int]:
    """The span ids of ``span``'s ancestors, walking the parent chain."""
    ids: set[int] = set()
    parent = span.parent
    while parent is not None:
        ids.add(parent.span_id)
        parent_span = by_id.get(parent.span_id)
        parent = parent_span.parent if parent_span is not None else None
    return ids


# ---------------------------------------------------------------------------
# CLI commands are traced end to end
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e9540797")
def test_index_search_and_dream_have_root_spans_and_counts(cli_db: Path, tmp_path: Path) -> None:
    """``index-tree``, ``search`` and ``dream`` export non-ERROR root spans; counts land."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = _write_tree(tmp_path / "corpus", ("a.txt", "b.txt"))

    index = runner.invoke(app, ["index-tree", str(folder)])
    assert index.exit_code == 0, index.output
    search = runner.invoke(app, ["search", "hello"])
    assert search.exit_code == 0, search.output
    dream = runner.invoke(app, ["dream"])
    assert dream.exit_code == 0, dream.output

    index_span = _named(exporter, "mintmory.cli.index-tree")
    search_span = _named(exporter, "mintmory.cli.search")
    dream_span = _named(exporter, "mintmory.cli.dream")
    for span in (index_span, search_span, dream_span):
        assert span.status.status_code != StatusCode.ERROR

    attributes = _attributes(index_span)
    assert attributes.get("mintmory.files.scanned") == 2
    assert attributes.get("mintmory.files.added") == 2


@pytest.mark.l4("C-e9540797")
def test_index_tree_counter_attributes_track_updated_and_unchanged(
    cli_db: Path, tmp_path: Path
) -> None:
    """The ``mintmory.files.*`` counters move from 0/0/0 to 1 updated / 1 unchanged."""
    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = _write_tree(tmp_path / "reindex", ("a.txt", "b.txt"))

    first = runner.invoke(app, ["index-tree", str(folder)])
    assert first.exit_code == 0, first.output
    (folder / "a.txt").write_text("changed content for a.txt\n")
    second = runner.invoke(app, ["index-tree", str(folder)])
    assert second.exit_code == 0, second.output

    spans = _spans_named(exporter, "mintmory.cli.index-tree")
    assert len(spans) == 2, sorted(s.name for s in exporter.get_finished_spans())
    by_start = sorted(spans, key=lambda s: s.start_time)
    first_run, second_run = _attributes(by_start[0]), _attributes(by_start[1])
    assert first_run.get("mintmory.files.scanned") == 2
    assert first_run.get("mintmory.files.added") == 2
    assert first_run.get("mintmory.files.updated") == 0
    assert first_run.get("mintmory.files.unchanged") == 0
    assert first_run.get("mintmory.files.failed") == 0
    assert second_run.get("mintmory.files.scanned") == 2
    assert second_run.get("mintmory.files.updated") == 1
    assert second_run.get("mintmory.files.unchanged") == 1
    assert second_run.get("mintmory.files.failed") == 0


@pytest.mark.l4("C-e9540797")
def test_add_root_span_contains_the_add_memory_span(cli_db: Path) -> None:
    """``mintmory add`` exports ``mintmory.cli.add`` with ``mintmory.add_memory`` below it."""
    exporter = _in_memory_span_exporter()
    _init_spans(exporter)

    result = runner.invoke(app, ["add", "hello from the CLI"])
    assert result.exit_code == 0, result.output

    root = _named(exporter, "mintmory.cli.add")
    child = _named(exporter, "mintmory.add_memory")
    assert child.parent is not None
    assert child.parent.span_id == root.context.span_id


@pytest.mark.l4("C-e9540797")
def test_history_sync_exports_its_root_span(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``mintmory history sync`` over an empty source exports its root span."""
    import mintmory.core.history.ingest as ingest_mod
    from opentelemetry.trace import StatusCode

    def _empty_iterator() -> Iterator[tuple[Any, list[Any]]]:
        return iter([])

    def _empty_adapter(_source: str) -> Callable[[], Iterator[tuple[Any, list[Any]]]]:
        return _empty_iterator

    monkeypatch.setattr(ingest_mod, "_load_adapter", _empty_adapter)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    history_db = tmp_path / "history.db"
    result = runner.invoke(
        app, ["history", "sync", "--db", str(history_db), "--source", "claude_code"]
    )
    assert result.exit_code == 0, result.output

    root = _named(exporter, "mintmory.cli.history.sync")
    assert root.status.status_code != StatusCode.ERROR


@pytest.mark.l4("C-ebe047e9", "C-64a88ce0")
def test_failing_ingest_command_is_marked(cli_db: Path, tmp_path: Path) -> None:
    """``ingest`` with no files raises ``typer.Exit(1)``; its span is ERROR with ``Exit``."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    empty = tmp_path / "empty"
    empty.mkdir()

    result = runner.invoke(app, ["ingest", str(empty)])
    assert result.exit_code == 1, result.output

    span = _named(exporter, "mintmory.cli.ingest")
    assert span.status.status_code == StatusCode.ERROR
    assert _attributes(span).get("error.type") == "Exit"


@pytest.mark.l4("C-64a88ce0")
def test_command_span_exit_code_zero_is_not_an_error(cli_db: Path) -> None:
    """Exit 0 stays UNSET and event-free; a non-zero exit is ERROR with ``error.type=Exit``."""
    import typer
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)

    @telemetry.command_span("probe-ok")
    def _probe_ok() -> None:
        raise typer.Exit(code=0)

    @telemetry.command_span("probe-fail")
    def _probe_fail() -> None:
        raise typer.Exit(code=1)

    with pytest.raises(typer.Exit):
        _probe_ok()
    with pytest.raises(typer.Exit):
        _probe_fail()

    spans = {span.name: span for span in exporter.get_finished_spans()}
    failed = spans.get("mintmory.cli.probe-fail")
    assert failed is not None, sorted(spans)
    assert failed.status.status_code == StatusCode.ERROR
    assert _attributes(failed).get("error.type") == "Exit"
    assert [event for event in failed.events if event.name == "exception"] == []

    ok = spans.get("mintmory.cli.probe-ok")
    assert ok is not None, sorted(spans)
    assert ok.status.status_code == StatusCode.UNSET
    assert list(ok.events) == []


# ---------------------------------------------------------------------------
# Indexing and conversion phases are traced
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3ce5b739")
def test_index_tree_records_scan_prune_and_cochange_children(cli_db: Path, tmp_path: Path) -> None:
    """A prune+cochange run hangs the three phase spans under the command span."""
    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = _write_tree(tmp_path / "three", ("a.txt", "b.txt", "c.txt"))

    result = runner.invoke(app, ["index-tree", str(folder), "--prune", "--cochange"])
    assert result.exit_code == 0, result.output

    command = _named(exporter, "mintmory.cli.index-tree")
    scan = _named(exporter, "mintmory.index_tree.scan")
    prune = _named(exporter, "mintmory.index_tree.prune")
    cochange = _named(exporter, "mintmory.index_tree.cochange")
    for child in (scan, prune, cochange):
        assert child.parent is not None
        assert child.parent.span_id == command.context.span_id

    attributes = _attributes(cochange)
    assert attributes.get("mintmory.outcome") == "ok"
    assert isinstance(attributes.get("mintmory.cochange.changesets"), int)
    assert _spans_named(exporter, "mintmory.convert") == []


@pytest.mark.l4("C-3ce5b739", "C-20646f63")
def test_cochange_unavailable_is_an_outcome_not_an_error(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caught ``CoChangeUnavailable`` sets ``outcome=unavailable`` and no ERROR."""
    from mintmory.core import cochange as cochange_mod
    from opentelemetry.trace import StatusCode

    def _unavailable(*args: Any, **kwargs: Any) -> Any:
        raise cochange_mod.CoChangeUnavailable("no scikit-learn")

    monkeypatch.setattr(cochange_mod, "cluster_changesets", _unavailable)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = _write_tree(tmp_path / "nocoh", ("a.txt", "b.txt", "c.txt"))

    result = runner.invoke(app, ["index-tree", str(folder), "--cochange"])
    assert result.exit_code == 0, result.output

    cochange = _named(exporter, "mintmory.index_tree.cochange")
    assert _attributes(cochange).get("mintmory.outcome") == "unavailable"
    assert cochange.status.status_code != StatusCode.ERROR


@pytest.mark.l4("C-a83f338b")
def test_no_cochange_span_with_one_changed_file(cli_db: Path, tmp_path: Path) -> None:
    """One file with co-change on exports no ``mintmory.index_tree.cochange`` span."""
    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    single = _write_tree(tmp_path / "single", ("only.txt",))

    result = runner.invoke(app, ["index-tree", str(single), "--cochange"])
    assert result.exit_code == 0, result.output

    _named(exporter, "mintmory.cli.index-tree")
    assert _spans_named(exporter, "mintmory.index_tree.cochange") == []


@pytest.mark.l4("C-a83f338b")
def test_no_cochange_span_when_disabled(cli_db: Path, tmp_path: Path) -> None:
    """Three files with ``--no-cochange`` export no ``mintmory.index_tree.cochange`` span."""
    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = _write_tree(tmp_path / "three", ("a.txt", "b.txt", "c.txt"))

    result = runner.invoke(app, ["index-tree", str(folder), "--no-cochange"])
    assert result.exit_code == 0, result.output

    _named(exporter, "mintmory.cli.index-tree")
    assert _spans_named(exporter, "mintmory.index_tree.cochange") == []


@pytest.mark.l4("C-55bbc2f5")
def test_conversion_spans_for_ingest_and_index_tree(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ``mintmory.convert`` span per binary conversion, under its command/phase span."""
    from mintmory.core import conversion

    def _fake_extract(path: str | Path, **kwargs: Any) -> Any:
        return conversion.ExtractResult(text="converted", method="markitdown", path=Path(path))

    monkeypatch.setattr(conversion, "extract_markdown", _fake_extract)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4 fake")
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "report.pdf").write_bytes(b"%PDF-1.4 fake")

    ingest_result = runner.invoke(app, ["ingest", str(report)])
    assert ingest_result.exit_code == 0, ingest_result.output
    index_result = runner.invoke(
        app, ["index-tree", str(folder), "--content", "--content-types", "pdf"]
    )
    assert index_result.exit_code == 0, index_result.output

    ingest = _named(exporter, "mintmory.cli.ingest")
    scan = _named(exporter, "mintmory.index_tree.scan")
    convert_spans = _spans_named(exporter, "mintmory.convert")
    assert len(convert_spans) == 2, sorted(s.name for s in exporter.get_finished_spans())

    under_ingest = [
        span
        for span in convert_spans
        if span.parent is not None and span.parent.span_id == ingest.context.span_id
    ]
    assert len(under_ingest) == 1, "one convert span must be a child of mintmory.cli.ingest"
    ingest_attrs = _attributes(under_ingest[0])
    assert ingest_attrs.get("mintmory.file.suffix") == ".pdf"
    assert ingest_attrs.get("mintmory.outcome") == "ok"

    by_id = {span.context.span_id: span for span in exporter.get_finished_spans()}
    under_scan = [
        span for span in convert_spans if scan.context.span_id in _ancestor_span_ids(span, by_id)
    ]
    assert len(under_scan) == 1, "one convert span must be a descendant of the scan span"
    scan_attrs = _attributes(under_scan[0])
    assert scan_attrs.get("mintmory.file.suffix") == ".pdf"
    assert scan_attrs.get("mintmory.outcome") == "ok"


@pytest.mark.l4("C-55bbc2f5", "C-20646f63")
def test_conversion_failure_span_is_failed(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``ConversionError`` gives ``outcome=failed`` and ERROR, then ingest keeps going."""
    from mintmory.core import conversion
    from opentelemetry.trace import StatusCode

    def _broken_extract(path: str | Path, **kwargs: Any) -> Any:
        raise conversion.ConversionError("conversion blew up")

    monkeypatch.setattr(conversion, "extract_markdown", _broken_extract)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4 fake")

    result = runner.invoke(app, ["ingest", str(report)])
    assert result.exit_code == 0, result.output

    convert = _named(exporter, "mintmory.convert")
    assert _attributes(convert).get("mintmory.outcome") == "failed"
    assert convert.status.status_code == StatusCode.ERROR
    assert _attributes(convert).get("error.type") == "ConversionError"


@pytest.mark.l4("C-193aef3b")
def test_inline_caption_span(cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The llm provider captions inline inside ``scan``; the agent provider only queues."""
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")
    from mintmory.core import llm as llm_mod

    def _fake_poster(**kwargs: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "A caption."}}]}

    monkeypatch.setattr(llm_mod, "post_chat_completion", _fake_poster)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    llm_folder = tmp_path / "llm_images"
    llm_folder.mkdir()
    (llm_folder / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    first = runner.invoke(app, ["index-tree", str(llm_folder), "--no-text-content", "--vision"])
    assert first.exit_code == 0, first.output
    assert "images-described" in first.output

    scan = _named(exporter, "mintmory.index_tree.scan")
    caption = _named(exporter, "mintmory.vision.caption")
    assert caption.parent is not None
    assert caption.parent.span_id == scan.context.span_id
    attributes = _attributes(caption)
    assert attributes.get("mintmory.file.suffix") == ".png"
    assert attributes.get("mintmory.outcome") == "ok"

    # A fresh run with the agent provider queues the raster instead of captioning it.
    exporter.clear()
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "agent.db"))
    agent_folder = tmp_path / "agent_images"
    agent_folder.mkdir()
    (agent_folder / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    second = runner.invoke(app, ["index-tree", str(agent_folder), "--no-text-content", "--vision"])
    assert second.exit_code == 0, second.output
    assert "images-queued" in second.output
    _named(exporter, "mintmory.cli.index-tree")
    assert _spans_named(exporter, "mintmory.vision.caption") == []


@pytest.mark.l4("C-193aef3b", "C-20646f63", "C-64a88ce0")
def test_caption_failure_span_is_failed(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``VisionError`` gives ``outcome=failed`` and ERROR; the image is skipped."""
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")
    from mintmory.core import llm as llm_mod
    from opentelemetry.trace import StatusCode

    def _broken_poster(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("caption blew up")

    monkeypatch.setattr(llm_mod, "post_chat_completion", _broken_poster)

    exporter = _in_memory_span_exporter()
    _init_spans(exporter)
    folder = tmp_path / "broken_images"
    folder.mkdir()
    (folder / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    result = runner.invoke(app, ["index-tree", str(folder), "--no-text-content", "--vision"])
    assert result.exit_code == 0, result.output

    caption = _named(exporter, "mintmory.vision.caption")
    assert _attributes(caption).get("mintmory.outcome") == "failed"
    assert caption.status.status_code == StatusCode.ERROR
    assert _attributes(caption).get("error.type") == "VisionError"
    assert "vision-skipped" in result.output
