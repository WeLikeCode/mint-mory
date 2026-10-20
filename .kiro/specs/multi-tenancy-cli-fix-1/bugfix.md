# Bugfix Requirements Document

## Bug Analysis

### Current Behavior (Defect)

1.1 Decided by human in Q-013: R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active image file-record found ...' to stderr and exits 1.. R6.10 requires exit 1 for a global image-caption-put on a tenant image. The code keeps the BadParameter path (exit 2) and the test was loosened to != 0. (Global image-caption-put exits 2, not 1; F-2192b892)

### Expected Behavior (Correct)

2.1 image-jobs/image-caption-put: an `acme` image file-record added with `add_memory(record=MemoryRecord(content="x.png", category="context", source="document", tenant_id="acme", metadata={"path": "/tmp/x.png", "rel": "x.png", "ext": ".png", "size": 10, "collection": "c"}))`: `--tenant acme image-jobs --json` lists its id and `image-jobs --json` does not; `--tenant acme image-caption-put <id> "a cat"` stores a description with `tenant_id == "acme"`; `image-caption-put <id> "a cat"` (global) exits 1 and its output contains today's `no active image file-record found`. (parent Req 6.10, C-5cf1ac32)
2.2 WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active image file-record found ...' to stderr and exits 1.

### Unchanged Behavior (Regression Prevention)

The system SHALL CONTINUE TO satisfy every other acceptance criterion of multi-tenancy-cli.
