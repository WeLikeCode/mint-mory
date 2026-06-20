# Tasks — `add-llm-vision-provider`

Disjoint file ownership so parallel Sonnet agents do not collide. The critical
path is **Group 2 (`core/vision.py` + `core/llm.py` poster)** — the `LLMCaptioner`
and `caption_pending_images`. Everything else depends on Group 1 (types/config/
prompts — pure additions) and Group 2 (the new core signatures).

**Order:** Group 1 first (types, config, prompts — independent pure additions).
Then Group 2 (the vision module + the shared poster — depends on Group 1, freezes
the §2/§3 signatures). Groups 3/4/5 (transports) run in parallel after Group 2
lands `LLMCaptioner` / `caption_pending_images` / `CaptionRunReport`; they treat
design §4/§5 as fixed. Group 6 (tests) runs alongside/after its impl group.
Group 7 (docs) last.

> Hard rule for every group: **defaults reproduce today.** `provider` STAYS
> `agent` → the factory still returns `None`, `index-tree --vision` still queues
> agent jobs, the caption-run entries no-op. The ONLY factory edit is the `llm`
> branch; `ocr` STAYS a stub.

## 1. Core types + config + prompts — owns `core/types.py`, `core/config.py`, `core/prompts.py`
- [x] 1.1 `core/types.py`: add a "Vision run types" block (after the
      `ImageDescription` block) with `CaptionRunItem` (file_id, rel, status: str,
      note: str = "") and `CaptionRunReport` (described: int = 0, skipped: int = 0,
      failed: int = 0, budget_hit: bool = False, provider: str = "llm", items:
      list[CaptionRunItem] = Field(default_factory=list)), matching the existing
      Pydantic style. No validators (design §3).
- [x] 1.2 `core/config.py`: extend `VisionSettings` — change `base_url`/`model`
      from `str | None = None` to defaulted `str`
      (`base_url="http://localhost:11434/v1"`, `model="llava"`); ADD
      `vision_timeout_s: float = Field(120.0, ge=1.0, le=600.0)`,
      `vision_temperature: float = Field(0.0, ge=0.0, le=2.0)`,
      `vision_max_tokens: int = Field(512, ge=1, le=8192)`, `vision_prompt: str =
      ""`. Leave `provider`/`max_image_mb`/`downscale_max_px`/`max_download_mb`/
      `api_key`/`tesseract_cmd`/the two byte properties UNCHANGED (design §1).
- [x] 1.3 `core/prompts.py`: add `IMAGE_CAPTION_PROMPT` (the default vision prompt,
      mirroring `SUMMARY_PROMPT` style) per design §1.

## 2. Core vision + shared poster — owns `core/vision.py` + the new `core/llm.py::post_chat_completion` (critical path)
- [x] 2.1 `core/llm.py`: factor `post_chat_completion(*, base_url, api_key, payload,
      timeout_s, system, model) -> dict[str, Any]` from `LLMClient.chat` (the
      `gen_ai.chat` span + `mintmory.llm.*` metrics + stdlib `urllib` POST +
      JSON-parse). Refactor `LLMClient.chat` to build its existing text payload and
      delegate to it; its OBSERVABLE behaviour MUST stay byte-for-byte identical
      (existing `core/llm.py` tests pass unedited). Keep `_THINK_RE` exported/usable
      by `core/vision.py` (design §2d).
- [x] 2.2 `core/vision.py`: add `class VisionError(RuntimeError)` with the
      skip-one-and-continue docstring (design §2a).
- [x] 2.3 `core/vision.py`: implement `class LLMCaptioner` + `describe(image:
      ImageInput) -> ImageDescription` — get bytes (image.data or read path; OSError
      → VisionError); `_downscale_bytes` (reuse); base64 `data:<mime>;base64,` URL;
      build the multimodal `/chat/completions` payload (text part = `settings
      .vision_prompt or IMAGE_CAPTION_PROMPT`, image_url part = data URL, max_tokens,
      temperature, stream=False); POST via `llm.post_chat_completion`; parse
      `choices[0].message.content`; `_THINK_RE` strip; empty/whitespace/decode/HTTP/
      network → VisionError; return a TRANSIENT `ImageDescription(record=<un-added
      MemoryRecord category=context/source=document/is_note=False/metadata{kind:
      image_description, source_image:path}>, file_id, source_image=path,
      replaced_description_id=None)` (design §2c).
- [x] 2.4 `core/vision.py`: change the `captioner_from_settings` `LLM` branch to
      `return LLMCaptioner(s)` (was: raise). `agent`→None and `ocr`→raise UNCHANGED
      (design §2b).
- [x] 2.5 `core/vision.py`: implement `caption_pending_images(adapter, *, captioner,
      limit=0, budget=None, include_all=False, settings=None) -> CaptionRunReport`
      — walk `image_jobs(adapter, include_all=include_all, include_bytes=True,
      limit=limit, settings=settings)`; per job: skip oversized (note 'oversized');
      obtain bytes (job.image_b64 decode else read path; online_only consumes
      `budget` — when `None` fall back to `settings.max_download_bytes`; over-budget
      → skip note 'budget' + budget_hit); `captioner.describe(...)` → VisionError
      caught, count `failed`, continue; else `image_caption_put(adapter,
      job.file_id, desc.record.content, settings=settings)` and count `described`
      (item note = new record id). Return `CaptionRunReport` (design §3). Per-image
      failures NEVER abort the run.

## 3. Transport: CLI — owns `packages/cli/src/mintmory/cli/main.py`
- [x] 3.1 `index-tree --vision` auto-run: capture `captioner =
      captioner_from_settings(settings.vision)` in the existing `if vision:` guard
      (keep the `NotImplementedError`→exit for ocr); add `max_image_bytes =
      settings.vision.max_image_bytes` to the budget locals; in the raster branch,
      when `captioner is None` keep `images_queued += 1` (UNCHANGED agent path),
      else caption inline (size-cap skip; online_only consumes the shared
      `downloaded`/`budget`/`budget_hit`; `describe` + `image_caption_put`;
      `content_hash = blake2b(description)`; `images_described += 1`; catch
      `VisionError`/`OSError` → `vision_skipped += 1` + continue); add an
      `images-described` report row (shown when captioner not None); manifest stays
      `index_mode='vision'`. UNCHANGED without `--vision` (design §4).
- [x] 3.2 `mintmory vision-run` command (`--limit`, `--budget`, `--all/--needed`):
      build captioner from settings; `NotImplementedError` (ocr) → console error +
      `typer.Exit(1)`; `None` (agent) → print no-op message + return (exit 0); else
      `caption_pending_images(...)` and render a rich table (described/skipped/
      failed/budget_hit) (design §5a).
- [x] 3.3 Add `mintmory vision-run` to the module docstring command list (top of
      `main.py`).

## 4. Transport: MCP — owns `packages/mcp/src/mintmory/mcp/server.py`
- [x] 4.1 `vision_run(limit=0, budget_mb=0.0, include_all=False) -> dict` tool:
      build captioner from settings; `NotImplementedError` →
      `{"error":"not_implemented","message":…}`; `None` (agent) →
      `CaptionRunReport(provider="agent").model_dump(mode="json")`; else
      `caption_pending_images(...).model_dump(mode="json")` (design §5b).
- [x] 4.2 Add a sentence to the FastMCP `instructions` (server-side vision_run vs
      the agent image_jobs loop; agent default no-ops) + the tool-map comment block
      at the top of the file (add `vision_run → POST /images/caption-run`).

## 5. Transport: HTTP API — owns `packages/api/src/mintmory/api/{schemas.py,app.py}` + `docs/openapi/mintmory.yaml`
- [x] 5.1 `schemas.py`: `CaptionRunRequest` (limit int ≥0 default 0, budget_mb
      number ≥0 default 0.0, include_all bool default False) (design §5c).
- [x] 5.2 `app.py`: `POST /images/caption-run` (→ `CaptionRunReport`, body
      `CaptionRunRequest`) under the "Images" tag — build captioner;
      `NotImplementedError`→422; `None`→`CaptionRunReport(provider="agent")`; else
      `caption_pending_images(...)`. Import `CaptionRunReport` (+ `CaptionRunRequest`
      from schemas). Declare AFTER `/images/jobs` + `/images/{file_id}` (design §5c).
- [x] 5.3 OpenAPI YAML: add `POST /images/caption-run` (operationId `captionRun`)
      + `CaptionRunRequest`, `CaptionRunReport`, `CaptionRunItem` component schemas
      (mirror the `ImageJob`/`SummaryJob` style; document the provider='agent'
      no-op) (design §5c).

## 6. Tests — owns the `tests/` trees (per package; disjoint from impl groups)
- [x] 6.1 core (`packages/core/tests/`): `VisionSettings` new defaults + bounds +
      env parse; `captioner_from_settings` (llm→`LLMCaptioner`, agent→None,
      ocr→raise); `LLMCaptioner.describe` with a **stubbed poster/urlopen** — assert
      the multimodal payload (model/messages/text+image_url data-url/max_tokens/
      temperature/stream/Bearer-iff-key/URL), response parse, `<think>` strip,
      transient record shape, `vision_prompt` override, and `VisionError` on
      network/timeout/HTTP/empty/think-only/decode/unreadable; Pillow-absent embeds
      raw bytes; `caption_pending_images` (describe pending + no-drift drop;
      VisionError→failed+continue; oversized→skipped; include_all re-captions;
      limit; online-only budget→skip+budget_hit) with a fake in-memory Captioner;
      `core/llm.py` `LLMClient.chat` unchanged after the poster refactor (design §7).
      NO real network anywhere.
- [x] 6.2 cli (`packages/cli/tests/`): `index-tree --vision` with provider=llm
      (poster stubbed) → images-described + manifest index_mode='vision' + ANNOTATES;
      stubbed VisionError → vision-skipped + walk completes; provider=agent still
      images-queued (UNCHANGED); incremental re-run (no re-caption); ocr exits
      non-zero. `mintmory vision-run` (describes pending; agent no-op exit 0;
      `--limit`/`--budget`/`--all`) (design §7).
- [x] 6.3 mcp (`packages/mcp/tests/`): `vision_run` agent→provider='agent'/0;
      provider=llm (poster stubbed)→describes + image drops from default image_jobs;
      ocr→not_implemented (design §7).
- [x] 6.4 api (`packages/api/tests/`): `POST /images/caption-run` agent→200
      provider='agent'; provider=llm (poster stubbed)→200 + absent from
      `GET /images/jobs`; ocr→422 (design §7).

## 7. Docs — owns `README*`, agent/onboarding docs, `openspec/README.md`
- [x] 7.1 README / agent doc: an "automated llm vision provider" subsection — set
      `MINTMORY_VISION_PROVIDER=llm` + the `MINTMORY_VISION_*` vision-model knobs
      (`MODEL`/`BASE_URL`/`API_KEY`/`VISION_MAX_TOKENS`/`VISION_PROMPT`); then either
      `index-tree --vision` captions inline OR `mintmory vision-run` /
      `POST /images/caption-run` caption already-indexed pending images; `agent`
      stays the default (zero behaviour change); no new dependency; `ocr` still a
      stub.
- [x] 7.2 `openspec/README.md`: add the `add-llm-vision-provider` bullet.

## 8. Review & integration (orchestrator, Opus)
- [x] 8.1 Verify gates per package (pytest cov ≥ 80 / ruff / ruff format /
      mypy --strict, line-length 100).
- [x] 8.2 Independent Opus reviewer: confirm (a) defaults reproduce today —
      `provider=agent` → factory None, `index-tree --vision` queues (UNCHANGED),
      caption-run entries no-op; every MM-18/MM-6 test green unedited (bar the
      intended `base_url/model` default assertions); (b) `llm` implemented / `ocr`
      stub / `agent` None — `captioner_from_settings` dispatch; (c) no new REQUIRED
      dependency — the vision call uses `core/llm.py::post_chat_completion` (stdlib
      urllib), Pillow optional+lazy, NO real network in tests; (d) skip-one — a
      `VisionError` is caught by `caption_pending_images` and `index-tree --vision`
      (counted, run continues); (e) same persistence — both apply paths go through
      the UNCHANGED `image_caption_put` (no schema change, no new `index_mode`); (f)
      `LLMClient.chat` byte-for-byte observable after the shared-poster refactor.
- [x] 8.3 Orchestrator applies fixes, re-runs gates, commits.
