# Design (proposed) — `add-recurrent-tree-indexing`

Stable across the scope/cadence/DB decisions in `gaps.md`; the scope-dependent
parts are marked. This is a *draft* contract — it is frozen only once the
decisions are answered.

## 1. Storage additions (resolves G3, G6)

New table in `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS index_manifest (
    path          TEXT PRIMARY KEY,   -- absolute file path (the source key)
    collection    TEXT NOT NULL,      -- source_root id, e.g. "onedrive:ExampleOrg"
    size          INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    content_hash  TEXT,               -- NULL until content is downloaded+hashed
    index_mode    TEXT NOT NULL,      -- "metadata" | "content"
    memory_ids    TEXT NOT NULL,      -- JSON array of memory ids produced for this path
    online_only   INTEGER NOT NULL,
    last_seen     REAL NOT NULL
);
```

New storage methods:
- `upsert_file_index(path, collection, *, size, mtime, online_only, mode, memory_ids, content_hash=None)`
  — insert or replace the manifest row.
- `replace_memories_for_path(path, new_records)` — archive/delete the prior
  `memory_ids` for a path and insert the new ones atomically (change handling).
- `manifest_get(path)` / `prune_missing(collection, seen_paths)` → archive rows
  whose path disappeared, returning the count.

## 2. Core: `mintmory.core.tree_index` (resolves G1, G2)

```python
@dataclass(frozen=True)
class FileEntry:
    path: Path
    rel: str            # path relative to its root
    size: int
    mtime: float
    online_only: bool   # st_blocks == 0 and st_size > 0

def walk_tree(root, *, include, exclude, follow_symlinks=False) -> Iterator[FileEntry]:
    """Stat-only walk (no file open ⇒ no OneDrive download). Applies include/exclude
    globs and a default artifact denylist."""

def render_file_record(entry, *, siblings, root_label, max_siblings=12) -> str:
    """Deterministic metadata+context text, e.g.:
      'File: Q3-plan.docx  (Word document, 84 KB, modified 2026-03-11)
       Location: Acme - Documents / 002_Team Drive / Marketing
       Alongside 11 files in this folder: brand.pdf, logo.svg, deck.pptx, ...
       Status: online-only (not downloaded).'
    """

# default artifact denylist (excluded unless explicitly included):
ARTIFACT_SUFFIXES = {".dll",".exe",".pdb",".jar",".zip",".rar",".crc",".config",
                     ".ttf",".aax",".class",".o",".bin"}
```

The file-record memory: `category=MemoryCategory.CONTEXT`, `source=DOCUMENT`,
metadata `{collection, path, rel, ext, size, mtime, online_only, folder,
siblings_sample, index_mode:"metadata"}`. Entity extraction still runs over the
rendered text (folder/file names become entities → folder-mates link via L2).

## 3. CLI: `mintmory index-tree` (resolves G7)

```
mintmory index-tree ROOT...
  --collection TEXT                 # logical id stamped on every row
  --include "*.pdf,*.docx,..."      # globs (default: all, minus denylist)
  --exclude "Personal/**,*.tmp"     # globs / folder filters
  --content / --no-content          # default --no-content (metadata only)
  --content-types "pdf,docx,xlsx,pptx,txt,html"
  --content-globs TEXT              # restrict content pass to a subtree
  --max-download-mb FLOAT           # budget for the content pass (default 200)
  --db PATH                         # target DB (e.g. ~/.mintmory/onedrive.db)
  --prune / --no-prune              # archive memories for vanished files
  --force                           # re-index everything (b); default = incremental (a: new/changed only)
  --limit N                         # stop after N files (smoke tests)
  --dream / --no-dream              # consolidate after
```

Flow per run: walk → for each entry, look up manifest → unchanged: skip;
new/changed: render metadata record (always, cheap) and, **iff** `--content` and
the type/glob/budget allow and the file is downloadable, also download + MM-11
`extract_markdown` + chunk; upsert manifest + replace memories for the path.
After the walk, `--prune` archives vanished paths. Emit a run report (G8).

Settings group `MINTMORY_INDEX_*` mirrors the flags (roots, includes, excludes,
content policy, budget, db).

## 4. Recurrence: launchd (resolves G4)

`~/Library/LaunchAgents/com.mintmory.index-tree.plist` — `StartCalendarInterval`
(daily, default 02:30) running `mintmory index-tree --once …`, `StandardOutPath`/
`StandardErrorPath` to `~/.mintmory/logs/index-tree.log`. Shipped as a template +
a `mintmory index-tree --install-agent` helper. **Install is user-gated** (writes
to the user's LaunchAgents and registers a recurring job).

## 5. Out of scope (this change)
Image OCR / vision captioning (G5) — images/diagrams get metadata+context only.
Tracked as a follow-up change `add-image-understanding`.

## 6. Test plan (once frozen)
Walk uses a synthetic tmp tree (no network); a fake "online-only" entry via a
monkeypatched `os.stat` (st_blocks=0); manifest skip/change/prune transitions;
`render_file_record` determinism + sibling capping; CLI metadata-only run stores
N records with correct metadata; content pass gated by budget/type; `--db`
isolation. Reuse MM-11 fake-markitdown injection for the content pass.
