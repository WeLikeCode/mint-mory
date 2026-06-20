# Design & FROZEN interface contract — `add-llm-vision-provider`

Implementers MUST match these signatures, names, return shapes, and behaviours
exactly. Where intuition and this doc disagree, this doc wins. This change
implements the **automated `llm` vision provider** in the Captioner seam that
`add-image-understanding` (MM-18) built and stubbed.

Overarching invariants (the MintMory house rules, all preserved here):

- **Every default reproduces today's behaviour.** The whole change is additive.
  `MINTMORY_VISION_PROVIDER` STAYS `agent`: `captioner_from_settings` STILL returns
  `None`, `index-tree --vision` STILL queues agent jobs, `image_jobs` /
  `image_caption_put` / the agent loop are UNCHANGED, and the new caption-run
  entries no-op when no captioner is configured. Nothing new runs unless an operator
  opts in with `provider=llm`.
- **One core, three transports.** All domain logic lives in `mintmory.core`
  (`core/vision.py`); MCP / CLI / API are thin wrappers that marshal `types.py`
  models and call the core with a `StorageAdapter` + `VisionSettings`.
- **No new REQUIRED runtime dependency.** The vision HTTP call REUSES the stdlib
  `urllib` machinery in `core/llm.py` (the OpenAI-compatible `/chat/completions`
  shape). No `openai` SDK. Pillow stays the optional `[image]` extra (lazy import).
- **Reuse, don't reinvent.** The MM-18 persistence path (`image_caption_put`), the
  MM-18 discovery (`image_jobs`), the MM-18 lazy-Pillow `_downscale_bytes`, the
  MM-18 `_mime_for`/size-cap logic, the MM-6 `LLMClient` request/response/`<think>`
  machinery, and the MM-6 `gen_ai.*` telemetry seam are ALL reused as-is.
- Gates for every package touched: `pytest` (cov ≥ 80), `ruff check`,
  `ruff format --check`, `mypy --strict` (line-length 100).

The load-bearing claims of this change:
1. **`llm` is now implemented:** `captioner_from_settings` returns an
   `LLMCaptioner` for `provider=llm` (no longer raises). `ocr` STAYS a stub.
2. **Defaults reproduce today:** `agent` still → `None`; every existing MM-18 test
   (image_jobs/image_caption_put/index-tree --vision queueing/the `ocr` raise)
   passes WITHOUT edits.
3. **Skip-one-and-continue:** a single image's network/timeout/empty-content error
   raises `VisionError` and is CAUGHT by the apply paths (`caption_pending_images`,
   `index-tree --vision`), which count it and move on — one bad image never aborts
   a run.
4. **No real network in tests:** `LLMCaptioner` is tested by stubbing the shared
   poster (`_chat_completion`) / `urlopen`; the suite makes ZERO outbound calls.

---

## 0. Ground truth — the MM-6 `LLMClient` request/response shape (REUSE)

From `core/llm.py` (quoted verbatim — the vision call is the SAME shape with a
multimodal `content` and an added `max_tokens`):

```python
def _build_request(self, prompt: str) -> urllib.request.Request:
    payload: dict[str, Any] = {
        "model": self.settings.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": self.settings.temperature,
        "stream": False,
    }
    headers = {"content-type": "application/json"}
    if self.settings.api_key:
        headers["Authorization"] = f"Bearer {self.settings.api_key}"
    return urllib.request.Request(
        self.settings.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

# in chat():
with urllib.request.urlopen(req, timeout=self.settings.timeout_s) as resp:  # noqa: S310
    data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
content: str = data["choices"][0]["message"]["content"]
```

`_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)` already exists in
`core/llm.py` and is reused. The `gen_ai.chat` span + `mintmory.llm.*` metrics
wrapper around the urlopen is reused (the vision call gets its own
`gen_ai.system="vision:<provider>"`-style attributes; see §2c).

## 0a. Ground truth — what MM-18 already gives us (DO NOT CHANGE)

In `core/vision.py` (all UNCHANGED by this change except the two noted seams):
- `Captioner` Protocol (`describe(image: ImageInput) -> ImageDescription`),
  `ImageInput` (`file_id, path, mime, data: bytes | None`).
- `captioner_from_settings(settings) -> Captioner | None` — **the `llm` raise
  branch is the ONE line we replace** (§2b); `agent`→`None` and `ocr`→raise stay.
- `image_jobs(adapter, *, include_all, include_bytes, limit, settings)` — discovery
  + no-drift predicate + hybrid bytes (REUSED by `caption_pending_images`, §3).
- `image_caption_put(adapter, file_id_or_path, description, *, settings)` — the
  persistence path (archive-then-add, ANNOTATES, no-drift) REUSED unchanged by both
  apply paths.
- `RASTER_SUFFIXES`, `SVG_SUFFIXES`, `IMAGE_SUFFIXES`,
  `PROPRIETARY_IMAGE_SUFFIXES`, `_mime_for(suffix)`, `_downscale_bytes(data, mime,
  max_px)` — REUSED.

---

## 1. Config — `VisionSettings` llm knobs (`core/config.py`)

Extend the EXISTING `VisionSettings` (env prefix `MINTMORY_VISION_`). The provider
field and the agent-path caps are UNCHANGED. Give `base_url`/`model` non-None
defaults (they were `None` "for the seam" in MM-18; the llm path needs real
defaults) and add four llm-tier knobs MIRRORING `LLMSettings`
(`timeout_s`/`temperature`/`max_tokens`-style). FROZEN field set:

```python
class VisionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_VISION_", extra="ignore")

    provider: VisionProvider = VisionProvider.AGENT  # UNCHANGED — default agent
    # --- agent-path knobs (UNCHANGED from MM-18) ---
    max_image_mb: float = Field(default=8.0, ge=0.0)
    downscale_max_px: int = Field(default=1568, ge=0)
    max_download_mb: float = Field(default=200.0, ge=0.0)
    # --- provider endpoint (llm/ocr). base_url/model now DEFAULTED for the llm tier;
    #     unused when provider=agent so defaults still reproduce today. ---
    base_url: str = "http://localhost:11434/v1"   # was: str | None = None
    model: str = "llava"                            # was: str | None = None  (vision model)
    api_key: str | None = None                      # UNCHANGED (Bearer iff set)
    tesseract_cmd: str | None = None                # UNCHANGED (future ocr)
    # --- NEW llm-vision tier knobs (mirror LLMSettings) ---
    vision_timeout_s: float = Field(default=120.0, ge=1.0, le=600.0)
    vision_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    vision_max_tokens: int = Field(default=512, ge=1, le=8192)
    vision_prompt: str = ""  # "" => use prompts.IMAGE_CAPTION_PROMPT default

    @property
    def max_image_bytes(self) -> int | None: ...      # UNCHANGED
    @property
    def max_download_bytes(self) -> int | None: ...    # UNCHANGED
```

FROZEN decisions:
- **Defaults reproduce today.** `provider` STAYS `agent`; giving `base_url`/`model`
  values changes NOTHING for `agent` (the factory returns `None` before reading
  them). No existing config test changes meaning except those asserting
  `base_url is None` / `model is None`, which MUST be updated to the new defaults
  (call this out in tasks — it is an expected, intended assertion change).
- **`vision_timeout_s` is SEPARATE from the agent-path settings** and defaults
  higher (120 s) than `LLMSettings.timeout_s` (60 s) because vision models are
  slower. Bounds match `LLMSettings.timeout_s` (1..600).
- **`vision_max_tokens=512`** caps the caption length (a description is a short
  blob, not an essay). Sent as `max_tokens` in the request body.
- **`vision_prompt=""`** means "use the default"; a non-empty value overrides it
  verbatim. The effective prompt is resolved at call time:
  `settings.vision_prompt or prompts.IMAGE_CAPTION_PROMPT`.
- Do NOT add a `VisionProvider` value and do NOT touch `LLMSettings` /
  `MINTMORY_LLM_*`. The vision tier is its own config (a vision model differs from
  the L3 text model). We reuse `LLMClient` *code*, not its *settings object*.

`prompts.py` gains the default (mirror `SUMMARY_PROMPT` style):

```python
IMAGE_CAPTION_PROMPT = (
    "Describe this image in 2-4 sentences for a search index. State what it "
    "depicts and transcribe ALL legible text verbatim (labels, captions, UI "
    "strings, diagram nodes). Be specific: keep names, numbers, and on-screen "
    "text. Reply with ONLY the description (no preamble)."
)
```

---

## 2. `LLMCaptioner` — the first real `Captioner` (`core/vision.py`)

### 2a. `VisionError`

A clear core exception so apply paths can SKIP one image and continue:

```python
class VisionError(RuntimeError):
    """A vision-provider call failed for one image (network/timeout/HTTP/empty
    response/decode). Callers (caption_pending_images, index-tree --vision) catch
    this, skip the single image, and continue — one bad image never aborts a run."""
```

### 2b. `captioner_from_settings` dispatch change (the ONE factory edit)

Replace ONLY the `LLM` branch's `raise` with a return. `agent`→`None` and
`ocr`→raise are UNCHANGED:

```python
def captioner_from_settings(settings: VisionSettings | None = None) -> Captioner | None:
    s = settings if settings is not None else VisionSettings()
    if s.provider is VisionProvider.AGENT:
        return None                       # UNCHANGED
    if s.provider is VisionProvider.LLM:
        return LLMCaptioner(s)            # CHANGED — was: raise NotImplementedError(...)
    if s.provider is VisionProvider.OCR:
        raise NotImplementedError(        # UNCHANGED — ocr stays a stub
            "vision provider 'ocr' is not implemented in this version; "
            "set MINTMORY_VISION_PROVIDER=agent for the agent-supplied loop"
        )
    raise NotImplementedError(f"unknown vision provider {s.provider!r}")  # UNCHANGED
```

> The factory STAYS the only place that branches on `provider`. `image_jobs` /
> `image_caption_put` STILL never call it.

### 2c. `LLMCaptioner` class + `describe()` (FROZEN)

```python
class LLMCaptioner:
    """Automated Captioner: caption a raster image via an OpenAI-compatible VISION
    model. Reuses the core/llm.py stdlib-urllib /chat/completions machinery (Bearer
    api_key, timeout, gen_ai OTel span, <think> stripping) with a multimodal user
    message. No new dependency; no openai SDK. Raises VisionError on any failure so
    the caller skips the one image and continues."""

    def __init__(self, settings: VisionSettings) -> None:
        self.settings = settings

    def describe(self, image: ImageInput) -> ImageDescription:
        ...
```

`describe(image)` FROZEN behaviour:
1. **Get bytes.** Use `image.data` if not None; else read `image.path`
   (`open(path, "rb").read()`). On `OSError` → raise `VisionError(f"cannot read
   {image.path}: {exc}")`.
2. **Downscale (reuse).** `data = _downscale_bytes(data, image.mime,
   self.settings.downscale_max_px)` — the EXISTING lazy-Pillow helper (no-op if
   Pillow absent or `downscale_max_px<=0`; never raises). Same size cap discipline
   as MM-18: the caller (§3) already enforces `max_image_bytes` BEFORE calling
   describe; `describe` itself does not re-check the on-disk cap (it trusts the
   caller) but DOES downscale.
3. **Build the data URL.** `b64 = base64.b64encode(data).decode("ascii")`;
   `data_url = f"data:{image.mime};base64,{b64}"`.
4. **Build the request body** (the SAME `/chat/completions` shape as §0, with a
   multimodal `content` list and `max_tokens`):

   ```python
   prompt = self.settings.vision_prompt or IMAGE_CAPTION_PROMPT
   payload = {
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
   ```
   Headers: `{"content-type": "application/json"}` plus
   `"Authorization": f"Bearer {api_key}"` IFF `self.settings.api_key`.
   URL: `self.settings.base_url.rstrip("/") + "/chat/completions"`. Method POST.
5. **POST + parse** via the shared poster `_chat_completion(...)` (§2d): on success
   read `data["choices"][0]["message"]["content"]`. A missing/empty/whitespace-only
   content → raise `VisionError("vision model returned empty content")`.
   `KeyError`/`IndexError`/`TypeError` from an unexpected JSON shape → raise
   `VisionError("unexpected vision response shape")`.
6. **Strip `<think>`** (reuse `_THINK_RE` from `core/llm.py`):
   `text = _THINK_RE.sub("", content).strip()`. If empty after stripping → raise
   `VisionError("vision model returned only reasoning")`.
7. **Return** `ImageDescription(record=<transient MemoryRecord>, file_id=image.file_id,
   source_image=image.path, replaced_description_id=None)` where the transient
   `MemoryRecord` carries `content=text, category=CONTEXT, source=DOCUMENT,
   is_note=False, metadata={"kind":"image_description","source_image":image.path}`.

   > **FROZEN:** `describe()` does NOT persist. The returned `record` is a NEW,
   > un-added `MemoryRecord` (no DB row). The apply paths (§3, §4) call
   > `image_caption_put(adapter, image.file_id, description.record.content)` to
   > persist (which is what makes the no-drift archive-then-add fire). This keeps
   > `LLMCaptioner` a pure text→text unit with no storage coupling, exactly matching
   > the `Captioner` protocol's "produce a description" responsibility, and lets the
   > apply paths own persistence + the file-record resolution.

### 2d. Shared HTTP poster — REUSE vs REFACTOR decision (FROZEN)

**Decision: factor a tiny shared module-private poster, do NOT reuse `LLMClient`
directly.** Rationale: `LLMClient.chat(prompt: str)` hard-codes a single
text-`content` message and `LLMSettings`; the vision call needs a multimodal
`content` list, `max_tokens`, and `VisionSettings`. Subclassing/overloading
`LLMClient` would entangle two settings types. Instead add ONE small function to
`core/llm.py` that both `LLMClient.chat` and `LLMCaptioner.describe` call:

```python
def post_chat_completion(
    *, base_url: str, api_key: str | None, payload: dict[str, Any],
    timeout_s: float, system: str, model: str,
) -> dict[str, Any]:
    """POST an OpenAI-compatible /chat/completions ``payload`` and return the parsed
    JSON dict. Wraps the call in the existing ``gen_ai.chat`` span + mintmory.llm.*
    metrics (no-op unless OTel on). Raises urllib.error.URLError / TimeoutError /
    json.JSONDecodeError to the caller (LLMClient maps as today; LLMCaptioner wraps
    in VisionError). ``system`` sets gen_ai.system (e.g. the provider name)."""
```

`LLMClient.chat` is refactored to build its existing text payload and delegate to
`post_chat_completion` (its OBSERVABLE behaviour MUST stay byte-for-byte identical —
the existing `core/llm.py` tests pass unedited). `LLMCaptioner.describe` builds the
multimodal payload (§2c) and calls `post_chat_completion(system=f"vision:{provider}"
or "vision", model=self.settings.model, …)`, then wraps EVERY exception it raises in
`VisionError`. `core/vision.py` imports `post_chat_completion` and `_THINK_RE` from
`core/llm.py` (lazy import inside `describe`/at module top — `core/vision.py` is
already imported lazily by callers, so a top-level import is fine; prefer a module
import `from mintmory.core import llm` and call `llm.post_chat_completion(...)` to
avoid a circular-import risk since `llm` imports many things — VERIFY no cycle: `llm`
does NOT import `vision`, so `vision` importing `llm` is safe).

> Alternative considered & REJECTED: a brand-new urllib poster in `core/vision.py`.
> Rejected because it would duplicate the Bearer/timeout/`urlopen`/`# noqa: S310` +
> the `gen_ai` span, drifting from `core/llm.py`. One poster, two callers.

---

## 3. Automated apply — `caption_pending_images` (`core/vision.py`)

```python
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
    each via image_caption_put. Walks image_jobs(adapter, include_all=include_all,
    include_bytes=True, limit=limit, settings=settings) — the SAME discovery +
    no-drift predicate as the agent loop — and for each job:
      * if the job is oversized (image_b64 is None AND job.oversized): SKIP (count
        skipped); record note 'oversized'.
      * obtain bytes: prefer the job's already-embedded image_b64 (base64-decode);
        else read job.path. For online_only files with no embedded bytes, the byte
        read counts against ``budget``; once the running download total exceeds
        budget, STOP captioning further online-only images (count skipped, note
        'budget'); set budget_hit. Local reads do not consume budget.
      * call captioner.describe(ImageInput(file_id, path, mime, data=<bytes>)); on
        VisionError, SKIP (count failed) with the error message as the note; continue.
      * on success, persist: image_caption_put(adapter, job.file_id,
        description.record.content, settings=settings). Count described; capture the
        new record id + replaced_description_id in the item note.
    Returns a CaptionRunReport (described, skipped, failed, budget_hit, items).
    No-drift: with include_all=False, already-described images are not in image_jobs,
    so re-running is incremental. Raises NOTHING for per-image failures (they are
    counted); MAY propagate only programmer errors (e.g. a None captioner is a
    caller bug — see the transports, which guard provider=agent BEFORE calling)."""
```

FROZEN decisions:
- **`include_bytes=True`** is passed to `image_jobs` so LOCAL files are also
  embedded (the captioner needs bytes regardless of host); the size cap + budget in
  `image_jobs` still apply, so oversized images come back with `image_b64=None,
  oversized=True` and are skipped here.
- **Budget semantics** match `index-tree --max-download-mb` and MM-18's
  `image_jobs` budget: bytes-counted, online-only only, `None` = unlimited. Because
  `image_jobs(include_bytes=True)` ALREADY applies `max_download_bytes` from
  settings when embedding online-only payloads, `caption_pending_images`'s own
  `budget` parameter is the run-level override the CLI/transports pass through (a
  caller-supplied `budget` takes precedence over the settings default by being the
  authoritative counter here; when `budget is None`, fall back to
  `settings.max_download_bytes`). Keep it simple: count `len(bytes)` for online-only
  images against `budget`; stop embedding/captioning further online-only images when
  exceeded.
- **Size cap** is enforced by `image_jobs` (not re-checked here); an oversized job
  is skipped with note `oversized`.
- **Failure isolation:** a `VisionError` from `describe` is the per-image skip; it
  is counted under `failed` (distinct from `skipped`, which is oversize/budget) and
  the loop continues. NEVER let one image abort the run.
- **`limit`** is passed straight to `image_jobs` (post-selection cap, `0`=no cap),
  matching MM-17/MM-18.

`CaptionRunReport` (`core/types.py`, new "Vision run types" block):

```python
class CaptionRunItem(BaseModel):
    """One image processed by a caption run (audit detail)."""
    file_id: str
    rel: str
    status: str           # "described" | "skipped" | "failed"
    note: str = ""        # description id / "oversized" / "budget" / the VisionError text


class CaptionRunReport(BaseModel):
    """Result of caption_pending_images / vision-run / POST /images/caption-run."""
    described: int = 0
    skipped: int = 0      # oversized or budget-exhausted
    failed: int = 0       # VisionError / unreadable
    budget_hit: bool = False
    provider: str = "llm" # "agent" when no captioner was configured (no-op run)
    items: list[CaptionRunItem] = Field(default_factory=list)
```

> `provider="agent"` + all-zero counts is the documented no-op shape the transports
> return when `captioner_from_settings(settings.vision) is None` (they DON'T call
> `caption_pending_images` in that case — see §5).

---

## 4. `index-tree --vision` auto-run (`cli/main.py`)

MM-18 already validates the provider once before the walk
(`captioner_from_settings(settings.vision)` inside the `if vision:` guard, catching
`NotImplementedError`). Change: **capture the returned captioner** and, in the
raster branch, run it inline when it is not None.

FROZEN integration (the ONLY change to `index_tree`; SVG branch + everything else
UNCHANGED):

```python
if vision:
    from mintmory.core import vision as vision_mod
    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)  # CHANGED: capture
    except NotImplementedError as _nie:   # still fires for ocr
        console.print(f"[red]error[/red]: {_nie}")
        raise typer.Exit(code=1) from _nie
else:
    vision_mod = None  # type: ignore[assignment]
    captioner = None
```

In the existing raster `else` branch (currently just `images_queued += 1`):

```python
else:  # raster image
    if captioner is None:
        # provider=agent (UNCHANGED MM-18 behaviour): queue for the agent loop.
        images_queued += 1
        # mode already 'vision'; no bytes read, no description yet.
    else:
        # provider=llm (or future ocr): caption inline under the SAME budget.
        # 1. size cap: skip oversized (reuse settings.max_image_bytes vs entry.size).
        # 2. read bytes: online_only consumes the shared `downloaded`/`budget`
        #    accounting EXACTLY like want_binary/SVG (and sets budget_hit); local
        #    read is free.
        # 3. describe + persist; on VisionError -> count vision_skipped, continue.
        try:
            if max_image_bytes is not None and entry.size > max_image_bytes:
                vision_skipped += 1
            elif entry.online_only and budget is not None and downloaded >= budget:
                vision_skipped += 1   # budget exhausted; leave as metadata-but-vision-attempted
            else:
                raw = entry.path.read_bytes()
                if entry.online_only:
                    downloaded += len(raw)
                    if budget is not None and downloaded >= budget:
                        budget_hit = True
                desc = captioner.describe(
                    vision_mod.ImageInput(
                        file_id=file_record.id, path=path_str,
                        mime=vision_mod._mime_for(entry.suffix), data=raw,
                    )
                )
                put = vision_mod.image_caption_put(
                    store, file_record.id, desc.record.content, settings=settings.vision
                )
                new_ids.append(put.record.id)
                content_hash = hashlib.blake2b(
                    desc.record.content.encode("utf-8"), digest_size=16
                ).hexdigest()
                images_described += 1   # NEW counter
        except vision_mod.VisionError as exc:
            console.print(f"[yellow]vision skip[/yellow] {entry.name}: {exc}")
            vision_skipped += 1
        except OSError as exc:
            console.print(f"[yellow]vision skip[/yellow] {entry.name}: read error {exc}")
            vision_skipped += 1
        # mode stays 'vision' in all cases (manifest records the attempt).
```

FROZEN decisions:
- **Captioner None ⇒ today's behaviour** (queue agent jobs). This is the
  defaults-reproduce-today guarantee for `index-tree --vision`.
- **Shared budget.** Online-only raster downloads consume the SAME
  `--max-download-mb` `downloaded`/`budget`/`budget_hit` accounting as `--content`
  and SVG (MM-18's "under the SAME download budget"). Add `max_image_bytes =
  settings.vision.max_image_bytes` next to the existing budget locals.
- **content_hash = blake2b(description)** so a re-run after the description changes
  re-captions (parallels the SVG `content_hash` MM-18 sets); an unchanged file with
  a successful caption is `covered` (manifest `index_mode='vision'`) and skipped on
  re-run.
- **Report rows:** add `images-described` (only shown when `captioner is not
  None`); keep `images-queued` (shown when `captioner is None`); `vision-skipped`
  already exists and now also counts oversized/budget/VisionError rasters.
- **Failure isolation:** a `VisionError`/`OSError` for ONE raster is caught,
  counted, logged; the walk continues (one image never aborts an index run).
- **No new flag.** `--vision` is the existing switch; the provider decides
  queue-vs-caption. (An `MINTMORY_VISION_PROVIDER=llm` is the opt-in.)

---

## 5. Standalone caption-run entries (no re-walk)

A core-backed entry to caption already-indexed PENDING images via the configured
provider WITHOUT re-walking the tree. All three transports:
1. `settings = load_settings()`; `captioner =
   vision.captioner_from_settings(settings.vision)`.
2. If `captioner is None` (provider=agent): **no-op** — return a `CaptionRunReport(
   provider="agent")` (all-zero) WITHOUT calling `caption_pending_images`. (Catch
   `NotImplementedError` for `ocr` and surface it as the transport's error: CLI exit
   non-zero with the message; MCP `{"error":"not_implemented","message":…}`; HTTP
   501 or 422 with the message — pick 422 to match the validation-error family, with
   the clear text.)
3. Else call `caption_pending_images(store, captioner=captioner, limit=…,
   budget=…, include_all=…, settings=settings.vision)` and return/serialise the
   report.

### 5a. CLI — `mintmory vision-run`

```python
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
    # load_settings(); captioner = vision.captioner_from_settings(settings.vision)
    #   - NotImplementedError (ocr) -> console error + raise typer.Exit(1)
    #   - None (agent) -> print "provider=agent: nothing to run (use image-jobs/
    #     image-caption-put)"; return (exit 0)
    #   - else budget = int(budget_mb*1024*1024) if budget_mb>0 else None;
    #     report = vision.caption_pending_images(store, captioner=captioner,
    #         limit=limit, budget=budget, include_all=include_all, settings=settings.vision)
    #     print a rich table: described / skipped / failed / budget_hit (+ a dim
    #     per-item line list when small).
```

Add `mintmory vision-run` to the module docstring command list (top of `main.py`).

### 5b. MCP — `vision_run`

```python
@mcp.tool()
def vision_run(
    limit: int = 0, budget_mb: float = 0.0, include_all: bool = False
) -> dict[str, Any]:
    """Caption already-indexed pending images with the configured SERVER-SIDE vision
    provider (MINTMORY_VISION_PROVIDER=llm). Unlike image_jobs/image_caption_put
    (where YOU, the agent, describe), this calls a configured vision MODEL server-side
    and persists each description. With provider=agent it is a no-op (returns
    provider='agent', described=0) — use the image_jobs loop instead. Per-image
    failures are skipped and counted. Returns a CaptionRunReport dict.

    Args:
        limit: max images to caption (0 = no cap).
        budget_mb: download budget MB for online-only images (0 = settings default).
        include_all: re-caption all raster images vs only pending (default).
    """
    store = _get_store(); settings = load_settings()
    from mintmory.core import vision as vision_mod
    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)
    except NotImplementedError as exc:
        return {"error": "not_implemented", "message": str(exc)}
    if captioner is None:
        return CaptionRunReport(provider="agent").model_dump(mode="json")
    budget = int(budget_mb * 1024 * 1024) if budget_mb > 0 else None
    report = vision_mod.caption_pending_images(
        store, captioner=captioner, limit=limit, budget=budget,
        include_all=include_all, settings=settings.vision,
    )
    return report.model_dump(mode="json")
```

Add a sentence to the FastMCP `instructions` (and the tool-map comment): "If a
server-side vision model is configured (MINTMORY_VISION_PROVIDER=llm), call
vision_run to auto-caption pending indexed images without the manual image_jobs
loop; with the default provider=agent it no-ops."

### 5c. HTTP — `POST /images/caption-run`

`schemas.py`:

```python
class CaptionRunRequest(BaseModel):
    """Request body for ``POST /images/caption-run`` (server-side auto-caption)."""
    limit: int = Field(default=0, ge=0)
    budget_mb: float = Field(default=0.0, ge=0.0)
    include_all: bool = False
```

`app.py` (declare AFTER `/images/jobs` and `/images/{file_id}` — distinct literal
path, no shadowing; response model the core `CaptionRunReport`):

```python
@app.post("/images/caption-run", response_model=CaptionRunReport, tags=["Images"])
async def caption_run(body: CaptionRunRequest) -> CaptionRunReport:
    """Caption already-indexed pending images server-side with the configured vision
    provider (MINTMORY_VISION_PROVIDER=llm). No-op (provider='agent') when no backend
    is configured. Per-image failures are skipped and counted."""
    from mintmory.core import vision as vision_mod
    settings = load_settings()
    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if captioner is None:
        return CaptionRunReport(provider="agent")
    budget = int(body.budget_mb * 1024 * 1024) if body.budget_mb > 0 else None
    return vision_mod.caption_pending_images(
        get_store(), captioner=captioner, limit=body.limit, budget=budget,
        include_all=body.include_all, settings=settings.vision,
    )
```

`docs/openapi/mintmory.yaml` — under the existing "Images" tag add:
- `POST /images/caption-run` (operationId `captionRun`, requestBody
  `CaptionRunRequest`, 200 → `CaptionRunReport`, 422 `UnprocessableEntity`);
- component schemas `CaptionRunRequest` (limit int ≥0, budget_mb number ≥0,
  include_all bool) and `CaptionRunReport` (described/skipped/failed int,
  budget_hit bool, provider string, items array of `CaptionRunItem`) +
  `CaptionRunItem` (file_id, rel, status, note). Mirror the `SummaryJob` /
  `ImageJob` YAML style; document the provider='agent' no-op.

---

## 6. Determinism / invariants the implementer MUST preserve

- **`llm` implemented; `ocr` stub; `agent` default-None.**
  `captioner_from_settings` returns `LLMCaptioner` for `llm`, `None` for `agent`,
  and STILL raises `NotImplementedError` for `ocr`. The ONLY factory edit is the
  `llm` branch.
- **Defaults reproduce today.** With `provider=agent` (default): the factory
  returns `None`, `index-tree --vision` queues agent jobs (UNCHANGED),
  `image_jobs`/`image_caption_put`/the agent loop are untouched, and
  `vision-run`/`vision_run`/`POST /images/caption-run` return the all-zero
  `provider="agent"` no-op report. Every existing MM-18/MM-6 test passes unedited
  (except config tests asserting `base_url/model is None`, which become the new
  defaults — an intended assertion update).
- **No new REQUIRED dependency / reuse the urllib poster.** The vision call goes
  through `core/llm.py::post_chat_completion` (stdlib `urllib`); no `openai` SDK.
  Pillow stays optional + lazy (the EXISTING `_downscale_bytes`); absent ⇒ raw bytes
  in the data URL. `core/llm.py::LLMClient.chat` stays byte-for-byte observable
  after delegating to the shared poster.
- **Skip-one-and-continue.** `LLMCaptioner.describe` raises `VisionError` on
  network/timeout/HTTP/empty/decode; `caption_pending_images` and `index-tree
  --vision` CATCH it, count it (`failed` / `vision_skipped`), and continue. One bad
  image never aborts a run.
- **Same persistence, no schema change.** Both apply paths persist via the
  UNCHANGED `image_caption_put` (archive-then-add, ANNOTATES `LinkSource.INFERENCE`,
  `kind=image_description`, no-drift). No new table/column/`index_mode` value; the
  single SQLite file is unchanged. `LLMCaptioner.describe` returns a TRANSIENT
  record; only `image_caption_put` writes a row.
- **Combined blob, raster only.** A description stays ONE blob (depicts + legible
  text); no `{ocr, caption}` split. SVG stays self-describing (`extract_svg_text`);
  the llm provider is raster-only.
- **Own config.** The vision tier reads `MINTMORY_VISION_*` (its own
  `model`/`base_url`/`api_key`/`vision_*` knobs), NOT `MINTMORY_LLM_*`. No
  `LLMSettings`/`MINTMORY_LLM_*` change.
- **No real network in tests.** `LLMCaptioner` is tested by monkeypatching
  `llm.post_chat_completion` (or `urllib.request.urlopen`); ZERO outbound calls.
- **Transports thin.** They build the captioner from settings, no-op on
  `agent`/raise-map on `ocr`, and otherwise call `caption_pending_images` +
  serialise `CaptionRunReport`. `limit` post-selection, `0`=no cap.

---

## 7. Tests (contract)

Group by ownership (see tasks.md). Minimum coverage (ALL with a stubbed
poster/urlopen — no network):

- **core config (`tests/test_config.py`):** `VisionSettings` new defaults
  (`base_url="http://localhost:11434/v1"`, `model="llava"`, `vision_timeout_s=120.0`,
  `vision_temperature=0.0`, `vision_max_tokens=512`, `vision_prompt=""`); bounds
  (`vision_max_tokens` ≥1 ≤8192; `vision_timeout_s` 1..600); env parse
  (`MINTMORY_VISION_MODEL`, `MINTMORY_VISION_VISION_MAX_TOKENS`,
  `MINTMORY_VISION_VISION_PROMPT`); `provider` still defaults `agent`.
- **core vision — factory:** `captioner_from_settings(VisionSettings(provider=llm))`
  returns an `LLMCaptioner` (isinstance); `agent` → `None`; `ocr` → raises
  `NotImplementedError` (message mentions agent).
- **core vision — `LLMCaptioner.describe` (stub the poster):** asserts the POSTed
  payload — `model`, `messages[0].role=="user"`, `content[0]=={"type":"text",
  "text":<prompt>}`, `content[1].type=="image_url"` with a `data:<mime>;base64,`
  URL, `max_tokens`, `temperature`, `stream=False`; Bearer header present iff
  `api_key`; URL ends `/chat/completions`. Response: `choices[0].message.content`
  is returned (combined text), `<think>…</think>` is stripped, surrounding
  whitespace trimmed; the returned `ImageDescription.record` is transient
  (`category=context`, `is_note=False`, `metadata.kind=image_description`,
  `source_image==path`). `vision_prompt` override replaces the default prompt.
  **VisionError** raised on: `urlopen` raising `URLError`/`TimeoutError`; non-2xx
  `HTTPError`; empty/whitespace content; content that is only `<think>…</think>`;
  unparseable JSON; unreadable `image.path` (OSError, no `data`). Pillow-absent:
  bytes embedded un-downscaled (monkeypatch the import to fail) — still produces a
  valid data URL.
- **core vision — `caption_pending_images` (stub describe):** two pending raster
  jobs → both described + persisted (default `image_jobs` then omits them =
  no-drift); a `VisionError` from one describe → that one counted `failed`, the
  other `described`, run completes; an oversized image (size > cap) → `skipped`
  (note `oversized`), not described; `include_all=True` re-captions already-described
  images (replaced_description_id set); `limit=1` caps; online-only budget — with a
  tiny `budget`, the second online-only image is skipped (note `budget`,
  `budget_hit=True`). Uses a fake in-memory `Captioner` (no network).
- **core/llm refactor:** `LLMClient.chat` still returns the assistant text and the
  existing `core/llm.py` tests pass unedited after delegating to
  `post_chat_completion`.
- **CLI:** `index-tree --vision` with `MINTMORY_VISION_PROVIDER=llm` (poster stubbed)
  on a tiny tree with one `.png` → `images-described=1`, manifest
  `index_mode='vision'`, the description ANNOTATES the file-record; a stubbed
  `VisionError` → `vision-skipped` and the walk completes; **agent default** still
  shows `images-queued` (UNCHANGED); re-run is incremental (no re-caption). `ocr`
  provider still exits non-zero. `mintmory vision-run` (`--limit`/`--budget`/`--all`):
  describes pending (poster stubbed); `provider=agent` prints the no-op + exit 0.
- **MCP (`tests/test_tools.py`):** `vision_run` with provider=agent → `{provider:
  'agent', described:0}`; with provider=llm (poster stubbed) → describes + the image
  drops from default `image_jobs`; `ocr` → `{error:'not_implemented'}`.
- **API (`tests/test_routes.py`):** `POST /images/caption-run` provider=agent → 200
  `CaptionRunReport(provider='agent')`; provider=llm (poster stubbed) → 200, images
  described, then absent from `GET /images/jobs`; `ocr` → 422 with the clear message.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`,
`mypy --strict` (line-length 100).
